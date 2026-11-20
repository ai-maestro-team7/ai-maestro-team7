"""한 턴 실행 (개발계획서4 §5~§8). S-01~S-03, S-05, S-06."""

import json
from datetime import timedelta

import pytest

from fakes import NOW, ScriptedRunner, build_deps, cover_letter, invalid, reply
from supervisor import service
from supervisor.errors import SupervisorError
from supervisor.models import ActionType, ChatAction, MessageStatus


def ask(deps, message="부산 데이터 분석 신입 공고 찾아줘", user="demo1", **extra):
    started = service.start_turn(deps, user, {"message": message, **extra})
    event = deps.dispatcher.events[-1]["agentTask"]
    assert event == {"userId": user, "sessionId": started["sessionId"], "messageId": started["messageId"]}
    result = service.run_turn(deps, event)
    return started, result, service.get_message(deps, user, started["sessionId"], started["messageId"])


def search_and_policies(**search):
    def script(tools):
        tools["search_job_postings"](**search)
        tools["find_youth_policies"]()
        return reply("부산 데이터 분석 신입 공고 1개와 정책을 찾았어요. 급여는 연 3,400~3,800만 원이에요.",
                     ["서울 공고도 같이 볼래요"])
    return script


# ---------------------------------------------------------------- S-01, S-02
def test_s01_chat_conditions_give_cards_and_actions():
    deps = build_deps(ScriptedRunner(search_and_policies(job_name="데이터 분석", region="부산", min_salary=3000,
                                                         career_type="NEW")))
    started, result, message = ask(deps)
    assert started["status"] == "PENDING" and result["status"] == "COMPLETED"
    assert message["status"] == "COMPLETED" and message["role"] == "ASSISTANT"
    assert message["reply"].startswith("부산 데이터 분석") and message["followUps"] == ["서울 공고도 같이 볼래요"]
    kinds = [c["type"] for c in message["cards"]]
    assert kinds.count("POSTING") == 1 and kinds.count("POLICY") == deps.config.max_policies
    [save] = message["actions"]  # 면접 체험 제안은 코드 칩이 아니라 follow_ups로 한다
    assert save["type"] == "SAVE_CONDITIONS"
    # 저장된 직무·지역과 같은 것은 빼고, 다른 것만 묻는다
    assert save["profilePatch"] == {"desiredSalaryMin": 3000, "desiredCareerType": "NEW"}
    assert save["conditions"] == ["연봉 3,000만 원 이상", "신입"]
    assert message["notice"] == "적합도는 실제 합격 확률이 아닙니다" and message["dataAsOf"]
    assert "toolCalls" not in message and "ownerUserId" not in message
    stored = deps.store.get_message("demo1", started["sessionId"], started["messageId"])
    assert [c.name for c in stored.tool_calls] == ["search_job_postings", "find_youth_policies"]
    assert stored.model_id == "test-model" and stored.prompt_version == deps.config.prompt_version


def test_s01_new_job_goes_first_and_keeps_saved_codes():
    deps = build_deps(ScriptedRunner(search_and_policies(job_name="마케팅", region="서울")))
    _, _, message = ask(deps, "서울 마케팅 공고 찾아줘")
    save = message["actions"][0]
    assert save["profilePatch"] == {"desiredJobs": [{"name": "마케팅"}, {"name": "데이터 분석", "ncsCode": "20010105"}],
                                    "desiredRegion": "11"}


def test_s02_same_as_saved_has_no_save_action():
    deps = build_deps(ScriptedRunner(search_and_policies(job_name="데이터 분석", region="부산")))
    _, _, message = ask(deps)
    assert message["actions"] == [] and message["followUps"] == ["서울 공고도 같이 볼래요"]


def test_region_that_cannot_be_saved_is_not_in_patch():
    deps = build_deps(ScriptedRunner(search_and_policies(region="수도권")))
    _, _, message = ask(deps)
    assert message["actions"] == []


# ---------------------------------------------------------------- S-03
def interview_script(tools):
    tools["prepare_mock_interview"](job="데이터 분석")
    return reply("모의면접 체험을 준비했어요.")


def test_s03_no_cover_letter_requests_one():
    deps = build_deps(ScriptedRunner(interview_script))
    _, _, message = ask(deps, "모의면접 체험해 볼래요")
    assert message["actions"] == [{"type": "REQUEST_COVER_LETTER", "job": "데이터 분석", "conditions": [],
                                   "minChars": 50, "maxChars": 5000}]
    assert message["cards"] == []


