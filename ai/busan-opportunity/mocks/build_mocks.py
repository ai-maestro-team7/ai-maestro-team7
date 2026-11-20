"""프론트용 가짜 응답을 만든다. 응답 모델로 검사한 뒤 `mocks/*.json`으로 쓴다.

실행: uv run --no-project --python 3.13 --with pydantic python mocks/build_mocks.py
값은 데모 데이터(가상 회사)다. 금액·통계 숫자도 예시다.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from opportunity import models as m  # noqa: E402

AS_OF = "2026-11-21T04:52:00+09:00"
CG = {"type": "CHEONGKKEUL", "label": "청끌기업 · 급여", "source": "부산광역시", "asOf": "2026-06-30", "cheonggeulType": "SALARY"}
RELOCATED = {"type": "RELOCATED_INSTITUTION", "label": "부산 이전 공공기관", "source": "국토교통부 혁신도시", "asOf": "2026-06-30"}
JOB = {"code": "D0101", "middle": "D01", "major": "D", "name": "데이터 분석가"}
ELIGIBLE = {"status": "ELIGIBLE", "conditions": [
    {"ruleId": "rule-edu", "type": "EDUCATION", "result": "MET", "reason": "학력 조건 충족"},
    {"ruleId": "rule-career", "type": "CAREER", "result": "MET", "reason": "신입 지원 가능"}], "unknown": [], "ruleVersion": "elig-v1"}
BUSAN_CARD = {
    "jobPostingId": "wk24-DEMO0001", "title": "데이터 분석 신입", "organization": "(주)가상데이터", "orgType": "PRIVATE",
    "workRegion": {"sido": "26", "sigungu": "26350", "label": "부산 해운대구"}, "isBusan": True, "isCapitalArea": False,
    "job": JOB, "closesAt": "2026-12-05", "rolling": False,
    "salary": {"disclosed": True, "min": 3400, "max": 3800, "unit": "MANWON_YEAR"}, "matchScore": 0.74, "matchLevel": "GOOD",
    "eligibility": ELIGIBLE, "badges": [CG], "facts": ["희망 직무와 같은 직종", "필수 조건 2개 중 2개 충족", "마감 D-14"], "isSample": True}
SEOUL_CARD = {
    "jobPostingId": "wk24-DEMO0002", "title": "Data Analyst", "organization": "(주)가상테크", "orgType": "PRIVATE",
    "workRegion": {"sido": "11", "sigungu": "11680", "label": "서울 강남구"}, "isBusan": False, "isCapitalArea": True,
    "job": JOB, "closesAt": "2026-11-30", "rolling": False,
    "salary": {"disclosed": True, "min": 4000, "max": 4400, "unit": "MANWON_YEAR"}, "matchScore": 0.79, "matchLevel": "GOOD",
    "eligibility": ELIGIBLE, "badges": [], "facts": ["희망 직무와 같은 직종", "마감 D-9"], "busanAlternativesCount": 2, "isSample": True}
ALT_PUBLIC = {
    "jobPostingId": "alio-DEMO0001", "title": "2026년 신입직원 채용 (데이터)", "organization": "가상금융공사",
    "workRegion": {"sido": "26", "sigungu": "26290", "label": "부산 남구"}, "closesAt": "2026-11-30", "similarity": 0.81,
    "matchScore": 0.71, "matchLevel": "GOOD", "badges": [RELOCATED],
    "facts": ["하는 일이 비슷함 (유사도 0.81)", "부산 이전 공공기관 · 지역인재 전형 대상일 수 있음", "마감 D-9"],
    "whyShown": "보고 있는 공고와 하는 일이 비슷해요", "isSample": True}
ALT_PRIVATE = {
    "jobPostingId": "wk24-DEMO0001", "title": "데이터 분석 신입", "organization": "(주)가상데이터",
    "workRegion": {"sido": "26", "sigungu": "26350", "label": "부산 해운대구"}, "closesAt": "2026-12-05", "similarity": 0.86,
    "matchScore": 0.74, "matchLevel": "GOOD", "badges": [CG],
    "facts": ["하는 일이 비슷함 (유사도 0.86)", "급여가 공고에 적혀 있음", "청끌기업 · 급여", "마감 D-14"],
    "whyShown": "하는 일이 비슷하고 급여가 공고에 적혀 있어요", "isSample": True}
SNAPSHOT = {
    "jobPostingId": "wk24-DEMO0002", "snapshotId": "20261121-a1b2c3d4", "title": "Data Analyst", "organization": "(주)가상테크",
    "jobDescription": "데이터 분석과 통계 모델링으로 서비스 지표를 분석하고 SQL로 데이터를 다룬다",
    "requirements": [
        {"requirementId": "req-1", "name": "SQL", "kind": "REQUIRED_SKILL", "weight": 1.0, "sourceQuote": "필수: SQL"},
        {"requirementId": "pref-1", "name": "Tableau", "kind": "PREFERRED_SKILL", "weight": 1.0, "sourceQuote": "우대: Tableau"}],
    "eligibilityRules": [{"ruleId": "rule-edu", "type": "EDUCATION", "value": "BACHELOR", "sourceQuote": "학력 조건"}],
    "closesAt": "2026-11-30", "officialUrl": "https://example.invalid/postings/wk24-DEMO0002", "sourceType": "DEMO",
    "checkedAt": "2026-11-21T04:40:00+09:00", "source": "WORK24", "company": {"name": "(주)가상테크", "hqSido": "11"},
    "orgType": "PRIVATE", "workRegion": {"sido": "11", "sigungu": "11680", "label": "서울 강남구"}, "job": JOB,
    "employmentType": "FULL_TIME", "careerType": "NEW", "salary": {"disclosed": True, "min": 4000, "max": 4400, "unit": "MANWON_YEAR"},
    "remoteWork": "NONE", "extractStatus": "DONE", "contentHash": "demo"}
JOY = {
    "policyId": "seed-busan-joy-double", "title": "부산청년 기쁨두배통장", "summary": "월 10만 원 저축 시 시가 같은 금액 지원",
    "category": "ASSET", "stage": "EMPLOYED", "bucket": "AFTER_EMPLOYMENT",
    "eligibility": {"status": "AFTER_EMPLOYMENT", "reasons": ["일하는 청년 대상: 지금은 미취업", "나이 18~39세 충족", "부산 거주 충족"]},
    "benefit": {"text": "월 10만 원 저축 시 시가 같은 금액 지원", "publicShareMax": 360, "selfShareMax": 360, "unit": "MANWON"},
    "application": {"expected": "2027년 8월 (작년 8.10~8.21 기준)", "selection": "LOTTERY", "lastCompetition": "13:1 (2025)"},
    "exclusiveWith": ["청년내일저축계좌"], "alertAvailable": True, "alertSubscribed": False, "source": "BUSAN_SEED", "asOf": "2026-11-20"}
DIDIMDOL = {
    "policyId": "seed-busan-didimdol-plus", "title": "디딤돌카드+", "summary": "월 30만 원, 최대 6개월", "category": "JOB",
    "stage": "PREPARE", "bucket": "NEXT_CYCLE",
    "eligibility": {"status": "ELIGIBLE", "reasons": ["취업 준비 청년 대상: 미취업 충족", "부산 거주 충족"]},
    "benefit": {"text": "월 30만 원, 최대 6개월", "publicShareMax": 180, "unit": "MANWON"},
    "application": {"expected": "2027년 상반기 (작년 3월 공지 기준)", "selection": "REVIEW"},
    "alertAvailable": True, "alertSubscribed": False, "source": "BUSAN_SEED", "asOf": "2026-11-20"}

MOCKS = {
    "GET_postings": (m.FeedResponse, {
        "items": [BUSAN_CARD, SEOUL_CARD],
        "ranking": {"sort": "BUSAN_FIRST", "basis": "비슷하게 맞는 공고 중 부산 근무 공고를 먼저 보여드려요", "busanBoost": 0.06},
        "dataAsOf": AS_OF, "stale": False, "askLeaveReason": False}),
    "GET_postings_id": (m.PostingDetailResponse, {
        "posting": SNAPSHOT, "isBusan": False, "isCapitalArea": True, "closed": False, "isSample": True, "matchLevel": "GOOD",
        "eligibility": ELIGIBLE, "badges": [], "relatedPolicies": [], "alternativesPreview": [ALT_PRIVATE, ALT_PUBLIC],
        "facts": ["희망 직무와 같은 직종", "마감 D-9"], "dataAsOf": AS_OF}),
    "GET_postings_id_explanation": (m.ExplanationResponse, {
        "jobPostingId": "wk24-DEMO0002", "sentences": ["희망하신 데이터 분석 직무와 같은 직종의 공고예요.", "마감까지 9일 남았어요."],
        "facts": ["희망 직무와 같은 직종", "마감 D-9"], "cached": False}),
    "GET_postings_id_alternatives": (m.AlternativesResponse, {
        "baseJobPostingId": "wk24-DEMO0002", "alternatives": [ALT_PRIVATE, ALT_PUBLIC], "expanded": False,
        "noAlternative": False, "leaveReasonApplied": "SALARY", "suggestCompare": True, "dataAsOf": AS_OF}),
    "GET_compare": (m.CompareResponse, {
        "base": {"jobPostingId": "wk24-DEMO0002", "label": "서울 강남구 · (주)가상테크"},
        "alt": {"jobPostingId": "alio-DEMO0001", "label": "부산 남구 · 가상금융공사"},
        "rows": [
            {"key": "SALARY", "label": "급여 (공고 기재)", "base": "연 4,000~4,400만 원", "alt": "공고에 없음", "comparable": False, "source": "각 공고"},
            {"key": "REGIONAL_POLICY", "label": "나에게 맞는 지역 정책 (온통청년 기준)", "base": {"count": 1}, "alt": {"count": 3},
             "nationalCommon": 1, "note": "전국 공통 정책 1개는 어디서든 같아요", "source": "온통청년", "asOf": "2026-11-21"},
            {"key": "REGIONAL_TALENT", "label": "지역인재 전형", "base": "해당 없음", "alt": "대상일 수 있음"},
            {"key": "VERIFIED", "label": "시·정부 인증", "base": "-", "alt": "-"}],
        "costAdjusted": {"available": False, "reason": "SALARY_NOT_COMPARABLE"}, "familyHousingOption": True,
        "familyHousingApplied": False, "suggestMore": True, "dataAsOf": AS_OF}),
    "GET_policies": (m.PolicyWalletResponse, {
        "profileUsed": {"ageRange": "22~23", "residence": "부산 남구", "employment": "UNEMPLOYED", "income": "UNKNOWN"},
        "buckets": {"OPEN_NOW": [], "NEXT_CYCLE": [DIDIMDOL], "AFTER_EMPLOYMENT": [JOY], "SETTLEMENT": [], "CLOSED": []},
        "totals": {"guaranteedIfEligible": 0, "selectiveMax": 540, "unit": "MANWON", "note": "추첨·심사·선착순 정책은 '선정되면 최대'로 따로 셉니다"},
        "dataAsOf": AS_OF}),
    "GET_policies_id": (m.PolicyDetailResponse, {"policy": {**JOY, "checklist": ["주민등록초본", "신청서"], "url": "https://example.invalid/busan-policy"}, "dataAsOf": AS_OF}),
    "POST_policies_id_alerts": (m.PolicyAlertResponse, {"alert": {"policyId": "seed-busan-joy-double", "scheduledAt": "2027-08-03T09:00:00+09:00"}, "created": True}),
    "GET_me_preferences": (m.PreferencesView, {"sort": "BUSAN_FIRST", "leaveReason": "SALARY", "notifications": {"email": False, "weekly": False}, "receivingPolicies": []}),
    "POST_saved": (m.SaveResponse, {
        "saved": {"jobPostingId": "alio-DEMO0001", "kind": "TARGET", "status": "PLANNED", "isBusan": True,
                  "savedAt": "2026-11-21T10:12:00+09:00", "workspaceId": "ws-alio-DEMO0001"},
        "schedules": [{"type": "TARGET_DEADLINE", "at": "2026-11-23T09:00:00+09:00", "label": "마감 D-7"},
                      {"type": "TARGET_DEADLINE", "at": "2026-11-27T09:00:00+09:00", "label": "마감 D-3"}],
        "askLeaveReason": False, "created": True}),
    "GET_saved": (m.SavedListResponse, {"items": [
        {"jobPostingId": "alio-DEMO0001", "kind": "TARGET", "status": "PLANNED", "isBusan": True, "savedAt": "2026-11-21T10:12:00+09:00",
         "workspaceId": "ws-alio-DEMO0001", "title": "2026년 신입직원 채용 (데이터)", "organization": "가상금융공사", "closesAt": "2026-11-30"}]}),
    "GET_notifications": (m.NotificationsResponse, {"items": [
        {"notificationId": "20261123T090000-a1b2c3d4", "type": "TARGET_DEADLINE", "title": "목표 공고 마감 D-7",
         "body": "가상금융공사 · 2026년 신입직원 채용 (데이터)", "link": "/opportunities/postings/alio-DEMO0001", "read": False,
         "channel": "INBOX", "createdAt": "2026-11-23T09:00:00+09:00", "simulated": True}]}),
    "POST_admin_demo-clock": (m.DemoClockResponse, {"asOf": "2026-11-27T09:00:00+09:00", "fired": 2, "simulated": True}),
}
ERROR = {"error": {"code": "POSTING_NOT_FOUND", "message": "공고를 찾을 수 없어요.", "requestId": "req-demo", "retryable": False,
                   "details": {"jobPostingId": "wk24-NOPE"}}}


def build() -> dict[str, dict]:
    out = {name: model.model_validate(raw).to_api() for name, (model, raw) in MOCKS.items()}
    out["ERROR_404"] = ERROR
    return out


if __name__ == "__main__":
    for name, body in build().items():
        (HERE / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name)
