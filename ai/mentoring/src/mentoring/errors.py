"""A가 내는 오류. 입구(REST·작업)가 팀 공통 형식 `error{code, message, requestId, retryable, details}`로 바꾼다.
사용자에게 보이는 message는 한국어다. details에 원문·인용문·사용자 ID를 넣지 않는다 (Requirement 1 기준 6, 12 기준 2).
"""


class MentoringError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def invalid_input(message: str, **details) -> MentoringError:
    return MentoringError(400, "INVALID_INPUT", message, False, details)


def unauthorized() -> MentoringError:
    return MentoringError(401, "UNAUTHORIZED", "로그인이 필요해요.")


def document_not_found() -> MentoringError:
    """없는 문서와 남의 문서를 구분하지 않는다 (docs/api.md §5, Requirement 2 기준 3)."""
    return MentoringError(404, "DOCUMENT_NOT_FOUND", "문서를 찾을 수 없어요.")


def not_found(message: str = "찾을 수 없어요.") -> MentoringError:
    return MentoringError(404, "NOT_FOUND", message)


def precondition_not_met(message: str, **details) -> MentoringError:
    return MentoringError(409, "PRECONDITION_NOT_MET", message, False, details)


def document_unreadable() -> MentoringError:
    return MentoringError(422, "DOCUMENT_UNREADABLE", "문서를 읽을 수 없어요. 텍스트로 직접 입력해 주세요.")


def ai_output_invalid() -> MentoringError:
    return MentoringError(500, "AI_OUTPUT_INVALID", "분석 결과 형식이 올바르지 않아요. 잠시 후 다시 시도해 주세요.", True)


def aws_service_error(service: str) -> MentoringError:
    return MentoringError(503, "AWS_SERVICE_ERROR", "잠시 후 다시 시도해 주세요.", True, {"service": service})


def not_implemented() -> MentoringError:
    return MentoringError(501, "NOT_IMPLEMENTED", "아직 준비 중인 기능이에요.")