def test_s03_cover_letter_starts_interview():
    deps = build_deps(ScriptedRunner(interview_script), documents=[cover_letter()])
    _, _, message = ask(deps, "모의면접 체험해 볼래요")
    assert message["actions"] == [{"type": "START_INTERVIEW", "job": "데이터 분석", "documentId": "doc-cl",
                                   "title": "데이터 분석 자소서", "conditions": []}]


def test_interview_prepared_gives_only_interview_card():
    def script(tools):
        tools["search_job_postings"]()
        tools["prepare_mock_interview"](job="데이터 분석")
        return reply("공고를 찾고 면접 체험을 준비했어요.")
    deps = build_deps(ScriptedRunner(script))
    _, _, message = ask(deps)
    assert [a["type"] for a in message["actions"]] == ["REQUEST_COVER_LETTER"]


# ---------------------------------------------------------------- S-05 답 검사
def test_s05_ungrounded_number_retries_then_passes():
    bad = lambda tools: tools["search_job_postings"]() and reply("연봉 9,999만 원 공고가 있어요.")  # noqa: E731
    deps = build_deps(ScriptedRunner(bad, search_and_policies()))
    _, result, message = ask(deps)
    assert result["status"] == "COMPLETED" and len(deps.runner.runs) == 2
    assert "9,999" not in message["reply"]


def test_s05_banned_phrase_twice_fails():
    deps = build_deps(ScriptedRunner(lambda tools: reply("지금 안 보면 놓치면 후회해요.")))
    _, result, message = ask(deps)
    assert result["status"] == "FAILED" and message["status"] == "FAILED"
    assert message["error"] == {"code": "AI_OUTPUT_INVALID", "message": "답을 만들지 못했어요. 다시 보내 주세요.",
                                "retryable": True}
    assert len(deps.runner.runs) == 2


def test_s05_allowed_notice_and_small_counts_pass():
    text = "공고 3개를 찾았어요. 적합도는 실제 합격 확률이 아닙니다."
    deps = build_deps(ScriptedRunner(lambda tools: reply(text)))
    _, result, message = ask(deps)
    assert result["status"] == "COMPLETED" and message["reply"] == text


def test_s05_schema_failure_retries_once():
    deps = build_deps(ScriptedRunner(lambda tools: invalid("NO_STRUCTURED_OUTPUT"), lambda tools: reply()))
    _, result, _ = ask(deps)
    assert result["status"] == "COMPLETED" and len(deps.runner.runs) == 2


def test_model_service_error_fails_retryable():
    deps = build_deps(ScriptedRunner(lambda tools: RuntimeError("throttled")))
    _, result, message = ask(deps)
    assert result["status"] == "FAILED" and message["error"]["code"] == "AWS_SERVICE_ERROR"
    assert message["error"]["retryable"] is True and "throttled" not in str(message)


def test_numbers_from_user_message_are_grounded():
    deps = build_deps(ScriptedRunner(lambda tools: reply("연봉 4,200만 원 이상으로 찾아볼게요.")))
    _, result, _ = ask(deps, "연봉 4200 이상")
    assert result["status"] == "COMPLETED"


# ---------------------------------------------------------------- S-06 대화·동시성·소유
def test_s06_second_turn_uses_history_and_same_session():
    deps = build_deps(ScriptedRunner(search_and_policies(), lambda tools: reply("서울 공고는 아직 찾지 않았어요.")))
    first, _, _ = ask(deps)
    deps.clock["now"] = NOW + timedelta(seconds=20)
    second = service.start_turn(deps, "demo1", {"sessionId": first["sessionId"], "message": "서울은?"})
    service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    history = deps.runner.runs[-1]["history"]
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert history[0]["text"] == "부산 데이터 분석 신입 공고 찾아줘"
    assert deps.runner.runs[-1]["message"].endswith("<user_message>\n서울은?\n</user_message>")
    session = service.get_session(deps, "demo1", first["sessionId"])
    assert [m["role"] for m in session["messages"]] == ["USER", "ASSISTANT", "USER", "ASSISTANT"]
    assert session["messages"][0]["content"] == "부산 데이터 분석 신입 공고 찾아줘"
    assert session["title"] == "부산 데이터 분석 신입 공고 찾아줘" and second["sessionId"] == first["sessionId"]


