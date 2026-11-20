# Implementation Plan

기준: 이 폴더의 `requirements.md`, `design.md`, 이슈 #74. 브랜치 `feat/be/#74-interview-voice` (최신 `main` `a24e3a9`에서). 테스트는 저장소 루트에서 `uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q`. 실패하면 실패한 테스트만 다시 돌린다.

- [x] 1. 설정 파일과 모델
  - [x] 1.1 `config/scoring_v1.json`(design §9)과 `config.py`의 `load_scoring_config()`를 만든다. 값은 노션 6-⑤와 대조한다
    - `tests/test_config.py`: 읽기, 버전 일치, 깨진 값 → `AWS_SERVICE_ERROR`
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 1.2 `models.py`에 `DeliveryMetrics`를 만들고 `AnswerRecord.delivery`(기본 None)를 추가한다. 평가 불가인데 `delivery`가 있으면 거절. 실수 필드는 int도 받는다
    - `test_models.py`: 1차 형식 Session 통과, 카멜 키, int로 돌아온 측정값 통과
    - _Requirements: 5.2, 5.3, 5.4_
  - 커밋: 2와 함께 한 커밋 (1만 커밋하면 `AnswerRecord`에 `delivery: null`이 생겨 기존 `test_flow`가 깨진다)

- [x] 2. 전달력 측정
  - [x] 2.1 `delivery.py`에 `measure_delivery`를 만든다 (design §7). 항목마다 자기 `min_answer_sec`를 쓴다
  - [x] 2.2 `tests/test_delivery.py`: 300음절/60초, 10초 `TOO_SHORT`, 영문 30% `NON_HANGUL_HEAVY`, 2초 공백 경계(1.9·2.0), 단어 없음
    - _Requirements: 4.1~4.8_
  - [x] 2.3 `flow.py` `process_answer`에서 평가 가능 답변만 측정해 기록한다. `test_flow.py`에 정상·무응답·변환 실패·시간 초과 케이스 추가
    - _Requirements: 5.1, 5.2, 5.5, 5.6_
  - 커밋: `feat: 전달력 측정과 점수 설정 파일 추가` (`08808f8`, 272 passed 1 skipped)

- [x] 3. 질문 음성
  - [x] 3.1 `settings.py`에 Polly·Transcribe 상수(#69의 생각 끄기 설정은 그대로), `voice.py`에 클라이언트 함수 3개와 `synthesize_question`을 만든다 (design §3, §4)
  - [x] 3.2 `tests/fakes.py`에 `FakePolly`, `tests/test_voice.py`에 Polly 테스트(인자, 빈 문장, 실패 → None)
    - _Requirements: 1.1~1.4_
  - 커밋: `feat: 질문 음성 생성 함수 추가` (`3397aad`)

- [x] 4. 답변 변환
  - [x] 4.1 `voice.py`에 `start_transcription`, `get_transcription_result`, `_split_s3_uri`, `parse_transcript`를 만든다 (design §5, §6)
  - [x] 4.2 `samples/transcribe/` 4개 파일을 만든다
  - [x] 4.3 `FakeTranscribe`, `FakeS3.get_object`를 추가하고 `test_voice.py`에 design §12 표의 변환 케이스를 쓴다
    - _Requirements: 2.1~2.6, 3.1~3.8_
  - 커밋: `feat: 답변 음성 변환 함수 추가` (`e45b986`)

- [x] 5. 실제 음성 함수 연결
  - [x] 5.1 `__init__.py`를 `voice.py`에서 import하도록 바꾸고, `placeholders.py`에서 음성 함수 3개·`_s3_client`를 지운다. 모듈 설명의 "6개"를 "3개"로 고친다
  - [x] 5.2 `test_package.py`(시그니처 그대로, `import interview`가 boto3 없이도 성공), `test_placeholders.py`, `test_logging.py`, `test_backend_flow.py`를 고친다 (design §12)
    - _Requirements: 7.1~7.3, 8.3, 8.4_
  - 커밋: `feat: 음성 함수를 실제 구현으로 연결` (`782d65e`, 340 passed 1 skipped. 백엔드가 부르는 동작이 바뀌므로 `refactor`가 아님)

- [x] 6. 수동 확인 (실제 AWS, 사람이 실행)
  - [x] 6.1 `tests/test_voice_manual.py`를 만든다 (design §12). 기본 실행에서는 건너뛴다. 녹음 형식은 키의 확장자로 정한다 (m4a 그대로)
  - [x] 6.2 수동 테스트 경로 `uploads/interview/manual-check/`: 업로드 후 녹음·결과 파일을 모두 지웠고, 백엔드 담당에게는 PR에서 사후 공유한다
  - [x] 6.3 m4a 녹음 2개(대본 읽기)로 변환을 실행하고 변환 시간·발화 속도를 PR 참고 사항에 적는다 (`botocore[crt]` 포함, design §12)
    - [x] Polly 엔진: `neural` 확정 (생성 0.8초, 자연스러움)
    - [x] m4a 52.6초 답변: 변환 13.3초, 단어 104개, 발화 속도 328.4, 긴 침묵 0회
    - [x] m4a 17.3초 답변: 변환 10.2초, 단어 31개, 발화 속도 333.2, 긴 침묵 0회
    - webm 녹음과 2분 답변 변환 시간(240초·300초 안인지)은 녹음이 없어 PR에 "프론트 연동 때 확인"으로 적는다
    - _Requirements: 8.5_
  - 커밋: `test: 음성 함수 수동 확인 테스트 추가` (`e0e14dc`)

- [ ] 7. 문서와 PR
  - [x] 7.1 `docs/개발계획서3.md` ★ `answers[]` 예시·`promptVersion`과 §11 체크 갱신 (design §14, `45d2581`, 수동 확인 결과는 다음 커밋)
  - [ ] 7.2 전체 테스트 통과 확인, PR 본문 참고 사항에 design §13 내용 정리
  - [ ] 7.3 Session 형식 변경이라 백엔드 담당에게 리뷰를 요청하고 PR 링크를 팀 채널에 알린다
  - 커밋: `docs: 음성 단계 명세 반영`
  - PR 제목 `feat: 모의면접 음성 질문·답변 변환과 전달력 측정 구현`, 라벨 `feat`·`be`, 본문 `Closes #74`
