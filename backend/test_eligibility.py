"""공통 자격 판정 테스트: uv run --no-project --python 3.13 python test_eligibility.py"""

from eligibility import evaluate_eligibility as ev

PROFILE = {"educationLevel": "BACHELOR", "major": "통계학", "certificates": ["SQLD"], "careerYears": 0}
EDU = {"ruleId": "r1", "type": "EDUCATION", "value": "BACHELOR", "sourceQuote": "학사 이상"}
NEW = {"ruleId": "r2", "type": "CAREER", "value": {"type": "NEW"}}
EXP3 = {"ruleId": "r3", "type": "CAREER", "value": {"type": "EXPERIENCED", "minYears": 3}}
ADSP = {"ruleId": "r4", "type": "CERTIFICATE", "value": "ADsP"}
SQLD = {"ruleId": "r5", "type": "CERTIFICATE", "value": "SQLD"}
MAJOR = {"ruleId": "r6", "type": "MAJOR", "value": ["통계", "컴퓨터공학"]}

CASES = [
    ("모두 충족 → ELIGIBLE", PROFILE, [EDU, NEW, SQLD, MAJOR], "ELIGIBLE"),
    ("경력 부족 → INELIGIBLE", PROFILE, [EDU, EXP3], "INELIGIBLE"),
    ("자격증이 프로필에 없음 → NOT_MET 아님, NEEDS_VERIFICATION", PROFILE, [EDU, ADSP], "NEEDS_VERIFICATION"),
    ("없다고 확인한 자격증 → INELIGIBLE", {**PROFILE, "confirmedMissingCertificates": ["ADsP"]}, [ADSP], "INELIGIBLE"),
    ("학력 정보 없음 → NEEDS_VERIFICATION", {"major": "통계"}, [EDU], "NEEDS_VERIFICATION"),
    ("조건 추출 전(빈 목록) → NEEDS_VERIFICATION", PROFILE, [], "NEEDS_VERIFICATION"),
    ("모르는 조건 종류 → NEEDS_VERIFICATION", PROFILE, [{"ruleId": "x", "type": "REGION_TALENT"}], "NEEDS_VERIFICATION"),
    ("NOT_MET과 UNKNOWN이 섞이면 INELIGIBLE 우선", PROFILE, [EXP3, ADSP], "INELIGIBLE"),
]

ok = 0
for name, profile, rules, expected in CASES:
    got = ev(profile, rules)["status"]
    ok += got == expected
    print(f"{'PASS' if got == expected else 'FAIL'} {name} (결과 {got})")
r = ev(PROFILE, [EDU, ADSP])
same = ev(PROFILE, [EDU, ADSP]) == r
print(f"{'PASS' if same else 'FAIL'} 같은 입력 → 같은 결과 (A·B 일관성)")
ok += same
print(f"\n{ok}/{len(CASES) + 1} 통과")
raise SystemExit(0 if ok == len(CASES) + 1 else 1)
