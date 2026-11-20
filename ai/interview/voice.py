"""음성 함수: 질문 음성(Polly) (voice design §3·§4, Requirement 1).

- boto3는 처음 호출할 때 import한다. `import interview`는 boto3 없이도 된다 (Requirement 7.3).
- 클라이언트는 프로세스에서 한 번 만든다. 테스트는 _polly_client 등을 가짜로 바꾼다.
- 로그에는 단계, 처리 시간, 오류 코드만 남긴다. 질문 문장과 mp3는 남기지 않는다.
"""

import logging
import time

from . import settings
from .errors import AWS_SERVICE_ERROR

logger = logging.getLogger("interview")

STAGE_SYNTHESIZE = "synthesize_question"

_clients: dict = {}


def _client(service: str):
    if service not in _clients:
        import boto3  # 지연 import

        _clients[service] = boto3.client(service, region_name=settings.region())
    return _clients[service]


def _polly_client():
    return _client("polly")


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _aws_error_code(exc: Exception) -> str:
    """botocore ClientError면 AWS 오류 코드, 아니면 예외 종류 이름. 메시지는 쓰지 않는다 (원문이 섞일 수 있음)."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        if code:
            return str(code)
    return type(exc).__name__


# ---------------------------------------------------------------- 질문 음성


def synthesize_question(text):
    """질문 문장 → mp3 bytes. 실패하면 None을 돌려준다 (voice 결정 1).

    None이면 백엔드 save_next_question이 음성을 올리지 않아 audioUrl이 null이 되고,
    화면은 자막과 [답변 시작]으로 진행한다 (C F-04). 예외를 던지면 면접 세션이 FAILED가 된다.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    started = time.monotonic()
    try:
        response = _polly_client().synthesize_speech(
            Text=text, TextType="text", OutputFormat=settings.POLLY_OUTPUT_FORMAT,
            VoiceId=settings.POLLY_VOICE_ID, Engine=settings.POLLY_ENGINE, LanguageCode=settings.LANGUAGE_CODE)
        audio = response["AudioStream"].read()
    except Exception as exc:  # noqa: BLE001 — 권한, 한도, 네트워크, SDK 없음 모두 음성 없이 진행
        logger.warning("stage=%s errorCode=%s awsError=%s durationMs=%d",
                       STAGE_SYNTHESIZE, AWS_SERVICE_ERROR, _aws_error_code(exc), _ms(started))
        return None
    if not audio:
        logger.warning("stage=%s errorCode=%s awsError=EmptyAudio durationMs=%d",
                       STAGE_SYNTHESIZE, AWS_SERVICE_ERROR, _ms(started))
        return None
    logger.info("stage=%s bytes=%d durationMs=%d", STAGE_SYNTHESIZE, len(audio), _ms(started))
    return audio
