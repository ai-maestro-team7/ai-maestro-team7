"""pipeline.py: 스냅샷 적재(T-17), 마감 처리, 정책 보강."""

from pathlib import Path

from opportunity.ingest.http import as_list, parse_body, walk
from opportunity.ingest.normalize import normalize_work24, normalize_youthcenter
from opportunity.ingest.pipeline import expire_postings, upsert_policies, upsert_postings
from opportunity.models import (
    Badge,
    BadgeType,
    ExtractStatus,
    Policy,
    PolicyBenefit,
    PolicyRegion,
    PolicySource,
    PolicyStage,
    RegionalTalent,
    RegionalTalentStatus,
    RegionScope,
    Requirement,
    RequirementKind,
)

FIXTURES = Path(__file__).parent / "fixtures"
DAY1, DAY2 = "2026-11-21T04:30:00+09:00", "2026-11-22T04:30:00+09:00"


def records():
    out = []
    for name in ("work24_list_p1.xml", "work24_list_p2.xml"):
        out += as_list(walk(parse_body((FIXTURES / name).read_bytes()), "wantedRoot.wanted"))
    return out


def snapshots(as_of, **override):
    return [normalize_work24({**r, **(override if r["wantedAuthNo"] == "K000000001" else {})}, as_of=as_of)
            for r in records()]


def test_t17_same_day_twice_changes_nothing(config, catalog):
    first = upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    assert (first["created"], first["updated"], first["unchanged"]) == (3, 0, 0)
    assert len(first["needsEnrich"]) == 3
    before = (len(catalog.snapshots), len(catalog.latest), dict(catalog.snapshots), dict(catalog.latest))

    second = upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    assert (second["created"], second["updated"], second["unchanged"]) == (0, 0, 3)
    assert second["needsEnrich"] == []
    assert (len(catalog.snapshots), len(catalog.latest), dict(catalog.snapshots), dict(catalog.latest)) == before


