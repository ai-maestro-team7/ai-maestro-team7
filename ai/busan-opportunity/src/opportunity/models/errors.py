"""B가 내는 오류. 입구(REST·Agent)가 팀 공통 형식 `error{code, message, requestId, retryable}`으로 바꾼다."""


class OppError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def invalid_input(message: str, **details) -> OppError:
    return OppError(400, "INVALID_INPUT", message, False, details)


def posting_not_found(job_posting_id: str) -> OppError:
    return OppError(404, "POSTING_NOT_FOUND", "공고를 찾을 수 없어요.", False, {"jobPostingId": job_posting_id})


def policy_not_found(policy_id: str) -> OppError:
    return OppError(404, "POLICY_NOT_FOUND", "정책을 찾을 수 없어요.", False, {"policyId": policy_id})


def profile_incomplete(missing_fields: list[str]) -> OppError:
    return OppError(422, "PROFILE_INCOMPLETE", "프로필에 필요한 정보가 없어 추천할 수 없어요.", False,
                    {"missingFields": missing_fields})


def precondition_not_met(message: str, **details) -> OppError:
    return OppError(409, "PRECONDITION_NOT_MET", message, False, details)


def ai_output_invalid(message: str = "AI 응답 형식이 올바르지 않아요.") -> OppError:
    return OppError(500, "AI_OUTPUT_INVALID", message, True)


def aws_service_error(service: str) -> OppError:
    return OppError(503, "AWS_SERVICE_ERROR", "잠시 후 다시 시도해 주세요.", True, {"service": service})