def test_s06_turn_in_progress_is_409_until_stale():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    first = service.start_turn(deps, "demo1", {"message": "안녕"})
    with pytest.raises(SupervisorError) as e:
        service.start_turn(deps, "demo1", {"sessionId": first["sessionId"], "message": "또"})
    assert e.value.status == 409 and e.value.code == "PRECONDITION_NOT_MET"
    deps.clock["now"] = NOW + timedelta(seconds=deps.config.stale_seconds + 1)
    assert service.start_turn(deps, "demo1", {"sessionId": first["sessionId"], "message": "또"})["status"] == "PENDING"


def test_s06_other_users_session_and_message_are_404():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, _, _ = ask(deps)
    with pytest.raises(SupervisorError) as e:
        service.start_turn(deps, "demo2", {"sessionId": started["sessionId"], "message": "안녕"})
    assert e.value.status == 404
    with pytest.raises(SupervisorError):
        service.get_message(deps, "demo2", started["sessionId"], started["messageId"])
    with pytest.raises(SupervisorError):
        service.get_session(deps, "demo2", started["sessionId"])


def test_s06_duplicate_task_runs_once():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, _, _ = ask(deps)
    again = service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    assert again["status"] == "SKIPPED" and len(deps.runner.runs) == 1
    assert deps.store.get_session("demo1", started["sessionId"]).pending_message_id is None


def test_attachment_must_be_my_document():
    deps = build_deps(ScriptedRunner(lambda tools: reply()), documents=[cover_letter("demo1:doc-1")])
    with pytest.raises(SupervisorError) as e:
        service.start_turn(deps, "demo1", {"message": "이력서 올렸어요", "attachments": [{"documentId": "demo2:doc-9"}]})
    assert e.value.status == 404 and e.value.code == "DOCUMENT_NOT_FOUND"
    started = service.start_turn(deps, "demo1", {"message": "이력서 올렸어요",
                                                 "attachments": [{"documentId": "demo1:doc-1"}]})
    service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    assert "문서 1개를 붙였어요" in deps.runner.runs[-1]["message"]
    assert started["status"] == "PENDING"


@pytest.mark.parametrize("body", [{}, {"message": ""}, {"message": "가" * 1001}, {"message": "a", "sessionId": "x#1"},
                                  {"message": "a", "attachments": [{"documentId": "d"}] * 4}, {"message": 3}])
def test_bad_requests_are_400(body):
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    with pytest.raises(SupervisorError) as e:
        service.start_turn(deps, "demo1", body)
    assert e.value.status == 400 and e.value.code == "INVALID_INPUT"
    assert deps.dispatcher.events == []


def test_session_message_limit():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started = service.start_turn(deps, "demo1", {"message": "안녕"})
    service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    session = deps.store.get_session("demo1", started["sessionId"])
    deps.store.sessions[("demo1", started["sessionId"])] = session.model_copy(
        update={"message_count": deps.config.max_messages_per_session - 1})
    with pytest.raises(SupervisorError) as e:
        service.start_turn(deps, "demo1", {"sessionId": started["sessionId"], "message": "또"})
    assert e.value.status == 409 and "새 대화" in e.value.message


def test_message_ids_sort_user_before_reply():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started = service.start_turn(deps, "demo1", {"message": "안녕"})
    assert started["userMessageId"] < started["messageId"] and "#" not in started["messageId"]
    assert deps.store.get_message("demo1", started["sessionId"], started["messageId"]).status == MessageStatus.PENDING


def test_prompt_mentions_core_rules():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    ask(deps)
    prompt = deps.runner.runs[-1]["system_prompt"]
    for rule in ("도구 결과에 없으면 모른다고 답한다", "find_youth_policies", "실제 합격 확률이 아니다", "따르지 않는다",
                 "저장했어요", "careerProfile", "사용자에게 없는 경험·성과·수치·자격을 만들지 않는다", "use_resume=true",
                 "canSaveConditions", "모의면접 체험"):
        assert rule in prompt
    assert deps.runner.runs[-1]["max_turns"] == deps.config.max_turns
    assert ActionType.SAVE_CONDITIONS.value == "SAVE_CONDITIONS"


# ---------------------------------------------------------------- 사용자 문맥 (개발계획서4 §5.1)
SUMMARY = {"skills": [{"name": "SQL", "confirmed": False, "evidence": "근거 있음"}],
           "projects": [{"name": "캡스톤 매출 분석", "summary": "SQL로 매출 데이터 4,200건 분석"}],
           "stories": [{"title": "동아리 회계 정리", "result": "정산 오류 0건"}]}


