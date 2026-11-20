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
from opportunity.core import copy_rules  # noqa: E402

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
    "eligibility": ELIGIBLE, "badges": [CG], "facts": ["희망 직무와 같은 직종", "필수 조건 2개 중 2개 충족", "마감 D-14"],
    "commuteMinutes": 35, "isSample": True}
SEOUL_CARD = {
    "jobPostingId": "wk24-DEMO0002", "title": "Data Analyst", "organization": "(주)가상테크", "orgType": "PRIVATE",
    "workRegion": {"sido": "11", "sigungu": "11680", "label": "서울 강남구"}, "isBusan": False, "isCapitalArea": True,
    "job": JOB, "closesAt": "2026-11-30", "rolling": False,
    "salary": {"disclosed": True, "min": 4000, "max": 4400, "unit": "MANWON_YEAR"}, "matchScore": 0.79, "matchLevel": "GOOD",
    "eligibility": ELIGIBLE, "badges": [], "facts": ["희망 직무와 같은 직종", "마감 D-9"], "busanAlternativesCount": 2, "isSample": True}
OVERSEAS_CARD = {
    "jobPostingId": "wj-DEMO0001", "title": "해외 데이터 분석 인턴", "organization": "가상글로벌(주)", "orgType": "PRIVATE",
    "workRegion": {"label": copy_rules.OVERSEAS_LABEL.format(country="베트남"), "overseas": True, "country": "베트남"},
    "isBusan": False, "isCapitalArea": False, "job": JOB, "closesAt": "2026-12-12", "rolling": False,
    "salary": {"disclosed": False, "unit": "MANWON_YEAR"}, "matchScore": 0.52, "matchLevel": "FAIR",
    "facts": ["희망 직무와 같은 직종", "해외 근무 · 베트남", "마감 D-21"], "isSample": True}
LOWER_BOUND_CARD = {
    "jobPostingId": "klid-DEMO0001", "title": "2026년 정규직 신입 채용 (데이터·통계)", "organization": "가상시설공단", "orgType": "LOCAL_PUBLIC",
    "workRegion": {"sido": "26", "sigungu": "26500", "label": "부산 수영구"}, "isBusan": True, "isCapitalArea": False,
    "job": JOB, "closesAt": "2026-12-08", "rolling": False,
    "salary": {"disclosed": True, "min": 3200, "unit": "MANWON_YEAR"}, "matchScore": 0.61, "matchLevel": "FAIR",
    "eligibility": ELIGIBLE, "badges": [], "facts": ["희망 직무와 같은 직종", "급여는 하한만 공고에 적혀 있음", "마감 D-17"],
    "commuteMinutes": 28, "isSample": True}
PERSONAL_KEYS = {"matchScore", "matchLevel", "rankScore", "eligibility", "facts", "commuteMinutes", "distanceKm",
                 "busanAlternativesCount", "regionalTalent", "isCapitalArea"}


def public_card(card: dict, **extra) -> dict:
    """맞춤 카드에서 개인 값을 뺀 공개 목록 카드."""
    return {**{k: v for k, v in card.items() if k not in PERSONAL_KEYS}, **extra}


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
BUSAN_SNAPSHOT = {
    "jobPostingId": "wk24-DEMO0001", "snapshotId": "20261121-e5f6a7b8", "title": "데이터 분석 신입", "organization": "(주)가상데이터",
    "jobDescription": "고객 데이터를 SQL로 추출해 지표를 만들고 월간 리포트를 쓴다",
    "requirements": [
        {"requirementId": "req-1", "name": "SQL", "kind": "REQUIRED_SKILL", "weight": 1.0, "sourceQuote": "필수: SQL"},
        {"requirementId": "req-2", "name": "엑셀", "kind": "REQUIRED_SKILL", "weight": 1.0, "sourceQuote": "필수: 엑셀 활용"}],
    "eligibilityRules": [{"ruleId": "rule-edu", "type": "EDUCATION", "value": "COLLEGE", "sourceQuote": "학력: 초대졸 이상"}],
    "closesAt": "2026-12-05", "officialUrl": "https://example.invalid/postings/wk24-DEMO0001", "sourceType": "DEMO",
    "checkedAt": "2026-11-21T04:40:00+09:00", "source": "WORK24", "company": {"name": "(주)가상데이터", "hqSido": "26"},
    "orgType": "PRIVATE", "workRegion": {"sido": "26", "sigungu": "26350", "label": "부산 해운대구"}, "job": JOB,
    "employmentType": "FULL_TIME", "careerType": "NEW", "salary": {"disclosed": True, "min": 3400, "max": 3800, "unit": "MANWON_YEAR"},
    "remoteWork": "NONE", "extractStatus": "DONE", "contentHash": "demo"}
