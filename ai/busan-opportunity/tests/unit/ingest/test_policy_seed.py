"""ingest/policy_seed.py: 공식 공고문으로 확인한 부산 정책 보강 시드."""

import json

import pytest

from opportunity.core.copy_rules import find_forbidden
from opportunity.core.policies import _public_amount
from opportunity.ingest.policy_seed import apply_policy_seed, load_policy_seed, main
from opportunity.models.enums import EmploymentStatus, PeriodType, PolicySource, PolicyStage, Selection
from opportunity.models.policy import Policy, PolicyApplication, PolicyBenefit, PolicyEligibility, PolicyRegion

BUSAN = PolicyRegion(scope="SIDO", sido="26")
JOY_ID = "20260513005400213197"
DIDIMDOL_ID = "20260406005400212421"
INTERN_ID = "20260429005400212910"
INTERN_SEED_ID = "seed-busan-job-matching-intern"
SRC = {"source": "가상 공고 제1호", "sourceUrl": "https://example.org/notice/1", "asOf": "2026-08-03",
       "verified": True, "verifiedBy": "공식 공고문 대조", "verifiedAt": "2026-11-20"}


def ontong(youthcenter_id: str, title: str, **override) -> Policy:
    """온통청년 정규화 결과와 같은 모양의 정책."""
    data = dict(
        policy_id=f"ythc-{youthcenter_id}", youthcenter_id=youthcenter_id, title=title, summary="온통청년 요약",
        age_min=18, age_max=39, apply_start="2026-08-10", apply_end="2026-08-21", url="https://young.busan.go.kr",
        source=PolicySource.YOUTHCENTER, as_of="2026-11-20", regions=[BUSAN], category="JOB",
        stage=PolicyStage.PREPARE, income_rule="기준중위소득 150% 이하",
        eligibility=PolicyEligibility(age_min=18, age_max=39, manual_checks=["온통청년 참여 제한 문구"]),
        benefit=PolicyBenefit(text="온통청년 지원 내용"),
        application=PolicyApplication(period_type=PeriodType.FIXED, selection=Selection.REVIEW),
        checklist=["제출 서류: 온통청년 안내"], verified=True, verified_by="YOUTHCENTER_API",
        verified_at="2026-11-20T09:00:00+09:00",
    )
    data.update(override)
    return Policy(**data)


