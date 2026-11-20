"""음성 함수 단위 테스트. Polly·Transcribe·S3는 가짜 클라이언트로 바꾼다 (AWS를 부르지 않는다)."""

import json
import logging

import pytest

from conftest import sample_json, sample_text
from fakes import FakePolly, FakeS3, FakeTranscribe, client_error
from interview import voice
from interview.errors import AWS_SERVICE_ERROR, INVALID_INPUT, InterviewError
from interview.models import AnswerResult

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


# ---------------------------------------------------------------- start_transcription

BUCKET = "test-uploads"
AUDIO_URI = f"s3://{BUCKET}/uploads/interview/iv-1/answers/a-q1-1.webm"
OUT_KEY = "uploads/interview/iv-1/transcripts/a-q1-1.json"
JOB = "team07-iv-1-a-q1-1"


def start(*args):
    args = args or (AUDIO_URI, JOB, "webm", BUCKET, OUT_KEY)
    return voice.start_transcription(*args)


@pytest.fixture
def transcribe(monkeypatch):
    fake = FakeTranscribe()
    monkeypatch.setattr(voice, "_transcribe_client", lambda: fake)
    return fake


def test_start_maps_five_backend_args(transcribe):
    assert start() == JOB
    assert transcribe.starts == [{"TranscriptionJobName": JOB, "LanguageCode": "ko-KR", "MediaFormat": "webm",
                                  "Media": {"MediaFileUri": AUDIO_URI}, "OutputBucketName": BUCKET,
                                  "OutputKey": OUT_KEY}]


@pytest.mark.parametrize("fmt", ["mp3", "mp4", "m4a", "wav", "flac", "ogg", "amr", "webm"])
def test_start_accepts_transcribe_formats(transcribe, fmt):
    assert start(AUDIO_URI, JOB, fmt, BUCKET, OUT_KEY) == JOB


@pytest.mark.parametrize("args", [
    (AUDIO_URI, JOB, "aac", BUCKET, OUT_KEY),          # Transcribe가 받지 않는 형식
    (AUDIO_URI, JOB, "WEBM", BUCKET, OUT_KEY),
    ("", JOB, "webm", BUCKET, OUT_KEY),
    ("https://example.com/a.webm", JOB, "webm", BUCKET, OUT_KEY),
    (AUDIO_URI, " ", "webm", BUCKET, OUT_KEY),
    (AUDIO_URI, JOB, "webm", "", OUT_KEY),
    (AUDIO_URI, JOB, "webm", BUCKET, None),
])
def test_start_invalid_input(transcribe, args):
    with pytest.raises(InterviewError) as exc:
        start(*args)
    assert exc.value.code == INVALID_INPUT and exc.value.retryable is False
    assert transcribe.starts == []


def test_start_conflict_is_success(monkeypatch):
    # 같은 이름의 작업이 이미 있다 (백엔드 재시도) → 오류 없이 job_name
    monkeypatch.setattr(voice, "_transcribe_client",
                        lambda: FakeTranscribe(start_error=client_error("ConflictException")))
    assert start() == JOB


@pytest.mark.parametrize("error, retryable", [
    (client_error("BadRequestException"), False),
    (client_error("LimitExceededException"), True),
    (client_error("AccessDeniedException"), True),
    (RuntimeError("network"), True),
])
def test_start_failures(monkeypatch, error, retryable):
    monkeypatch.setattr(voice, "_transcribe_client", lambda: FakeTranscribe(start_error=error))
    with pytest.raises(InterviewError) as exc:
        start()
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is retryable
    assert exc.value.__cause__ is None


# ---------------------------------------------------------------- get_transcription_result

PATH_URI = f"https://s3.ap-northeast-2.amazonaws.com/{BUCKET}/{OUT_KEY}"
NORMAL_DOC = sample_text("transcribe/result_normal.json")


