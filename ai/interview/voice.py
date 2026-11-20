"""음성 함수: 질문 음성(Polly), 답변 변환(Transcribe) (voice design §3~§6, Requirement 1~3).

- boto3는 처음 호출할 때 import한다. `import interview`는 boto3 없이도 된다 (Requirement 7.3).
- 클라이언트는 프로세스에서 한 번 만든다. 테스트는 _polly_client 등을 가짜로 바꾼다.
- 로그에는 단계, 처리 시간, 오류 코드만 남긴다. 질문 문장과 mp3는 남기지 않는다.
"""

import json
import logging
import time
from urllib.parse import unquote, urlparse

from . import settings
from .errors import AWS_SERVICE_ERROR, INVALID_INPUT, InterviewError

logger = logging.getLogger("interview")

STAGE_SYNTHESIZE = "synthesize_question"
STAGE_START = "start_transcription"
STAGE_RESULT = "get_transcription_result"

TRANSCRIBE_INPUT_MESSAGE = "답변 음성 정보를 확인할 수 없어요. 다시 녹음해 주세요."
TRANSCRIBE_MESSAGE = "답변 음성을 변환하지 못했어요. 다시 시도해 주세요."

# GetTranscriptionJob 일시 오류: IN_PROGRESS로 돌려 백엔드가 2초 뒤 다시 조회하게 한다 (voice design §6)
_TRANSIENT_CODES = frozenset({"ThrottlingException", "LimitExceededException", "InternalFailureException",
                              "ServiceUnavailableException", "RequestTimeout", "RequestTimeoutException"})

IN_PROGRESS = {"status": "IN_PROGRESS"}
FAILED = {"status": "FAILED"}

_clients: dict = {}


def _client(service: str):
    if service not in _clients:
        import boto3  # 지연 import

        _clients[service] = boto3.client(service, region_name=settings.region())
    return _clients[service]


def _polly_client():
    return _client("polly")


def _transcribe_client():
    return _client("transcribe")


def _s3_client():
    return _client("s3")


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


def _is_connection_error(exc: Exception) -> bool:
    """botocore 연결·시간 초과 오류 (ClientError가 아닌 BotoCoreError)."""
    try:
        from botocore.exceptions import BotoCoreError
    except ImportError:
        return False
    return isinstance(exc, BotoCoreError)


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


# ---------------------------------------------------------------- 답변 변환 시작


def _blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def start_transcription(s3_uri, job_name, media_format, output_bucket, output_key):
    """녹음 변환 작업을 시작하고 job_name을 돌려준다 (Requirement 2).

    결과는 백엔드가 정한 output_bucket·output_key에 저장된다 (★ 백엔드와의 약속). 함수가 경로를 정하지 않는다.
    """
    started = time.monotonic()
    args = (s3_uri, job_name, media_format, output_bucket, output_key)
    if any(_blank(v) for v in args) or not s3_uri.startswith("s3://") or media_format not in settings.MEDIA_FORMATS:
        logger.warning("stage=%s errorCode=%s", STAGE_START, INVALID_INPUT)
        raise InterviewError(INVALID_INPUT, TRANSCRIBE_INPUT_MESSAGE)
    try:
        _transcribe_client().start_transcription_job(
            TranscriptionJobName=job_name, LanguageCode=settings.LANGUAGE_CODE, MediaFormat=media_format,
            Media={"MediaFileUri": s3_uri}, OutputBucketName=output_bucket, OutputKey=output_key)
    except Exception as exc:  # noqa: BLE001
        code = _aws_error_code(exc)
        if code == "ConflictException":  # 같은 이름의 작업이 이미 있다 → 재시도로 보고 성공 처리
            logger.info("stage=%s awsError=%s durationMs=%d", STAGE_START, code, _ms(started))
            return job_name
        retryable = code != "BadRequestException"
        logger.warning("stage=%s errorCode=%s awsError=%s retryable=%s durationMs=%d",
                       STAGE_START, AWS_SERVICE_ERROR, code, retryable, _ms(started))
        raise InterviewError(AWS_SERVICE_ERROR, TRANSCRIBE_MESSAGE, retryable=retryable) from None
    logger.info("stage=%s durationMs=%d", STAGE_START, _ms(started))
    return job_name