def test_next_day_with_same_content_makes_no_new_snapshot_but_refreshes_checked_at(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    result = upsert_postings(config, catalog, snapshots(DAY2), as_of=DAY2)
    assert result["unchanged"] == 3 and result["needsEnrich"] == []
    assert len(catalog.snapshots) == 3
    latest = catalog.get_latest("wk24-K000000001")
    assert latest.checked_at == "2026-11-22T04:30:00+09:00" and latest.snapshot_id.startswith("20261121-")


def test_changed_content_makes_new_snapshot_and_needs_enrich(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    old_id = catalog.get_latest("wk24-K000000001").snapshot_id

    result = upsert_postings(config, catalog, snapshots(DAY2, closeDt="2026-12-30"), as_of=DAY2)
    assert (result["created"], result["updated"], result["unchanged"]) == (0, 1, 2)
    assert result["needsEnrich"] == ["wk24-K000000001"]
    latest = catalog.get_latest("wk24-K000000001")
    assert latest.snapshot_id != old_id and latest.snapshot_id.startswith("20261122-")
    assert latest.closes_at == "2026-12-30"
    assert catalog.get_snapshot("wk24-K000000001", old_id).closes_at == "2026-12-15"  # 이전 스냅샷은 남는다
    assert len(catalog.snapshots) == 4


def test_unchanged_posting_keeps_enriched_values(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    snap = catalog.get_snapshot("wk24-K000000001", catalog.get_latest("wk24-K000000001").snapshot_id)
    enriched = snap.model_copy(update={
        "requirements": [Requirement(requirement_id="r1", name="SQL", kind=RequirementKind.REQUIRED_SKILL)],
        "badges": [Badge(type=BadgeType.GANGSO, label="강소", source="고용24", as_of="2026-11-20")],
        "regional_talent": RegionalTalent(status=RegionalTalentStatus.LIKELY),
        "extract_status": ExtractStatus.DONE})
    catalog.put_snapshot(enriched)

    result = upsert_postings(config, catalog, snapshots(DAY2), as_of=DAY2)
    assert result["needsEnrich"] == []
    kept = catalog.get_snapshot("wk24-K000000001", enriched.snapshot_id)
    assert kept == enriched  # 지우거나 다시 쓰지 않았다


def test_changed_posting_inherits_company_badges_but_not_requirements(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    snap = catalog.get_snapshot("wk24-K000000001", catalog.get_latest("wk24-K000000001").snapshot_id)
    badge = Badge(type=BadgeType.GANGSO, label="강소", source="고용24", as_of="2026-11-20")
    catalog.put_snapshot(snap.model_copy(update={
        "badges": [badge], "company_id": "biz-1", "extract_status": ExtractStatus.DONE,
        "requirements": [Requirement(requirement_id="r1", name="SQL", kind=RequirementKind.REQUIRED_SKILL)]}))

    upsert_postings(config, catalog, snapshots(DAY2, title="데이터 분석 신입 (수정)"), as_of=DAY2)
    latest = catalog.get_latest("wk24-K000000001")
    new = catalog.get_snapshot("wk24-K000000001", latest.snapshot_id)
    assert new.badges == [badge] and new.company_id == "biz-1"
    assert new.requirements == [] and new.extract_status == ExtractStatus.PENDING
    assert latest.badges == [badge] and latest.required_names == []


def test_latest_flags_busan_and_unknown(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    assert catalog.get_latest("wk24-K000000001").is_busan is True
    assert catalog.get_latest("wk24-K000000002").is_capital_area is True
    unknown = catalog.get_latest("wk24-K000000003")
    assert unknown.is_busan is False and unknown.work_region.unknown is True


def test_posting_already_past_deadline_is_marked_expired_on_arrival(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1, closeDt="2026-11-20"), as_of=DAY1)
    assert catalog.get_latest("wk24-K000000001").is_expired is True


def test_expire_marks_closed_postings_and_keeps_snapshots(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)  # K1 12-15, K3 12-01, K2 상시
    snapshot_ids = {key: snap for key, snap in catalog.snapshots.items()}

    assert expire_postings(config, catalog, as_of="2026-11-30T09:00:00+09:00") == 0
    assert expire_postings(config, catalog, as_of="2026-12-02T09:00:00+09:00",
                           job_posting_ids=["wk24-K000000003"]) == 1  # 근무지 미상은 ID로 넘겨야 닿는다
    assert catalog.get_latest("wk24-K000000003").is_expired is True
    assert expire_postings(config, catalog, as_of="2026-12-16T09:00:00+09:00") == 1
    assert catalog.get_latest("wk24-K000000001").is_expired is True
    assert catalog.get_latest("wk24-K000000002").is_expired is False  # 상시 채용은 마감하지 않는다
    assert catalog.snapshots == snapshot_ids  # 스냅샷은 그대로
    assert expire_postings(config, catalog, as_of="2026-12-16T09:00:00+09:00") == 0  # 두 번 돌려도 같다


# ---------------------------------------------------------------- 정책
def youth(as_of=DAY1):
    parsed = parse_body((FIXTURES / "youthcenter_list_p1.json").read_bytes())
    return [normalize_youthcenter(r, as_of=as_of) for r in walk(parsed, "result.youthPolicyList")[:3]]


def test_policies_are_created_once(catalog):
    first = upsert_policies(catalog, youth())
    assert first == {"created": 3, "enriched": 0, "updated": 0, "unchanged": 0}
    again = upsert_policies(catalog, youth())
    assert again == {"created": 0, "enriched": 0, "updated": 0, "unchanged": 3}
    assert len(catalog.policies) == 3
    assert {p.policy_id for p in catalog.query_policies("00")} == {"ythc-20260100000001"}
    assert {p.policy_id for p in catalog.query_policies("26")} == {"ythc-20260100000002"}


def test_policy_same_content_next_day_refreshes_as_of_only(catalog):
    upsert_policies(catalog, youth(DAY1))
    result = upsert_policies(catalog, youth(DAY2))
    assert result["unchanged"] == 3 and result["updated"] == 0
    assert catalog.get_policy("ythc-20260100000001").as_of == "2026-11-22"


def test_policy_content_change_updates(catalog):
    upsert_policies(catalog, youth())
    changed = [p.model_copy(update={"title": "[가상] 이름이 바뀐 정책"}) for p in youth()[:1]]
    assert upsert_policies(catalog, changed)["updated"] == 1


def seed_policy(**override):
    base = dict(policy_id="seed-busan-housing", title="부산 주거 시드", source=PolicySource.BUSAN_SEED,
                as_of="2026-11-20", regions=[PolicyRegion(scope=RegionScope.SIDO, sido="26")],
                stage=PolicyStage.SETTLE, verified=False, youthcenter_id="20260100000002",
                benefit=PolicyBenefit(text="시드에 적은 혜택"))
    return Policy(**{**base, **override})


def test_policy_seed_is_enriched_not_duplicated(catalog):
    seed = seed_policy()
    catalog.put_policy(seed)
    result = upsert_policies(catalog, youth())
    assert result["enriched"] == 1 and result["created"] == 2
    assert "ythc-20260100000002" not in catalog.policies  # 새로 만들지 않는다
    merged = catalog.get_policy("seed-busan-housing")
    assert merged.title == "부산 주거 시드" and merged.benefit.text == "시드에 적은 혜택"  # 시드 값은 그대로
    assert merged.summary == "주거비를 돕는 가상 정책" and merged.url == "https://example.invalid/policy/2"
    assert merged.income_rule == "연소득 중위소득 150% 이하"
    assert merged.verified is False and merged.source == PolicySource.BUSAN_SEED  # 확인 상태는 건드리지 않는다
    assert merged.eligibility.manual_checks == ["부산 거주 6개월 이상"]

    again = upsert_policies(catalog, youth())
    assert again["enriched"] == 0 and again["unchanged"] == 3


def test_policy_seed_matches_prefixed_youthcenter_id(catalog):
    catalog.put_policy(seed_policy(youthcenter_id="ythc-20260100000002"))
    assert upsert_policies(catalog, youth())["enriched"] == 1
