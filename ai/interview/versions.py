"""결과에 남기는 버전 (AGENTS.md "AI·데이터 규칙", design §7.4).

프롬프트 파일을 바꾸면 파일 이름(`*_v1.md`)과 여기 버전을 같이 올린다.
"""

SCORING_VERSION = "v1.0"  # C §3 점수 설정 파일 버전. 점수 계산은 3차
PROMPT_A_VERSION = "A-v2"  # 질문 생성
PROMPT_B_VERSION = "B-v1"  # 꼬리질문 판단
PROMPT_VERSION = f"{PROMPT_A_VERSION}/{PROMPT_B_VERSION}"  # Session에 남기는 값 (질문 생성·꼬리질문)

PROMPT_EVAL_SYSTEM_VERSION = "E-v1"  # C-1·C-2 공통 시스템 프롬프트 (system_eval_v1.md)
PROMPT_C1_VERSION = "C1-v1"  # 내용 평가 (평가표를 바꿔도 올린다)
PROMPT_C2_VERSION = "C2-v1"  # 피드백
REPORT_PROMPT_VERSION = f"{PROMPT_C1_VERSION}/{PROMPT_C2_VERSION}"  # 리포트에 남기는 값
