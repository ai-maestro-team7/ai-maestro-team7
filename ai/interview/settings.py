"""설정 값 (design §8).

환경변수는 import할 때가 아니라 호출할 때 읽는다. 그래서 MODEL_ID가 없어도 `import interview`는 된다.
모델 ID는 코드에 기본값을 두지 않는다. 배포 값은 infra/config.sh가 정한다 (기본 Haiku, 시연 Sonnet).
"""

import os

from .errors import AWS_SERVICE_ERROR, InterviewError

DEFAULT_REGION = "ap-northeast-2"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_FEEDBACK_MAX_TOKENS = 2048

# 피드백 에이전트 상한 (report design §6.2·§6.5). 리포트는 변환 대기와 같은 Lambda 실행(300초) 안에서 만든다
FEEDBACK_MAX_TURNS = 6            # 모델 호출 + 툴 실행 한 번이 한 턴
FEEDBACK_MAX_TOTAL_TOKENS = 30000  # 한 번 실행의 입력+출력 토큰 합
FEEDBACK_MAX_TOOL_CALLS = 12       # 넘으면 툴이 "지금까지 정보로 답하라"를 돌려준다
# 꼬리질문 판단 에이전트 상한 (follow-up design §4.4, #109). 기본 답변마다 사용자가 기다리는 시간을 묶는다
FOLLOW_UP_MAX_TURNS = 4             # 툴 2~3개를 한 턴에 같이 부르고 답을 쓰면 2~3턴
FOLLOW_UP_MAX_TOOL_CALLS = 4        # 툴 3개 + 키워드 다시 찾기 1번
FOLLOW_UP_MAX_TOTAL_TOKENS = 12000  # 자소서(최대 5,000자)·이전 답변이 턴마다 다시 들어간다
DEFAULT_FOLLOW_UP_MAX_TOKENS = 1024  # 출력은 판단 JSON 하나
# 이전 답변 툴이 돌려주는 양 (기본 2 + 꼬리 2 + 여유)
FOLLOW_UP_PREVIOUS_MAX = 5
FOLLOW_UP_ANSWER_MAX_CHARS = 500
# 피드백 문장에 쓰지 않는 표현 (제품 원칙 4, AGENTS.md "문구"). "떨어지다"는 일반 표현이라 넣지 않는다
FEEDBACK_BANNED_WORDS = ("합격", "불합격", "확률")

# 입력 한도 (C §5.2, 계약 InterviewJobContext)
JOB_MIN, JOB_MAX = 1, 50
RESUME_MIN, RESUME_MAX = 50, 5000

# LLM이 만든 질문 문장 길이 (design §8 제안 값)
QUESTION_MIN, QUESTION_MAX = 5, 300
# 꼬리질문 후보 길이 상한 (공백 포함, follow-up 결정 7). 프롬프트는 "100자 안팎", 넘는 후보는 버린다
FOLLOW_UP_QUESTION_MAX = 150

# 면접 고정 규칙 (C §4.2)
BASE_QUESTION_COUNT = 3

CONFIG_ERROR_MESSAGE = "면접 설정에 문제가 있어요. 관리자에게 알려 주세요."

# 생각(thinking) 끄기 (design §6.2·§8, #58).
# Claude 5 이후 모델은 요청에 thinking을 빼면 adaptive thinking으로 돌고, 생각 토큰도 max_tokens에 들어간다.
# 질문 생성·꼬리질문 판단은 짧은 JSON이라 생각을 끈다. 끄는 값은 모델마다 다르다
# (Bedrock 사용자 가이드 "Adaptive thinking" > "Thinking configuration by model").
#   Haiku 5.5: {"type": "disabled"}
#   Sonnet 5.5: disabled는 400 오류. 가장 낮은 값이 between_tools(응답 전 생각 끔)이고, 도구를 안 쓰므로 생각하지 않는다.
# 표에 없는 모델은 thinking을 보내지 않는다 (모델 기본 동작). 잘못된 값을 보내면 400이 나기 때문이다.
THINKING_OFF_BY_MODEL: tuple[tuple[str, dict], ...] = (
    ("claude-haiku-5-5", {"type": "disabled"}),
    ("claude-sonnet-5-5", {"type": "between_tools"}),
)


# 음성 (voice design §4·§5, C §11: Polly Seoyeon·Transcribe 한국어 확인됨)
LANGUAGE_CODE = "ko-KR"
POLLY_VOICE_ID = "Seoyeon"
POLLY_ENGINE = "neural"  # 확정: 서울 리전 수동 확인에서 생성 0.8초, 자연스러움 (#74, voice design §15-4)
POLLY_OUTPUT_FORMAT = "mp3"
# Transcribe StartTranscriptionJob MediaFormat 허용 값
MEDIA_FORMATS = frozenset({"mp3", "mp4", "m4a", "wav", "flac", "ogg", "amr", "webm"})


def model_id() -> str:
    value = os.environ.get("MODEL_ID", "").strip()
    if not value:
        raise InterviewError(AWS_SERVICE_ERROR, CONFIG_ERROR_MESSAGE, retryable=False)
    return value


def region() -> str:
    return os.environ.get("AWS_REGION", "").strip() or DEFAULT_REGION


def thinking_off(model_id_value: str) -> dict | None:
    """모델 ID에 맞는 '생각 끄기' thinking 값. 모르는 모델이면 None (요청에 넣지 않는다)."""
    for family, thinking in THINKING_OFF_BY_MODEL:
        if family in model_id_value:
            return dict(thinking)
    return None


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise InterviewError(AWS_SERVICE_ERROR, CONFIG_ERROR_MESSAGE, retryable=False)
    return value


def max_tokens() -> int:
    """질문 생성·꼬리질문 판단·내용 평가(C-1)의 호출당 출력 상한."""
    return _positive_int_env("INTERVIEW_MAX_TOKENS", DEFAULT_MAX_TOKENS)


def feedback_max_tokens() -> int:
    """피드백 에이전트(C-2)의 호출당 출력 상한. 질문 3개 피드백 JSON이 1024를 넘을 수 있다 (report design §6.5)."""
    return _positive_int_env("INTERVIEW_FEEDBACK_MAX_TOKENS", DEFAULT_FEEDBACK_MAX_TOKENS)


def follow_up_max_tokens() -> int:
    """꼬리질문 판단 에이전트의 호출당 출력 상한 (#109)."""
    return _positive_int_env("INTERVIEW_FOLLOW_UP_MAX_TOKENS", DEFAULT_FOLLOW_UP_MAX_TOKENS)