def write(tmp_path, data, name="seed.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def seed():
    return load_policy_seed()


@pytest.fixture
def ontong_policies():
    return [
        ontong(JOY_ID, "부산 청년 자산형성 지원(부산청년 기쁨두배통장)"),
        ontong(DIDIMDOL_ID, "부산 미취업 청년 사회진입 활동비 지원(청년디딤돌플러스+ 카드)",
               apply_start="2026-03-01", apply_end="2026-03-31"),
        ontong("20260513005400213198", "부산 청년 중개보수 및 이사비 지원", stage=PolicyStage.SETTLE),
    ]


def by_id(policies: list[Policy]) -> dict[str, Policy]:
    return {p.policy_id: p for p in policies}


# ---------------------------------------------------------------- 시드 파일
def test_seed_file_passes_loader(seed):
    assert len(seed) == 3
    for row in seed:
        assert row["source"] and row["sourceUrl"].startswith("https://") and row["asOf"]
        assert row["verified"] is True and row["verifiedBy"] == "공식 공고문 대조" and row["verifiedAt"] == "2026-11-20"


def test_seed_file_has_no_forbidden_copy(seed):
    def texts(value):
        if isinstance(value, dict):
            return [t for v in value.values() for t in texts(v)]
        if isinstance(value, list):
            return [t for v in value for t in texts(v)]
        return [value] if isinstance(value, str) else []

    assert [t for row in seed for t in texts(row) if find_forbidden(t)] == []


@pytest.mark.parametrize("missing", ["source", "sourceUrl", "asOf"])
def test_rejects_item_without_source(tmp_path, missing):
    row = {"youthcenterId": JOY_ID, "amountMax": 360, **SRC}
    row.pop(missing)
    with pytest.raises(ValueError) as e:
        load_policy_seed(write(tmp_path, {"items": [row]}))
    assert missing in str(e.value) and JOY_ID in str(e.value)


def test_rejects_blank_source_and_unknown_field(tmp_path):
    rows = [{"youthcenterId": JOY_ID, **SRC, "source": "  "},
            {"youthcenterId": DIDIMDOL_ID, **SRC, "benefit": {"text": "x", "publicShare": 1}}]
    with pytest.raises(ValueError) as e:
        load_policy_seed(write(tmp_path, rows))
    message = str(e.value)
    assert "source 없음" in message and "benefit.publicShare" in message


def test_rejects_unverified_bad_type_and_forbidden_copy(tmp_path):
    rows = [{"youthcenterId": JOY_ID, **SRC, "verified": False},
            {"youthcenterId": DIDIMDOL_ID, **SRC, "amountMax": "많이"},
            {"policyId": "seed-x", "title": "가상", **SRC, "summary": "놓치면 후회해요"}]
    with pytest.raises(ValueError) as e:
        load_policy_seed(write(tmp_path, rows))
    message = str(e.value)
    assert "verified=true" in message and "amountMax" in message and "금지 문구" in message


def test_rejects_item_without_any_id(tmp_path):
    with pytest.raises(ValueError, match="youthcenterId나 policyId"):
        load_policy_seed(write(tmp_path, [{"title": "이름만", **SRC}]))


# ---------------------------------------------------------------- 보강
def test_joy_double_gets_exclusive_and_separate_self_share(seed, ontong_policies):
    out, _ = apply_policy_seed(ontong_policies, seed)
    joy = by_id(out)[f"ythc-{JOY_ID}"]
    assert "청년내일저축계좌" in joy.exclusive_with
    assert {"부산청년 일하는 기쁨카드", "디딤돌카드+"} <= set(joy.exclusive_with)
    assert joy.benefit.public_share_max == 360 and joy.benefit.self_share_max == 360
    assert joy.amount_max == 360  # 본인 저축 360을 더한 720이 아니다
    assert _public_amount(joy) == 360
    assert joy.application.selection == Selection.LOTTERY
    assert joy.application.last_competition == "13:1 (2025년 모집)"
    assert (joy.last_cycle.start, joy.last_cycle.end) == ("2026-08-10", "2026-08-21")
    assert "240만 원" in joy.benefit.text
    checks = " ".join(joy.eligibility.manual_checks)
    for word in ("부산광역시 거주 유지", "근로 유지", "50% 이상 저축", "금융교육 총 2회"):
        assert word in checks


def test_enriched_keeps_youthcenter_identity_and_notes_verification(seed, ontong_policies):
    out, _ = apply_policy_seed(ontong_policies, seed)
    joy = by_id(out)[f"ythc-{JOY_ID}"]
    assert joy.source == PolicySource.YOUTHCENTER and joy.youthcenter_id == JOY_ID
    assert joy.verified is True and joy.verified_at == "2026-11-20"
    assert joy.verified_by.startswith("YOUTHCENTER_API + 공식 공고문 대조")
    assert "제2026-2363호" in joy.verified_by


def test_fields_not_in_seed_keep_youthcenter_values(seed, ontong_policies):
    original = by_id(ontong_policies)[f"ythc-{JOY_ID}"]
    out, _ = apply_policy_seed(ontong_policies, seed)
    joy = by_id(out)[f"ythc-{JOY_ID}"]
    assert joy.title == original.title  # 시드 title은 이름표라 덮어쓰지 않는다
    assert joy.summary == "온통청년 요약"
    assert joy.income_rule == original.income_rule
    assert joy.url == original.url and joy.as_of == original.as_of
    assert joy.regions == original.regions and joy.checklist == original.checklist
    assert joy.eligibility.age_min == 18 and joy.eligibility.age_max == 39
    assert joy.application.period_type == PeriodType.FIXED
    assert joy.eligibility.manual_checks[0] == "온통청년 참여 제한 문구"  # 목록은 뒤에 붙인다
    untouched = by_id(out)["ythc-20260513005400213198"]
    assert untouched == by_id(ontong_policies)["ythc-20260513005400213198"]


def test_didimdol_benefit_and_lottery(seed, ontong_policies):
    out, _ = apply_policy_seed(ontong_policies, seed)
    card = by_id(out)[f"ythc-{DIDIMDOL_ID}"]
    assert card.benefit.public_share_max == 180 and card.benefit.self_share_max is None
    assert "30만 원" in card.benefit.text and "조건부" in card.benefit.text
    assert card.application.selection == Selection.LOTTERY
    assert (card.last_cycle.start, card.last_cycle.end) == ("2026-03-09", "2026-03-27")
    assert (card.apply_start, card.apply_end) == ("2026-03-09", "2026-03-27")  # 공고문 기간으로 고친다
    checks = " ".join(card.eligibility.manual_checks)
    assert "4배수" in checks and "생애 1회" in checks and "국민취업지원제도" in checks
    assert card.eligibility.employment == [EmploymentStatus.UNEMPLOYED]


def test_missing_youthcenter_policy_is_created_from_seed(seed, ontong_policies):
    out, summary = apply_policy_seed(ontong_policies, seed)
    intern = by_id(out)[INTERN_SEED_ID]
    assert intern.source == PolicySource.BUSAN_SEED and intern.youthcenter_id == INTERN_ID
    assert intern.title == "부산청년 잡(JOB)매칭 인턴사업"
    assert intern.stage == PolicyStage.PREPARE and intern.regions == [BUSAN]
    assert intern.amount_max is None and intern.benefit.public_share_max is None  # 기업 지원금은 청년 몫이 아니다
    assert "기업 지원" in intern.summary and "150만 원" in intern.summary
    assert any("직접 신청하는 공고가 아니" in c for c in intern.eligibility.manual_checks)
    assert intern.verified is True and intern.as_of == "2026-04-15" and intern.url.startswith("https://")
    assert summary["created"] == 1 and summary["createdIds"] == [INTERN_SEED_ID]
    assert len(out) == len(ontong_policies) + 1


def test_intern_in_youthcenter_is_enriched_not_duplicated(seed, ontong_policies):
    policies = [*ontong_policies, ontong(INTERN_ID, "부산청년 잡(JOB)매칭 인턴사업",
                                         application=PolicyApplication(period_type=PeriodType.ALWAYS,
                                                                       selection=Selection.FIRST_COME))]
    out, summary = apply_policy_seed(policies, seed)
    assert INTERN_SEED_ID not in by_id(out) and len(out) == len(policies)
    intern = by_id(out)[f"ythc-{INTERN_ID}"]
    assert intern.source == PolicySource.YOUTHCENTER and intern.amount_max is None
    assert intern.application.period_type == PeriodType.TBD
    assert summary == {"enriched": 3, "created": 0, "notFound": 0,
                       "enrichedIds": [f"ythc-{JOY_ID}", f"ythc-{DIDIMDOL_ID}", f"ythc-{INTERN_ID}"],
                       "createdIds": [], "notFoundItems": []}


def test_policy_id_is_used_when_youthcenter_id_is_absent(tmp_path):
    seed = load_policy_seed(write(tmp_path, [{"policyId": "ythc-1", **SRC, "amountMax": 50}]))
    plain = ontong("1", "가상 정책").model_copy(update={"youthcenter_id": None})
    out, summary = apply_policy_seed([plain], seed)
    assert out[0].amount_max == 50 and summary["enrichedIds"] == ["ythc-1"]


def test_unmatched_item_is_reported(seed):
    out, summary = apply_policy_seed([ontong(JOY_ID, "기쁨두배통장")], seed)
    assert summary["enriched"] == 1 and summary["created"] == 1
    assert summary["notFound"] == 1 and summary["notFoundItems"] == [DIDIMDOL_ID]
    assert len(out) == 2


def test_reapply_is_stable(seed, ontong_policies):
    once, _ = apply_policy_seed(ontong_policies, seed)
    twice, summary = apply_policy_seed(once, seed)
    assert (summary["enriched"], summary["created"]) == (3, 0) and len(twice) == len(once)  # 만든 시드 정책을 다시 찾는다
    assert by_id(twice)[INTERN_SEED_ID].source == PolicySource.BUSAN_SEED
    assert [p.to_api() for p in twice] == [p.to_api() for p in once]  # 두 번 덧씌워도 같다
    joy = by_id(twice)[f"ythc-{JOY_ID}"]
    assert joy.exclusive_with.count("청년내일저축계좌") == 1  # 목록이 겹쳐 쌓이지 않는다


# ---------------------------------------------------------------- CLI
def test_cli_writes_seeded_jsonl(tmp_path, ontong_policies, capsys):
    source = tmp_path / "policies.jsonl"
    source.write_text("".join(json.dumps(p.to_api(), ensure_ascii=False) + "\n" for p in ontong_policies),
                      encoding="utf-8")
    out = tmp_path / "policies_seeded.jsonl"
    assert main(["--normalized", str(source), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(ontong_policies) + 1
    report = json.loads(capsys.readouterr().out)
    assert report["input"] == 3 and report["output"] == 4
    assert (report["enriched"], report["created"], report["notFound"]) == (2, 1, 0)


def test_cli_refuses_to_overwrite_input(tmp_path):
    source = tmp_path / "policies.jsonl"
    source.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--normalized", str(source), "--out", str(source)])
