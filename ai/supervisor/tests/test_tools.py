"""도구 (개발계획서4 §4). S-04 사용자 ID, S-07 호출 상한, 저장 조건 기본값, 오류 변환."""

import inspect

from fakes import FakeError, build_deps, cover_letter, reply
from supervisor.tools import TurnTools


def tools_for(deps, user="demo1", attachments=None):
    turn = TurnTools(deps, user, attachments=attachments)
    return turn, {f.__name__: f for f in turn.functions()}


def test_s04_tools_have_no_user_id_parameter():
    deps = build_deps(None)
    _, tools = tools_for(deps)
    assert set(tools) == {"get_my_status", "search_job_postings", "find_youth_policies", "ask_youth_policy",
                          "save_search_conditions", "prepare_mock_interview"}
    for fn in tools.values():
        params = inspect.signature(fn).parameters
        assert not any("user" in p.lower() for p in params), fn.__name__
        assert fn.__doc__ and fn.__doc__.strip()


def test_s04_ports_get_backend_user_only():
    deps = build_deps(None)
    _, tools = tools_for(deps, user="demo2")
    tools["search_job_postings"](job_name="데이터 분석")
    tools["find_youth_policies"]()
    assert {call[1] for call in deps.opportunities.calls} == {"demo2"}
    tools["save_search_conditions"]()
    assert {u for u, _ in deps.profiles.updates} == {"demo2"}


def test_search_uses_saved_conditions_when_not_given():
    deps = build_deps(None, profiles={"demo1": {"desiredJobs": [{"name": "데이터 분석"}], "desiredRegion": "26",
                                                "desiredSalaryMin": 2800, "desiredCareerType": "NEW"}})
    turn, tools = tools_for(deps)
    out = tools["search_job_postings"]()
    kwargs = deps.opportunities.calls[-1][2]
    assert kwargs["job_name"] is None and kwargs["region"] == "26"
    assert kwargs["min_salary"] == 2800 and kwargs["career_type"] == "NEW" and kwargs["query_terms"] is None
    assert "연봉 2,800만 원 이상" in out["appliedConditions"] and "신입" in out["appliedConditions"]
    assert turn.record.search.chat_conditions == {}  # 모델이 넘긴 조건이 없으면 저장 묻기도 없다
    assert turn.record.search.job_name == "데이터 분석"


def test_search_chat_conditions_override_and_are_recorded():
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    out = tools["search_job_postings"](job_name="  데이터  분석 ", region="서울", min_salary=3000, career_type="new",
                                       organization="가상")
    kwargs = next(c[2] for c in deps.opportunities.calls if c[0] == "search")
    assert kwargs == {"job_name": "데이터 분석", "keyword": None, "organization": "가상", "region": "서울",
                      "min_salary": 3000, "career_type": "NEW", "query_terms": None, "scope": "OFFICIAL"}
    assert turn.record.search.chat_conditions == {"jobName": "데이터 분석", "region": "서울", "minSalary": 3000,
                                                  "careerType": "NEW"}
    assert out["items"][0]["jobPostingId"] == "demo-busan-data"
    assert "연봉 3,000만 원 이상" in out["appliedConditions"]


def test_search_with_resume_passes_terms():
    deps = build_deps(None, terms=["SQL", "Python"])
    _, tools = tools_for(deps)
    out = tools["search_job_postings"](use_resume=True)
    assert deps.opportunities.calls[-1][2]["query_terms"] == ["SQL", "Python"]
    assert "이력서 역량 함께 사용" in out["appliedConditions"]


def test_bad_tool_input_is_error_fact_not_exception():
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    assert tools["search_job_postings"](min_salary=-1)["error"]["code"] == "INVALID_INPUT"
    assert tools["search_job_postings"](career_type="INTERN")["error"]["code"] == "INVALID_INPUT"
    assert tools["prepare_mock_interview"](job="")["error"]["code"] == "INVALID_INPUT"
    assert tools["ask_youth_policy"](question=" ")["error"]["code"] == "INVALID_INPUT"
    assert deps.opportunities.calls == []
    assert [c.ok for c in turn.record.calls] == [False, False, False, False]


