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


def model_id() -> str:
    value = os.environ.get("MODEL_ID", "").strip()
    if not value:
        raise InterviewError(AWS_SERVICE_ERROR, CONFIG_ERROR_MESSAGE, retryable=False)
    return value


def region() -> str:
    return os.environ.get("AWS_REGION", "").strip() or DEFAULT_REGION


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