def completed(uri=PATH_URI):
    return {"TranscriptionJobName": JOB, "TranscriptionJobStatus": "COMPLETED", "Transcript": {"TranscriptFileUri": uri}}


def result_with(monkeypatch, responses, s3=None):
    fake_t = FakeTranscribe(get_responses=responses)
    fake_s3 = s3 if s3 is not None else FakeS3(objects={(BUCKET, OUT_KEY): NORMAL_DOC})
    monkeypatch.setattr(voice, "_transcribe_client", lambda: fake_t)
    monkeypatch.setattr(voice, "_s3_client", lambda: fake_s3)
    return voice.get_transcription_result(JOB), fake_t, fake_s3


@pytest.mark.parametrize("status", ["QUEUED", "IN_PROGRESS"])
def test_result_in_progress(monkeypatch, status):
    tr, _, s3 = result_with(monkeypatch, [{"TranscriptionJobName": JOB, "TranscriptionJobStatus": status}])
    assert tr == {"status": "IN_PROGRESS"} and s3.gets == []


def test_result_failed_job_hides_reason(monkeypatch, caplog):
    job = {"TranscriptionJobName": JOB, "TranscriptionJobStatus": "FAILED", "FailureReason": "비밀 실패 사유"}
    with caplog.at_level(logging.DEBUG, logger="interview"):
        tr, _, _ = result_with(monkeypatch, [job])
    assert tr == {"status": "FAILED"}
    assert "비밀 실패 사유" not in caplog.text


@pytest.mark.parametrize("uri", [
    PATH_URI,
    f"https://{BUCKET}.s3.ap-northeast-2.amazonaws.com/{OUT_KEY}",
])
def test_result_completed_reads_s3(monkeypatch, uri):
    tr, _, s3 = result_with(monkeypatch, [completed(uri)])
    doc = json.loads(NORMAL_DOC)
    assert tr["status"] == "COMPLETED"
    assert tr["text"] == doc["results"]["transcripts"][0]["transcript"]
    assert s3.gets == [{"Bucket": BUCKET, "Key": OUT_KEY}]
    # 문장부호 항목은 빼고 발음 항목만, 시각은 float
    assert len(tr["words"]) == sum(1 for it in doc["results"]["items"] if it["type"] == "pronunciation") == 27
    assert tr["words"][0] == {"word": "저는", "start": 0.3, "end": 0.85}
    assert all(isinstance(w["start"], float) for w in tr["words"])
    AnswerResult.model_validate({"answerId": "a-q1-1", "transcription": tr})  # process_answer에 그대로 넘길 수 있다


def test_result_key_is_unquoted(monkeypatch):
    key = "uploads/interview/iv 1/transcripts/a-q1-1.json"
    s3 = FakeS3(objects={(BUCKET, key): NORMAL_DOC})
    tr, _, s3 = result_with(monkeypatch, [completed(f"https://s3.ap-northeast-2.amazonaws.com/{BUCKET}/uploads/interview/iv%201/transcripts/a-q1-1.json")], s3)
    assert tr["status"] == "COMPLETED" and s3.gets[0]["Key"] == key


def test_result_empty_transcript(monkeypatch):
    s3 = FakeS3(objects={(BUCKET, OUT_KEY): sample_text("transcribe/result_empty.json")})
    tr, _, _ = result_with(monkeypatch, [completed()], s3)
    assert tr == {"status": "COMPLETED", "text": "", "words": []}


@pytest.mark.parametrize("s3", [
    FakeS3(),                                                                   # 결과 파일 없음
    FakeS3(errors={OUT_KEY: client_error("AccessDenied", "GetObject")}),
    FakeS3(objects={(BUCKET, OUT_KEY): "{깨진 json"}),
    FakeS3(objects={(BUCKET, OUT_KEY): json.dumps({"jobName": JOB})}),          # results 없음
    FakeS3(objects={(BUCKET, OUT_KEY): json.dumps({"results": {"transcripts": [{"transcript": 1}]}})}),
])
def test_result_unreadable_file_is_failed(monkeypatch, s3):
    tr, _, _ = result_with(monkeypatch, [completed()], s3)
    assert tr == {"status": "FAILED"}


