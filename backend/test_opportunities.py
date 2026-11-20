"""부산 기회 추천 연결 테스트 (moto). 백엔드 라우터 → opportunities_api → B 패키지 → DynamoDB까지 본다.

실행: cd backend && uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb,scheduler]" \
        --with-requirements ../ai/busan-opportunity/requirements.txt python test_opportunities.py

S3 Vectors와 Bedrock은 moto에 없어서 B의 메모리 구현으로 바꿔 끼운다. 데이터는 B의 데모 데이터(가상 회사)다.
"""

import json
import os
import sys
from pathlib import Path

os.environ.update(
    AWS_DEFAULT_REGION="ap-northeast-2", AWS_REGION="ap-northeast-2", AWS_ACCESS_KEY_ID="test",
    AWS_SECRET_ACCESS_KEY="test", ALLOW_DEV_USER_HEADER="1", TABLE_CAREER_MENTOR="test-cm", TABLE_CATALOG="test-cat",
    OPP_VECTOR_BUCKET="test-vectors", OPP_VECTOR_INDEX="postings-v1", OPP_DATA_BUCKET="test-data",
    MODEL_ID="test-model", EMBEDDING_MODEL_ID="test-embed",
    SCHEDULER_TARGET_ARN="arn:aws:lambda:ap-northeast-2:123456789012:function:test-api",
    SCHEDULER_ROLE_ARN="arn:aws:iam::123456789012:role/test-scheduler-role")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai" / "busan-opportunity" / "src"))  # 배포에서는 package.sh가 묶는다

from moto import mock_aws  # noqa: E402

results = []


def check(name, cond):
    cond = bool(cond)
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def create_table(client, name):
    client.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                               {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}])


