"""모의면접 백엔드 — /api/v1/interview/*

역할 분담 (AI 모의면접 개발명세서 ★ 함수 명세):
  백엔드(여기) = 세션 꺼내기 → 면접 함수 부르기 → 돌려받은 값 저장, 중복 제출 확인, S3 업로드, 뒤에서 처리
  면접 함수(저장소 ai/interview/ → 배포 때 `interview` 패키지, 담당 안현지) = 면접 규칙, AI, Polly·Transcribe·Rekognition 호출, 점수, 리포트

저장 (team07-career-mentor, PK = USER#{userId}, ivId = sessionId):
  INTERVIEW#{ivId}                                   면접 함수가 준 session 그대로 + 백엔드 관리 값
  INTERVIEW#{ivId}#FRAME#{answerId}#{capturedAt}     analyze_face 결과 (이미지는 저장하지 않음)
  INTERVIEW#{ivId}#REPORT                            리포트

뒤에서 처리: SQS 권한이 없어 Lambda 비동기 자기 호출(InvocationType=Event)로 처리한다.
"""

import base64
import json
import os
import re
import time
import uuid
from email import policy
from email.parser import BytesParser

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from common import TeamError, error_response, get_user_id, json_response, new_request_id, now_iso, to_dynamo, to_plain

try:  # 실제 면접 함수 (저장소 ai/interview/, infra/package.sh가 `interview`로 묶음)
    import interview as impl

    IMPL_NAME = "interview"
except ImportError:  # 들어오기 전까지 대역
    import interview_stub as impl

    IMPL_NAME = "stub"