@pytest.mark.parametrize("uri", ["", "s3://bucket/key", "https://example.com/file.json",
                                 f"https://s3.ap-northeast-2.amazonaws.com/{BUCKET}"])
def test_result_bad_uri_is_failed(monkeypatch, uri):
    tr, _, s3 = result_with(monkeypatch, [completed(uri)])
    assert tr == {"status": "FAILED"} and s3.gets == []


@pytest.mark.parametrize("error", [client_error("ThrottlingException"), client_error("LimitExceededException"),
                                   client_error("InternalFailureException")])
def test_result_transient_error_is_in_progress(monkeypatch, error):
    tr, _, _ = result_with(monkeypatch, [error])
    assert tr == {"status": "IN_PROGRESS"}


def test_result_connection_error_is_in_progress(monkeypatch):
    from botocore.exceptions import EndpointConnectionError

    tr, _, _ = result_with(monkeypatch, [EndpointConnectionError(endpoint_url="https://transcribe.example")])
    assert tr == {"status": "IN_PROGRESS"}


@pytest.mark.parametrize("error", [client_error("BadRequestException"), client_error("NotFoundException"),
                                   client_error("AccessDeniedException")])
def test_result_missing_job_is_failed(monkeypatch, error):
    tr, _, _ = result_with(monkeypatch, [error])
    assert tr == {"status": "FAILED"}


@pytest.mark.parametrize("job_name", ["", "  ", None])
def test_result_blank_job_name_is_failed(monkeypatch, job_name):
    fake_t = FakeTranscribe()
    monkeypatch.setattr(voice, "_transcribe_client", lambda: fake_t)
    assert voice.get_transcription_result(job_name) == {"status": "FAILED"}
    assert fake_t.gets == []


def test_result_does_not_delete_file(monkeypatch):
    # 삭제는 백엔드 task_answer가 한다. FakeS3에는 delete_object가 없어서 지우려 하면 FAILED가 된다
    tr, _, s3 = result_with(monkeypatch, [completed()])
    assert tr["status"] == "COMPLETED" and not hasattr(s3, "delete_object")


def test_result_logs_have_no_transcript(monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG, logger="interview"):
        result_with(monkeypatch, [completed()])
    assert "stage=get_transcription_result status=COMPLETED" in caplog.text
    assert "대응표" not in caplog.text and BUCKET not in caplog.text and OUT_KEY not in caplog.text


def test_returned_dicts_are_fresh(monkeypatch):
    a, _, _ = result_with(monkeypatch, [{"TranscriptionJobName": JOB, "TranscriptionJobStatus": "QUEUED"}])
    a["status"] = "CHANGED"
    b, _, _ = result_with(monkeypatch, [{"TranscriptionJobName": JOB, "TranscriptionJobStatus": "QUEUED"}])
    assert b == {"status": "IN_PROGRESS"}


# ---------------------------------------------------------------- parse_transcript와 전달력 샘플


@pytest.mark.parametrize("name, words", [("result_normal.json", 27), ("result_short.json", 6),
                                         ("result_english.json", 9), ("result_empty.json", 0)])
def test_transcribe_samples_parse(name, words):
    out = voice.parse_transcript(sample_json(f"transcribe/{name}"))
    assert len(out["words"]) == words


def test_split_s3_uri():
    assert voice._split_s3_uri(PATH_URI) == (BUCKET, OUT_KEY)
    assert voice._split_s3_uri(f"https://{BUCKET}.s3.ap-northeast-2.amazonaws.com/{OUT_KEY}") == (BUCKET, OUT_KEY)
    with pytest.raises(ValueError):
        voice._split_s3_uri("https://s3.ap-northeast-2.amazonaws.com/")