def test_port_error_keeps_user_message_and_hides_unknown_errors():
    deps = build_deps(None)
    deps.opportunities.search_error = FakeError("PROFILE_INCOMPLETE", "프로필에 필요한 정보가 없어 추천할 수 없어요.")
    _, tools = tools_for(deps)
    assert tools["search_job_postings"]() == {"error": {"code": "PROFILE_INCOMPLETE",
                                                        "message": "프로필에 필요한 정보가 없어 추천할 수 없어요."}}
    deps.opportunities.search_error = KeyError("secret-table-name")
    out = tools["search_job_postings"]()
    assert out["error"]["code"] == "TOOL_FAILED" and "secret" not in str(out)


def test_s07_tool_call_limit():
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    for _ in range(deps.config.max_tool_calls):
        tools["find_youth_policies"]()
    assert tools["find_youth_policies"]()["error"]["code"] == "TOOL_LIMIT"
    assert len(deps.opportunities.calls) == deps.config.max_tool_calls


def test_policies_are_capped():
    deps = build_deps(None)
    _, tools = tools_for(deps)
    assert len(tools["find_youth_policies"](stage="prepare")["items"]) == deps.config.max_policies
    assert deps.opportunities.calls[-1][2] == {"stage": "PREPARE"}


def test_prepare_interview_with_and_without_cover_letter():
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    out = tools["prepare_mock_interview"](job="데이터 분석")
    assert out["ready"] is False and out["needsCoverLetter"] is True and turn.record.interview.cover_letter is None
    deps = build_deps(None, documents=[cover_letter(), cover_letter("doc-old", has_text=False)])
    turn, tools = tools_for(deps)
    out = tools["prepare_mock_interview"](job="데이터 분석")
    assert out["ready"] is True and turn.record.interview.cover_letter.document_id == "doc-cl"
    assert "doc-cl" not in str(out)  # 문서 ID는 모델에 주지 않는다 (행동 카드에만)


def test_status_reports_documents_and_resume_terms():
    deps = build_deps(None, documents=[cover_letter()], terms=["SQL"])
    _, tools = tools_for(deps, attachments=["doc-cl"])
    out = tools["get_my_status"]()
    assert out["savedConditions"]["desiredJobs"] == ["데이터 분석"] and out["hasCoverLetter"] is True
    assert out["resumeSkills"] == ["SQL"] and out["attachedThisMessage"] == ["COVER_LETTER"]


def test_reply_helper_is_valid():
    assert reply().reply


# ---------------------------------------------------------------- 데이터 순서 (개발계획서4 §9.1)
def test_official_first_and_no_team_lookup_when_found():
    deps = build_deps(None)
    _, tools = tools_for(deps)
    out = tools["search_job_postings"](job_name="데이터 분석")
    assert out["officialFound"] is True and out["dataSource"].startswith("공식 데이터")
    assert [c[2]["scope"] for c in deps.opportunities.calls] == ["OFFICIAL"]
    assert "officialNote" not in out


def test_team_data_when_official_is_empty_is_labelled():
    deps = build_deps(None)
    deps.opportunities.feeds["OFFICIAL"] = {**deps.opportunities.feeds["OFFICIAL"], "items": []}
    turn, tools = tools_for(deps)
    out = tools["search_job_postings"](job_name="데이터 분석")
    assert [c[2]["scope"] for c in deps.opportunities.calls] == ["OFFICIAL", "TEAM"]
    assert out["officialFound"] is False and "공식 데이터" in out["officialNote"]
    assert out["dataSource"] == deps.config.team_data.label and deps.config.team_data.label in out["teamDataNote"]
    assert out["items"][0]["jobPostingId"] == "demo-team-1"
    assert turn.record.search.feed["items"][0]["isSample"] is True  # 카드에도 팀 데이터 표시가 남는다


