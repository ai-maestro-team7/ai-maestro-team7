"""공고문의 지역 조건 읽기 (`enrich.regional_talent.find_conditions`).

문구는 2026-11-20에 모은 잡알리오·지방공공기관 공고에 실제로 나온 꼴을 따랐다. 기관 이름은 넣지 않았다.
"""

import pytest

from opportunity.enrich.regional_talent import find_conditions, find_sidos, judge_regional_talent
from opportunity.models.enums import RegionalBenefitKind as K
from opportunity.models.enums import RegionalTalentStatus


def kinds(text, **kwargs):
    conditions, _ = find_conditions(text, **kwargs)
    return [(c.kind, c.sido, c.sigungu) for c in conditions]


@pytest.mark.parametrize("text", [
    "우대 대상: 국가유공자, 장애인, 비수도권 지역인재, 청년",
    "ㅇ비수도권인재(3점)",
    "우대 대상: 저소득층, 비수도권인재, 이공계 인재",
    "※ 대학까지의 최종학력을 기준으로 비수도권(서울, 인천, 경기 제외) 지역학교를 졸업(예정)한 자 대상",
])
def test_non_capital(text):
    assert kinds(text) == [(K.NON_CAPITAL, None, None)]


def test_relocated_region_with_named_sidos():
    assert kinds("○ 이전지역(대구.경북)인재는 서류심사에 만점의 5% 가산점 부여") == [
        (K.SCHOOL, "27", None), (K.SCHOOL, "47", None)]
    assert kinds("○ 이전지역(광주·전남)인재에 해당하는 경우(혁신도시법 제29조의 2)") == [
        (K.SCHOOL, "29", None), (K.SCHOOL, "46", None)]
    assert kinds("우대 대상: 보훈대상자, 이전지역 인재(세종, 대전, 충북, 충남지역)")[:3] == [
        (K.SCHOOL, "36", None), (K.SCHOOL, "30", None), (K.SCHOOL, "43", None)]


def test_region_group_names():
    assert set(find_sidos("지역인재(충청권 지역 학부까지의 졸업자) 우대")) == {"30", "36", "43", "44"}
    assert set(find_sidos("부울경 지역인재")) == {"26", "31", "48"}
    assert set(find_sidos("우대 대상: 비수도권 지역인재, 광주전남지역인재")) == {"29", "46"}


def test_relocated_region_without_sido_uses_busan_for_busan_relocated():
    text = "우대 대상: 국가유공자, 장애인, 이전지역인재"
    assert kinds(text, relocated_sido="26") == [(K.SCHOOL, "26", None)]
    assert kinds(text) == [(K.UNKNOWN, None, None)]


def test_both_non_capital_and_relocated_on_one_line():
    found = kinds("우대: 이전지역인재, 비수도권(서울·인천·경기 제외) 지역인재")
    assert found == [(K.NON_CAPITAL, None, None), (K.UNKNOWN, None, None)]  # 괄호 속 서울·인천·경기는 조건이 아니다


def test_unknown_dropped_when_a_line_names_the_region():
    text = "우대 대상: 지역인재, 장애인\n○ 이전지역(대구.경북)인재는 5% 가산점"
    assert kinds(text) == [(K.SCHOOL, "27", None), (K.SCHOOL, "47", None)]


@pytest.mark.parametrize("line, expected", [
    ("지역 제한: 인천광역시 (지역인재 우선 채용)", [(K.SCHOOL_OR_RESIDENCE, "28", None)]),
    ("지역 제한: 경상남도 김해시 (지역인재 우선채용)", [(K.RESIDENCE, "48", "김해시")]),
    ("지역 제한: 부산광역시,울산광역시,경상남도 (지역 인재 채용)",
     [(K.SCHOOL_OR_RESIDENCE, "26", None), (K.SCHOOL_OR_RESIDENCE, "31", None), (K.SCHOOL_OR_RESIDENCE, "48", None)]),
    ("지역 제한: 부산광역시 기장군 (지역인재 채용)", [(K.RESIDENCE, "26", "기장군")]),
    ("지역 제한: 양산시 (지역인재 채용)", [(K.RESIDENCE, "48", "양산시")]),  # 시·도가 없으면 기관 시·도
    ("지역 제한: 전남광주통합특별시 목포시 (공고일 현재 주민등록상 주소지가 목포시로 되어 있는 사람(자격 요건))",
     [(K.RESIDENCE, "12", "목포시")]),
    ("지역 제한: 경기도 파주시 (파주시 관내 일자리 창출)", [(K.RESIDENCE, "41", "파주시")]),
    ("지역 제한: 분야별 상이", [(K.UNKNOWN, None, None)]),
])
def test_local_public_region_limit(line, expected):
    assert kinds(line, home_sido="48") == expected


@pytest.mark.parametrize("line, expected", [
    ("- 주민등록상 주소지가 울산, 양산, 부산 거주자", [(K.RESIDENCE, "31", None), (K.RESIDENCE, "26", None)]),
    ("· 서울시 강동구 거주자", [(K.RESIDENCE, "11", "강동구")]),
    ("※ 대전광역시 거주자(40점), 세종시 거주자(30점), 타지역 거주자(20점)",
     [(K.RESIDENCE, "30", None), (K.RESIDENCE, "36", None)]),
    ("○ 근무지 인근지역 거주자(공고일 전일 주민등록지 기준) / 충청북도 영동군(※사택 미제공)",
     [(K.RESIDENCE, "43", "영동군")]),
])
def test_residence(line, expected):
    assert kinds(line) == expected


@pytest.mark.parametrize("text", [
    "- 성별, 학력, 거주지 제한 없음",
    "- 거주(F-2), 재외동포(F-4), 영주(F-5)의 체류 자격 등",
    "근무지: 부산·울산·대구 (해당 지역 거주 또는 출퇴근 가능자)",
    "블라인드 채용: 출신지역, 학교명 등을 적으면 불이익",
    "양성평등 채용목표제 적용",
    "○ 근무지 인근지역 거주자(공고일 전일 주민등록지 기준) *사택 미제공",  # 지역 이름이 없다
    "부산대학교 졸업자 우대",  # 학교 이름은 지역 조건이 아니다
])
def test_not_a_regional_condition(text):
    assert kinds(text) == []


def test_judge_status():
    assert judge_regional_talent("비수도권 지역인재 우대").status == RegionalTalentStatus.LIKELY
    assert judge_regional_talent("공단 행정 업무", relocated_sido="26").status == RegionalTalentStatus.CHECK_NEEDED
    assert judge_regional_talent("공단 행정 업무").status == RegionalTalentStatus.NOT_APPLICABLE
    talent = judge_regional_talent("업무 소개\n우대 대상: 장애인, 비수도권 지역인재")
    assert talent.basis == "우대 대상: 장애인, 비수도권 지역인재"