TABLE = os.environ.get("TABLE_CAREER_MENTOR", "team07-career-mentor")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
DOCS_BUCKET = os.environ.get("CAREER_DOCS_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
MAX_AUDIO = 6 * 1024 * 1024
MAX_IMAGE = 5 * 1024 * 1024
TRANSCRIBE_WAIT_SEC = 240
INTERVIEW_TYPES = {"PERSONALITY", "JOB", "MIXED"}
FRAME_TYPES = {"CALIBRATION", "ANSWER"}

_ddb = _s3 = _lambda = None


def table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    return _ddb


def s3():
    global _s3
    if _s3 is None:
        from botocore.config import Config

        _s3 = boto3.client("s3", region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com",
                           config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    return _s3


def pk(user_id):
    return f"USER#{user_id}"


def sk(iv_id, *rest):
    return "#".join(["INTERVIEW", iv_id, *rest])


def audio_key(user_id, iv_id, name):
    # uploads/ 아래라 7일 자동 삭제(안전장치) 대상. 녹음은 변환 끝나면 바로 지운다.
    return f"uploads/interview/{iv_id}/{name}"


# ---------------------------------------------------------------- 요청 파싱


def body_bytes(event):
    raw = event.get("body") or ""
    return base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")


def parse_json(event):
    try:
        data = json.loads(body_bytes(event) or b"{}")
    except json.JSONDecodeError:
        raise TeamError(400, "INVALID_INPUT", "요청 형식이 올바르지 않아요.")
    if not isinstance(data, dict):
        raise TeamError(400, "INVALID_INPUT", "요청 형식이 올바르지 않아요.")
    return data


def parse_multipart(event):
    ctype = (event.get("headers") or {}).get("content-type", "")
    if "multipart/form-data" not in ctype:
        raise TeamError(400, "INVALID_INPUT", "multipart/form-data로 보내 주세요.")
    msg = BytesParser(policy=policy.default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body_bytes(event))
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        if part.get_filename() is not None:
            files[name] = (payload, part.get_content_type())
        else:
            fields[name] = payload.decode("utf-8").strip()
    return fields, files


def as_bool(value):
    return str(value).lower() in ("true", "1", "yes")


# ---------------------------------------------------------------- 저장소


def get_interview(user_id, iv_id):
    item = table().get_item(Key={"PK": pk(user_id), "SK": sk(iv_id)}).get("Item")
    if not item:
        raise TeamError(404, "SESSION_NOT_FOUND", "면접 세션을 찾을 수 없어요.")
    return to_plain(item)


def update_interview(user_id, iv_id, values, condition=None, cond_values=None):
    names, sets, vals = {}, [], {}
    for i, (k, v) in enumerate({**values, "updatedAt": now_iso()}.items()):
        names[f"#k{i}"], vals[f":v{i}"] = k, to_dynamo(v)
        sets.append(f"#k{i} = :v{i}")
    # 세션이 있을 때만 갱신한다. update_item은 아이템이 없으면 새로 만들어 버리므로,
    # 지워진 세션(회원 탈퇴 등)을 뒤에서 처리하던 작업이 반쪽짜리로 되살리지 않게 막는다.
    cond = "attribute_exists(SK)" + (f" AND ({condition})" if condition else "")
    kwargs = dict(Key={"PK": pk(user_id), "SK": sk(iv_id)}, UpdateExpression="SET " + ", ".join(sets),
                  ExpressionAttributeNames=names, ExpressionAttributeValues=vals, ConditionExpression=cond)
    if cond_values:
        kwargs["ExpressionAttributeValues"].update(to_dynamo(cond_values))
    table().update_item(**kwargs)


def query_frames(user_id, iv_id):
    items, start = [], None
    while True:
        kw = dict(KeyConditionExpression=Key("PK").eq(pk(user_id)) & Key("SK").begins_with(sk(iv_id, "FRAME") + "#"))
        if start:
            kw["ExclusiveStartKey"] = start
        page = table().query(**kw)
        items += page["Items"]
        start = page.get("LastEvaluatedKey")
        if not start:
            return [to_plain(i) for i in items]


def load_resume_text(user_id, document_id):
    """요청: resume_text = 문서의 extractedTextKey(S3)에서 읽은 텍스트"""
    if "#" in document_id:
        raise TeamError(400, "INVALID_INPUT", "documentId 형식이 올바르지 않아요.")
    doc = table().get_item(Key={"PK": pk(user_id), "SK": f"DOC_LATEST#{document_id}"}).get("Item")  # 최신 버전 사본
    if not doc or not doc.get("extractedTextKey"):
        raise TeamError(404, "DOCUMENT_NOT_FOUND", "자소서 문서를 찾을 수 없거나 아직 글자 추출이 끝나지 않았어요.")
    obj = s3().get_object(Bucket=DOCS_BUCKET, Key=doc["extractedTextKey"])
    return obj["Body"].read().decode("utf-8")


def load_latest_profile(user_id):
    """요청: profile = PROFILE#LATEST가 가리키는 최신 버전의 projects, skills, needsConfirmation"""
    latest = table().get_item(Key={"PK": pk(user_id), "SK": "PROFILE#LATEST"}).get("Item")
    if not latest:
        return None
    version = int(latest["latestVersion"])
    item = table().get_item(Key={"PK": pk(user_id), "SK": f"PROFILE#{latest['latestProfileId']}#V#{version:04d}"}).get("Item")
    if not item:
        return None
    item = to_plain(item)
    return {k: item.get(k, []) for k in ("projects", "skills", "needsConfirmation")}


# ---------------------------------------------------------------- 응답 조립


def public_question(q):
    if not q:
        return None
    out = {k: q.get(k) for k in ("questionId", "answerId", "text", "isFollowUp")}
    out["audioUrl"] = None
    if q.get("audioKey") and UPLOAD_BUCKET:
        out["audioUrl"] = s3().generate_presigned_url("get_object", Params={"Bucket": UPLOAD_BUCKET, "Key": q["audioKey"]}, ExpiresIn=600)
    return out


def progress(item):
    session = item.get("session") or {}
    nq = item.get("nextQuestion") or {}
    total = len(session.get("questions") or []) or 3
    return {"baseQuestionNo": min((session.get("currentIndex") or 0) + 1, total), "totalBaseQuestions": total,
            "isFollowUp": bool(nq.get("isFollowUp"))}


def status_body(user_id, item):
    body = {"sessionId": item["sessionId"], "status": item["status"], "stage": item["stage"], "progress": progress(item),
            "nextQuestion": public_question(item.get("nextQuestion")) if item["stage"] == "NEXT_QUESTION_READY" else None,
            "lastAnswer": item.get("lastAnswer"), "report": None}
    if item["status"] == "COMPLETED":
        rep = table().get_item(Key={"PK": pk(user_id), "SK": sk(item["sessionId"], "REPORT")}).get("Item")
        body["report"] = to_plain(rep)["report"] if rep else None
    if item["status"] == "FAILED":
        body["error"] = item.get("error")
    return body


# ---------------------------------------------------------------- 뒤에서 처리 (비동기)


def enqueue(task):
    """SQS 대신 Lambda 비동기 자기 호출. 로컬 테스트에서는 바로 실행."""
    fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not fn or os.environ.get("RUN_TASKS_INLINE") == "1":
        return run_task(task)
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda", region_name=REGION)
    _lambda.invoke(FunctionName=fn, InvocationType="Event", Payload=json.dumps(task).encode())


def save_next_question(user_id, iv_id, result, extra=None):
    """질문 음성 만들기 → S3 저장 → 상태 NEXT_QUESTION_READY"""
    nq = dict(result["nextQuestion"])
    mp3 = impl.synthesize_question(nq["text"])
    if mp3 and UPLOAD_BUCKET:
        nq["audioKey"] = audio_key(user_id, iv_id, f"questions/{nq['questionId']}.mp3")
        s3().put_object(Bucket=UPLOAD_BUCKET, Key=nq["audioKey"], Body=mp3, ContentType="audio/mpeg")
    update_interview(user_id, iv_id, {"session": result["session"], "nextQuestion": nq, "expectedAnswerId": nq["answerId"],
                                      "status": "PROCESSING", "stage": "NEXT_QUESTION_READY", **(extra or {})})


def task_start(t):
    user_id, iv_id, inp = t["userId"], t["sessionId"], t["input"]
    result = impl.start_interview(iv_id, inp["job"], inp["resumeText"], inp["interviewType"], inp["cameraConsent"], inp.get("profile"))
    save_next_question(user_id, iv_id, result)


def task_answer(t):
    user_id, iv_id, answer_id = t["userId"], t["sessionId"], t["answerId"]
    item = get_interview(user_id, iv_id)
    job = item["transcribeJobs"][answer_id]

    deadline = time.time() + TRANSCRIBE_WAIT_SEC
    while True:
        tr = impl.get_transcription_result(job["jobName"])
        if tr.get("status") != "IN_PROGRESS" or time.time() > deadline:
            break
        time.sleep(2)
    if tr.get("status") == "IN_PROGRESS":
        tr = {"status": "FAILED"}  # 너무 오래 걸리면 변환 실패로 기록하고 면접은 계속

    # 요청: 녹음은 Transcribe 변환이 끝나면 바로 삭제 (7일 자동 삭제는 안전장치)
    if UPLOAD_BUCKET:
        s3().delete_object(Bucket=UPLOAD_BUCKET, Key=job["audioKey"])

    update_interview(user_id, iv_id, {"stage": "JUDGING"})
    answer_result = {"answerId": answer_id, "timeLimitReached": job["timeLimitReached"], "transcription": tr}
    result = impl.process_answer(item["session"], answer_result)

    if result["action"] == "REPORT":
        update_interview(user_id, iv_id, {"session": result["session"], "lastAnswer": result["lastAnswer"],
                                          "nextQuestion": None, "stage": "REPORT_GENERATING"})
        make_report(user_id, iv_id)
    else:
        save_next_question(user_id, iv_id, result, {"lastAnswer": result["lastAnswer"]})


def make_report(user_id, iv_id):
    item = get_interview(user_id, iv_id)
    session = item["session"]
    frames = query_frames(user_id, iv_id)
    if session.get("baseline") is None:
        calib = [f for f in frames if f["type"] == "CALIBRATION" and f.get("valid")]
        session["baseline"] = impl.compute_baseline(calib)  # 부족하면 함수가 기본값을 돌려줌
    answer_frames = [{k: f.get(k) for k in ("type", "questionId", "answerId", "capturedAt", "accepted", "valid", "gaze", "head")}
                     for f in frames if f["type"] == "ANSWER"]
    report = impl.generate_report(session, answer_frames)
    report.setdefault("interviewDate", now_iso()[:10])
    table().put_item(Item=to_dynamo({"PK": pk(user_id), "SK": sk(iv_id, "REPORT"), "entityType": "InterviewReport",
                                     "sessionId": iv_id, "report": report, "createdAt": now_iso()}))
    # 리포트는 저장된 값을 그대로 돌려준다 (generate_report를 다시 부르지 않음)
    update_interview(user_id, iv_id, {"session": session, "status": "COMPLETED", "stage": "REPORT_READY"})


TASKS = {"interview.start": task_start, "interview.answer": task_answer}


def run_task(task):
    user_id, iv_id = task["userId"], task["sessionId"]
    try:
        TASKS[task["task"]](task)
    except Exception as e:  # noqa: BLE001 — 실패는 세션 상태로 남겨 화면이 알 수 있게
        code = getattr(e, "code", None) or "INTERNAL_ERROR"
        retryable = getattr(e, "retryable", True)
        print(f"[ERROR] task={task['task']} session={iv_id} code={code} err={type(e).__name__}")  # 원문은 로그에 남기지 않음
        try:
            update_interview(user_id, iv_id, {"status": "FAILED", "error": {
                "code": code, "message": "면접을 처리하지 못했어요. 다시 시도해 주세요.", "requestId": task.get("requestId"), "retryable": retryable}})
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- API 핸들러


def h_start(event, user_id, params, request_id):
    data = parse_json(event)
    job = (data.get("job") or "").strip()
    interview_type = data.get("interviewType")
    if not 1 <= len(job) <= 50:
        raise TeamError(400, "INVALID_INPUT", "직무는 1~50자로 입력해 주세요.")
    if interview_type not in INTERVIEW_TYPES:
        raise TeamError(400, "INVALID_INPUT", "면접 유형을 골라 주세요.")
    if not isinstance(data.get("cameraConsent"), bool):
        raise TeamError(400, "INVALID_INPUT", "카메라 동의 여부가 필요해요.")

    resume_text = data.get("resumeText")
    if not resume_text and data.get("documentId"):
        resume_text = load_resume_text(user_id, data["documentId"])
    if not resume_text or not 50 <= len(resume_text) <= 5000:
        raise TeamError(400, "INVALID_INPUT", "자소서는 50~5,000자로 입력해 주세요.")
    profile = data.get("profile") or load_latest_profile(user_id)

    iv_id = str(uuid.uuid4())  # 백엔드가 만들어 함수에 넘김 (202 응답에 바로 쓰기 위해)
    item = {"PK": pk(user_id), "SK": sk(iv_id), "entityType": "Interview", "schemaVersion": "1.0", "ownerUserId": user_id,
            "sessionId": iv_id, "jobRole": job, "interviewType": interview_type, "cameraConsent": data["cameraConsent"],
            "status": "PENDING", "stage": "QUESTION_GENERATING", "session": None, "nextQuestion": None,
            "expectedAnswerId": None, "submittedAnswerIds": [], "transcribeJobs": {}, "lastAnswer": None,
            "createdAt": now_iso(), "updatedAt": now_iso()}
    if data.get("workspaceId"):  # 선택: 공고별 워크스페이스에서 면접 기록도 보이게
        ws = data["workspaceId"]
        if "#" in ws or len(ws) > 200:
            raise TeamError(400, "INVALID_INPUT", "workspaceId 형식이 올바르지 않아요.")
        # GSI 키에도 userId를 넣는다 (DB 스키마 v1.1 §2.1). 읽을 때도 ownerUserId 재확인
        item.update(workspaceId=ws, GSI1PK=f"USER#{user_id}#WS#{ws}", GSI1SK=f"INTERVIEW#{item['createdAt']}#{iv_id}")
    table().put_item(Item=to_dynamo(item))
    enqueue({"task": "interview.start", "userId": user_id, "sessionId": iv_id, "requestId": request_id,
             "input": {"job": job, "resumeText": resume_text, "interviewType": interview_type,
                       "cameraConsent": data["cameraConsent"], "profile": profile}})
    return 202, {"sessionId": iv_id, "status": "PENDING", "stage": "QUESTION_GENERATING"}


def h_answer(event, user_id, params, request_id):
    fields, files = parse_multipart(event)
    iv_id, answer_id = fields.get("sessionId"), fields.get("answerId")
    if not iv_id or not answer_id or "audio" not in files:
        raise TeamError(400, "INVALID_INPUT", "sessionId, answerId, audio가 필요해요.")
    audio, audio_type = files["audio"]
    if len(audio) > MAX_AUDIO:
        raise TeamError(413, "FILE_TOO_LARGE", "녹음 파일이 너무 커요 (6MB 이하).")
    get_interview(user_id, iv_id)  # 없으면 404

    # 중복 제출 방지: 지금 받을 answerId이고 아직 제출되지 않았을 때만 (조건부 쓰기)
    try:
        update_interview(user_id, iv_id, {"stage": "TRANSCRIBING", "status": "PROCESSING", "nextQuestion": None},
                         condition="expectedAnswerId = :aid AND NOT contains(submittedAnswerIds, :aid)",
                         cond_values={":aid": answer_id})
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        item = get_interview(user_id, iv_id)
        if answer_id in (item.get("submittedAnswerIds") or []):
            raise TeamError(409, "ANSWER_ALREADY_SUBMITTED", "이미 제출된 답변이에요.")
        raise TeamError(409, "INVALID_STATE", "지금은 이 답변을 받을 수 없어요.")

    media_format = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/wav": "wav",
                    "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/flac": "flac"}.get(audio_type.split(";")[0], "webm")
    key = audio_key(user_id, iv_id, f"answers/{answer_id}.{media_format}")
    if UPLOAD_BUCKET:
        s3().put_object(Bucket=UPLOAD_BUCKET, Key=key, Body=audio, ContentType=audio_type)
    job_name = re.sub(r"[^0-9a-zA-Z._-]", "-", f"team07-{iv_id}-{answer_id}")[:200]
    job_name = impl.start_transcription(f"s3://{UPLOAD_BUCKET}/{key}", job_name, media_format)

    table().update_item(
        Key={"PK": pk(user_id), "SK": sk(iv_id)},
        UpdateExpression="SET submittedAnswerIds = list_append(submittedAnswerIds, :one), transcribeJobs.#aid = :job",
        ExpressionAttributeNames={"#aid": answer_id},
        ExpressionAttributeValues=to_dynamo({":one": [answer_id], ":job": {
            "jobName": job_name, "audioKey": key, "timeLimitReached": as_bool(fields.get("timeLimitReached"))}}),
    )
    enqueue({"task": "interview.answer", "userId": user_id, "sessionId": iv_id, "answerId": answer_id, "requestId": request_id})
    return 202, {"sessionId": iv_id, "answerId": answer_id, "status": "PROCESSING", "stage": "TRANSCRIBING"}


def h_status(event, user_id, params, request_id):
    return 200, status_body(user_id, get_interview(user_id, params["sessionId"]))


def h_frame(event, user_id, params, request_id):
    fields, files = parse_multipart(event)
    iv_id, ftype, captured_at = fields.get("sessionId"), fields.get("type"), fields.get("capturedAt")
    if not iv_id or ftype not in FRAME_TYPES or not captured_at or "image" not in files:
        raise TeamError(400, "INVALID_INPUT", "sessionId, type, capturedAt, image가 필요해요.")
    image, _ = files["image"]
    if len(image) > MAX_IMAGE:
        raise TeamError(413, "FILE_TOO_LARGE", "이미지가 너무 커요 (5MB 이하).")
    answer_id, question_id = fields.get("answerId"), fields.get("questionId")
    if ftype == "ANSWER" and not answer_id:
        raise TeamError(400, "INVALID_INPUT", "답변 중 캡처에는 answerId가 필요해요.")

    item = get_interview(user_id, iv_id)
    # 답변 제출 이후 도착한 이미지는 accepted=false → 리포트에서 제외
    accepted = ftype == "CALIBRATION" or (answer_id == item.get("expectedAnswerId")
                                          and answer_id not in (item.get("submittedAnswerIds") or []))
    face = impl.analyze_face(image)  # 이미지는 여기서만 쓰고 저장하지 않음
    frame = {"PK": pk(user_id), "SK": sk(iv_id, "FRAME", answer_id or "CALIBRATION", captured_at), "entityType": "InterviewFrame",
             "type": ftype, "questionId": question_id, "answerId": answer_id, "capturedAt": captured_at, "accepted": accepted,
             "valid": bool(face.get("valid")), "reason": face.get("reason"), "gaze": face.get("gaze"), "head": face.get("head")}
    table().put_item(Item=to_dynamo(frame))
    return 200, {"accepted": accepted, "valid": frame["valid"]}


ROUTES = [
    ("POST", r"/api/v1/interview/start", h_start),
    ("POST", r"/api/v1/interview/answer", h_answer),
    ("POST", r"/api/v1/interview/frame", h_frame),
    ("GET", r"/api/v1/interview/(?P<sessionId>[0-9a-f-]{36})/status", h_status),
]


def handle(event, method, path):
    request_id = new_request_id()
    try:
        for m, pattern, fn in ROUTES:
            match = re.fullmatch(pattern, path)
            if match and m == method:
                user_id = get_user_id(event)
                status, body = fn(event, user_id, match.groupdict(), request_id)
                return json_response(status, body, request_id)
        raise TeamError(404, "NOT_FOUND", "없는 주소예요.")
    except TeamError as e:
        return error_response(e, request_id)
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        if code in ("INVALID_INPUT", "AI_OUTPUT_INVALID", "AWS_SERVICE_ERROR"):  # 면접 함수의 InterviewError
            status = {"INVALID_INPUT": 400, "AI_OUTPUT_INVALID": 500, "AWS_SERVICE_ERROR": 503}[code]
            return error_response(TeamError(status, code, getattr(e, "message", "처리하지 못했어요."), getattr(e, "retryable", True)), request_id)
        print(f"[ERROR] {method} {path} {request_id}: {type(e).__name__}")
        return error_response(TeamError(500, "INTERNAL_ERROR", "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", True), request_id)