@mock_aws
def main():
    import boto3

    client = boto3.client("dynamodb")
    create_table(client, "test-cm")
    create_table(client, "test-cat")

    import opportunities_api
    import workspace as ws
    from app import lambda_handler
    from opportunity.seeds import demo_world as w

    check("B 패키지를 찾았다", opportunities_api.IMPL_NAME == "opportunity")

    # 데모 데이터를 실제 저장소 구현(DynamoDB)에 넣고, 벡터·임베딩만 메모리 구현으로 바꾼다
    demo = w.build_deps()
    deps = opportunities_api.deps()
    for snap in demo.catalog.snapshots.values():
        deps.catalog.put_snapshot(snap)
    for latest in demo.catalog.latest.values():
        deps.catalog.put_latest(latest)
    for alts in demo.catalog.alts.values():
        deps.catalog.put_alts(alts)
    for policy in demo.catalog.policies.values():
        deps.catalog.put_policy(policy)
    for company in demo.catalog.companies.values():
        deps.catalog.put_company(company)
    deps.catalog.set_data_as_of(w.DATA_AS_OF)
    deps.vectors, deps.embedder, deps.llm = demo.vectors, demo.embedder, None

    def call(method, path, body=None, user="u-demo1", query=None, headers=None):
        e = {"version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
             "requestContext": {"requestId": "req-test", "stage": "$default",
                                "http": {"method": method, "path": path, "protocol": "HTTP/1.1",
                                         "sourceIp": "127.0.0.1", "userAgent": "test"}},
             "headers": {"content-type": "application/json", **({"x-user-id": user} if user else {}), **(headers or {})},
             "queryStringParameters": query, "isBase64Encoded": False}
        if body is not None:
            e["body"] = json.dumps(body, ensure_ascii=False)
        r = lambda_handler(e, None)
        return r["statusCode"], json.loads(r["body"]) if r.get("body") else None

    base = "/api/v1/opportunities"

    s, body = call("GET", "/api/v1/health", user=None)
    check("health에 opportunitiesImpl", s == 200 and body["opportunitiesImpl"] == "opportunity")

    s, body = call("GET", f"{base}/postings", user=None)
    check("사용자 정보가 없으면 401", s == 401 and body["error"]["code"] == "UNAUTHORIZED")

    s, body = call("GET", f"{base}/postings")
    check("희망 직무가 없으면 422 PROFILE_INCOMPLETE", s == 422 and body["error"]["code"] == "PROFILE_INCOMPLETE")

    # 공통 프로필은 백엔드 API로 넣는다 (B는 읽기만)
    profile = w.build_profiles()["demo1"].to_api()
    for key in ("skills", "certificates", "confirmedMissingCertificates", "isDemo", "talentPoolConsent"):
        profile.pop(key, None)
    s, body = call("PUT", "/api/v1/me/profile", body=profile)
    check("기본 프로필 저장", s == 200)
    # 기준 시각을 데모 시각으로 고정한다 (B는 설정의 demoAsOf를 쓴다)
    from opportunity.models import OppPrefs
    deps.users.put_prefs("u-demo1", OppPrefs(demo_as_of=w.DEMO_AS_OF))
    as_of = None

    s, feed = call("GET", f"{base}/postings", query=as_of)
    ids = [i["jobPostingId"] for i in feed.get("items", [])] if s == 200 else []
    check("피드: 부산·서울 공고가 함께 나온다", s == 200 and w.BUSAN_DATA in ids and w.SEOUL_DATA in ids)
    check("피드: 마감 공고는 없다", w.BUSAN_DATA_EXPIRED not in ids and w.BUSAN_DATA_JUST_CLOSED not in ids)

    s, detail = call("GET", f"{base}/postings/{w.BUSAN_DATA}", query=as_of)
    check("상세: 공통 판정 함수(elig-v1)를 쓴다",
          s == 200 and detail["eligibility"]["ruleVersion"] == "elig-v1" and detail["eligibility"]["status"] == "ELIGIBLE")

    s, alts = call("GET", f"{base}/postings/{w.SEOUL_DATA}/alternatives", query=as_of)
    check("대안: 부산 공고 2개 이상", s == 200 and len(alts["alternatives"]) >= 2)

    s, wallet = call("GET", f"{base}/policies", query=as_of)
    check("정책 지갑", s == 200 and w.P_JOY_DOUBLE in json.dumps(wallet) and w.P_UNVERIFIED not in json.dumps(wallet))

    s, saved = call("POST", f"{base}/saved", body={"jobPostingId": w.BUSAN_DATA, "kind": "TARGET"}, query=as_of,
                    headers={"idempotency-key": "k-1"})
    check("목표 담기 201, 일정 2개", s == 201 and len(saved["schedules"]) == 2 and saved["saved"]["status"] == "PLANNED")
    workspace = ws.get_workspace("u-demo1", f"ws-{w.BUSAN_DATA}")
    check("워크스페이스가 같은 트랜잭션으로 생겼다", workspace["status"] == "PLANNED" and workspace["jobPostingId"] == w.BUSAN_DATA)
    s, again = call("POST", f"{base}/saved", body={"jobPostingId": w.BUSAN_DATA, "kind": "TARGET"}, query=as_of,
                    headers={"idempotency-key": "k-1"})
    check("같은 Idempotency-Key는 한 번만 반영", again["saved"] == saved["saved"])
    s, body = call("POST", f"{base}/saved", body={"jobPostingId": w.SEOUL_DATA, "kind": "TARGET"}, query=as_of,
                   headers={"idempotency-key": "k-1"})
    check("같은 키에 다른 본문은 409", s == 409 and body["error"]["code"] == "PRECONDITION_NOT_MET")

    ws.set_status("u-demo1", f"ws-{w.BUSAN_DATA}", "APPLIED")
    s, listed = call("GET", f"{base}/saved", query=as_of)
    check("저장 목록의 상태는 워크스페이스에서 온다", s == 200 and listed["items"][0]["status"] == "APPLIED")

    names = [x["Name"] for x in boto3.client("scheduler").list_schedules()["Schedules"]]
    check("EventBridge 일정 2개 (team07-opp-)", len(names) == 2 and all(n.startswith("team07-opp-") for n in names))
    target = boto3.client("scheduler").get_schedule(Name=names[0])["Target"]
    payload = json.loads(target["Input"])
    check("일정 Input은 oppSchedule로 감싼다", "oppSchedule" in payload)

    ws.set_status("u-demo1", f"ws-{w.BUSAN_DATA}", "PLANNED")
    r = lambda_handler(payload, None)
    s, inbox = call("GET", f"{base}/notifications")
    check("일정이 울리면 알림함에 들어간다", r == {"notified": True} and len(inbox["items"]) == 1)

    agent_event = {"messageVersion": "1.0", "agent": {"name": "CareerMentoringAgent", "id": "A", "alias": "a", "version": "1"},
                   "inputText": "받을 수 있는 정책 알려줘", "sessionId": "s-1", "actionGroup": "BusanOpportunity",
                   "apiPath": "/agent/policies", "httpMethod": "GET",
                   "parameters": [{"name": "userId", "type": "string", "value": "someone-else"}],
                   "sessionAttributes": {"userId": "u-demo1"}, "promptSessionAttributes": {}}
    r = lambda_handler(agent_event, None)
    check("Action Group 호출이 B 함수로 간다", r["response"]["httpStatusCode"] == 200
          and r["response"]["actionGroup"] == "BusanOpportunity")

    s, body = call("GET", f"{base}/postings/wk24-NOPE")
    check("없는 공고는 404 팀 공통 오류 형식", s == 404 and set(body["error"]) >= {"code", "message", "requestId", "retryable"})

    print(f"\n{sum(results)}/{len(results)} 통과")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
