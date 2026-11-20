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
    check("A 역량 프로필을 면접 계약으로 변환하며 원문은 제외", sess2["profile"] == {
        "projects": ["예약 API"], "skills": ["Python"], "needsConfirmation": ["트래픽"],
        "profileId": "p-1", "profileVersion": 2,
    })
    t.put_item(Item={**career_profile, "skills": ["이전 형식의 원본"]})
    check("변환할 수 없는 역량 프로필은 전달하지 않음", api.load_latest_profile("u-1") is None)

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
