"""보강 배치 전체."""

from unit.enrich import factories as f

from opportunity.enrich.pipeline import enrich_postings
from opportunity.models.enums import (
    BadgeType,
    ExtractedBy,
    ExtractStatus,
    OrgType,
    RegionalTalentStatus,
    RemoteWork,
)
from opportunity.seeds import demo_world as w
from opportunity.store.memory import ScriptedLlm


def test_pipeline_enriches_and_rewrites_latest(deps, as_of):
    f.store(deps, f.snapshot(org="(주)가상데이터"))
    deps.llm = ScriptedLlm([f.extract_reply()])
    summary = enrich_postings(deps, ["wk24-TEST0001"], as_of=as_of)
    assert summary["enriched"] == 1 and summary["failed"] == 0
    snap = f.stored(deps, "wk24-TEST0001")
    latest = deps.catalog.get_latest("wk24-TEST0001")
    assert snap.extract_status == ExtractStatus.DONE == latest.extract_status
    assert latest.required_names == ["SQL"] and latest.preferred_names == ["ADsP"]
    assert latest.eligibility_rules == snap.eligibility_rules
    assert {b.type for b in latest.badges} == {BadgeType.CHEONGKKEUL, BadgeType.REMOTE_WORK}
    assert snap.company_id == "biz-DEMO000001"
    assert latest.regional_talent.status == RegionalTalentStatus.NOT_APPLICABLE
    assert deps.vectors.get("wk24-TEST0001") is not None
    # 부산 공고가 바뀌었으니 진행 중인 수도권 공고의 대안 후보를 다시 계산한다
    assert summary["alts"] >= 1
    assert "wk24-TEST0001" in [c.job_posting_id for c in deps.catalog.get_alts(w.SEOUL_DATA).candidates]


def test_pipeline_keeps_api_values(deps, as_of):
    snap = f.snapshot(remote=RemoteWork.NONE, extracted_by={"closesAt": ExtractedBy.API, "salary": ExtractedBy.API,
                                                           "workRegion": ExtractedBy.API,
                                                           "remoteWork": ExtractedBy.API})
    f.store(deps, snap)
    deps.llm = ScriptedLlm([f.extract_reply()])
    enrich_postings(deps, [snap.job_posting_id], as_of=as_of)
    out = f.stored(deps, snap.job_posting_id)
    assert (out.closes_at, out.work_region, out.salary, out.remote_work) == \
        (snap.closes_at, snap.work_region, snap.salary, RemoteWork.NONE)
    assert all(b.type != BadgeType.REMOTE_WORK for b in out.badges)


def test_pipeline_marks_failed_after_two_bad_replies(deps, as_of):
    f.store(deps, f.snapshot())
    deps.llm = ScriptedLlm(["{}garbage", "[]"])
    summary = enrich_postings(deps, ["wk24-TEST0001"], as_of=as_of)
    assert summary["failed"] == 1 and summary["enriched"] == 1
    assert deps.catalog.get_latest("wk24-TEST0001").extract_status == ExtractStatus.FAILED
    assert deps.vectors.get("wk24-TEST0001") is not None  # 추출에 실패해도 나머지는 한다


def test_pipeline_without_llm_skips_extraction(deps, as_of):
    f.store(deps, f.snapshot(org="가상금융공사", org_type=OrgType.PUBLIC_INSTITUTION,
                             description="지역인재 채용목표제를 적용한다."))
    deps.llm = None
    summary = enrich_postings(deps, ["wk24-TEST0001", "missing"], as_of=as_of)
    assert summary == {"enriched": 1, "failed": 0, "alts": summary["alts"]}
    snap = f.stored(deps, "wk24-TEST0001")
    assert snap.extract_status == ExtractStatus.PENDING and snap.requirements == []
    assert snap.regional_talent.status == RegionalTalentStatus.LIKELY
    assert snap.regional_talent.basis == "지역인재 채용목표제를 적용한다."
    assert [b.type for b in snap.badges] == [BadgeType.RELOCATED_INSTITUTION]


def test_pipeline_skips_done_extraction(deps, as_of):
    deps.llm = ScriptedLlm([f.extract_reply()])
    enrich_postings(deps, [w.BUSAN_DATA], as_of=as_of)
    assert deps.llm.calls == []  # 이미 DONE인 스냅샷은 다시 뽑지 않는다
    assert f.stored(deps, w.BUSAN_DATA).requirements[0].name == "SQL"


def test_pipeline_drops_unsourced_badge_and_keeps_expired(deps, as_of):
    enrich_postings(deps, [w.BUSAN_BADGE_NO_SOURCE, w.BUSAN_DATA_EXPIRED, w.BUSAN_DATA_JUST_CLOSED], as_of=as_of)
    assert deps.catalog.get_latest(w.BUSAN_BADGE_NO_SOURCE).badges == []
    assert deps.catalog.get_latest(w.BUSAN_DATA_EXPIRED).is_expired
    assert deps.catalog.get_latest(w.BUSAN_DATA_JUST_CLOSED).is_expired  # as_of로 다시 보면 마감이다
    assert deps.vectors.rows[w.BUSAN_DATA_JUST_CLOSED][1]["active"] is False
    assert deps.catalog.get_latest(w.BUSAN_DATA_EXPIRED).is_sample


def test_pipeline_is_idempotent(deps, as_of):
    f.store(deps, f.snapshot())
    deps.llm = ScriptedLlm([f.extract_reply()])
    enrich_postings(deps, ["wk24-TEST0001"], as_of=as_of)
    first = f.stored(deps, "wk24-TEST0001")
    enrich_postings(deps, ["wk24-TEST0001", "wk24-TEST0001"], as_of=as_of)
    assert f.stored(deps, "wk24-TEST0001") == first and len(deps.llm.calls) == 1