# ---------------------------------------------------------------- 변환 결과 조회


def _split_s3_uri(uri: str) -> tuple[str, str]:
    """TranscriptFileUri → (버킷, 키). 경로형과 가상 호스트형 https 주소를 받는다."""
    parsed = urlparse(uri)
    host, path = parsed.netloc, parsed.path.lstrip("/")
    if parsed.scheme != "https" or not host:
        raise ValueError("not https")
    if host.startswith(("s3.", "s3-")):           # https://s3.<region>.amazonaws.com/<bucket>/<key>
        bucket, _, key = path.partition("/")
    elif ".s3." in host or ".s3-" in host:        # https://<bucket>.s3.<region>.amazonaws.com/<key>
        bucket, key = host.split(".s3", 1)[0], path
    else:
        raise ValueError("not s3")
    if not bucket or not key:
        raise ValueError("missing bucket or key")
    return bucket, unquote(key)


def parse_transcript(doc) -> dict:
    """Transcript_File(JSON) → {"status": "COMPLETED", "text", "words"} (Requirement 3.4·3.5)."""
    results = doc["results"]
    transcripts = results.get("transcripts") or []
    text = transcripts[0].get("transcript", "") if transcripts else ""
    if not isinstance(text, str):
        raise ValueError("transcript is not text")
    words = []
    for item in results.get("items") or []:
        if item.get("type") != "pronunciation":  # 문장부호 항목은 시간이 없다
            continue
        words.append({"word": item["alternatives"][0]["content"], "start": float(item["start_time"]),
                      "end": float(item["end_time"])})
    return {"status": "COMPLETED", "text": text, "words": words}


def _result_log(status: str, started: float, code: str | None = None, level=logging.INFO) -> None:
    if code is None:
        logger.log(level, "stage=%s status=%s durationMs=%d", STAGE_RESULT, status, _ms(started))
    else:
        logger.log(level, "stage=%s status=%s awsError=%s durationMs=%d", STAGE_RESULT, status, code, _ms(started))


def get_transcription_result(job_name):
    """변환 상태를 보고, 끝났으면 결과 파일을 S3에서 읽어 돌려준다 (Requirement 3).

    예외를 던지지 않는다. 읽지 못하면 FAILED(→ process_answer가 TRANSCRIBE_FAILED로 기록하고 면접 계속),
    일시 오류면 IN_PROGRESS(→ 백엔드가 다시 조회, 240초가 지나면 실패 처리)를 돌려준다 (voice 결정 2).
    백엔드 task_answer가 이 함수 직후 결과 파일을 지우므로 결과는 같은 호출 안에서 읽는다.
    """
    started = time.monotonic()
    if _blank(job_name):
        _result_log("FAILED", started, "InvalidJobName", logging.WARNING)
        return dict(FAILED)
    try:
        job = _transcribe_client().get_transcription_job(TranscriptionJobName=job_name)["TranscriptionJob"]
    except Exception as exc:  # noqa: BLE001
        code = _aws_error_code(exc)
        if code in _TRANSIENT_CODES or _is_connection_error(exc):
            _result_log("IN_PROGRESS", started, code, logging.WARNING)
            return dict(IN_PROGRESS)
        _result_log("FAILED", started, code, logging.WARNING)  # BadRequest(작업 없음 포함), NotFound, 권한 등
        return dict(FAILED)

    status = job.get("TranscriptionJobStatus")
    if status in ("QUEUED", "IN_PROGRESS"):
        return dict(IN_PROGRESS)
    if status != "COMPLETED":  # FAILED. FailureReason은 로그에 남기지 않는다
        _result_log("FAILED", started, "JobFailed", logging.WARNING)
        return dict(FAILED)
    try:
        bucket, key = _split_s3_uri((job.get("Transcript") or {}).get("TranscriptFileUri") or "")
        body = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
        result = parse_transcript(json.loads(body))
    except Exception as exc:  # noqa: BLE001 — URI·S3·JSON·형식 오류 모두 변환 실패로 본다
        _result_log("FAILED", started, _aws_error_code(exc), logging.WARNING)
        return dict(FAILED)
    _result_log("COMPLETED", started)
    return result
