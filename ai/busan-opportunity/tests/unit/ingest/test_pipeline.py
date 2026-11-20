"""pipeline.py: 스냅샷 적재(T-17), 마감 처리, 정책 보강."""

from pathlib import Path

from opportunity.ingest.http import as_list, parse_body, walk
from opportunity.ingest.normalize import (
    compute_content_hash,
    normalize_gangso,
    normalize_work24,
    normalize_youthcenter,
    snapshot_id_for,
)
from opportunity.ingest.pipeline import expire_postings, upsert_companies, upsert_policies, upsert_postings
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
    # 요건·배지·추출 상태는 그대로다. 지역 조건만 지금 규칙으로 공고문을 다시 읽는다 (이 공고문에는 지역 조건이 없다)
    assert kept.model_copy(update={"regional_talent": enriched.regional_talent}) == enriched
    assert kept.regional_talent.status == RegionalTalentStatus.NOT_APPLICABLE


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
BUSAN_HOUSING = "20260513005400213198"  # 부산 청년 중개보수 및 이사비 지원 (부산 전체)
NATIONAL = "ythc-20261021005400214232"


def youth(as_of=DAY1):
    parsed = parse_body((FIXTURES / "youthcenter_list_p1.json").read_bytes())
    return [normalize_youthcenter(r, as_of=as_of, first_sido="26") for r in walk(parsed, "result.youthPolicyList")]


def test_policies_are_created_once(catalog):
    first = upsert_policies(catalog, youth())
    assert first == {"created": 8, "enriched": 0, "updated": 0, "unchanged": 0}
    again = upsert_policies(catalog, youth())
    assert again == {"created": 0, "enriched": 0, "updated": 0, "unchanged": 8}
    assert len(catalog.policies) == 8
    assert {p.policy_id for p in catalog.query_policies("00")} == {NATIONAL}
    assert {p.policy_id for p in catalog.query_policies("26")} == {
        "ythc-20261030005400214630", f"ythc-{BUSAN_HOUSING}", "ythc-20260923005400113568",
        "ythc-20260914005400213409", "ythc-20260513005400213204"}
    assert {p.policy_id for p in catalog.query_policies("11")} == {"ythc-20261023005400214282"}


def test_policy_same_content_next_day_refreshes_as_of_only(catalog):
    upsert_policies(catalog, youth(DAY1))
    result = upsert_policies(catalog, youth(DAY2))
    assert result["unchanged"] == 8 and result["updated"] == 0
    assert catalog.get_policy(NATIONAL).as_of == "2026-11-22"


def test_policy_content_change_updates(catalog):
    upsert_policies(catalog, youth())
    changed = [p.model_copy(update={"title": "이름이 바뀐 정책"}) for p in youth()[:1]]
    assert upsert_policies(catalog, changed)["updated"] == 1


def seed_policy(**override):
    base = dict(policy_id="seed-busan-housing", title="부산 주거 시드", source=PolicySource.BUSAN_SEED,
                as_of="2026-11-20", regions=[PolicyRegion(scope=RegionScope.SIDO, sido="26")],
                stage=PolicyStage.SETTLE, verified=False, youthcenter_id=BUSAN_HOUSING,
                benefit=PolicyBenefit(text="시드에 적은 혜택"))
    return Policy(**{**base, **override})


def test_policy_seed_is_enriched_not_duplicated(catalog):
    seed = seed_policy()
    catalog.put_policy(seed)
    result = upsert_policies(catalog, youth())
    assert result["enriched"] == 1 and result["created"] == 7
    assert f"ythc-{BUSAN_HOUSING}" not in catalog.policies  # 새로 만들지 않는다
    merged = catalog.get_policy("seed-busan-housing")
    assert merged.title == "부산 주거 시드" and merged.benefit.text == "시드에 적은 혜택"  # 시드 값은 그대로
    assert merged.summary.startswith("○ 지원내용") and merged.url == "https://young.busan.go.kr/index.nm?menuCd=271"
    assert merged.income_rule == "기준중위소득 120%이하(월 3,078천원 이하)"
    assert merged.verified is False and merged.source == PolicySource.BUSAN_SEED  # 확인 상태는 건드리지 않는다
    assert (merged.age_min, merged.age_max) == (18, 39)
    assert merged.eligibility.manual_checks[-1] == "참여 제한 대상: ※ 유사사업 수혜이력이 있는 자 등"

    again = upsert_policies(catalog, youth())
    assert again["enriched"] == 0 and again["unchanged"] == 8  # 보강이 끝난 시드도 unchanged로 센다


def test_policy_seed_matches_prefixed_youthcenter_id(catalog):
    catalog.put_policy(seed_policy(youthcenter_id=f"ythc-{BUSAN_HOUSING}"))
    assert upsert_policies(catalog, youth())["enriched"] == 1


