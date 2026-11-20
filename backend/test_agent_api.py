"""채팅 Agent 백엔드 흐름 테스트 (moto DynamoDB, B는 데모 데이터 메모리 저장소, 모델은 대본 실행기).
실행: cd backend && uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb]" \
  --with-requirements ../ai/busan-opportunity/requirements.txt --with-requirements ../ai/supervisor/requirements.txt \
  --with-requirements ../ai/mentoring/requirements.txt --with-requirements ../contracts/requirements.txt python test_agent_api.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "ai/supervisor/src"), str(ROOT / "ai/busan-opportunity/src"), str(ROOT / "ai/mentoring/src"),
                str(ROOT / "ai/mentoring/tests"), str(ROOT / "contracts/src")]
os.environ.update(AWS_DEFAULT_REGION="ap-northeast-2", AWS_REGION="ap-northeast-2", AWS_ACCESS_KEY_ID="test",
                  AWS_SECRET_ACCESS_KEY="test", TABLE_CAREER_MENTOR="test-cm", RUN_TASKS_INLINE="1",
                  ALLOW_DEV_USER_HEADER="1", MODEL_ID="test-model")
os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
from moto import mock_aws  # noqa: E402

results = []


def check(name, cond):
    cond = bool(cond)
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def ev(method, path, user="demo1", body=None):
    e = {"rawPath": path, "requestContext": {"http": {"method": method, "path": path}},
         "headers": {"x-user-id": user} if user else {}}
    if body is not None:
        e["body"] = json.dumps(body, ensure_ascii=False)
    return e


class Runner:
    """모델 대신 도구를 정해진 대로 부르고 답을 돌려준다."""

    def __init__(self):
        self.script = None
        self.runs = []

    def run(self, *, system_prompt, history, message, tools, max_turns):
        from supervisor.models import ChatReply

        by_name = {t.__name__: t for t in tools}
        self.runs.append({"message": message, "history": history})
        text = self.script(by_name)
        return ChatReply(reply=text, follow_ups=["모의면접 체험해 볼래요"])


@mock_aws
def main():
    import boto3

    boto3.client("dynamodb").create_table(
        TableName="test-cm", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}])
    table = boto3.resource("dynamodb").Table("test-cm")

    import agent_api
    import opportunities_api
    from app import lambda_handler
    from opportunity.config import load_config
    from opportunity.seeds import demo_world

    opportunities_api._deps = demo_world.build_deps(load_config())  # B는 데모 데이터 (AWS 안 부름)
    runner = Runner()
    agent_api.build_runner = lambda: runner

    def call(method, path, body=None, user="demo1"):
        r = lambda_handler(ev(method, path, user, body), None)
        return r["statusCode"], json.loads(r["body"]) if r["body"] else None

    check("health에 agentImpl", call("GET", "/api/v1/health")[1].get("agentImpl") == "supervisor")
    table.put_item(Item={"PK": "USER#demo1", "SK": "PROFILE#BASIC", "desiredJobs": [{"name": "데이터 분석"}],
                         "desiredRegion": "26"})

    # 1. 조건 대화 → 공고·정책 카드, 저장 묻기, 면접 체험 제안 (S-01, BE-S1)
    def search(tools):
        out = tools["search_job_postings"](job_name="데이터 분석", region="부산", min_salary=3000, career_type="NEW")
        tools["find_youth_policies"]()
        return f"부산 데이터 분석 공고 {len(out.get('items', []))}개와 청년정책을 찾았어요."

    runner.script = search
    s, b = call("POST", "/api/v1/agent/chat", {"message": "부산 데이터 분석 신입 연봉 3천 이상", "userId": "demo2"})
    check("POST /agent/chat → 202 PENDING", s == 202 and b["status"] == "PENDING" and b["sessionId"].startswith("chat-"))
    sid, mid = b["sessionId"], b["messageId"]
    s, m = call("GET", f"/api/v1/agent/chat/{sid}/messages/{mid}")
    check("조회 → COMPLETED", s == 200 and m["status"] == "COMPLETED" and m["reply"].startswith("부산 데이터 분석"))
    postings = [c["posting"] for c in m["cards"] if c["type"] == "POSTING"]
    policies = [c for c in m["cards"] if c["type"] == "POLICY"]
    check("B 실제 함수로 찾은 공고 카드 (최대 5개, 숫자 점수 없음)",
          0 < len(postings) <= 5 and all("matchScore" not in p and p["career"] for p in postings))
    check("정책 카드가 함께 온다", len(policies) > 0)
    actions = {a["type"]: a for a in m["actions"]}
    check("저장 묻기는 바뀐 조건만", actions.get("SAVE_CONDITIONS", {}).get("profilePatch") ==
          {"desiredSalaryMin": 3000, "desiredCareerType": "NEW"})
    check("면접 체험 제안은 follow_ups 칩으로 (코드 칩 없음)", "SUGGEST_INTERVIEW" not in actions and m["followUps"] == ["모의면접 체험해 볼래요"])
    check("본문 userId는 무시 (demo1로 저장)", table.get_item(Key={"PK": "USER#demo1", "SK": f"SESSION#{sid}"}).get("Item"))

    # 2. 저장 버튼 → PUT /me/profile (D-40)
    s, prof = call("PUT", "/api/v1/me/profile", actions["SAVE_CONDITIONS"]["profilePatch"])
    check("PUT /me/profile에 새 필드 저장", s == 200 and prof["desiredSalaryMin"] == 3000 and prof["desiredCareerType"] == "NEW")
    s, _ = call("PUT", "/api/v1/me/profile", {"desiredCareerType": "INTERN"})
    check("잘못된 desiredCareerType은 400", s == 400)

    # 3. 면접 체험: 자소서 없음 → 입력 요청, 있음 → 시작 카드 (S-03)
    def interview(tools):
        tools["prepare_mock_interview"](job="데이터 분석")
        return "모의면접 체험을 준비했어요."

    runner.script = interview
    s, b = call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "모의면접 체험해 볼래요"})
    s, m = call("GET", f"/api/v1/agent/chat/{sid}/messages/{b['messageId']}")
    check("자소서 없음 → REQUEST_COVER_LETTER", [a["type"] for a in m["actions"]] == ["REQUEST_COVER_LETTER"])
    check("두 번째 턴은 지난 대화를 받는다", runner.runs[-1]["history"][0]["text"] == "부산 데이터 분석 신입 연봉 3천 이상")
    table.put_item(Item={"PK": "USER#demo1", "SK": "DOC_LATEST#doc-cl1", "documentId": "doc-cl1",
                         "documentType": "COVER_LETTER", "title": "데이터 분석 자소서", "latestVersion": 1,
                         "extractionStatus": "COMPLETED", "ownerUserId": "demo1", "updatedAt": "2026-11-20T10:00:00+09:00"})
    s, b = call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "자소서 저장해 뒀어요",
                                               "attachments": [{"documentId": "doc-cl1"}]})
    s, m = call("GET", f"/api/v1/agent/chat/{sid}/messages/{b['messageId']}")
    check("저장된 자소서 → START_INTERVIEW(documentId)", m["actions"] and m["actions"][0]["type"] == "START_INTERVIEW"
          and m["actions"][0]["documentId"] == "doc-cl1")
    s, _ = call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "남의 문서",
                                               "attachments": [{"documentId": "doc-none"}]})
    check("남의·없는 문서 첨부는 404", s == 404)

    # 4. 대화 목록, 소유 확인
    s, session = call("GET", f"/api/v1/agent/chat/{sid}")
    check("대화 목록 (USER·ASSISTANT 번갈아 6개)", s == 200 and [x["role"] for x in session["messages"]] ==
          ["USER", "ASSISTANT"] * 3)
    check("남의 대화는 404", call("GET", f"/api/v1/agent/chat/{sid}", user="demo2")[0] == 404)
    check("남의 메시지는 404", call("GET", f"/api/v1/agent/chat/{sid}/messages/{mid}", user="demo2")[0] == 404)
    check("토큰 없으면 401", call("POST", "/api/v1/agent/chat", {"message": "안녕"}, user=None)[0] == 401)
    check("빈 메시지는 400", call("POST", "/api/v1/agent/chat", {"message": " "})[0] == 400)
    check("없는 경로 404", call("GET", "/api/v1/agent/nope")[0] == 404)

    # 5. 저장된 메시지에 원문 도구 결과가 없다
    stored = table.get_item(Key={"PK": "USER#demo1", "SK": f"CHAT#{sid}#{mid}"})["Item"]
    check("toolCalls에는 이름·성공·시간만", all(set(c) == {"name", "ok", "durationMs"} for c in stored["toolCalls"]))

    # 5-1. 이력서·경험 요약이 모델 문맥으로 간다 (개발계획서4 §5.1). 원문·인용문은 빠진다
    table.put_item(Item={"PK": "USER#demo1", "SK": "PROFILE#LATEST", "latestProfileId": "p-1", "latestVersion": 1})
    table.put_item(Item={"PK": "USER#demo1", "SK": "PROFILE#p-1#V#0001", "profileId": "p-1", "profileVersion": 1,
                         "skills": [{"name": "SQL", "factStatus": "VERIFIED", "evidenceLevel": "EVIDENCED"},
                                    {"name": "Tableau", "factStatus": "NEEDS_CONFIRMATION", "evidenceLevel": "SELF_REPORTED"},
                                    {"name": "Java", "factStatus": "VERIFIED", "evidenceLevel": "USER_CONFIRMED_GAP"}],
                         "projects": [{"name": "캡스톤 매출 분석", "summary": "SQL로 매출 데이터 분석", "factStatus": "NEEDS_CONFIRMATION"}],
                         "evidence": [{"quotedText": "이력서 원문 인용"}], "needsConfirmation": ["통계 분석 경험"]})
    table.put_item(Item={"PK": "USER#demo1", "SK": "STORY_LATEST#st-1", "storyId": "st-1", "latestVersion": 1,
                         "updatedAt": "2026-11-20T09:00:00+09:00"})
    table.put_item(Item={"PK": "USER#demo1", "SK": "STORY#st-1#V#0001", "storyId": "st-1", "version": 1,
                         "title": "동아리 회계 정리", "rawExperience": "원문 경험 전체", "result": "정산 오류 0건"})
    runner.script = lambda tools: "SQL을 쓴 캡스톤 매출 분석 경험이 데이터 분석 공고와 이어져요."
    s, b = call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "내 경험이랑 맞는 공고 있어?"})
    context = runner.runs[-1]["message"]
    check("모델 문맥에 역량·프로젝트·경험 블록", all(t in context for t in ("SQL", "Tableau", "캡스톤 매출 분석", "동아리 회계 정리", "정산 오류 0건")))
    check("원문·인용문·미보유 확인 역량은 문맥에서 뺀다",
          "이력서 원문 인용" not in context and "원문 경험 전체" not in context and "Java" not in context)
    check("확인 여부를 구분해 넘긴다", '"name":"SQL","confirmed":true' in context and '"name":"Tableau","confirmed":false' in context)
    check("CHAT_MODEL_ID가 없으면 MODEL_ID", agent_api.model_id() == "test-model")
    os.environ["CHAT_MODEL_ID"] = "chat-model"
    check("CHAT_MODEL_ID가 있으면 그 값", agent_api.model_id() == "chat-model")
    os.environ.pop("CHAT_MODEL_ID")

    # 5-2. 데이터 순서: 공식 데이터에 없으면 팀 데이터 (데모 공고는 모두 팀 데이터). 회사 이름은 기업 데이터도 본다
    seen = {}

    def tiered(tools):
        seen["out"] = tools["search_job_postings"](job_name="데이터 분석", organization="가상")
        return "공식 데이터에는 조건에 맞는 공고가 없어요. 팀이 넣어 둔 시연용 데이터에서 찾았어요."

    runner.script = tiered
    call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "가상 회사 데이터 분석 공고"})
    out = seen["out"]
    check("공식 데이터에 없으면 officialFound=false + 팀 데이터", out["officialFound"] is False and out["items"]
          and all(i["isSample"] for i in out["items"]) and "teamDataNote" in out)
    check("회사 이름은 기업 데이터에서도 찾는다 (출처·기준일)", "companies" in out and all(c["source"] and c["asOf"] for c in out["companies"]))

    # 5-3. 말로 묻고 승낙하면 저장 도구가 실제로 저장한다 (D-40)
    def ask_save(tools):
        tools["search_job_postings"](min_salary=2500)
        return "공고를 찾았어요. 이 조건을 저장할까요?"

    runner.script = ask_save
    s, b = call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "연봉 2500 이상으로 다시 찾아줘"})
    s, m = call("GET", f"/api/v1/agent/chat/{sid}/messages/{b['messageId']}")
    check("저장 묻기 카드", m["actions"][0]["type"] == "SAVE_CONDITIONS")

    def do_save(tools):
        res = tools["save_search_conditions"]()
        return "저장했어요." if res.get("saved") else "저장하지 못했어요."

    runner.script = do_save
    s, b = call("POST", "/api/v1/agent/chat", {"sessionId": sid, "message": "응 저장해 줘"})
    s, m = call("GET", f"/api/v1/agent/chat/{sid}/messages/{b['messageId']}")
    basic = table.get_item(Key={"PK": "USER#demo1", "SK": "PROFILE#BASIC"})["Item"]
    check("채팅 승낙 → PROFILE#BASIC 저장", int(basic["desiredSalaryMin"]) == 2500 and m["reply"] == "저장했어요.")
    check("저장 완료 카드", m["actions"] == [{"type": "CONDITIONS_SAVED", "conditions": ["연봉 2,500만 원 이상"]}])

    # 5-5. 채팅 화면: 대화 목록·고정·삭제·멈추기
    s, listed = call("GET", "/api/v1/agent/chat")
    check("GET /agent/chat → 내 대화 목록 (메시지 없이)", s == 200 and any(x["sessionId"] == sid for x in listed["sessions"])
          and all("messages" not in x and "ownerUserId" not in x for x in listed["sessions"]))
    check("남의 목록에는 내 대화가 없다",
          all(x["sessionId"] != sid for x in call("GET", "/api/v1/agent/chat", user="demo2")[1]["sessions"]))
    runner.script = lambda tools: "새 대화예요."
    s, other = call("POST", "/api/v1/agent/chat", {"message": "새 대화"})
    rows = call("GET", "/api/v1/agent/chat")[1]["sessions"]
    stamps = [r["lastMessageAt"] for r in rows]  # 초 단위라 같은 초에 말한 대화끼리는 순서가 정해지지 않는다
    check("최근에 말한 순서 (lastMessageAt 내림차순)", stamps == sorted(stamps, reverse=True)
          and any(r["sessionId"] == other["sessionId"] for r in rows))
    s, pinned = call("PATCH", f"/api/v1/agent/chat/{sid}", {"pinned": True})
    check("PATCH {pinned:true} → 고정", s == 200 and pinned["pinned"] is True and pinned["sessionId"] == sid)
    check("고정한 대화가 맨 위", call("GET", "/api/v1/agent/chat")[1]["sessions"][0]["sessionId"] == sid)
    check("pinned 말고는 400", call("PATCH", f"/api/v1/agent/chat/{sid}", {"title": "바꾸기"})[0] == 400)
    check("남의 대화 고정은 404", call("PATCH", f"/api/v1/agent/chat/{sid}", {"pinned": False}, user="demo2")[0] == 404)

    held = []  # 멈추기: 실행 이벤트를 바로 돌리지 않고 붙잡아 둔다 (답을 만드는 중인 상태)
    dispatcher = agent_api.deps().dispatcher
    dispatcher.dispatch = held.append
    s, b = call("POST", "/api/v1/agent/chat", {"sessionId": other["sessionId"], "message": "오래 걸리는 질문"})
    check("만드는 중인 답 PENDING", s == 202 and b["status"] == "PENDING")
    cancel_path = f"/api/v1/agent/chat/{other['sessionId']}/messages/{b['messageId']}/cancel"
    check("남의 답은 멈출 수 없다 (404)", call("POST", cancel_path, user="demo2")[0] == 404)
    s, m = call("POST", cancel_path)
    check("POST .../cancel → CANCELLED", s == 200 and m["status"] == "CANCELLED")
    out = lambda_handler(held.pop(), None)
    check("멈춘 답의 실행 이벤트는 SKIPPED", out["status"] == "SKIPPED")
    s, b2 = call("POST", "/api/v1/agent/chat", {"sessionId": other["sessionId"], "message": "다시 물어볼게요"})
    check("멈추면 바로 다음 말을 보낼 수 있다", s == 202)
    del dispatcher.dispatch  # 인스턴스에 덮어쓴 것을 지워 원래 메서드로 돌린다
    lambda_handler(held.pop(), None)
    check("이어서 보낸 답은 완료", call("GET", f"/api/v1/agent/chat/{other['sessionId']}/messages/{b2['messageId']}")[1]["status"]
          == "COMPLETED")
    check("끝난 답을 멈춰도 그대로", call("POST", f"/api/v1/agent/chat/{other['sessionId']}/messages/{b2['messageId']}/cancel")[1][
        "status"] == "COMPLETED")

    check("남의 대화 삭제는 404", call("DELETE", f"/api/v1/agent/chat/{other['sessionId']}", user="demo2")[0] == 404)
    s, gone = call("DELETE", f"/api/v1/agent/chat/{other['sessionId']}")
    check("DELETE → 대화 지움", s == 200 and gone == {"sessionId": other["sessionId"], "deleted": True})
    check("지운 대화는 404", call("GET", f"/api/v1/agent/chat/{other['sessionId']}")[0] == 404)
    left = table.query(KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
                       ExpressionAttributeValues={":pk": "USER#demo1", ":sk": f"CHAT#{other['sessionId']}#"})["Items"]
    check("지운 대화의 메시지도 남지 않는다", left == [])
    check("고정 해제", call("PATCH", f"/api/v1/agent/chat/{sid}", {"pinned": False})[1]["pinned"] is False)

    # 6. 비동기 이벤트 입구 (같은 작업 두 번 → 한 번만)
    out = lambda_handler({"agentTask": {"userId": "demo1", "sessionId": sid, "messageId": mid}}, None)
    check("agentTask 이벤트: 끝난 턴은 SKIPPED", out["status"] == "SKIPPED")

    print(f"\n{sum(results)}/{len(results)} 통과")
    raise SystemExit(0 if all(results) else 1)


main()
