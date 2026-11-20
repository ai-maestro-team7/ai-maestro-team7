"""실제 Polly·Transcribe 확인 (voice tasks 6, Requirement 8.5). 기본 실행에서는 건너뛴다.

켜는 방법 (aws login 뒤, botocore[crt] 포함, -s로 이 파일만):
- RUN_AWS_VOICE=1                     둘 다 필요
- VOICE_OUT_DIR (선택)                 질문 mp3를 저장할 폴더. 없으면 pytest 임시 폴더
- VOICE_TEST_POLLY_ENGINE (선택)       "standard"로 바꿔 들어 볼 때
- VOICE_TEST_BUCKET, VOICE_TEST_AUDIO_KEY  변환 확인에 필요. 녹음은 uploads/interview/manual-check/ 아래에 미리 올린다
- VOICE_TEST_MEDIA_FORMAT (선택)       없으면 녹음 키의 확장자

출력에는 측정값과 시간만 찍고 질문·답변 문장은 찍지 않는다. 결과 파일은 끝나면 지운다.
결과는 커밋하지 않고 PR 참고 사항에 숫자만 적는다.
"""

import os
import time
from pathlib import Path

import pytest

from interview import settings, voice
from interview.config import load_scoring_config
from interview.delivery import measure_delivery
from interview.models import Word

pytestmark = pytest.mark.skipif(os.environ.get("RUN_AWS_VOICE") != "1",
                                reason="실제 Polly·Transcribe 호출은 RUN_AWS_VOICE=1일 때만")

QUESTION = "팀 프로젝트에서 의견이 갈렸을 때 어떻게 해결했나요?"
OUTPUT_PREFIX = "uploads/interview/manual-check/transcripts/"
POLL_SEC = 3
WAIT_SEC = 240  # 백엔드 TRANSCRIBE_WAIT_SEC와 같다


def test_polly_mp3(monkeypatch, tmp_path):
    engine = os.environ.get("VOICE_TEST_POLLY_ENGINE", "").strip()
    if engine:
        monkeypatch.setattr(settings, "POLLY_ENGINE", engine)
    started = time.monotonic()
    audio = voice.synthesize_question(QUESTION)
    elapsed = time.monotonic() - started
    assert audio, "Polly가 음성을 만들지 못했다 (엔진을 standard로 바꿔 다시 확인)"
    out_dir = Path(os.environ.get("VOICE_OUT_DIR") or tmp_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"question-{settings.POLLY_ENGINE}.mp3"
    path.write_bytes(audio)
    print(f"\n[VOICE] engine={settings.POLLY_ENGINE} bytes={len(audio)} seconds={elapsed:.1f} file={path}")


def test_transcribe_answer():
    bucket = os.environ.get("VOICE_TEST_BUCKET", "").strip()
    audio_key = os.environ.get("VOICE_TEST_AUDIO_KEY", "").strip()
    if not bucket or not audio_key:
        pytest.skip("VOICE_TEST_BUCKET, VOICE_TEST_AUDIO_KEY가 있어야 변환을 확인한다")
    media_format = os.environ.get("VOICE_TEST_MEDIA_FORMAT", "").strip() or audio_key.rsplit(".", 1)[-1].lower()
    job_name = f"team07-manual-check-{int(time.time())}"
    output_key = f"{OUTPUT_PREFIX}{job_name}.json"

    started = time.monotonic()
    voice.start_transcription(f"s3://{bucket}/{audio_key}", job_name, media_format, bucket, output_key)
    try:
        while True:
            result = voice.get_transcription_result(job_name)
            elapsed = time.monotonic() - started
            if result["status"] != "IN_PROGRESS" or elapsed > WAIT_SEC:
                break
            time.sleep(POLL_SEC)
    finally:
        # 결과 파일에는 답변 원문이 들어 있다. 백엔드처럼 바로 지운다
        try:
            voice._s3_client().delete_object(Bucket=bucket, Key=output_key)
        except Exception as exc:  # noqa: BLE001
            print(f"\n[VOICE] 결과 파일을 지우지 못했다: {type(exc).__name__}")

    print(f"\n[VOICE] format={media_format} status={result['status']} transcribeSeconds={elapsed:.1f} "
          f"withinBackendWait={elapsed <= WAIT_SEC}")
    assert result["status"] == "COMPLETED", "변환 실패 또는 240초 초과"
    words = [Word(**w) for w in result["words"]]
    metrics = measure_delivery(result["text"], words, load_scoring_config().delivery)
    print(f"[VOICE] words={len(words)} textChars={len(result['text'])} "
          f"delivery={metrics.model_dump(by_alias=True)}")
