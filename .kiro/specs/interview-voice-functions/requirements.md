# Requirements Document

## Introduction

AI 모의면접 함수의 2차 단계다 (이슈 #74). 1차(`.kiro/specs/interview-text-functions/`, PR #51)에서 임시 구현으로 둔 `synthesize_question`, `start_transcription`, `get_transcription_result`를 Polly·Transcribe 실제 호출로 바꾸고, 답변마다 전달력 측정값을 Session에 기록한다. 음성으로 면접 한 바퀴가 도는 것이 목표다.

기준 커밋: `main` `a24e3a9` (1차 #51, 프롬프트 A-v2·생각 끄기 #69 반영).

근거:
- 기준 문서: C = `docs/개발계획서3.md` ★ 함수 명세·백엔드와의 약속·§4.2·§4.3·§7·§8·§9(5~7h)·§11, `docs/db-schema.md` §2.4, `AGENTS.md`, `.kiro/steering/*.md`
- 전달력 계산식과 기준값: 노션 "AI 모의면접 에이전트 기능" 6-② 표와 6-⑤ 설정 파일 (C §4.3이 "기능 정리 페이지 6번을 따른다"고 정함. 저장소에는 없다)
- 백엔드 호출부: `backend/interview_api.py`의 `save_next_question`(질문 음성), `h_answer`(녹음 업로드·변환 시작), `task_answer`(결과 조회 반복·결과 파일 삭제·`process_answer`). 대역 `backend/interview_stub.py`
- 실행 역할 권한: `infra/iam/lambda-role-policy.json` `InterviewAI`(polly:SynthesizeSpeech, transcribe:StartTranscriptionJob·GetTranscriptionJob), `S3Uploads`(uploads 버킷 Get·Put·Delete). 2차에 권한 추가는 필요 없다

이 스펙의 결정 (C 담당 확인 필요):
1. `synthesize_question`은 Polly 호출이 실패하면 예외 대신 `None`을 돌려준다. 백엔드 `save_next_question`은 `None`이면 `audioKey`를 두지 않아 `audioUrl`이 null이 되고, 프론트는 자막과 [답변 시작]으로 진행한다(C F-04). 예외를 던지면 백엔드 `run_task`가 세션을 `FAILED`로 남겨 면접이 끝나기 때문이다.
2. `get_transcription_result`는 결과를 읽지 못하면 `{"status": "FAILED"}`를 돌려준다. `process_answer`가 `TRANSCRIBE_FAILED`로 기록하고 면접을 계속한다(C §4.2, §7). 같은 이유로 일시적 AWS 오류에도 예외를 던지지 않는다 (Requirement 3 기준 6).
3. 2차의 `measure_delivery`는 **측정값만** 만든다. 점수 환산(시간 관리 10·발화 속도 30·긴 침묵 30)은 3차 `calculate_interview_scores`가 한다.
4. `config/scoring_v1.json`은 노션 6-⑤ 내용 그대로 2차에 추가한다. C §9는 설정 파일을 3차(7~10h)에 두지만, 전달력 기준값을 코드에 박지 않으려고(AGENTS.md "코딩 규칙") 2차에 먼저 넣는다. 단, `model_id` 키는 넣지 않고(1차 결정 5, 모델은 `MODEL_ID` 환경변수만), 긴 침묵 기준 `long_pause_sec: 2`를 추가한다(6-② 표 "2초 이상 공백").
5. 단어별 시간(`words`)은 Session에 넣지 않고 측정값만 넣는다 (크기·원문 최소화).
6. 측정값은 실수로 Session에 넣는다. 1차 design §4.2는 "Session에 실수를 넣지 않고 2차에서 방식을 정한다"고 했다. 백엔드 `to_dynamo`가 실수를 Decimal로 저장하고 `to_plain`이 정수 값은 int, 나머지는 float로 돌려주므로 왕복된다. 그래서 측정값 모델은 int로 돌아온 값(예: `300.0` → `300`)도 받아야 한다.

범위에서 제외:
- 점수 계산·리포트(3차), 시선 분석(4차)
- `backend/`, `infra/`, `docs/db-schema.md` 수정, AWS 자원 생성·권한 변경·배포
- 질문 유형이 내용과 안 맞는 문제 (#69 후속 개선, 별도 이슈)

## Glossary

- **Polly_Client / Transcribe_Client / S3_Client**: `voice.py`가 쓰는 boto3 클라이언트. 테스트에서는 가짜 클라이언트로 바꾼다
- **Transcript_File**: Transcribe가 `output_bucket`의 `output_key`에 쓰는 결과 JSON (`results.transcripts`, `results.items`)
- **Speech_Span**: 첫 단어 시작부터 마지막 단어 끝까지의 초
- **Delivery_Metrics**: 답변 하나의 전달력 측정값 (`answers[].delivery`)

## Requirements

### Requirement 1: 질문 음성 생성 (`synthesize_question`)

**User Story:** 지원자로서, 질문을 귀로 듣고 싶다. 그래야 실제 면접처럼 연습할 수 있다.

#### Acceptance Criteria
1. WHEN `synthesize_question(text)`를 부르면 THE 함수 SHALL Polly `SynthesizeSpeech`를 VoiceId `Seoyeon`, LanguageCode `ko-KR`, OutputFormat `mp3`로 호출하고 mp3 bytes를 돌려준다.
2. IF `text`가 비었거나 공백뿐이면 THEN THE 함수 SHALL Polly를 부르지 않고 `None`을 돌려준다.
3. IF Polly 호출이 실패하면 THEN THE 함수 SHALL `None`을 돌려주고 `stage=synthesize_question errorCode=AWS_SERVICE_ERROR`만 로그로 남긴다 (결정 1).
4. THE 함수 SHALL 질문 문장을 로그에 남기지 않는다.

### Requirement 2: 답변 변환 시작 (`start_transcription`)

**User Story:** 백엔드 담당으로서, 녹음을 올린 직후 함수 하나로 변환을 시작하고 싶다.

#### Acceptance Criteria
1. THE 함수 SHALL 인자 5개 `(s3_uri, job_name, media_format, output_bucket, output_key)`를 위치 인자로 받는다 (백엔드 `h_answer`).
2. WHEN 호출되면 THE 함수 SHALL Transcribe `StartTranscriptionJob`을 `LanguageCode=ko-KR`, `Media.MediaFileUri=s3_uri`, `MediaFormat=media_format`, `OutputBucketName=output_bucket`, `OutputKey=output_key`로 부르고 `job_name`을 돌려준다. 결과 위치는 백엔드가 넘긴 값만 쓴다 (★ 백엔드와의 약속).
3. IF `media_format`이 Transcribe 지원 형식(mp3, mp4, m4a, wav, flac, ogg, amr, webm)이 아니거나 인자가 비었으면 THEN THE 함수 SHALL `INVALID_INPUT`(retryable false)을 던진다.
4. IF 같은 이름의 작업이 이미 있으면(`ConflictException`) THEN THE 함수 SHALL 오류 없이 `job_name`을 돌려준다 (재시도 안전).
5. IF 그 밖의 호출 실패면 THEN THE 함수 SHALL `AWS_SERVICE_ERROR`를 던진다. `BadRequestException`은 retryable false, 나머지는 true.
6. THE 함수 SHALL 버킷·계정 ID를 코드에 쓰지 않는다.

### Requirement 3: 변환 결과 조회 (`get_transcription_result`)

**User Story:** 백엔드 담당으로서, 완료될 때까지 반복 조회해 `process_answer`에 그대로 넘길 결과를 받고 싶다.

#### Acceptance Criteria
1. WHEN 작업 상태가 `QUEUED`·`IN_PROGRESS`면 THE 함수 SHALL `{"status": "IN_PROGRESS"}`를 돌려준다.
2. WHEN 작업 상태가 `COMPLETED`면 THE 함수 SHALL `GetTranscriptionJob` 응답의 `TranscriptFileUri`에서 버킷·키를 얻어 S3에서 Transcript_File을 읽고 `{"status": "COMPLETED", "text": str, "words": [{"word", "start", "end"}]}`를 돌려준다. 인터넷 주소로 내려받지 않는다.
3. THE 함수 SHALL 같은 호출 안에서 결과 파일을 읽는다. 백엔드 `task_answer`는 이 함수가 `IN_PROGRESS`가 아닌 값을 돌려준 직후 결과 파일을 지운다.
4. THE 함수 SHALL `words`를 `results.items` 중 `type == "pronunciation"`인 항목으로 만들고 `start`·`end`를 float로 바꾼다. 문장부호 항목은 넣지 않는다.
5. WHEN 결과에 말이 없으면 THE 함수 SHALL `text: ""`, `words: []`로 돌려준다 (`process_answer`가 `NO_ANSWER` 처리).
6. IF 작업이 `FAILED`이거나, 작업이 없거나, 결과 파일을 읽거나 해석하지 못하면 THEN THE 함수 SHALL `{"status": "FAILED"}`를 돌려준다 (결정 2).
7. IF `GetTranscriptionJob`이 일시적 오류(스로틀링, 내부 오류, 연결 오류)면 THEN THE 함수 SHALL `{"status": "IN_PROGRESS"}`를 돌려준다. 백엔드가 2초 뒤 다시 조회하고, 240초(`TRANSCRIBE_WAIT_SEC`)가 지나면 실패로 처리한다.
8. THE 함수 SHALL 결과 파일을 지우지 않는다 (삭제는 백엔드 `task_answer`). 답변 원문·`FailureReason`을 로그에 남기지 않는다.

### Requirement 4: 전달력 측정 (`measure_delivery`)

**User Story:** 지원자로서, 말 속도와 긴 침묵을 수치로 확인하고 싶다.

#### Acceptance Criteria
1. THE 함수 SHALL `measure_delivery(text, words, config)`로 Delivery_Metrics `{"answerSec", "speechRate", "speechRateReason", "longPauseCount", "longPausePerMin", "longPauseReason"}`를 돌려준다. 기준값은 `config/scoring_v1.json`에서 읽고 코드에 쓰지 않는다.
2. THE `answerSec` SHALL Speech_Span(소수 첫째 자리)이다. `words`가 없으면 0이다.
3. IF Speech_Span이 항목별 `min_answer_sec`(발화 속도·긴 침묵 모두 15) 미만이면 THEN THE 함수 SHALL 그 항목을 null로 두고 사유 `TOO_SHORT`를 남긴다. 기본 설정에서는 둘 다 미측정이다 (C §7 "15초 미만 답변 → 발화 속도·침묵 미측정").
4. THE 발화 속도 SHALL `한글 음절 수 ÷ Speech_Span × 60`(소수 첫째 자리)이다. 한글 음절은 U+AC00~U+D7A3이다.
5. IF 숫자·영문 글자 비율이 `max_non_hangul_ratio`(0.2) 이상이면 THEN THE 함수 SHALL 발화 속도를 null로 두고 사유 `NON_HANGUL_HEAVY`를 남긴다. 비율 = 숫자·영문 글자 수 ÷ 공백·문장부호를 뺀 전체 글자 수.
6. THE 긴 침묵 횟수 SHALL 이웃한 단어 사이 공백(`다음 start − 앞 end`)이 `long_pause_sec`(2) 이상인 횟수이고, 분당 값은 `횟수 ÷ Speech_Span × 60`(소수 둘째 자리)이다.
7. THE 함수 SHALL AWS를 부르지 않는 순수 함수다. 같은 입력이면 같은 값을 돌려준다.
8. THE 함수 SHALL 설정의 `enabled` 값과 관계없이 측정한다. `enabled`·`weight`는 3차 점수 계산이 쓴다.

### Requirement 5: 측정값 기록 (`process_answer`)

#### Acceptance Criteria
1. WHEN 답변이 평가 가능하면 THE `process_answer` SHALL `measure_delivery` 결과를 `answers[].delivery`에 넣는다.
2. WHEN 답변이 평가 불가(`NO_ANSWER`, `TRANSCRIBE_FAILED`)면 THE `delivery` SHALL null이다.
3. THE `AnswerRecord` SHALL `delivery`가 없는 1차 Session도 읽는다 (기본값 null).
4. THE `DeliveryMetrics` SHALL 백엔드 저장·조회 뒤 int로 돌아온 수치(결정 6)를 받는다.
5. THE `timeLimitReached` SHALL 1차처럼 `answers[]`에 그대로 기록한다 (시간 관리 점수는 3차).
6. THE Session SHALL `words`를 담지 않는다 (결정 5).

### Requirement 6: 설정 파일

#### Acceptance Criteria
1. THE 패키지 SHALL `ai/interview/config/scoring_v1.json`을 두고 `config.py`의 `load_scoring_config()`로 읽는다 (`Path(__file__).parent / "config"`, 프로세스에서 한 번).
2. IF 파일이 없거나 delivery 값이 틀리면 THEN THE 함수 SHALL `AWS_SERVICE_ERROR`(retryable false, 설정 오류 문구)를 던진다.
3. THE 파일의 `scoring_version` SHALL `versions.SCORING_VERSION`(`v1.0`)과 같다.

### Requirement 7: 패키지와 임시 구현 정리

#### Acceptance Criteria
1. THE `__init__.py` SHALL 음성 함수 3개를 `voice.py`에서 내보내고, `__all__` 9개 이름과 백엔드 호출 시그니처는 1차와 같다.
2. THE `placeholders.py` SHALL `analyze_face`, `compute_baseline`, `generate_report`만 남긴다.
3. THE boto3 SHALL 함수 안에서 지연 import한다 (`MODEL_ID`·AWS 없이 `import interview` 성공).

### Requirement 8: 테스트

#### Acceptance Criteria
1. THE 단위 테스트 SHALL AWS 없이 가짜 Polly·Transcribe·S3 클라이언트로 통과한다 (`moto` 쓰지 않음).
2. THE 테스트 SHALL C §7 시나리오(15초 미만, 숫자·영어 많은 답변, 2분 초과, Transcribe 실패, 무응답)를 확인한다.
3. THE `test_backend_flow.py` SHALL 백엔드 순서(`start_interview` → `synthesize_question` → `start_transcription` → `get_transcription_result` 반복 → `process_answer`)를 실제 음성 함수와 가짜 클라이언트로 재현하고, 단계마다 저장·조회 변환(`store`)을 거친 Session이 검사를 통과하는지 확인한다.
4. THE 로그 테스트 SHALL 질문·답변 원문이 로그에 없음을 확인한다.
5. THE 수동 테스트 1개 SHALL `RUN_AWS_VOICE=1`과 버킷·녹음 키 환경변수가 있을 때만 실제 Polly·Transcribe를 부른다.
