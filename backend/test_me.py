"""기본 프로필·워크스페이스 테스트 (moto).

실행: cd backend && uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb]" python test_me.py
"""

import json
import os

os.environ.update(AWS_DEFAULT_REGION="ap-northeast-2", AWS_REGION="ap-northeast-2", AWS_ACCESS_KEY_ID="test",
                  AWS_SECRET_ACCESS_KEY="test", TABLE_CAREER_MENTOR="test-cm", ALLOW_DEV_USER_HEADER="1")

from moto import mock_aws  # noqa: E402

results = []


def check(name, cond):
    cond = bool(cond)
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {name}")


@mock_aws
def main():
    import boto3

    boto3.client("dynamodb").create_table(
        TableName="test-cm", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}])
    import workspace as ws
    from app import lambda_handler

    def call(method, path, body=None, user="u-1", query=None):
        e = {"rawPath": path, "requestContext": {"http": {"method": method, "path": path}},
             "headers": {"x-user-id": user} if user else {}, "queryStringParameters": query}
        if body is not None:
            e["body"] = json.dumps(body, ensure_ascii=False)
        r = lambda_handler(e, None)
        return r["statusCode"], json.loads(r["body"]) if r["body"] else None

    # ---- 기본 프로필
    s, b = call("GET", "/api/v1/me/profile")
    check("프로필 없으면 404 PROFILE_NOT_FOUND", s == 404 and b["error"]["code"] == "PROFILE_NOT_FOUND")
    s, b = call("PUT", "/api/v1/me/profile", {"birthYear": 2003, "residenceSido": "26", "residenceSigungu": "26290",
                                              "educationLevel": "BACHELOR", "major": "통계학", "userId": "someone-else",
                                              "desiredJobs": [{"work24Code": None, "ncsCode": "20010105", "name": "데이터 분석"}]})
    check("PUT 프로필 → 저장 (본문 userId는 무시)", s == 200 and b["major"] == "통계학" and "userId" not in b)
    item = boto3.resource("dynamodb").Table("test-cm").get_item(Key={"PK": "USER#u-1", "SK": "PROFILE#BASIC"})["Item"]
    check("토큰 사용자(USER#u-1) 아래에 저장, ownerUserId도 같음", item["ownerUserId"] == "u-1")
    s, b = call("PUT", "/api/v1/me/profile", {"employmentStatus": "UNEMPLOYED"})
    check("부분 수정: 보낸 필드만 바뀌고 나머지 유지", s == 200 and b["major"] == "통계학" and b["employmentStatus"] == "UNEMPLOYED")
    s, b = call("PUT", "/api/v1/me/profile", {"major": None})
    check("null을 보내면 그 항목 삭제", s == 200 and "major" not in b)
    s, b = call("PUT", "/api/v1/me/profile", {"birthYear": "2003"})
    check("형식이 틀리면 400 (birthYear 문자열)", s == 400 and "birthYear" in b["error"]["message"])
    s, b = call("PUT", "/api/v1/me/profile", {"hacked": True})
    check("모르는 필드 → 400", s == 400)
    s, b = call("PUT", "/api/v1/me/profile", {"residenceSido": "26", "desiredJobs": [{"name": "a"}] * 4})
    check("희망 직무 4개 → 400 (최대 3개)", s == 400)
    s, b = call("GET", "/api/v1/me/profile", user="u-2")
    check("다른 사용자 프로필은 안 보임", s == 404)

    # ---- 워크스페이스
    s, b = call("POST", "/api/v1/me/workspaces", {"jobPostingId": "wk24-K0001", "snapshotId": "20261120-ab12cd34"})
    check("공고로 워크스페이스 생성 → 201, ws-{jobPostingId}", s == 201 and b["workspaceId"] == "ws-wk24-K0001" and b["status"] == "INTEREST")
    s, b = call("POST", "/api/v1/me/workspaces", {"jobPostingId": "wk24-K0001"})
    check("같은 공고 다시 → 200, 기존 것 (중복 없음)", s == 200 and b["created"] is False and b["snapshotId"] == "20261120-ab12cd34")
    s, b = call("POST", "/api/v1/me/workspaces", {"targetNcsCode": "20010105"})
    check("NCS 직무로 생성 → ws-ncs-{code}", s == 201 and b["workspaceId"] == "ws-ncs-20010105")
    s, b = call("POST", "/api/v1/me/workspaces", {"jobPostingId": "bad#id"})
    check("ID에 # → 400", s == 400)

    s, b = call("PATCH", "/api/v1/me/workspaces/ws-wk24-K0001", {"status": "PREPARING",
                                                                 "selectedDocuments": {"RESUME": {"documentId": "doc-1", "version": 2}}})
    check("상태·문서 버전 변경", s == 200 and b["status"] == "PREPARING" and b["selectedDocuments"]["RESUME"]["version"] == 2)
    s, b = call("PATCH", "/api/v1/me/workspaces/ws-wk24-K0001", {"selectedDocuments": {"COVER_LETTER": {"documentId": "doc-2", "version": 1}}})
    check("문서 선택은 합쳐짐 (이력서 유지 + 자소서 추가)", set(b["selectedDocuments"]) == {"RESUME", "COVER_LETTER"})
    s, b = call("PATCH", "/api/v1/me/workspaces/ws-wk24-K0001", {"status": "WINNING"})
    check("없는 상태값 → 400", s == 400)

    s, b = call("GET", "/api/v1/me/workspaces", query={"status": "PREPARING"})
    check("상태별 목록 (PREPARING만)", s == 200 and [i["workspaceId"] for i in b["items"]] == ["ws-wk24-K0001"])
    s, b = call("GET", "/api/v1/me/workspaces")
    check("전체 목록 2개, 최근 수정순", len(b["items"]) == 2 and b["items"][0]["workspaceId"] == "ws-wk24-K0001")
    s, b = call("GET", "/api/v1/me/workspaces", user="u-2")
    check("다른 사용자는 내 워크스페이스 목록이 안 보임", b["items"] == [])
    s, b = call("GET", "/api/v1/me/workspaces/ws-wk24-K0001", user="u-2")
    check("다른 사용자는 내 워크스페이스를 못 엶 (404)", s == 404)

    # 연결된 결과 (A의 분석·C의 면접이 GSI1에 USER#{u}#WS#{ws}로 들어온 상황)
    t = boto3.resource("dynamodb").Table("test-cm")
    t.put_item(Item={"PK": "USER#u-1", "SK": "ANALYSIS#analysis-1", "GSI1PK": "USER#u-1#WS#ws-wk24-K0001",
                     "GSI1SK": "ANALYSIS#2026-11-20T10:00:00+09:00#analysis-1", "ownerUserId": "u-1", "status": "COMPLETED",
                     "entityType": "JobAnalysis", "createdAt": "2026-11-20T10:00:00+09:00"})
    t.put_item(Item={"PK": "USER#u-1", "SK": "INTERVIEW#iv-1", "GSI1PK": "USER#u-1#WS#ws-wk24-K0001",
                     "GSI1SK": "INTERVIEW#2026-11-20T11:00:00+09:00#iv-1", "ownerUserId": "u-1", "status": "COMPLETED",
                     "entityType": "Interview", "createdAt": "2026-11-20T11:00:00+09:00"})
    s, b = call("GET", "/api/v1/me/workspaces/ws-wk24-K0001")
    check("워크스페이스 상세에 연결된 분석·면접", s == 200 and b["linked"]["ANALYSIS"][0]["id"] == "analysis-1"
          and b["linked"]["INTERVIEW"][0]["id"] == "iv-1" and b["linked"]["REVIEW"] == [])

    # B가 코드에서 쓰는 방식: OPP#SAVED#와 워크스페이스를 한 트랜잭션으로
    client = boto3.client("dynamodb")
    from boto3.dynamodb.types import TypeSerializer

    ser = TypeSerializer()
    put = ws.workspace_put("u-3", job_posting_id="alio-000001", snapshot_id="20261120-11112222", status="PLANNED")
    saved = {"PK": "USER#u-3", "SK": "OPP#SAVED#alio-000001", "kind": "TARGET", "workspaceId": "ws-alio-000001"}
    client.transact_write_items(TransactItems=[
        {"Put": {"TableName": put["Put"]["TableName"], "Item": {k: ser.serialize(v) for k, v in put["Put"]["Item"].items()},
                 "ConditionExpression": put["Put"]["ConditionExpression"]}},
        {"Put": {"TableName": "test-cm", "Item": {k: ser.serialize(v) for k, v in saved.items()}}}])
    item, created = ws.ensure_workspace("u-3", job_posting_id="alio-000001")
    check("B 트랜잭션으로 만든 워크스페이스를 ensure가 그대로 돌려줌", created is False and item["status"] == "PLANNED")

    print(f"\n{sum(results)}/{len(results)} 통과")
    raise SystemExit(0 if all(results) else 1)


main()
