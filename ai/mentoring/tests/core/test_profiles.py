"""역량 프로필 확인 (Requirement 7, UT-03)."""
import pytest

from mentoring.core.documents import create_text_document
from mentoring.core.profiles import confirm_profile, get_latest_profile
from mentoring.errors import MentoringError
from mentoring.models import ConfirmRequest, EvidenceLevel, FactStatus, TextDocumentRequest
from support.data import DATA_ANALYST_RESUME
from support.factory import make_deps, run_pending

USER = "user-a"


@pytest.fixture
def ready():
    deps = make_deps()
    create_text_document(deps, USER, TextDocumentRequest.model_validate({"text": DATA_ANALYST_RESUME}))
    run_pending(deps)
    return deps, get_latest_profile(deps, USER)


def skill_id(profile, name):
    return next(s.skill_id for s in profile.skills if s.name == name)


def confirm(deps, profile, decisions=(), additions=(), base=None):
    request = ConfirmRequest.model_validate({
        "baseVersion": base or profile.profile_version,
        "decisions": list(decisions), "additions": [{"name": n} for n in additions]})
    return confirm_profile(deps, USER, profile.profile_id, request)


def test_confirm_creates_new_version_and_keeps_old(ready):
    deps, v1 = ready
    v2 = confirm(deps, v1, [{"skillId": skill_id(v1, "데이터 전처리"), "action": "CONFIRM"}])
    assert (v2.profile_version, v2.based_on_version, v2.created_by) == (2, 1, "USER_CONFIRMATION")
    assert next(s for s in v2.skills if s.name == "데이터 전처리").fact_status == FactStatus.VERIFIED
    old = deps.users.get_profile_version(USER, v1.profile_id, 1)
    assert all(s.fact_status == FactStatus.NEEDS_CONFIRMATION for s in old.skills)  # v1 보존
    assert get_latest_profile(deps, USER).profile_version == 2


def test_ut03_user_confirmed_gap(ready):
    deps, v1 = ready
    v2 = confirm(deps, v1, [{"skillId": skill_id(v1, "머신러닝"), "action": "NOT_HELD"}])
    ml = next(s for s in v2.skills if s.name == "머신러닝")
    assert ml.evidence_level == EvidenceLevel.USER_CONFIRMED_GAP and ml.evidence_ids == []


def test_addition_without_evidence_is_self_reported(ready):
    deps, v1 = ready
    v2 = confirm(deps, v1, additions=["통계 분석"])
    added = next(s for s in v2.skills if s.name == "통계 분석")
    assert added.evidence_level == EvidenceLevel.SELF_REPORTED and added.evidence_ids == []
    assert added.fact_status == FactStatus.VERIFIED
    assert "통계 분석" not in v2.needs_confirmation
    assert len(v2.evidence) == len(v1.evidence)  # 인용을 새로 만들지 않는다


def test_delete_and_rename(ready):
    deps, v1 = ready
    v2 = confirm(deps, v1, [{"skillId": skill_id(v1, "SQL"), "action": "DELETE"},
                            {"skillId": skill_id(v1, "데이터 시각화"), "action": "RENAME", "name": "Tableau 시각화"}])
    names = [s.name for s in v2.skills]
    assert "SQL" not in names and "Tableau 시각화" in names


def test_stale_base_version_is_409(ready):
    deps, v1 = ready
    confirm(deps, v1, [{"skillId": skill_id(v1, "SQL"), "action": "CONFIRM"}])
    with pytest.raises(MentoringError) as error:
        confirm(deps, v1, [{"skillId": skill_id(v1, "SQL"), "action": "CONFIRM"}], base=1)
    assert error.value.status == 409 and error.value.code == "PRECONDITION_NOT_MET"
    assert get_latest_profile(deps, USER).profile_version == 2


def test_unknown_or_duplicate_skill_decision_is_400(ready):
    deps, v1 = ready
    with pytest.raises(MentoringError) as error:
        confirm(deps, v1, [{"skillId": "skill-999", "action": "CONFIRM"}])
    assert error.value.code == "INVALID_INPUT"
    sid = skill_id(v1, "SQL")
    with pytest.raises(MentoringError):
        confirm(deps, v1, [{"skillId": sid, "action": "CONFIRM"}, {"skillId": sid, "action": "DELETE"}])


def test_other_users_profile_is_not_found(ready):
    deps, v1 = ready
    request = ConfirmRequest.model_validate({"baseVersion": 1, "decisions": []})
    with pytest.raises(MentoringError) as error:
        confirm_profile(deps, "user-b", v1.profile_id, request)
    assert error.value.status == 404


def test_confirm_project_correct_experience_and_remove_certificate(ready):
    deps, v1 = ready
    project, experience, certificate = v1.projects[0], v1.experiences[0], v1.certificates[0]
    request = ConfirmRequest.model_validate({"baseVersion": v1.profile_version, "entryDecisions": [
        {"group": "PROJECT", "itemId": project.item_id, "action": "CONFIRM"},
        {"group": "EXPERIENCE", "itemId": experience.item_id, "action": "RENAME", "name": "SQL 스터디 운영"},
        {"group": "CERTIFICATE", "itemId": certificate.item_id, "action": "DELETE"},
    ]})
    v2 = confirm_profile(deps, USER, v1.profile_id, request)
    assert v2.projects[0].fact_status == FactStatus.VERIFIED
    assert v2.experiences[0].name == "SQL 스터디 운영"
    assert v2.experiences[0].fact_status == FactStatus.VERIFIED
    assert v2.certificates == []
    assert not any(e.evidence_id in certificate.evidence_ids for e in v2.evidence)
    assert v1.certificates[0].name == "ADsP"  # 기존 버전 보존


def test_entry_confirmation_rejects_duplicate_and_stale_version(ready):
    deps, v1 = ready
    entry = {"group": "PROJECT", "itemId": v1.projects[0].item_id, "action": "CONFIRM"}
    with pytest.raises(MentoringError) as duplicate:
        confirm_profile(deps, USER, v1.profile_id, ConfirmRequest.model_validate({
            "baseVersion": 1, "entryDecisions": [entry, entry]}))
    assert duplicate.value.code == "INVALID_INPUT"
    confirm_profile(deps, USER, v1.profile_id, ConfirmRequest.model_validate({
        "baseVersion": 1, "entryDecisions": [entry]}))
    with pytest.raises(MentoringError) as stale:
        confirm_profile(deps, USER, v1.profile_id, ConfirmRequest.model_validate({
            "baseVersion": 1, "entryDecisions": [entry]}))
    assert stale.value.status == 409


def test_new_extraction_continues_the_same_profile(ready):
    deps, v1 = ready
    create_text_document(deps, USER, TextDocumentRequest.model_validate({"text": DATA_ANALYST_RESUME + "\n추가"}))
    run_pending(deps)
    latest = get_latest_profile(deps, USER)
    assert latest.profile_id == v1.profile_id and latest.profile_version == 2
