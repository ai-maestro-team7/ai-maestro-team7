"""Agent 패키지 오류. 백엔드가 팀 공통 오류 형식으로 바꾼다 (docs/api.md §5)."""


class SupervisorError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def invalid_input(message: str) -> SupervisorError:
    return SupervisorError(400, "INVALID_INPUT", message)


def session_not_found() -> SupervisorError:
    return SupervisorError(404, "SESSION_NOT_FOUND", "대화를 찾을 수 없어요.")


def message_not_found() -> SupervisorError:
    return SupervisorError(404, "MESSAGE_NOT_FOUND", "메시지를 찾을 수 없어요.")


def document_not_found() -> SupervisorError:
    return SupervisorError(404, "DOCUMENT_NOT_FOUND", "첨부한 문서를 찾을 수 없어요.")


def turn_in_progress() -> SupervisorError:
    return SupervisorError(409, "PRECONDITION_NOT_MET", "이전 답변을 만들고 있어요. 잠시 후 다시 보내 주세요.", True)


def session_full() -> SupervisorError:
    return SupervisorError(409, "PRECONDITION_NOT_MET", "대화가 너무 길어졌어요. 새 대화를 시작해 주세요.")


class OutputInvalid(Exception):
    """모델 답이 스키마나 검사를 통과하지 못했다. 한 번 다시 돌린다."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
