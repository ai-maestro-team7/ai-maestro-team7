"""가상 이력서와 모델 응답. 통합 데모 직무는 데이터 분석(NCS 빅데이터분석 20010105)이다 (D-37).
이름·연락처·학교는 모두 가상이다.
"""

DATA_ANALYST_RESUME = """가상 지원자 A
연락처: 010-0000-1234 / 이메일: applicant-a@example.com

[학력]
가상대학교 통계학과 졸업 예정 (2027년 2월)

[프로젝트]
부산 버스 이용 데이터 분석 프로젝트 (2025.03~2025.06)
- 팀원 4명 중 데이터 전처리와 시각화를 맡았습니다.
- Python pandas로 결측치를 처리하고 정류장별 이용량을 집계했습니다.
- 분석 결과를 Tableau 대시보드로 만들어 발표했습니다.

[활동]
교내 데이터 분석 동아리에서 SQL 스터디를 1년 동안 운영했습니다.

[자격]
ADsP(데이터분석 준전문가) 취득

[기타]
머신러닝에 관심이 있어 온라인 강의를 듣고 있습니다."""

QUOTE_PANDAS = "Python pandas로 결측치를 처리하고 정류장별 이용량을 집계했습니다."
QUOTE_TABLEAU = "분석 결과를 Tableau 대시보드로 만들어 발표했습니다."
QUOTE_SQL = "교내 데이터 분석 동아리에서 SQL 스터디를 1년 동안 운영했습니다."
QUOTE_ML = "머신러닝에 관심이 있어 온라인 강의를 듣고 있습니다."
QUOTE_PROJECT = "부산 버스 이용 데이터 분석 프로젝트 (2025.03~2025.06)"
QUOTE_CERT = "ADsP(데이터분석 준전문가) 취득"


def good_output() -> dict:
    """원문 근거가 모두 맞는 모델 응답. 위치는 일부러 비우거나 틀리게 둬서 다시 찾는지도 본다."""
    return {
        "skills": [
            {"name": "데이터 전처리", "evidenceLevel": "EVIDENCED", "ncsUnitCode": "2001010501_23v2",
             "quotes": [{"quotedText": QUOTE_PANDAS, "startChar": None, "endChar": None}]},
            {"name": "데이터 시각화", "evidenceLevel": "EVIDENCED",
             "quotes": [{"quotedText": QUOTE_TABLEAU, "startChar": 0, "endChar": 10}]},
            {"name": "SQL", "evidenceLevel": "PARTIAL", "quotes": [{"quotedText": QUOTE_SQL}]},
            {"name": "머신러닝", "evidenceLevel": "SELF_REPORTED", "quotes": [{"quotedText": QUOTE_ML}]},
            {"name": "통계 분석", "evidenceLevel": "NOT_FOUND", "quotes": []},
        ],
        "projects": [{"name": "부산 버스 이용 데이터 분석 프로젝트", "summary": "정류장별 이용량 집계와 대시보드 발표",
                      "period": "2025.03~2025.06", "quotes": [{"quotedText": QUOTE_PROJECT}]}],
        "experiences": [{"name": "데이터 분석 동아리 SQL 스터디 운영", "summary": None, "period": "1년",
                         "quotes": [{"quotedText": QUOTE_SQL}]}],
        "certificates": [{"name": "ADsP", "quotes": [{"quotedText": QUOTE_CERT}]}],
        "needsConfirmation": ["프로젝트에서 본인이 직접 만든 시각화 범위"],
    }
