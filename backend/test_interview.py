"""모의면접 백엔드 흐름 테스트 (moto로 DynamoDB·S3 흉내, 면접 함수는 대역).

실행: cd backend && uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb,s3]" python test_interview.py
"""

import json
import os
import uuid

os.environ.update(AWS_DEFAULT_REGION="ap-northeast-2", AWS_REGION="ap-northeast-2", AWS_ACCESS_KEY_ID="test",
                  AWS_SECRET_ACCESS_KEY="test", UPLOAD_BUCKET="test-uploads", CAREER_DOCS_BUCKET="test-docs",
                  TABLE_CAREER_MENTOR="test-cm", RUN_TASKS_INLINE="1", ALLOW_DEV_USER_HEADER="1")
os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)

from moto import mock_aws  # noqa: E402

RESUME = "저는 부산에서 캡스톤 프로젝트로 예약 API 서버를 맡아 개발했고, 장애 대응과 성능 개선을 경험했습니다. " * 2
results = []


def check(name, cond):
    cond = bool(cond)
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def ev(method, path, user="u-1", body=None, multipart=None):
    headers = {"x-user-id": user} if user else {}
    e = {"rawPath": path, "requestContext": {"http": {"method": method, "path": path}}, "headers": headers}
    if body is not None:
        e["body"] = json.dumps(body, ensure_ascii=False)
    if multipart is not None:
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in multipart.items():
            if isinstance(v, tuple):
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="f"\r\nContent-Type: {v[1]}\r\n\r\n'.encode() + v[0] + b"\r\n")
            else:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        import base64

        e["body"] = base64.b64encode(b"".join(parts) + f"--{boundary}--\r\n".encode()).decode()
        e["isBase64Encoded"] = True
        headers["content-type"] = f"multipart/form-data; boundary={boundary}"
    return e


