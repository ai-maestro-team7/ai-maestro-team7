"""문구 규칙 (개발계획서2 §4.7). 화면 문구와 LLM 출력이 같이 지킨다.

- 사실과 다른 손실 문구, 가짜 긴급함을 쓰지 않는다.
- "부산이 좋다"가 아니라 "당신에게 이게 유리하다"로 말한다.
- 점수는 숫자 대신 3단계 말로 보여 준다.
"""

import re

from ..models.enums import LeaveReason, MatchLevel, Sort

# LLM 출력에서 걸리면 다시 만든다 (T-19)
FORBIDDEN_PATTERNS = ("떠나면", "손해", "잃", "놓치면", "후회", "임박", "합격에 유리", "이득")

MATCH_LEVEL_LABEL = {MatchLevel.GOOD: "잘 맞아요", MatchLevel.FAIR: "맞는 편이에요", MatchLevel.LOW: "조금 맞아요"}

RANKING_BASIS = {
    Sort.BUSAN_FIRST: "비슷하게 맞는 공고 중 부산 근무 공고를 먼저 보여드려요",
    Sort.MATCH: "잘 맞는 순서로 보여드려요",
    Sort.DEADLINE: "마감이 가까운 순서로 보여드려요",
    Sort.RECENT: "최근에 확인한 순서로 보여드려요",
}

WHY_SHOWN_DEFAULT = "보고 있는 공고와 하는 일이 비슷해요"
WHY_SHOWN_BY_REASON = {
    LeaveReason.SALARY: "하는 일이 비슷하고 급여가 공고에 적혀 있어요",
    LeaveReason.NO_JOB_IN_BUSAN: "부산에서 비슷한 직무를 넓혀 찾았어요",
    LeaveReason.GROWTH: "하는 일이 비슷하고 성장 지원이 확인된 곳이에요",
    LeaveReason.WORK_LIFE: "하는 일이 비슷하고 워라밸이 확인된 곳이에요",
}

REGIONAL_TALENT_LIKELY = "{school} 소재 학교 {status}이라 지역인재 전형 대상일 수 있어요 · 공고문 확인"
REGIONAL_TALENT_CHECK = "이전 공공기관 공고예요. 지역인재 전형이 있는지 공고문에서 확인해 주세요"

EMPTY_BUSAN = "부산에는 아직 이 직무 공고가 적어요. 비슷한 직무를 함께 보여드려요 · 새 공고 알림 받기"
NOT_IN_POSTING = "공고에 없음"
MATCH_NOT_PROBABILITY = "적합도는 실제 합격 확률이 아닙니다"
SIMULATED = "시뮬레이션"
SAMPLE_DATA = "데모 데이터"

LOCAL_LIFE_TITLE = "이 동네에서 일하면"
COMMUTE_LABEL = "집에서 대중교통 약 {minutes}분"
OVERSEAS_LABEL = "해외 근무 · {country}"
MOVE_NEEDED = "이사가 필요한 거리예요"

POLICY_TOTAL_NOTE = "추첨·심사·선착순 정책은 '선정되면 최대'로 따로 셉니다"
NATIONAL_COMMON_NOTE = "전국 공통 정책 {count}개는 어디서든 같아요"

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def find_forbidden(text: str) -> list[str]:
    """금지 문구가 있으면 걸린 패턴을 돌려준다."""
    return [p for p in FORBIDDEN_PATTERNS if p in text]


def numbers_in(text: str) -> set[str]:
    """문장 속 숫자 (쉼표 제거). 설명 문장의 숫자가 사실 목록에 있는지 대조할 때 쓴다."""
    return {m.replace(",", "") for m in _NUMBER.findall(text)}


def deadline_label(days: int | None) -> str | None:
    """마감 D-3. 상시 채용은 '상시 채용'."""
    if days is None:
        return "상시 채용"
    if days < 0:
        return "마감"
    return "오늘 마감" if days == 0 else f"마감 D-{days}"


def salary_label(disclosed: bool, low: int | None, high: int | None) -> str:
    """연 4,000~4,400만 원. 공고에 없으면 '공고에 없음'."""
    if not disclosed or (low is None and high is None):
        return NOT_IN_POSTING
    if low is not None and high is not None and low != high:
        return f"연 {low:,}~{high:,}만 원"
    return f"연 {(low if low is not None else high):,}만 원"
