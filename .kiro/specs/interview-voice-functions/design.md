# Design Document

## 1. 개요

1차 패키지(`ai/interview/`, #51·#69 반영)에 `voice.py`, `delivery.py`, `config.py`, `config/scoring_v1.json`을 더하고, `placeholders.py`의 음성 함수 3개를 지운다 (이슈 #74). 공개 함수 이름·인자는 1차와 같다. 백엔드 코드는 바꾸지 않는다.

## 2. 파일 변경

```
ai/interview/
  __init__.py          음성 함수 3개를 .voice에서 import (나머지 그대로)
  voice.py             새 파일: synthesize_question, start_transcription, get_transcription_result
  delivery.py          새 파일: measure_delivery
  config.py            새 파일: load_scoring_config
  config/scoring_v1.json  새 파일 (노션 6-⑤, model_id 제외, long_pause_sec 추가)
  settings.py          POLLY_VOICE_ID, POLLY_ENGINE, TRANSCRIBE_LANGUAGE, MEDIA_FORMATS 상수
  models.py            DeliveryMetrics 모델, AnswerRecord.delivery 추가
  flow.py              process_answer에서 measure_delivery 호출
  placeholders.py      음성 함수 3개와 _s3_client 삭제, 모듈 설명 "6개" → "3개"
  samples/transcribe/  Transcript_File 예시 4개
  tests/               test_voice.py, test_delivery.py, test_config.py, test_voice_manual.py 추가, 기존 테스트 수정
```

- `infra/package.sh`가 `ai/interview/`를 `tests`·`samples`만 빼고 통째로 복사하므로 `config/`도 배포 묶음에 들어간다.
- `settings.py`에는 이미 #69의 `THINKING_OFF_BY_MODEL`·`thinking_off()`가 있다. 새 상수는 그 아래에 더하고 기존 값은 건드리지 않는다.

## 3. 클라이언트

```python
def _polly_client():      import boto3; return boto3.client("polly", region_name=settings.region())
def _transcribe_client(): ...("transcribe", ...)
def _s3_client():         ...("s3", ...)
```
- 모듈 변수에 한 번 만들어 재사용한다. 테스트는 `monkeypatch.setattr(voice, "_polly_client", lambda: fake)`로 바꾼다 (1차 `placeholders._s3_client`와 같은 방식).
- 오류 구분은 `botocore.exceptions.ClientError`의 `response["Error"]["Code"]`, 연결 오류는 `BotoCoreError`. botocore도 함수 안에서 import한다 (Requirement 7.3).

## 4. `synthesize_question(text)`

```python
resp = _polly_client().synthesize_speech(Text=text, TextType="text", OutputFormat="mp3",
                                         VoiceId="Seoyeon", Engine=POLLY_ENGINE, LanguageCode="ko-KR")
return resp["AudioStream"].read()
```
- `POLLY_ENGINE`은 `"neural"`로 확정했다. 서울 리전 수동 확인에서 Seoyeon neural이 0.8초에 생성됐고 소리가 자연스러웠다.
- 질문 최대 300자(1차 `QUESTION_MAX`)라 Polly 3,000자 한도 안이다.
- 실패 → 로그 `stage=synthesize_question errorCode=AWS_SERVICE_ERROR durationMs=…` 후 `None` (결정 1).
- 백엔드 `save_next_question`은 `if mp3 and UPLOAD_BUCKET`일 때만 S3에 올리므로 `None`이면 `audioUrl`이 null이 된다.

## 5. `start_transcription(...)`

```python
_transcribe_client().start_transcription_job(
    TranscriptionJobName=job_name, LanguageCode="ko-KR", MediaFormat=media_format,
    Media={"MediaFileUri": s3_uri}, OutputBucketName=output_bucket, OutputKey=output_key)
return job_name
```
- `media_format` 검사: `MEDIA_FORMATS = {"mp3","mp4","m4a","wav","flac","ogg","amr","webm"}`. 백엔드 `h_answer`는 Content-Type을 `webm`·`ogg`·`mp4`·`wav`·`mp3`·`flac`으로 바꾸고, 모르는 형식은 `webm`으로 보낸다.
- `job_name`은 백엔드가 `[0-9a-zA-Z._-]` 200자 이하로 만든다. 함수는 비었는지만 본다.
- 오류: `ConflictException` → 성공으로 보고 `job_name` 반환 / `BadRequestException` → `AWS_SERVICE_ERROR` retryable false / 그 밖 → retryable true.
- 메시지: "답변 음성을 변환하지 못했어요. 다시 시도해 주세요."
- `OutputKey`가 `.json`으로 끝나면 Transcribe가 그 이름 그대로 저장한다. 백엔드 키는 `uploads/interview/{ivId}/transcripts/{answerId}.json`이다.

## 6. `get_transcription_result(job_name)`

```
GetTranscriptionJob
 ├ QUEUED / IN_PROGRESS → {"status": "IN_PROGRESS"}
 ├ FAILED               → {"status": "FAILED"}   (FailureReason은 로그에 안 남김)
 └ COMPLETED → TranscriptFileUri → (bucket, key) → S3 get_object → parse_transcript()
```
- 결과 파일은 같은 호출 안에서 읽는다. 백엔드 `task_answer`가 이 호출 직후 녹음과 결과 파일을 지운다.
- URI 해석 `_split_s3_uri(uri)`: `https://s3.<region>.amazonaws.com/<bucket>/<key>`(경로형)와 `https://<bucket>.s3.<region>.amazonaws.com/<key>`(가상 호스트형) 둘 다 처리, 키는 `urllib.parse.unquote`.
- `parse_transcript(doc)`:
  - `text = doc["results"]["transcripts"][0]["transcript"]` (없으면 `""`)
  - `words = [{"word": it["alternatives"][0]["content"], "start": float(it["start_time"]), "end": float(it["end_time"])} for it in items if it["type"] == "pronunciation"]`
- 오류 표:

| 상황 | 반환 |
| --- | --- |
| `ThrottlingException`, `LimitExceededException`, `InternalFailureException`, 연결 오류 | `IN_PROGRESS` (백엔드가 2초 뒤 다시 조회, 240초 뒤 실패 처리) |
| `BadRequestException`·`NotFoundException`(작업 없음) | `FAILED` |
| S3 읽기 실패, JSON 해석 실패, URI 해석 실패 | `FAILED` |

- 로그: `stage=get_transcription_result status=… durationMs=…`, 실패면 `errorCode`.

## 7. 전달력 측정 (`delivery.py`)

```python
def measure_delivery(text: str, words: list[Word], config: DeliveryConfig) -> DeliveryMetrics
```
1. `span = words[-1].end - words[0].start` (단어 없으면 0)
2. 긴 침묵: `span < long_pause_per_min.min_answer_sec`면 null, 사유 `TOO_SHORT`. 아니면 `count = sum(1 for a, b in pairwise(words) if b.start - a.end >= long_pause_sec)`, `perMin = round(count / span * 60, 2)`
3. 속도: `span < speech_rate.min_answer_sec`면 null, 사유 `TOO_SHORT`. 아니면 `chars = [c for c in text if c.isalnum()]`, `non = 숫자·ASCII 영문 수`, `non / len(chars) >= max_non_hangul_ratio` → null, `NON_HANGUL_HEAVY` / 아니면 `round(한글 음절 수 / span * 60, 1)`
- 두 항목은 각자의 `min_answer_sec`를 쓴다. 노션 6-⑤ 기본값은 둘 다 15라 15초 미만이면 둘 다 미측정이다 (C §7).
- `enabled`·`weight`는 읽기만 하고 측정에는 쓰지 않는다 (3차 점수 계산용).

출력 (`DeliveryMetrics`, 카멜):
```json
{"answerSec": 17.2, "speechRate": 333.1, "speechRateReason": null,
 "longPauseCount": 0, "longPausePerMin": 0.0, "longPauseReason": null}
```
- 사유 값: `TOO_SHORT`, `NON_HANGUL_HEAVY`. 미측정이면 해당 값 null, `longPauseCount`도 null.
- 실수 저장 (결정 6, 1차 design §4.2의 "2차에서 정함"을 여기서 정한다):
  - 백엔드 `to_dynamo`가 실수를 Decimal로 저장하고, `get_interview`가 `to_plain`으로 정수 값은 int, 나머지는 float로 돌린다(`backend/common.py`).
  - 그래서 `300.0`은 `300`(int)으로 돌아온다. `DeliveryMetrics`의 실수 필드는 `float | None`(엄격 모드 아님)으로 두어 int도 받는다.
  - 반올림으로 자릿수를 줄인다.
- 점수 환산은 하지 않는다 (3차).

## 8. `process_answer` 변경 (`flow.py`)

- `_evaluate`가 평가 가능으로 판단한 경우에만 `measure_delivery(text, result.transcription.words, load_scoring_config().delivery)`를 부르고 `AnswerRecord(delivery=...)`로 넣는다.
- `AnswerRecord.delivery: DeliveryMetrics | None = None`. 1차 Session(키 없음)도 그대로 읽힌다.
- 모델 검사 추가 (`AnswerRecord._consistent`): `evaluable`이 false면 `delivery`는 null이어야 한다.
- 순서: 측정은 LLM 호출(`judge_follow_up`) 전에 한다. 측정은 실패하지 않는 순수 계산이다. 설정 파일 오류만 `AWS_SERVICE_ERROR`로 올라간다.

## 9. 설정 파일 (`config/scoring_v1.json`, `config.py`)

노션 6-⑤를 그대로 옮기되 두 곳만 다르다:
```json
"long_pause_per_min": { "enabled": true, "weight": 30, "full_max": 1, "zero_min": 5, "min_answer_sec": 15, "long_pause_sec": 2 }
```
- `model_id` 키는 넣지 않는다 (1차 결정 5).
- C §9는 설정 파일을 3차에 둔다. 전달력 기준값을 코드에 박지 않으려고 2차에 먼저 넣는다 (결정 4). 3차는 같은 파일의 나머지 부분을 검사에 더한다.
- `config.py`: Pydantic `ScoringConfig`(delivery 부분만 엄격 검사, 나머지 `dict`로 보관해 3차에서 채움), `functools.lru_cache`로 한 번 읽음. 실패 → `AWS_SERVICE_ERROR` retryable false, 1차 `CONFIG_ERROR_MESSAGE`.

## 10. 오류 처리 요약

| 함수 | 상황 | 결과 |
| --- | --- | --- |
| `synthesize_question` | Polly 실패 | `None` (예외 없음) |
| `start_transcription` | 입력 오류 | `INVALID_INPUT` false |
| `start_transcription` | `BadRequestException` / 그 밖 | `AWS_SERVICE_ERROR` false / true |
| `get_transcription_result` | 일시 오류 | `IN_PROGRESS` |
| `get_transcription_result` | 작업 실패·결과 못 읽음 | `FAILED` |
| `load_scoring_config` | 파일·값 오류 | `AWS_SERVICE_ERROR` false |

- 백엔드는 `INVALID_INPUT` 400, `AWS_SERVICE_ERROR` 503으로 바꾼다 (`interview_api.handle`). `start_transcription`은 `h_answer`에서 동기로 불리므로 이 오류가 바로 응답이 된다.

## 11. 로그

- 남김: `stage`(`synthesize_question`, `start_transcription`, `get_transcription_result`, `process_answer`), `status`, `durationMs`, `errorCode`, AWS 오류 코드 이름
- 남기지 않음: 질문 문장, 답변 `text`·`words`, Transcribe `FailureReason`, mp3, 버킷 이름, S3 키, presigned URL
- `process_answer` 로그에 `speechRateReason`·`longPauseReason`만 더한다 (수치는 원문이 아니지만 굳이 남기지 않는다).

## 12. 테스트

실행은 1차와 같다 (저장소 루트):
```
uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q
```

| 파일 | 확인 내용 |
| --- | --- |
| `test_voice.py` | Polly 호출 인자·mp3 반환, 빈 문장 → 호출 없이 None, Polly 실패 → None / Transcribe 호출 인자 5개 매핑, 형식 오류 → `INVALID_INPUT`, Conflict → 성공, BadRequest·그 밖 retryable / 결과 조회: 진행 중, 실패, 완료(경로형·가상 호스트형 URI), 말 없음, S3 실패·JSON 깨짐 → FAILED, 스로틀링 → IN_PROGRESS, 문장부호 항목 제외 |
| `test_delivery.py` | 60초 300음절 → 300.0, 10초 → 둘 다 `TOO_SHORT`, 영문 30% → 속도만 `NON_HANGUL_HEAVY`, 2초 공백 2회·60초 → 2.0, 1.9초 공백은 세지 않음, 단어 없음 |
| `test_config.py` | 파일 읽기, `scoring_version` = `SCORING_VERSION`, 깨진 값 → `AWS_SERVICE_ERROR` |
| `test_models.py` (수정) | `delivery` 없는 1차 Session 통과, int로 돌아온 측정값 통과, 평가 불가인데 `delivery` 있으면 거절 |
| `test_flow.py` (수정) | 정상 답변에 `delivery` 기록, 무응답·변환 실패 → `delivery` null, `timeLimitReached` 기록, 1차 형식 Session 입력 허용 |
| `test_backend_flow.py` (수정) | `placeholders._s3_client` 대신 `voice`의 가짜 Polly·Transcribe·S3로 백엔드 순서 재현, `store()` 왕복 뒤 `Session.model_validate` 통과. 결과 파일 put 4개 확인은 Transcribe 호출 4개 확인으로 바꾼다 |
| `test_placeholders.py` (수정) | 음성 함수 테스트 4개와 `fake_s3` fixture 삭제, 남은 3개만 |
| `test_package.py` (수정) | 시그니처 그대로, boto3 없이도 `import interview` 성공 |
| `test_logging.py` (수정) | 음성 함수·측정 로그에 원문 없음 |
| `test_voice_manual.py` | `RUN_AWS_VOICE=1`, `VOICE_TEST_BUCKET`, `VOICE_TEST_AUDIO_KEY`가 있을 때만. 질문 mp3를 `VOICE_OUT_DIR`(없으면 pytest 임시 폴더)에 저장 → 녹음 변환 시작 → 3초마다 최대 240초 조회 → 측정값과 변환 시간 출력(문장은 출력하지 않음) → 결과 파일 삭제 |

- 가짜 클라이언트는 `tests/fakes.py`에 둔다: `FakePolly`(`AudioStream`에 `io.BytesIO`), `FakeTranscribe`(응답 목록을 차례로 돌려주고 호출 기록), `FakeS3`(1차 것에 `get_object`·오류 주입 추가).
- `samples/transcribe/`: `result_normal.json`(약 20초, 2초 공백 1회), `result_short.json`(10초), `result_english.json`(영문·숫자 30%), `result_empty.json`(items 없음). Transcribe 실제 형식을 따르되 문장은 가상 자소서 내용으로 지어낸다.
- 수동 테스트는 `aws login` 자격 증명을 읽어야 하므로 `botocore[crt]`를 더해 실행한다 (`docs/team-guide.md` §1):
```
uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt --with "botocore[crt]" pytest ai/interview/tests/test_voice_manual.py -s -q
```

## 13. 백엔드·프론트에 전할 것 (PR 참고 사항)

- Session 형식 변경: `answers[].delivery`가 새로 생긴다. 백엔드는 Session을 그대로 저장하므로 코드 변경은 없지만, 파트 경계를 넘는 데이터 형식 변경이라 백엔드 담당에게 리뷰를 요청하고 PR 링크를 팀 채널에 알린다 (AGENTS.md "파트", CONTRIBUTING "코드 리뷰").
- 권한: 실행 역할에 이미 있음(`InterviewAI`, `S3Uploads`). 추가 요청 없음. Transcribe는 호출한 역할 권한으로 녹음을 읽고 결과를 쓴다.
- 지원 녹음 형식: webm, ogg, mp4(m4a), wav, mp3, flac. 수동 확인은 m4a 녹음 2개(대본 읽기, 1분 남짓)로 했고 변환 시간을 적는다. 브라우저 녹음(webm)과 2분 답변의 변환 시간(백엔드 대기 한도 240초, Lambda 300초 안인지)은 **프론트 연동 때 확인**한다 (C §11 미완료 항목).
- Transcribe 작업 기록은 계정에 90일 남는다(답변 원문은 우리 버킷에만 있고 백엔드가 지움). 지우려면 `transcribe:DeleteTranscriptionJob` 권한이 필요하므로 이번에는 하지 않는다.
- `synthesize_question`이 None을 돌려주는 경우가 생기므로 프론트의 자막 + [답변 시작] 경로가 필요하다 (C F-04, 이미 명세에 있음).

## 14. 문서 변경 (`docs/개발계획서3.md`)

| 위치 | 바꿀 내용 |
| --- | --- |
| ★ 주요 데이터 형식 `session` 예시 | `answers[]` 항목 예시 한 줄 추가 (`delivery` 포함). `promptVersion`을 `"A-v2/B-v1"`로 (#69에서 바뀌었는데 문서는 `A-v1/B-v1`) |
| §11 착수 전 확인 | "브라우저 녹음 형식(webm)과 2분 답변 변환 시간" → 확인 결과로 체크, "Transcribe 결과 읽는 방법" → 체크 (백엔드 `h_answer`·`task_answer`에 `output_bucket`·`output_key`·결과 파일 삭제 반영 확인) |

## 15. 열린 질문과 위험

| # | 내용 | 제안 |
| --- | --- | --- |
| 1 | Polly 실패 시 None(결정 1)은 개발 가이드 초안(예외)과 다르다 | 면접이 끊기지 않는 쪽을 택함. 바꾸려면 Requirement 1.3만 고친다 |
| 2 | 노션 6-②의 "답변 길이"가 녹음 길이인지 말한 구간인지 불명확 | 함수가 받는 값이 `words`뿐이라 Speech_Span으로 정함. 녹음 길이가 필요하면 백엔드가 `answer_result`에 넘겨야 함 |
| 3 | Transcribe ko-KR이 숫자를 아라비아 숫자로 적어 한글 음절 수가 줄어든다 | 20% 미만이면 감수 (노션 6-② 메모와 같음). 수동 테스트에서 확인 |
| 4 | neural 엔진이 서울 리전에서 Seoyeon을 지원하지 않으면 실패 → 늘 None | 해결: 수동 확인에서 neural 동작(0.8초, 자연스러움). `neural`로 확정 |
| 5 | 수동 테스트용 녹음을 uploads 버킷에 올려야 함 | 경로는 `uploads/interview/manual-check/`로 하고 백엔드 담당에게 먼저 확인. 버킷 생성·권한 변경은 하지 않음 |
| 6 | 노션 6-②·6-⑤ 값(15초, 0.2, 2초 등)은 저장소에 없다 | 설정 파일을 만들 때 노션 페이지와 한 번 더 대조하고 PR 참고 사항에 대조했다고 적는다 |
