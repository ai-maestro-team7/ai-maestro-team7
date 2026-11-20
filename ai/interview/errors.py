"""면접 함수 오류 (C ★ "백엔드와의 약속", C §5.1).

백엔드는 code·message·retryable 속성만 읽어 팀 공통 오류 형식으로 바꾼다
(backend/interview_api.py, team07_contracts.interview_error_to_envelope).
message는 화면에 보여 줄 한국어 문장이고, 자소서·답변·LLM 출력 원문을 넣지 않는다.
"""

INVALID_INPUT = "INVALID_INPUT"
AI_OUTPUT_INVALID = "AI_OUTPUT_INVALID"
AWS_SERVICE_ERROR = "AWS_SERVICE_ERROR"

DEFAULT_RETRYABLE: dict[str, bool] = {
    INVALID_INPUT: False,
    AI_OUTPUT_INVALID: True,
    AWS_SERVICE_ERROR: True,
}


class InterviewError(Exception):
    """면접 함수가 밖으로 내는 유일한 오류.

    retryable을 주지 않으면 code별 기본값을 쓴다 (C §5.1 오류 코드 표).
    """

    def __init__(self, code: str, message: str, retryable: bool | None = None):
        if code not in DEFAULT_RETRYABLE:
            raise ValueError(f"unknown interview error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = DEFAULT_RETRYABLE[code] if retryable is None else bool(retryable)

    def __repr__(self) -> str:
        return f"InterviewError(code={self.code!r}, retryable={self.retryable!r})"