def test_team_fallback_can_be_turned_off():
    deps = build_deps(None)
    deps.config = deps.config.model_copy(update={"team_data": deps.config.team_data.model_copy(update={"fallback": False})})
    deps.opportunities.feeds["OFFICIAL"] = {**deps.opportunities.feeds["OFFICIAL"], "items": []}
    _, tools = tools_for(deps)
    out = tools["search_job_postings"]()
    assert out["items"] == [] and out["officialFound"] is False and "teamDataNote" not in out


def test_company_name_looks_up_company_data():
    deps = build_deps(None)
    _, tools = tools_for(deps)
    found = tools["search_job_postings"](organization="가상데이터")
    assert found["companies"] == [{"name": "(주)가상데이터", "industry": "데이터 분석업", "source": "부산광역시 (데모)",
                                   "asOf": "2026-06-30"}]
    missing = tools["search_job_postings"](organization="없는회사")
    assert missing["companies"] == [] and "없는회사" in missing["companiesNote"]


# ---------------------------------------------------------------- 채팅으로 저장 (D-40)
def test_save_uses_this_turn_search_conditions():
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    tools["search_job_postings"](min_salary=3000, career_type="NEW")
    out = tools["save_search_conditions"]()
    assert out["saved"] is True and out["conditions"] == ["연봉 3,000만 원 이상", "신입"]
    assert deps.profiles.updates == [("demo1", {"desiredSalaryMin": 3000, "desiredCareerType": "NEW"})]
    assert turn.record.saved_conditions == ["연봉 3,000만 원 이상", "신입"]


def test_save_uses_previous_question_and_only_allowed_fields():
    deps = build_deps(None)
    pending = {"conditions": ["연봉 3,000만 원 이상"], "profilePatch": {"desiredSalaryMin": 3000, "birthYear": 1990}}
    turn = TurnTools(deps, "demo1", pending_save=pending)
    out = {f.__name__: f for f in turn.functions()}["save_search_conditions"]()
    assert out["saved"] is True and deps.profiles.updates == [("demo1", {"desiredSalaryMin": 3000})]


def test_save_without_candidate_is_error_and_writes_nothing():
    deps = build_deps(None)
    _, tools = tools_for(deps)
    assert tools["save_search_conditions"]()["error"]["code"] == "NOTHING_TO_SAVE"
    tools["search_job_postings"](job_name="데이터 분석", region="26")  # 저장된 조건과 같다
    assert tools["save_search_conditions"]()["error"]["code"] == "NOTHING_TO_SAVE"
    assert deps.profiles.updates == []


def _feed(*ids):
    return {"items": [{"jobPostingId": i, "title": i} for i in ids], "rankingBasis": "추천순"}


def test_compare_two_regions_keeps_both_cards_and_does_not_offer_region():
    """"부산이랑 서울 비교해 줘"처럼 한 턴에 지역을 바꿔 두 번 찾으면 공고는 둘 다 남기고, 지역은 저장 묻기에서 뺀다.
    전에는 마지막 검색(서울)만 남아 카드가 서울 공고뿐이고 "지역 서울"을 저장하자고 물었다 (QA 2026-11-21 #3)."""
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    deps.opportunities.feeds["OFFICIAL"] = _feed("busan-1", "both")
    tools["search_job_postings"](job_name="데이터 분석", region="부산", career_type="NEW")
    deps.opportunities.feeds["OFFICIAL"] = _feed("both", "seoul-1")
    tools["search_job_postings"](job_name="데이터 분석", region="서울", career_type="NEW")
    record = turn.record.search
    assert [i["jobPostingId"] for i in record.feed["items"]] == ["busan-1", "both", "seoul-1"]
    assert record.chat_conditions == {"jobName": "데이터 분석", "careerType": "NEW"}


def test_same_region_twice_or_region_then_none_keeps_region():
    deps = build_deps(None)
    turn, tools = tools_for(deps)
    tools["search_job_postings"](job_name="데이터 분석", region="부산")
    tools["search_job_postings"](job_name="데이터 분석", region=" 부산 ")
    assert turn.record.search.chat_conditions["region"] == "부산"
    tools["search_job_postings"](job_name="데이터 분석")
    assert turn.record.search.chat_conditions["region"] == "부산"