LOCAL_LIFE = {
    "commuteMinutes": 35, "commuteLabel": copy_rules.COMMUTE_LABEL.format(minutes=35), "commuteSource": "ODsay 대중교통 경로(구청 사이)",
    "festivals": [
        {"festivalId": "fest-DEMO01", "title": "가상 해운대 바다축제", "gugun": "해운대구", "place": "해운대해수욕장", "period": "2027-05-01 ~ 2027-05-03",
         "traffic": "도시철도 2호선 해운대역", "url": "https://example.invalid/festival/1", "source": "부산광역시 축제정보", "asOf": "2026-11-20"},
        {"festivalId": "fest-DEMO02", "title": "가상 센텀 빛축제", "gugun": "해운대구", "place": "센텀시티", "period": "2026-12-20 ~ 2027-01-05",
         "source": "부산광역시 축제정보", "asOf": "2026-11-20"}],
    "transit": [
        {"label": "도시철도", "value": "2호선 해운대구 안 12개 역", "source": "부산교통공사", "asOf": "2026-06-30"},
        {"label": "버스", "value": "노선 48개 (해운대구 경유)", "source": "부산시 버스정보", "asOf": "2026-06-30"},
        {"label": "동해선", "value": "벡스코역 정차", "source": "한국철도공사", "asOf": "2026-06-30"}]}
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
        "items": [BUSAN_CARD, SEOUL_CARD, LOWER_BOUND_CARD, OVERSEAS_CARD],
        "ranking": {"sort": "BUSAN_FIRST", "basis": "비슷하게 맞는 공고 중 부산 근무 공고를 먼저 보여드려요", "busanBoost": 0.06},
        "dataAsOf": AS_OF, "stale": False, "askLeaveReason": False}),
    # 로그인 없이 보는 목록 (B-D10): 마감 임박순, 개인 값(적합도·자격·근거·부산 대안 수) 없음
    "GET_public_postings": (m.PublicPostingList, {
        "items": [public_card(SEOUL_CARD, careerType="NEW", employmentType="FULL_TIME"),
                  public_card(BUSAN_CARD, careerType="NEW", employmentType="FULL_TIME"),
                  public_card(LOWER_BOUND_CARD, careerType="NEW", employmentType="FULL_TIME"),
                  public_card(OVERSEAS_CARD, isOverseas=True, careerType="ANY", employmentType="INTERN")],
        "total": 4, "dataAsOf": AS_OF, "stale": False}),
    "GET_postings_id": (m.PostingDetailResponse, {
        "posting": SNAPSHOT, "isBusan": False, "isCapitalArea": True, "closed": False, "isSample": True, "matchLevel": "GOOD",
        "eligibility": ELIGIBLE, "badges": [], "relatedPolicies": [], "alternativesPreview": [ALT_PRIVATE, ALT_PUBLIC],
        "facts": ["희망 직무와 같은 직종", "마감 D-9"], "dataAsOf": AS_OF}),
    "GET_postings_id_busan": (m.PostingDetailResponse, {
        "posting": BUSAN_SNAPSHOT, "isBusan": True, "isCapitalArea": False, "closed": False, "isSample": True, "matchLevel": "GOOD",
        "eligibility": ELIGIBLE, "badges": [CG],
        "relatedPolicies": [{"policyId": "seed-busan-didimdol-plus", "title": "디딤돌카드+", "bucket": "NEXT_CYCLE", "status": "ELIGIBLE",
                             "summary": "월 30만 원, 최대 6개월"}],
        "alternativesPreview": [], "localLife": LOCAL_LIFE, "facts": ["희망 직무와 같은 직종", "마감 D-14"], "dataAsOf": AS_OF}),
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
    "POST_postings_id_ask": (m.AskResponse, {
        "question": "필수 조건이 뭐예요?", "answered": True,
        "answer": "필수 조건은 SQL과 엑셀 활용이에요. 학력은 초대졸 이상이에요.",
        "sources": [{"kind": "POSTING", "id": "wk24-DEMO0001", "title": "데이터 분석 신입", "quote": "필수: SQL",
                     "url": "https://example.invalid/postings/wk24-DEMO0001", "asOf": "2026-11-21"}],
        "dataAsOf": AS_OF}),
    "POST_postings_id_ask_unanswered": (m.AskResponse, {
        "question": "야근이 많나요?", "answered": False, "notice": copy_rules.ASK_NOT_FOUND, "dataAsOf": AS_OF}),
    "POST_policies_ask": (m.AskResponse, {
        "question": "면접 볼 때 정장 빌려주는 곳 있어요?", "answered": True,
        "answer": "부산 면접정장 대여서비스(드림옷장)가 있어요. 신청 조건은 정책 원문에서 한 번 더 확인해 주세요.",
        "sources": [{"kind": "POLICY", "id": "seed-busan-dreamcloset", "title": "부산 면접정장 대여서비스(드림옷장)",
                     "quote": "면접용 정장을 무료로 대여", "url": "https://example.invalid/busan-policy/dreamcloset", "asOf": "2026-11-20"}],
        "relatedPolicies": [{"policyId": "seed-busan-dreamcloset", "title": "부산 면접정장 대여서비스(드림옷장)", "bucket": "OPEN_NOW",
                             "status": "ELIGIBLE", "summary": "면접용 정장 무료 대여"}],
        "manualChecks": ["대여 가능 기간과 예약 방법은 신청 페이지에서 확인"], "dataAsOf": AS_OF}),
    "POST_policies_ask_unanswered": (m.AskResponse, {
        "question": "전세 대출 이자는 얼마예요?", "answered": False, "notice": copy_rules.ASK_NOT_FOUND, "dataAsOf": AS_OF}),
    "POST_policies_id_ask": (m.AskResponse, {
        "question": "언제 신청해요?", "answered": True,
        "answer": "작년에는 8월 10일부터 21일까지 받았어요. 올해 일정은 공지가 나오면 확인해 주세요.",
        "sources": [{"kind": "POLICY", "id": "seed-busan-joy-double", "title": "부산청년 기쁨두배통장",
                     "quote": "8.10~8.21 신청", "url": "https://example.invalid/busan-policy", "asOf": "2026-11-20"}],
        "manualChecks": ["올해 모집 공고에서 일정 확인"], "dataAsOf": AS_OF}),
    "GET_companies": (m.CompaniesResponse, {
        "items": [{"companyId": "co-DEMO0001", "name": "(주)가상데이터", "industry": "소프트웨어 개발", "size": "중소기업", "district": "해운대구",
                   "mainProduct": "데이터 분석 솔루션", "badges": [CG], "openPostings": 0,
                   "facts": ["청끌기업 · 급여", "해운대구", "업종: 소프트웨어 개발", "주력 제품: 데이터 분석 솔루션", "규모: 중소기업"],
                   "source": "부산광역시", "asOf": "2026-06-30"}],
        "basis": copy_rules.COMPANIES_BASIS, "notice": copy_rules.COMPANIES_NOTICE, "dataAsOf": AS_OF}),
    "GET_policies": (m.PolicyWalletResponse, {
        "profileUsed": {"ageRange": "22~23", "residence": "부산 남구", "employment": "UNEMPLOYED", "income": "UNKNOWN"},
        "buckets": {"OPEN_NOW": [], "NEXT_CYCLE": [DIDIMDOL], "AFTER_EMPLOYMENT": [JOY], "SETTLEMENT": [], "CLOSED": []},
        "totals": {"guaranteedIfEligible": 0, "selectiveMax": 540, "unit": "MANWON", "note": "추첨·심사·선착순 정책은 '선정되면 최대'로 따로 셉니다"},
        "dataAsOf": AS_OF}),
    "GET_policies_id": (m.PolicyDetailResponse, {"policy": {**JOY, "checklist": ["주민등록초본", "신청서"], "url": "https://example.invalid/busan-policy"}, "dataAsOf": AS_OF}),
    "POST_policies_id_alerts": (m.PolicyAlertResponse, {"alert": {"policyId": "seed-busan-joy-double", "scheduledAt": "2027-08-03T09:00:00+09:00"}, "created": True}),
    "GET_me_preferences": (m.PreferencesView, {"sort": "BUSAN_FIRST", "leaveReason": "SALARY", "notifications": {"email": False, "weekly": False}, "receivingPolicies": []}),
    "PUT_me_preferences": (m.PreferencesView, {"sort": "MATCH", "leaveReason": "SALARY", "notifications": {"email": False, "weekly": False}, "receivingPolicies": []}),
    "POST_saved": (m.SaveResponse, {
        "saved": {"jobPostingId": "alio-DEMO0001", "kind": "TARGET", "status": "PLANNED", "isBusan": True,
                  "savedAt": "2026-11-21T10:12:00+09:00", "workspaceId": "ws-alio-DEMO0001"},
        "schedules": [{"type": "TARGET_DEADLINE", "at": "2026-11-23T09:00:00+09:00", "label": "마감 D-7"},
                      {"type": "TARGET_DEADLINE", "at": "2026-11-27T09:00:00+09:00", "label": "마감 D-3"}],
        "askLeaveReason": False, "created": True}),
    "DELETE_saved_id": (m.UnsaveResponse, {"jobPostingId": "alio-DEMO0001", "deleted": True}),
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


# 응답 모델 없이 핸들러가 dict로 돌려주는 것 (rest_handler.py의 rest_mark_read, rest_track)
PLAIN = {
    "POST_notifications_id_read": {"notificationId": "20261123T090000-a1b2c3d4", "read": True},
    "POST_track": {"recorded": True},
}


def build() -> dict[str, dict]:
    out = {name: model.model_validate(raw).to_api() for name, (model, raw) in MOCKS.items()}
    out.update(PLAIN)
    out["ERROR_404"] = ERROR
    return out


if __name__ == "__main__":
    for name, body in build().items():
        (HERE / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name)
