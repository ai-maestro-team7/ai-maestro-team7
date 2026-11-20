import pytest

from interview.errors import (AI_OUTPUT_INVALID, AWS_SERVICE_ERROR, DEFAULT_RETRYABLE, INVALID_INPUT,
                              InterviewError)


def test_only_three_codes():
    assert set(DEFAULT_RETRYABLE) == {INVALID_INPUT, AI_OUTPUT_INVALID, AWS_SERVICE_ERROR}


@pytest.mark.parametrize("code, expected", [
    (INVALID_INPUT, False),
    (AI_OUTPUT_INVALID, True),
    (AWS_SERVICE_ERROR, True),
])
def test_default_retryable_per_code(code, expected):
    assert InterviewError(code, "msg").retryable is expected


def test_explicit_retryable_overrides_default():
    err = InterviewError(AWS_SERVICE_ERROR, "msg", retryable=False)
    assert err.retryable is False


def test_attributes_and_str():
    err = InterviewError(INVALID_INPUT, "입력을 확인해 주세요.")
    assert err.code == INVALID_INPUT
    assert err.message == "입력을 확인해 주세요."
    assert str(err) == "입력을 확인해 주세요."
    assert isinstance(err, Exception)


def test_repr_has_no_message():
    err = InterviewError(INVALID_INPUT, "자소서 원문이 들어가면 안 되는 자리")
    assert "자소서" not in repr(err)


def test_unknown_code_rejected():
    with pytest.raises(ValueError):
        InterviewError("SOMETHING_ELSE", "msg")


def test_backend_style_attribute_access():
    # backend/interview_api.py는 getattr로 code·message·retryable을 읽는다
    err = InterviewError(AI_OUTPUT_INVALID, "질문을 만들지 못했어요.")
    assert getattr(err, "code", None) == AI_OUTPUT_INVALID
    assert getattr(err, "retryable", None) is True


def test_contract_envelope_conversion():
    # 계약 패키지의 변환 함수가 그대로 받아들인다 (team07_contracts.interview_error_to_envelope)
    from team07_contracts import interview_error_to_envelope

    env = interview_error_to_envelope(InterviewError(INVALID_INPUT, "입력을 확인해 주세요."), "req-1")
    body = env.model_dump(by_alias=True)["error"]
    assert body["code"] == INVALID_INPUT
    assert body["retryable"] is False
    assert body["requestId"] == "req-1"