# ---------------------------------------------------------------- 기업
def gangso(as_of=DAY1):
    xml = (FIXTURES / "work24_gangso_region26000_p1.xml").read_bytes()
    return [normalize_gangso(r, as_of=as_of) for r in as_list(walk(parse_body(xml), "smallGiantsList.smallGiant"))]


def test_companies_created_once_and_next_day_unchanged(catalog):
    assert upsert_companies(catalog, gangso()) == {"created": 3, "updated": 0, "unchanged": 0}
    assert upsert_companies(catalog, gangso(DAY2)) == {"created": 0, "updated": 0, "unchanged": 3}
    assert catalog.get_company("biz-6088195805").as_of == "2026-11-22"  # 기준일만 새로 쓴다


def test_company_badges_from_other_sources_are_kept(catalog):
    cheonggeul = Badge(type=BadgeType.CHEONGKKEUL, label="청끌기업", source="고용노동부 청끌기업", as_of="2026-06-30")
    seeded = gangso()[0].model_copy(update={"highlights": [cheonggeul], "source": "청끌기업 시드",
                                            "as_of": "2026-06-30"})
    catalog.put_company(seeded)
    result = upsert_companies(catalog, gangso())
    assert result["updated"] == 1 and result["created"] == 2
    merged = catalog.get_company("biz-6088195805")
    assert [b.type for b in merged.highlights] == [BadgeType.CHEONGKKEUL, BadgeType.GANGSO]
    assert merged.source == "청끌기업 시드" and merged.as_of == "2026-06-30"  # 먼저 넣은 출처를 따른다
    assert upsert_companies(catalog, gangso())["unchanged"] == 3


# ---------------------------------------------------------------- 지역 조건 다시 읽기·색인 (2026-11-21)
def _with_mention(as_of, text="우대 대상: 장애인, 비수도권 지역인재"):
    snaps = snapshots(as_of)
    changed = snaps[0].model_copy(update={"job_description": text})
    digest = compute_content_hash(changed)
    snaps[0] = changed.model_copy(update={"content_hash": digest, "snapshot_id": snapshot_id_for(as_of, digest)})
    return snaps


def test_unchanged_posting_is_rejudged_and_indexed(config, catalog):
    """규칙이 바뀌기 전에 넣은 공고도 다음 수집에서 지역 조건을 다시 읽고 색인에 들어간다."""
    upsert_postings(config, catalog, _with_mention(DAY1), as_of=DAY1)
    pid = "wk24-K000000001"
    latest = catalog.get_latest(pid)
    assert latest.regional_talent.status == RegionalTalentStatus.LIKELY and pid in catalog.regional_index
    # 예전 규칙으로 넣어 둔 상태로 되돌린다
    snap = catalog.get_snapshot(pid, latest.snapshot_id)
    catalog.put_snapshot(snap.model_copy(update={"regional_talent": None}))
    catalog.put_latest(latest.model_copy(update={"regional_talent": None}))
    catalog.delete_regional_index(pid)

    result = upsert_postings(config, catalog, _with_mention(DAY2), as_of=DAY2)
    assert result["unchanged"] == len(records()) and result["needsEnrich"] == []
    again = catalog.get_latest(pid)
    assert [c.kind.value for c in again.regional_talent.conditions] == ["NON_CAPITAL"]
    assert catalog.get_snapshot(pid, again.snapshot_id).regional_talent == again.regional_talent
    assert catalog.list_regional_index(closes_from="2026-11-22") == [pid]


def test_regional_index_drops_removed_and_expired(config, catalog):
    upsert_postings(config, catalog, _with_mention(DAY1), as_of=DAY1)
    pid = "wk24-K000000001"
    upsert_postings(config, catalog, snapshots(DAY2), as_of=DAY2)  # 공고문이 바뀌어 지역 조건이 없어졌다
    assert pid not in catalog.regional_index
    upsert_postings(config, catalog, _with_mention(DAY2), as_of=DAY2)
    assert pid in catalog.regional_index
    closes = catalog.get_latest(pid).closes_at
    expire_postings(config, catalog, as_of=f"{closes}T23:59:59+09:00", job_posting_ids=[pid])
    expire_postings(config, catalog, as_of="2099-01-01T00:00:00+09:00", job_posting_ids=[pid])
    assert pid not in catalog.regional_index


def test_manual_regional_talent_is_not_rejudged(config, catalog):
    upsert_postings(config, catalog, snapshots(DAY1), as_of=DAY1)
    pid = "wk24-K000000001"
    snap = catalog.get_snapshot(pid, catalog.get_latest(pid).snapshot_id)
    manual = RegionalTalent(status=RegionalTalentStatus.LIKELY, basis="사람이 확인")
    catalog.put_snapshot(snap.model_copy(update={"regional_talent": manual,
                                                 "extracted_by": {**snap.extracted_by, "regionalTalent": "MANUAL"}}))
    upsert_postings(config, catalog, snapshots(DAY2), as_of=DAY2)
    assert catalog.get_snapshot(pid, snap.snapshot_id).regional_talent == manual
