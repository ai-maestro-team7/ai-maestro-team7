"""면접용 역량 요약 (Requirement 8, 계약 CareerProfileSummary)."""
from team07_contracts import CAREER_SUMMARY_LIMITS, validate

from mentoring.core.documents import create_text_document
from mentoring.core.profiles import confirm_profile, get_latest_profile
from mentoring.core.summary import to_career_profile_summary
from mentoring.models import ConfirmRequest, FactStatus, TextDocumentRequest
from support.data import DATA_ANALYST_RESUME, QUOTE_PANDAS
from support.factory import make_deps, run_pending

USER = "user-a"


def profile_after(decisions=()):
    deps = make_deps()
    create_text_document(deps, USER, TextDocumentRequest.model_validate({"text": DATA_ANALYST_RESUME}))
    run_pending(deps)
    profile = get_latest_profile(deps, USER)
    if decisions:
        ids = {s.name: s.skill_id for s in profile.skills}
        request = ConfirmRequest.model_validate({"baseVersion": profile.profile_version, "decisions": [
            {"skillId": ids[name], "action": action} for name, action in decisions]})
        profile = confirm_profile(deps, USER, profile.profile_id, request)
    return profile


def test_summary_passes_contract_and_has_only_verified_skills():
    profile = profile_after([("데이터 전처리", "CONFIRM"), ("머신러닝", "NOT_HELD")])
    summary = to_career_profile_summary(profile)
    validate("CareerProfileSummary", summary, schema_version="1.0")
    assert summary["skills"] == ["데이터 전처리"]  # 미보유로 확인한 머신러닝은 빠진다
    assert "데이터 시각화" in summary["needsConfirmation"] and "통계 분석" in summary["needsConfirmation"]
    assert summary["profileId"] == profile.profile_id and summary["profileVersion"] == 2


def test_summary_before_confirmation_has_no_skills():
    summary = to_career_profile_summary(profile_after())
    assert summary["skills"] == []


def test_summary_has_no_raw_text_or_quotes():
    summary = to_career_profile_summary(profile_after([("데이터 전처리", "CONFIRM")]))
    text = str(summary)
    assert QUOTE_PANDAS not in text and "010-0000" not in text and "example.com" not in text
    assert set(summary) == {"projects", "skills", "needsConfirmation", "profileId", "profileVersion"}


def test_summary_accepts_stored_dynamo_item_shape():
    profile = profile_after([("SQL", "CONFIRM")])
    summary = to_career_profile_summary(profile.to_api())
    assert summary["skills"] == ["SQL"]


def test_summary_respects_limits():
    profile = profile_after()
    base = profile.skills[0]
    many = [base.model_copy(update={"skill_id": f"skill-{i}", "name": f"역량{i}", "fact_status": FactStatus.VERIFIED})
            for i in range(60)]
    long = profile.projects[0].model_copy(update={"summary": "가" * 300})
    profile = profile.model_copy(update={"skills": many, "projects": [long]})
    summary = to_career_profile_summary(profile)
    max_skills, _ = CAREER_SUMMARY_LIMITS["skills"]
    assert len(summary["skills"]) == max_skills
    assert summary["projects"][0] == "부산 버스 이용 데이터 분석 프로젝트"  # 너무 긴 요약은 이름만


def test_invalid_input_returns_none():
    assert to_career_profile_summary({"profileId": "x"}) is None