@mock_aws
def main():
    import boto3

    boto3.client("s3").create_bucket(Bucket="test-uploads", CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"})
    boto3.client("dynamodb").create_table(
        TableName="test-cm", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}])
    import interview_api as api
    from app import lambda_handler

    def call(*a, **kw):
        r = lambda_handler(ev(*a, **kw), None)
        return r["statusCode"], json.loads(r["body"])

    # 입력 검사 · 인증
    s, b = call("POST", "/api/v1/interview/start", user=None, body={})
    check("userId 없으면 401 + 팀 공통 오류 형식", s == 401 and set(b["error"]) == {"code", "message", "requestId", "retryable"})
    s, _ = call("POST", "/api/v1/interview/start", body={"job": "백엔드", "interviewType": "MIXED", "cameraConsent": True, "resumeText": "짧음"})
    check("자소서 50자 미만이면 400", s == 400)

    # 시작 (workspaceId 포함 → GSI1)
    s, b = call("POST", "/api/v1/interview/start", body={"job": "백엔드 개발", "interviewType": "MIXED", "cameraConsent": True,
                                                       "resumeText": RESUME, "workspaceId": "ws-1"})
    sid = b["sessionId"]
    check("start → 202, ivId = sessionId(UUID)", s == 202 and len(sid) == 36)
    item = api.get_interview("u-1", sid)
    check("INTERVIEW#{ivId}에 함수가 준 session 그대로 저장", item["session"]["sessionId"] == sid and item["jobRole"] == item["session"]["job"])
    check("GSI1PK = USER#{userId}#WS#{workspaceId}", item.get("GSI1PK") == "USER#u-1#WS#ws-1" and item["GSI1SK"].endswith(sid))

    # documentId → DOC_LATEST#의 extractedTextKey, profile → PROFILE#LATEST 최신 버전
    boto3.client("s3").create_bucket(Bucket="test-docs", CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"})
    boto3.client("s3").put_object(Bucket="test-docs", Key="users/h/documents/doc-1/v2/extracted.txt", Body=RESUME.encode())
    t = boto3.resource("dynamodb").Table("test-cm")
    t.put_item(Item={"PK": "USER#u-1", "SK": "DOC_LATEST#doc-1", "latestVersion": 2, "extractedTextKey": "users/h/documents/doc-1/v2/extracted.txt"})
    t.put_item(Item={"PK": "USER#u-1", "SK": "PROFILE#LATEST", "latestProfileId": "p-1", "latestVersion": 2})
    career_profile = {
        "PK": "USER#u-1", "SK": "PROFILE#p-1#V#0002", "ownerUserId": "u-1",
        "profileId": "p-1", "profileVersion": 2, "createdBy": "USER_CONFIRMATION",
        "createdAt": "2026-11-20T10:00:00+09:00",
        "projects": [{"itemId": "proj-1", "name": "예약 API", "factStatus": "VERIFIED"}],
        "skills": [
            {"skillId": "sk-1", "name": "Python", "factStatus": "VERIFIED", "evidenceLevel": "EVIDENCED"},
            {"skillId": "sk-2", "name": "트래픽", "factStatus": "NEEDS_CONFIRMATION", "evidenceLevel": "PARTIAL"},
        ],
        "evidence": [{"evidenceId": "ev-1", "sourceDocumentId": "doc-1", "page": 1, "startChar": 0,
                      "endChar": 6, "quotedText": "면접에 넘기지 않는 원문"}],
    }
    t.put_item(Item=career_profile)
    s2, b2 = call("POST", "/api/v1/interview/start", body={"job": "백엔드", "interviewType": "JOB", "cameraConsent": False, "documentId": "doc-1"})
    sess2 = api.get_interview("u-1", b2["sessionId"])["session"]
    check("documentId → DOC_LATEST#의 extractedTextKey에서 자소서 읽음", s2 == 202 and sess2["resumeText"] == RESUME)
    # A가 실제로 쓰는 모양: DOC_LATEST#에는 키가 없고 문서 버전 DOC#{id}#V#{n}의 textKey에 있다 (db-schema v1.4)
    boto3.client("s3").put_object(Bucket="test-docs", Key="users/h/documents/doc-a/v1/extracted.txt", Body=RESUME.encode())
    t.put_item(Item={"PK": "USER#u-1", "SK": "DOC_LATEST#doc-a", "documentId": "doc-a", "latestVersion": 1,
                     "documentType": "COVER_LETTER", "extractionStatus": "COMPLETED"})
    t.put_item(Item={"PK": "USER#u-1", "SK": "DOC#doc-a#V#0001", "documentId": "doc-a", "version": 1,
                     "textKey": "users/h/documents/doc-a/v1/extracted.txt"})
    s3_, b3 = call("POST", "/api/v1/interview/start", body={"job": "데이터 분석", "interviewType": "JOB", "cameraConsent": False, "documentId": "doc-a"})
    check("documentId → A 문서 버전의 textKey에서 자소서 읽음", s3_ == 202 and api.get_interview("u-1", b3["sessionId"])["session"]["resumeText"] == RESUME)
    t.put_item(Item={"PK": "USER#u-1", "SK": "DOC_LATEST#doc-b", "documentId": "doc-b", "latestVersion": 1})
    check("문서 버전에 textKey가 없으면 404", call("POST", "/api/v1/interview/start", body={"job": "데이터 분석", "interviewType": "JOB", "cameraConsent": False, "documentId": "doc-b"})[0] == 404)
    check("A 역량 프로필을 면접 계약으로 변환하며 원문은 제외", sess2["profile"] == {
        "projects": ["예약 API"], "skills": ["Python"], "needsConfirmation": ["트래픽"],
        "profileId": "p-1", "profileVersion": 2,
    })
    t.put_item(Item={**career_profile, "skills": ["이전 형식의 원본"]})
    check("변환할 수 없는 역량 프로필은 전달하지 않음", api.load_latest_profile("u-1") is None)

    # 채용공고 (#167, C #158): jobPosting 글 또는 B 공고 ID. 공고는 7번째 인자로 넘기고 INTERVIEW#에는 두지 않는다
    real_start, seen = api.impl.start_interview, {}

    def spy_start(*args):
        seen["args"] = args
        return real_start(*args)

    api.impl.start_interview = spy_start
    try:
        posting = {"title": "데이터 분석 신입", "company": "가상데이터", "text": "SQL로 매출 데이터를 분석하고 대시보드를 만듭니다. Python 우대."}
        base = {"job": "데이터 분석", "interviewType": "JOB", "cameraConsent": False, "resumeText": RESUME}
        s, b = call("POST", "/api/v1/interview/start", body={**base, "jobPosting": posting})
        stored = api.get_interview("u-1", b["sessionId"])
        check("jobPosting → 202, jobPostingUsed=true, 면접 함수 7번째 인자로 전달",
              s == 202 and b["jobPostingUsed"] is True and len(seen["args"]) == 7 and seen["args"][6] == posting)
        check("채용공고 원문은 INTERVIEW#에 저장하지 않음", posting["text"] not in json.dumps(stored, ensure_ascii=False))
        s, b = call("POST", "/api/v1/interview/start", body=base)
        check("공고 없이 시작 → jobPostingUsed=false, 7번째 인자 None", s == 202 and b["jobPostingUsed"] is False and seen["args"][6] is None)
        s, b = call("POST", "/api/v1/interview/start", body={**base, "jobPosting": posting, "jobPostingId": "wk24-1"})
        check("jobPosting과 jobPostingId를 함께 보내면 400", s == 400 and b["error"]["code"] == "INVALID_INPUT")
        s, b = call("POST", "/api/v1/interview/start", body={**base, "jobPostingId": "wk24#1"})
        check("jobPostingId에 #이 있으면 400", s == 400 and b["error"]["code"] == "INVALID_INPUT")

        real_load = api.load_b_posting
        b_posting = {"jobPostingId": "wk24-1", "title": "데이터 분석 신입", "organization": "(주)가상데이터",
                     "jobDescription": "공공데이터로 월별 방문객 추이를 분석하고 결측치 기준을 정해 보고서를 씁니다.",
                     "requirements": [{"name": "SQL", "kind": "REQUIRED_SKILL", "sourceQuote": "SQL 활용 가능자"}]}
        api.load_b_posting = lambda pid: b_posting if pid == "wk24-1" else (_ for _ in ()).throw(
            api.TeamError(404, "POSTING_NOT_FOUND", "공고를 찾을 수 없어요."))
        try:
            s, b = call("POST", "/api/v1/interview/start", body={**base, "jobPostingId": "wk24-1"})
            check("jobPostingId → B 공고를 변환해 전달", s == 202 and b["jobPostingUsed"] is True
                  and seen["args"][6] == api.impl.job_posting_from_posting(b_posting))
            s, b = call("POST", "/api/v1/interview/start", body={**base, "jobPostingId": "wk24-none"})
            check("없는 공고 ID → 404 POSTING_NOT_FOUND, 세션을 만들지 않음", s == 404 and b["error"]["code"] == "POSTING_NOT_FOUND")
            b_posting["jobDescription"] = "짧음"
            s, b = call("POST", "/api/v1/interview/start", body={**base, "jobPostingId": "wk24-1"})
            check("B 공고 본문이 짧으면 공고 없이 시작 (jobPostingUsed=false)", s == 202 and b["jobPostingUsed"] is False)
        finally:
            api.load_b_posting = real_load
    finally:
        api.impl.start_interview = real_start

    # 채용공고 PDF → 글자만 돌려줌 (저장 안 함)
    def tiny_pdf(text):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                b"<< /Length %d >>stream\n" % len(stream) + stream + b"\nendstream",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        out, offsets = b"%PDF-1.4\n", []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
        return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)

    try:
        import mentoring.extract  # noqa: F401  (CI처럼 ai/mentoring/src가 PYTHONPATH에 있을 때만)
        has_reader = True
    except ImportError:
        has_reader = False
    if has_reader:
        body = "Data analyst wanted. SQL and Python required. Build dashboards for monthly sales."
        s, b = call("POST", "/api/v1/interview/job-posting/text", multipart={"file": (tiny_pdf(body), "application/pdf")})
        check("공고 PDF → 200, 읽은 글을 돌려줌", s == 200 and "SQL and Python" in b["text"] and b["truncated"] is False and b["pageCount"] == 1)
        s, b = call("POST", "/api/v1/interview/job-posting/text", multipart={"file": (tiny_pdf("Too short"), "application/pdf")})
        check("공고 PDF 글이 30자 미만이면 422", s == 422 and b["error"]["code"] == "DOCUMENT_UNREADABLE")
    s, b = call("POST", "/api/v1/interview/job-posting/text", multipart={"file": (b"hello", "text/plain")})
    check("PDF가 아니면 400", s == 400 and b["error"]["code"] == "INVALID_INPUT")
    s, b = call("POST", "/api/v1/interview/job-posting/text", multipart={"file": (b"%PDF" + b"0" * api.MAX_POSTING_PDF, "application/pdf")})
    check("4MB를 넘는 공고 PDF는 413", s == 413 and b["error"]["code"] == "FILE_TOO_LARGE")

    s, b = call("GET", f"/api/v1/interview/{sid}/status")
    check("status → NEXT_QUESTION_READY + answerId", b["stage"] == "NEXT_QUESTION_READY" and b["nextQuestion"]["answerId"] == "a-q1-1")
    s, _ = call("GET", f"/api/v1/interview/{sid}/status", user="u-2")
    check("다른 사용자는 세션을 못 봄 (404)", s == 404)

    img = (b"\xff\xd8fakejpeg", "image/jpeg")
    for t in ("2026-11-20T10:00:00.0", "2026-11-20T10:00:00.5", "2026-11-20T10:00:01.0"):
        call("POST", "/api/v1/interview/frame", multipart={"sessionId": sid, "type": "CALIBRATION", "capturedAt": t, "image": img})

    def answer(aid, qid):
        call("POST", "/api/v1/interview/frame", multipart={"sessionId": sid, "type": "ANSWER", "questionId": qid, "answerId": aid,
                                                         "capturedAt": f"2026-11-20T10:01:{aid[-1]}0", "image": img})
        return call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid, "answerId": aid, "timeLimitReached": "false",
                                                                  "audio": (b"OggS-fake", "audio/webm")})

    s, b = answer("a-q1-1", "q1")
    check("answer → 202 TRANSCRIBING", s == 202 and b["stage"] == "TRANSCRIBING")
    s, b = call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid, "answerId": "a-q1-1", "timeLimitReached": "false",
                                                              "audio": (b"x", "audio/webm")})
    check("같은 answerId 두 번 → 409 ANSWER_ALREADY_SUBMITTED", s == 409 and b["error"]["code"] == "ANSWER_ALREADY_SUBMITTED")
    s, b = call("POST", "/api/v1/interview/frame", multipart={"sessionId": sid, "type": "ANSWER", "questionId": "q1", "answerId": "a-q1-1",
                                                            "capturedAt": "2026-11-20T10:09:00", "image": img})
    check("제출 뒤 도착한 캡처 → accepted=false", s == 200 and b["accepted"] is False)
    keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket="test-uploads").get("Contents", [])]
    check("녹음은 변환 끝나면 바로 삭제", not any("/answers/" in k for k in keys))
    check("Transcribe 결과 파일(답변 원문)도 함께 삭제", not any("/transcripts/" in k for k in keys))
    job = api.get_interview("u-1", sid)["transcribeJobs"]["a-q1-1"]
    check("변환 결과 위치를 백엔드가 정함: uploads/interview/{ivId}/transcripts/{answerId}.json",
          job["transcriptKey"] == f"uploads/interview/{sid}/transcripts/a-q1-1.json")

    s, b = call("GET", f"/api/v1/interview/{sid}/status")
    check("꼬리질문으로 진행", b["nextQuestion"]["isFollowUp"] is True)
    answer(b["nextQuestion"]["answerId"], "q1-f")
    s, b = call("GET", f"/api/v1/interview/{sid}/status")
    answer(b["nextQuestion"]["answerId"], "q2")
    s, b = call("GET", f"/api/v1/interview/{sid}/status")
    check("질문 3/3 진행 표시", b["progress"]["baseQuestionNo"] == 3)
    answer(b["nextQuestion"]["answerId"], "q3")

    s, b = call("GET", f"/api/v1/interview/{sid}/status")
    check("마지막 답변 후 COMPLETED + 리포트", b["status"] == "COMPLETED" and b["stage"] == "REPORT_READY" and b["report"])
    rep = boto3.resource("dynamodb").Table("test-cm").get_item(Key={"PK": "USER#u-1", "SK": f"INTERVIEW#{sid}#REPORT"}).get("Item")
    check("리포트는 INTERVIEW#{ivId}#REPORT로 따로 저장", rep is not None)
    frames = api.query_frames("u-1", sid)
    check("FRAME SK = INTERVIEW#{ivId}#FRAME#{answerId}#{capturedAt}", any(f["SK"].startswith(f"INTERVIEW#{sid}#FRAME#a-q1-1#") for f in frames))
    check("캡처 이미지는 저장 안 함 (frameKeys·이미지 필드 없음)", all("image" not in f and "frameKeys" not in f for f in frames))
    check("FRAME 필드: type, accepted, valid, gaze, head, eyesOpen", all({"type", "accepted", "valid", "gaze", "head", "eyesOpen"} <= set(f) for f in frames))
    check("보정 캡처 3장 → 정면 기준값이 session.baseline에 저장", api.get_interview("u-1", sid)["session"]["baseline"] is not None)

    # 보정 캡처가 3장 미만이면 baseline=None 그대로 (태도 미측정, 대체값 없음)
    s, b = call("POST", "/api/v1/interview/start", body={"job": "데이터 분석", "interviewType": "MIXED", "cameraConsent": True, "resumeText": RESUME})
    sid2 = b["sessionId"]
    call("POST", "/api/v1/interview/frame", multipart={"sessionId": sid2, "type": "CALIBRATION", "capturedAt": "2026-11-20T11:00:00", "image": img})
    for _ in range(4):
        st = call("GET", f"/api/v1/interview/{sid2}/status")[1]
        if st["status"] == "COMPLETED":
            break
        call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid2, "answerId": st["nextQuestion"]["answerId"],
                                                           "timeLimitReached": "false", "audio": (b"OggS-fake", "audio/webm")})
    done = api.get_interview("u-1", sid2)
    check("보정 1장 → baseline은 None 그대로 저장, 리포트는 생성", done["status"] == "COMPLETED" and done["session"]["baseline"] is None)

    # 글로 쓴 답변 (텍스트 방식, #121): 녹음 없이 text만 보내도 면접이 끝까지 간다
    s, b = call("POST", "/api/v1/interview/start", body={"job": "데이터 분석", "interviewType": "MIXED", "cameraConsent": False, "resumeText": RESUME})
    sid3 = b["sessionId"]
    first = call("GET", f"/api/v1/interview/{sid3}/status")[1]["nextQuestion"]["answerId"]
    s, b = call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid3, "answerId": first, "timeLimitReached": "false",
                                                               "text": "공공데이터로 방문객 추이를 분석했습니다."})
    check("글 답변 → 202, 음성 변환 없이 JUDGING", s == 202 and b["stage"] == "JUDGING")
    mid = api.get_interview("u-1", sid3)
    check("글 답변은 Transcribe 작업을 만들지 않음", "jobName" not in mid["transcribeJobs"][first] and mid["transcribeJobs"][first]["text"])
    check("글 답변도 다음 질문으로 넘어감", mid["stage"] == "NEXT_QUESTION_READY" and mid["lastAnswer"] == {"answerId": first, "evaluable": True, "reason": None})
    s, b = call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid3, "answerId": first, "timeLimitReached": "false", "text": "다시"})
    check("글 답변 중복 제출 → 409", s == 409 and b["error"]["code"] == "ANSWER_ALREADY_SUBMITTED")
    aid = call("GET", f"/api/v1/interview/{sid3}/status")[1]["nextQuestion"]["answerId"]
    s, b = call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid3, "answerId": aid, "timeLimitReached": "false", "text": "가" * 3001})
    check("글 답변 3,000자 초과 → 400", s == 400 and b["error"]["code"] == "INVALID_INPUT")
    s, b = call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid3, "answerId": aid, "timeLimitReached": "false", "text": "   "})
    check("빈 글 답변 → 평가 불가(NO_ANSWER)로 기록하고 계속", s == 202 and api.get_interview("u-1", sid3)["lastAnswer"]["reason"] == "NO_ANSWER")
    for _ in range(4):
        st = call("GET", f"/api/v1/interview/{sid3}/status")[1]
        if st["status"] == "COMPLETED":
            break
        call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid3, "answerId": st["nextQuestion"]["answerId"],
                                                           "timeLimitReached": "false", "text": "회귀분석 결과를 전년 자료와 비교해 검증했습니다."})
    check("글 답변만으로 리포트까지 완료", call("GET", f"/api/v1/interview/{sid3}/status")[1]["status"] == "COMPLETED")
    s, b = call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid3, "answerId": "a-q1-1", "timeLimitReached": "false"})
    check("audio도 text도 없으면 400", s == 400 and b["error"]["code"] == "INVALID_INPUT")

    # AI 출력 형식 오류는 같은 입력으로 다시 부른다 (#121). 한 번 어긋났다고 세션이 FAILED가 되지 않는다
    class AiOutputInvalid(Exception):
        code, retryable = "AI_OUTPUT_INVALID", True

    real_process, flaky = api.impl.process_answer, {"calls": 0, "fail": 1}

    def flaky_process(session, answer_result):
        flaky["calls"] += 1
        if flaky["calls"] <= flaky["fail"]:
            raise AiOutputInvalid()
        return real_process(session, answer_result)

    api.impl.process_answer = flaky_process
    try:
        s, b = call("POST", "/api/v1/interview/start", body={"job": "데이터 분석", "interviewType": "MIXED", "cameraConsent": False, "resumeText": RESUME})
        sid4 = b["sessionId"]
        aid = call("GET", f"/api/v1/interview/{sid4}/status")[1]["nextQuestion"]["answerId"]
        call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid4, "answerId": aid, "timeLimitReached": "false", "text": "결측치 기준을 정했습니다."})
        st = call("GET", f"/api/v1/interview/{sid4}/status")[1]
        check("AI 출력 오류 1번 → 다시 불러서 다음 질문으로 진행", st["status"] == "PROCESSING" and st["stage"] == "NEXT_QUESTION_READY" and flaky["calls"] == 2)
        flaky.update(calls=0, fail=99)
        call("POST", "/api/v1/interview/answer", multipart={"sessionId": sid4, "answerId": st["nextQuestion"]["answerId"], "timeLimitReached": "false", "text": "다시 답합니다."})
        st = call("GET", f"/api/v1/interview/{sid4}/status")[1]
        check("AI 출력 오류가 계속되면 3번 부른 뒤 FAILED(AI_OUTPUT_INVALID, retryable)", st["status"] == "FAILED" and st["error"]["code"] == "AI_OUTPUT_INVALID"
              and st["error"]["retryable"] is True and flaky["calls"] == api.AI_RETRY_CALLS)
    finally:
        api.impl.process_answer = real_process

    # 지워진 세션을 뒤늦은 작업이 되살리지 않음 (회원 탈퇴 중 경쟁 상태)
    s, b = call("POST", "/api/v1/interview/start", body={"job": "데이터 분석", "interviewType": "MIXED", "cameraConsent": False, "resumeText": RESUME})
    gone = b["sessionId"]
    tbl = boto3.resource("dynamodb").Table("test-cm")
    tbl.delete_item(Key={"PK": "USER#u-1", "SK": f"INTERVIEW#{gone}"})
    api.run_task({"task": "interview.start", "userId": "u-1", "sessionId": gone, "input": {
        "job": "데이터 분석", "resumeText": RESUME, "interviewType": "MIXED", "cameraConsent": False}})
    check("지워진 세션은 뒤늦은 작업이 다시 만들지 않음", tbl.get_item(Key={"PK": "USER#u-1", "SK": f"INTERVIEW#{gone}"}).get("Item") is None)

    print(f"\n{sum(results)}/{len(results)} 통과")
    raise SystemExit(0 if all(results) else 1)


main()
