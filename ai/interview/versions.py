"""결과에 남기는 버전 (AGENTS.md "AI·데이터 규칙", design §7.4).

프롬프트 파일을 바꾸면 파일 이름(`*_v1.md`)과 여기 버전을 같이 올린다.
"""

SCORING_VERSION = "v1.0"  # C §3 점수 설정 파일 버전. 점수 계산은 3차
PROMPT_A_VERSION = "A-v1"  # 질문 생성
PROMPT_B_VERSION = "B-v1"  # 꼬리질문 판단
PROMPT_VERSION = f"{PROMPT_A_VERSION}/{PROMPT_B_VERSION}"