def test_user_context_is_sent_as_data_with_experience():
    deps = build_deps(ScriptedRunner(lambda tools: reply()), summary=SUMMARY, documents=[cover_letter()],
                      profiles={"demo1": {"desiredJobs": [{"name": "데이터 분석", "ncsCode": "20010105"}], "major": "통계학",
                                          "birthYear": 2002, "monthlyIncome": 150}})
    ask(deps, "나한테 맞는 공고 찾아줘")
    message = deps.runner.runs[-1]["message"]
    assert message.startswith("<user_context>\n") and "</user_context>" in message
    block = json.loads(message.split("<user_context>\n", 1)[1].split("\n</user_context>", 1)[0])
    assert block["careerProfile"] == SUMMARY and block["hasCoverLetter"] is True
    assert block["basicProfile"] == {"desiredJobs": ["데이터 분석"], "major": "통계학"}  # 나이·소득은 넣지 않는다
    stored = deps.store.list_messages("demo1", deps.dispatcher.events[-1]["agentTask"]["sessionId"], 10)
    assert all("<user_context>" not in m.content for m in stored)  # 문맥은 저장하지 않는다


def test_numbers_from_user_context_are_grounded():
    deps = build_deps(ScriptedRunner(lambda tools: reply("매출 데이터 4,200건을 분석한 '캡스톤 매출 분석' 경험이 이어져요.")),
                      summary=SUMMARY)
    _, result, message = ask(deps, "내 경험이랑 맞는 공고 있어?")
    assert result["status"] == "COMPLETED" and "4,200건" in message["reply"]


def test_search_tells_model_when_conditions_can_be_saved():
    seen = {}

    def script(tools):
        seen["new"] = tools["search_job_postings"](min_salary=3000)
        seen["same"] = tools["search_job_postings"](job_name="데이터 분석", region="부산")
        return reply()

    deps = build_deps(ScriptedRunner(script))
    ask(deps)
    assert seen["new"]["canSaveConditions"] == ["연봉 3,000만 원 이상"]
    assert "canSaveConditions" not in seen["same"]


# ---------------------------------------------------------------- 채팅으로 저장 (D-40)
def test_reply_yes_saves_previous_question_and_shows_saved():
    def first(tools):
        tools["search_job_postings"](min_salary=3000)
        return reply("공고를 찾았어요. 이 조건(연봉 3,000만 원 이상)을 저장할까요?")

    def second(tools):
        out = tools["save_search_conditions"]()
        return reply("저장했어요. 다음 검색부터 연봉 3,000만 원 이상으로 찾을게요." if out.get("saved") else "저장할 조건이 없어요.")

    deps = build_deps(ScriptedRunner(first, second))
    started, _, message = ask(deps)
    assert [a["type"] for a in message["actions"]][0] == "SAVE_CONDITIONS"
    deps.clock["now"] = NOW + timedelta(seconds=20)
    again = service.start_turn(deps, "demo1", {"sessionId": started["sessionId"], "message": "응 저장해 줘"})
    service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    saved = service.get_message(deps, "demo1", started["sessionId"], again["messageId"])
    assert deps.profiles.updates == [("demo1", {"desiredSalaryMin": 3000})]
    assert saved["actions"] == [{"type": "CONDITIONS_SAVED", "conditions": ["연봉 3,000만 원 이상"]}]
    assert saved["reply"].startswith("저장했어요")


def test_old_question_is_not_saved_after_another_turn():
    def ask_save(tools):
        tools["search_job_postings"](min_salary=3000)
        return reply("저장할까요?")

    def other(tools):
        return reply("청년정책을 알려 드릴게요.")

    def try_save(tools):
        out = tools["save_search_conditions"]()
        return reply("저장할 조건이 없어요." if "error" in out else "저장했어요.")

    deps = build_deps(ScriptedRunner(ask_save, other, try_save))
    started, _, _ = ask(deps)
    for i, text in enumerate(["정책은?", "저장해 줘"], start=1):
        deps.clock["now"] = NOW + timedelta(seconds=20 * i)
        service.start_turn(deps, "demo1", {"sessionId": started["sessionId"], "message": text})
        service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    assert deps.profiles.updates == []  # 바로 앞 답의 질문만 승낙 대상이다


def test_prompt_v3_rules():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    ask(deps)
    prompt = deps.runner.runs[-1]["system_prompt"]
    for rule in ("공식 데이터에는 조건에 맞는 공고가 없어요", "teamDataNote", "save_search_conditions",
                 "`saved=true`일 때만", "묻지 않았는데 저장하지 않는다", "실시간으로 부르지 않는다"):
        assert rule in prompt
    assert deps.config.prompt_version == "chat-v5"


