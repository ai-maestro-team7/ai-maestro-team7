"""설정 값 (design §8).

환경변수는 import할 때가 아니라 호출할 때 읽는다. 그래서 MODEL_ID가 없어도 `import interview`는 된다.
모델 ID는 코드에 기본값을 두지 않는다. 배포 값은 infra/config.sh가 정한다 (기본 Haiku, 시연 Sonnet).
"""

import os

from .errors import AWS_SERVICE_ERROR, InterviewError

DEFAULT_REGION = "ap-northeast-2"
DEFAULT_MAX_TOKENS = 1024

# 입력 한도 (C §5.2, 계약 InterviewJobContext)
JOB_MIN, JOB_MAX = 1, 50
RESUME_MIN, RESUME_MAX = 50, 5000

# LLM이 만든 질문 문장 길이 (design §8 제안 값)
QUESTION_MIN, QUESTION_MAX = 5, 300

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


def max_tokens() -> int:
    raw = os.environ.get("INTERVIEW_MAX_TOKENS", "").strip()
    if not raw:
        return DEFAULT_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise InterviewError(AWS_SERVICE_ERROR, CONFIG_ERROR_MESSAGE, retryable=False)
    return value
