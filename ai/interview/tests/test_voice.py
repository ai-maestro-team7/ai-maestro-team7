"""음성 함수 단위 테스트. Polly·Transcribe·S3는 가짜 클라이언트로 바꾼다 (AWS를 부르지 않는다)."""

import logging

import pytest

from fakes import FakePolly, client_error
from interview import voice

QUESTION = "팀 프로젝트에서 의견이 갈렸을 때 어떻게 해결했나요?"


@pytest.fixture
def polly(monkeypatch):
    fake = FakePolly()
    monkeypatch.setattr(voice, "_polly_client", lambda: fake)
    return fake


# ---------------------------------------------------------------- synthesize_question


def test_synthesize_calls_polly_korean_mp3(polly):
    audio = voice.synthesize_question(QUESTION)
    assert audio == b"ID3fake-mp3"
    assert polly.calls == [{"Text": QUESTION, "TextType": "text", "OutputFormat": "mp3", "VoiceId": "Seoyeon",
                            "Engine": "neural", "LanguageCode": "ko-KR"}]


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None, 123])
def test_synthesize_blank_returns_none_without_call(polly, text):
    assert voice.synthesize_question(text) is None
    assert polly.calls == []


@pytest.mark.parametrize("error", [client_error("ThrottlingException"), client_error("AccessDeniedException"),
                                   RuntimeError("network")])
def test_synthesize_failure_returns_none(monkeypatch, caplog, error):
    monkeypatch.setattr(voice, "_polly_client", lambda: FakePolly(error=error))
    with caplog.at_level(logging.INFO, logger="interview"):
        assert voice.synthesize_question(QUESTION) is None
    assert "stage=synthesize_question errorCode=AWS_SERVICE_ERROR" in caplog.text
    assert QUESTION not in caplog.text


def test_synthesize_client_creation_failure_returns_none(monkeypatch):
    def broken():
        raise ImportError("no boto3")

    monkeypatch.setattr(voice, "_polly_client", broken)
    assert voice.synthesize_question(QUESTION) is None


def test_synthesize_empty_audio_returns_none(monkeypatch):
    monkeypatch.setattr(voice, "_polly_client", lambda: FakePolly(audio=b""))
    assert voice.synthesize_question(QUESTION) is None


def test_synthesize_logs_no_question_text(polly, caplog):
    with caplog.at_level(logging.DEBUG, logger="interview"):
        voice.synthesize_question(QUESTION)
    assert "stage=synthesize_question" in caplog.text and QUESTION not in caplog.text


def test_aws_error_code():
    assert voice._aws_error_code(client_error("ConflictException")) == "ConflictException"
    assert voice._aws_error_code(RuntimeError("비밀 문장")) == "RuntimeError"