def test_prompt_v5_rules():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    ask(deps)
    prompt = deps.runner.runs[-1]["system_prompt"]
    for rule in ("recentPostings", "면접을 원하지 않는다고 했으면 다시 권하지 않는다", "이 공고로 모의면접 체험해 볼래요",
                 "여러 기능을 한 번에 이어 실행하지 않는다", "이 서비스에서 하지 않는다"):
        assert rule in prompt
    # 진단·첨삭 화면과 진단 도구를 지웠다 (#155). 지침이 없는 도구나 화면을 가리키지 않는다
    for gone in ("start_resume_diagnosis", "진단 결과 보기", "이 공고와 내 이력서 비교해 보기"):
        assert gone not in prompt


def test_old_diagnosis_action_still_reads():
    """진단 도구를 지우기 전에 저장된 대화의 OPEN_DIAGNOSIS 행동도 읽을 수 있다 (새로 만들지는 않는다)."""
    action = ChatAction.model_validate({"type": "OPEN_DIAGNOSIS", "job": "데이터 분석", "analysisId": "a-1"})
    assert action.type == "OPEN_DIAGNOSIS" and action.analysis_id == "a-1"


def test_missing_claimed_message_releases_session_lock(monkeypatch):
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started = service.start_turn(deps, "demo1", {"message": "안녕"})
    monkeypatch.setattr(deps.store, "get_message", lambda *a, **k: None)  # 읽기가 아직 따라오지 못한 경우
    out = service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    assert out["status"] == "SKIPPED" and deps.runner.runs == []
    assert deps.store.get_session("demo1", started["sessionId"]).pending_message_id is None


# ---------------------------------------------------------------- 채팅 화면: 멈추기, 대화 목록·고정·삭제
def start_only(deps, message="부산 데이터 분석 신입 공고 찾아줘", user="demo1"):
    """턴을 시작만 하고 실행 이벤트는 돌리지 않는다 (답을 만드는 중인 상태)."""
    started = service.start_turn(deps, user, {"message": message})
    return started, deps.dispatcher.events[-1]["agentTask"]


def test_cancel_pending_answer_releases_lock_and_task_skips():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, task = start_only(deps)
    sid, mid = started["sessionId"], started["messageId"]
    assert service.cancel_message(deps, "demo1", sid, mid)["status"] == "CANCELLED"
    deps.clock["now"] += timedelta(seconds=1)  # stale(180초)보다 훨씬 짧다
    # 잠금이 풀려 기다리지 않고 바로 다음 말을 보낼 수 있다
    assert service.start_turn(deps, "demo1", {"sessionId": sid, "message": "다시 찾아줘"})["status"] == "PENDING"
    assert service.run_turn(deps, task)["status"] == "SKIPPED"  # 멈춘 답은 실행하지 않는다
    assert service.get_message(deps, "demo1", sid, mid)["status"] == "CANCELLED"


def test_cancel_while_model_runs_drops_late_result():
    ids = {}

    def script(tools):
        ids["view"] = service.cancel_message(deps, "demo1", ids["sid"], ids["mid"])  # 모델이 도는 중에 멈춘다
        return reply()

    deps = build_deps(ScriptedRunner(script))
    started, task = start_only(deps)
    ids.update(sid=started["sessionId"], mid=started["messageId"])
    assert ids.get("view") is None
    result = service.run_turn(deps, task)
    assert ids["view"]["status"] == "CANCELLED"
    assert result == {"messageId": ids["mid"], "status": "SKIPPED", "reason": "CANCELLED"}
    message = service.get_message(deps, "demo1", ids["sid"], ids["mid"])
    assert message["status"] == "CANCELLED" and message["reply"] == "" and message["cards"] == []
    assert deps.store.get_session("demo1", ids["sid"]).pending_message_id is None


def test_cancel_finished_answer_returns_it_unchanged():
    deps = build_deps(ScriptedRunner(search_and_policies(job_name="데이터 분석", region="부산")))
    started, _, message = ask(deps)
    assert service.cancel_message(deps, "demo1", started["sessionId"], started["messageId"]) == message


def test_cancel_checks_owner_and_role():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, _ = start_only(deps)
    for user, mid in (("demo2", started["messageId"]), ("demo1", started["userMessageId"]), ("demo1", "nope")):
        with pytest.raises(SupervisorError) as error:
            service.cancel_message(deps, user, started["sessionId"], mid)
        assert error.value.status == 404


