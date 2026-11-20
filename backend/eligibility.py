"""공고 지원 자격 판정 — A(직무 적합도)와 B(공고 상세)가 같이 쓰는 단 하나의 함수.

공고 조건(eligibilityRules)은 B가 catalog 스냅샷에 저장하고, 판정은 이 함수만 한다.
같은 입력이면 어느 파트가 불러도 같은 결과가 나온다 (규칙 코드, LLM 없음).

조건별 결과 (B 방식): MET / NOT_MET / UNKNOWN
전체 결과 (A 방식):  ELIGIBLE / INELIGIBLE / NEEDS_VERIFICATION
  - 하나라도 NOT_MET → INELIGIBLE
  - 아니고 하나라도 UNKNOWN → NEEDS_VERIFICATION
  - 조건이 아직 없으면(추출 전) → NEEDS_VERIFICATION
  - 모두 MET → ELIGIBLE

A 원칙 "서류에 없음 ≠ 없음": 자격증이 프로필에 없다고 NOT_MET으로 보지 않는다.
사용자가 '없다'고 확인한 경우(confirmedMissingCertificates)에만 NOT_MET.
"""

RULE_VERSION = "elig-v1"

EDUCATION_ORDER = {"NONE": 0, "HIGH_SCHOOL": 1, "ASSOCIATE": 2, "BACHELOR": 3, "MASTER": 4, "DOCTOR": 5}


def _norm(text):
    return "".join(str(text).lower().split())


def _education(rule, profile):
    need = EDUCATION_ORDER.get(rule.get("value", "NONE"))
    have = EDUCATION_ORDER.get(profile.get("educationLevel"))
    if need is None:
        return "UNKNOWN", "공고의 학력 조건을 해석하지 못했어요"
    if need == 0:
        return "MET", "학력 무관"
    if have is None:
        return "UNKNOWN", "프로필에 학력이 없어요"
    return ("MET", "학력 조건 충족") if have >= need else ("NOT_MET", "요구 학력보다 낮아요")


def _career(rule, profile):
    value = rule.get("value") or {}
    if value.get("type") in ("NEW", "ANY", None):
        return "MET", "신입 지원 가능" if value.get("type") == "NEW" else "경력 무관"
    years = profile.get("careerYears")
    if years is None:
        return "UNKNOWN", "프로필에 경력 기간이 없어요"
    need = value.get("minYears") or 0
    return ("MET", f"경력 {need}년 이상 충족") if years >= need else ("NOT_MET", f"경력 {need}년 이상이 필요해요")


def _certificate(rule, profile):
    name = rule.get("value")
    have = {_norm(c) for c in profile.get("certificates") or []}
    missing = {_norm(c) for c in profile.get("confirmedMissingCertificates") or []}
    if _norm(name) in have:
        return "MET", f"{name} 보유"
    if _norm(name) in missing:
        return "NOT_MET", f"{name}이(가) 필요해요"
    return "UNKNOWN", f"{name} 보유 여부를 확인해 주세요"


def _major(rule, profile):
    majors = rule.get("value") or []
    mine = profile.get("major")
    if not majors:
        return "MET", "전공 무관"
    if not mine:
        return "UNKNOWN", "프로필에 전공이 없어요"
    ok = any(_norm(m) in _norm(mine) or _norm(mine) in _norm(m) for m in majors)
    return ("MET", "전공 조건 충족") if ok else ("NOT_MET", "요구 전공과 달라요")


CHECKS = {"EDUCATION": _education, "CAREER": _career, "CERTIFICATE": _certificate, "MAJOR": _major}


def evaluate_eligibility(profile, rules):
    """profile: PROFILE#BASIC + (있으면) 역량 프로필의 certificates 등을 합친 dict
    rules:   catalog SNAP#의 eligibilityRules[] — {ruleId, type, value, sourceQuote}
    """
    profile = profile or {}
    conditions = []
    for rule in rules or []:
        check = CHECKS.get(rule.get("type"))
        result, reason = check(rule, profile) if check else ("UNKNOWN", "직접 확인이 필요한 조건이에요")
        conditions.append({"ruleId": rule.get("ruleId"), "type": rule.get("type"), "result": result,
                           "reason": reason, "sourceQuote": rule.get("sourceQuote")})

    results = {c["result"] for c in conditions}
    if not conditions or "UNKNOWN" in results and "NOT_MET" not in results:
        status = "NEEDS_VERIFICATION"
    elif "NOT_MET" in results:
        status = "INELIGIBLE"
    else:
        status = "ELIGIBLE"
    return {"status": status, "conditions": conditions,
            "unknown": [c["ruleId"] for c in conditions if c["result"] == "UNKNOWN"], "ruleVersion": RULE_VERSION}