def test_cancelled_answer_is_not_history_and_previous_cards_stay_recent():
    def script(tools):
        tools["search_job_postings"](job_name="데이터 분석", region="부산")
        return reply("부산 데이터 분석 공고 1개를 찾았어요.")

    runner = ScriptedRunner(script)
    deps = build_deps(runner)
    first, _, _ = ask(deps)
    sid = first["sessionId"]
    deps.clock["now"] += timedelta(seconds=10)  # 메시지 ID가 시각순이라 턴마다 시간을 옮긴다
    second = service.start_turn(deps, "demo1", {"sessionId": sid, "message": "서울도 찾아줘"})
    service.cancel_message(deps, "demo1", sid, second["messageId"])
    deps.clock["now"] += timedelta(seconds=10)
    third = service.start_turn(deps, "demo1", {"sessionId": sid, "message": "이 공고 더 알려줘"})
    service.run_turn(deps, deps.dispatcher.events[-1]["agentTask"])
    assert service.get_message(deps, "demo1", sid, third["messageId"])["status"] == "COMPLETED"
    history = [h["text"] for h in runner.runs[-1]["history"]]
    assert "서울도 찾아줘" not in history and history[0] == "부산 데이터 분석 신입 공고 찾아줘"
    assert "demo-busan-data" in runner.runs[-1]["message"]  # 멈춘 답을 건너뛰고 그 앞 답의 공고를 가리킨다


def test_sessions_list_pinned_first_then_recent():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    first, _, _ = ask(deps, "첫 대화")
    deps.clock["now"] += timedelta(minutes=5)
    second, _, _ = ask(deps, "둘째 대화")
    ask(deps, "남의 대화", user="demo2")
    titles = [s["title"] for s in service.list_sessions(deps, "demo1")["sessions"]]
    assert titles == ["둘째 대화", "첫 대화"]

    assert service.update_session(deps, "demo1", first["sessionId"], {"pinned": True})["pinned"] is True
    listed = service.list_sessions(deps, "demo1")["sessions"]
    assert [s["sessionId"] for s in listed] == [first["sessionId"], second["sessionId"]]
    assert all("messages" not in s and "ownerUserId" not in s for s in listed)
    service.update_session(deps, "demo1", first["sessionId"], {"pinned": False})
    assert [s["title"] for s in service.list_sessions(deps, "demo1")["sessions"]] == ["둘째 대화", "첫 대화"]


@pytest.mark.parametrize("body", [{}, {"pinned": "true"}, {"pinned": 1}, {"pinned": True, "title": "x"}, []])
def test_update_session_accepts_only_pinned_bool(body):
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, _, _ = ask(deps)
    with pytest.raises(SupervisorError) as error:
        service.update_session(deps, "demo1", started["sessionId"], body)
    assert error.value.status == 400


def test_pin_and_delete_check_owner():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, _, _ = ask(deps)
    for call in (lambda: service.update_session(deps, "demo2", started["sessionId"], {"pinned": True}),
                 lambda: service.delete_session(deps, "demo2", started["sessionId"]),
                 lambda: service.delete_session(deps, "demo1", "chat-none")):
        with pytest.raises(SupervisorError) as error:
            call()
        assert error.value.status == 404
    assert service.get_session(deps, "demo1", started["sessionId"])["pinned"] is False


def test_delete_session_removes_messages():
    deps = build_deps(ScriptedRunner(lambda tools: reply()))
    started, _, _ = ask(deps)
    keep, _, _ = ask(deps, "다른 대화")
    sid = started["sessionId"]
    assert service.delete_session(deps, "demo1", sid) == {"sessionId": sid, "deleted": True}
    assert deps.store.list_messages("demo1", sid, 100) == []
    with pytest.raises(SupervisorError):
        service.get_session(deps, "demo1", sid)
    assert [s["sessionId"] for s in service.list_sessions(deps, "demo1")["sessions"]] == [keep["sessionId"]]


def test_delete_while_answer_runs_drops_late_result():
    ids = {}

    def script(tools):
        service.delete_session(deps, "demo1", ids["sid"])  # 답을 만드는 중에 대화를 지운다
        return reply()

    deps = build_deps(ScriptedRunner(script))
    started, task = start_only(deps)
    ids["sid"] = started["sessionId"]
    assert service.run_turn(deps, task)["reason"] == "CANCELLED"
    assert deps.store.list_messages("demo1", ids["sid"], 100) == []  # 지운 대화에 답이 다시 생기지 않는다
