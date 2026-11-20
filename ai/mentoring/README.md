# 멘토링 (A)

이력서·경력 분석, 역량 프로필, 경험 블록, 직무 적합도, 첨삭, 학습 경로를 만드는 A 파트 코드다.
명세는 `docs/개발계획서1.md`, 요구사항은 `.kiro/specs/mentoring-profile-storybank/requirements.md`를 본다.

## 테스트

```bash
cd ai/mentoring
uv run --no-project --python 3.13 --with-requirements requirements-dev.txt \
  --with-requirements ../../contracts/requirements.txt python -m pytest -q -p no:cacheprovider
```

AWS와 네트워크를 부르지 않는다. 메모리 저장소(`store/memory.py`), MockLLM(`llm/mock.py`), 가짜 텍스트 도구
(`tests/support/fake_text_tools.py`)로 돈다. 테스트 데이터는 모두 가상이다.

## 백엔드가 부르는 것

| 입구 | 언제 | 비고 |
|---|---|---|
| `mentoring.api.rest_handler.handle(event, deps, user_id)` | `/api/v1/mentoring/*` | user_id는 `get_user_id()` 결과 (BE-1) |
| `mentoring.api.task_handler.handle(event, deps)` | 이벤트에 `mentoringTask` 키가 있을 때 | Lambda 비동기 자기 호출 (D-19, BE-2) |
| `mentoring.core.summary.to_career_profile_summary(profile_item)` | 면접 시작 때 | 저장된 역량 프로필 항목 → `CareerProfileSummary` dict 또는 None (BE-5) |

`Deps`(`deps.py`)는 입구를 부르는 쪽이 만든다. 운영에서는 `store/factory.py`의 `build_aws_deps()`를 인자 없이 부르고,
백엔드가 `hash_user_id`를 `backend/common.py`의 함수로 바꿔 넣는다 (`backend/mentoring_api.py`).
`build_aws_deps()`는 PDF 추출기(`PdfExtractor` + Textract OCR)와 경험 블록 저장소(`DynamoStoryRepo`)를 함께 넣는다.
`Deps.extractor`가 없으면 업로드 완료가, `Deps.stories`가 없으면 경험 블록 경로가 501이다.

## 경험 블록 경로 (Requirement 9)

| 요청 | 응답 | 모델 호출 |
|---|---|---|
| `POST /stories` `{rawExperience, targetRole?, sourceDocumentId?, title?}` | 201 경험 블록 (`status: QUESTIONS_READY`, `questions` 최대 3개) | 있음 |
| `GET /stories` | 200 `{stories: [{storyId, title, status, latestVersion, updatedAt}]}` | 없음 |
| `GET /stories/{storyId}` | 200 경험 블록 최신 버전 | 없음 |
| `PATCH /stories/{storyId}` `{baseVersion, answers?, confirmFields?, edits?}` | 200 경험 블록. 답변이 있으면 질문을 다시 만든다 | 답변이 있을 때만 |

- 질문 생성은 동기다 (M-7, 2026-11-20). 그래서 `POST`는 개발계획서1 §6.1의 202가 아니라 201로 결과를 바로 준다.
- `POST`가 모델 오류(`AI_OUTPUT_INVALID` 500, `AWS_SERVICE_ERROR` 503, 둘 다 `retryable: true`)로 실패해도 초안은 `DRAFT`로 남는다.
  같은 `Idempotency-Key`로 다시 보내면 새 경험 블록을 만들지 않고 그 초안에서 질문만 다시 만든다.
- `PATCH`에서 질문 갱신만 실패하면 답변은 저장하고 `warnings: ["QUESTIONS_NOT_REFRESHED"]`를 붙여 200으로 준다.
- `baseVersion`이 최신이 아니면 409 `PRECONDITION_NOT_MET`. `VERIFIED`는 사용자가 확인하거나 고친 필드에만 생기고,
  질문을 다시 만들어도 그 값은 모델 출력으로 바뀌지 않는다.

## 직무 적합도 (`fit/`, mentoring-fit-review-learning Requirement 1~8)

| 요청 | 응답 |
|---|---|
| `POST /analyses` `{profileId, profileVersion?, jobPostingId?, targetNcsCode?, workspaceId?}` | 202 `{analysisId, taskId, status: PENDING}`. 공고나 NCS 코드 중 하나는 꼭 있어야 한다 |
| `GET /analyses/{analysisId}` | 200. 끝나면 `eligibility`(점수보다 앞), `fitScore`·`potentialUpperBound`, `strengths`, `partialEvidence`, `unverifiedSkills`(확인 질문), `confirmedGaps`, `summary`, `sources`, `warnings` |

작업 `JOB_FIT` 순서 (`fit/analysis.py`, 모델은 2·6번에서만):
1. 프로필 버전과 요건 읽기. 공고는 요청 시점의 `SNAP#`을 고정하고, NCS 모드는 능력단위를 요건으로 쓴다
2. [모델] 요건마다 프로필에 **이미 있는** `skillId`·`evidenceId` 고르기 (`job-fit-link-v1`)
3. 없는 ID는 버린다. 근거 단계는 연결된 역량의 저장 상태로 코드가 정한다. 연결이 없으면 미확인 + 확인 질문
4. 점수(`fit/score.py`), 격차(`fit/gaps.py`), 지원자격(`Deps.eligibility` = 백엔드 `evaluate_eligibility`)
5. KB 검색: NCS 직무가 하나로 정해졌을 때만, `job_role` 필터(그 직무 + 공통). 방법론 문서는 `role: GUIDANCE`
6. [모델] 설명 문장 (`job-fit-summary-v1`). 합격 확률·퍼센트 표현이 있으면 1회 다시 쓰게 하고, 그래도 있으면 버린다
7. `ANALYSIS#` 저장. 워크스페이스가 있으면 GSI1로 워크스페이스 상세에 붙는다

정한 것
- 점수의 "관련 경험" 분류(0.1)는 MVP에서 쓰지 않는다. 그 분류가 없으면 남은 가중치로 다시 나눈다 (M-8)
- 자격 보유는 이력서 원문 인용이 붙은 자격만 본다. 사용자가 "없다"고 확인하면 미보유로 넘긴다
- 공고에 NCS 코드가 0개·여러 개면 하나로 정하지 않고 `ncs.candidates`로 남긴다. 고용24 직종 → NCS 매핑(`MAP#WORK24#`)은 아직 쓰지 않는다
- 요건 추출이 끝나지 않은 공고(`extractStatus != DONE`)는 `REQUIRES_USER_REVIEW` / `POSTING_NOT_READY` [D-39]

운영 의존성 (`build_aws_deps`): `TABLE_CATALOG`(있음), `TABLE_REFERENCE`·`KB_ID`(BE-4), `eligibility`(BE-8). 없으면 각각
공고 분석 501, NCS 분석 501, KB 근거 없음 경고, 지원자격 "확인 필요"로 동작한다.

## PDF 업로드 흐름

1. `POST /documents/upload-url` `{fileName, contentType, sizeBytes, documentType}` → 201 `{documentId, uploadUrl, expiresInSeconds, status: PENDING}`
2. 브라우저가 `uploadUrl`로 바로 PUT. `Content-Type` 헤더를 요청 때와 같게 보낸다 (서명에 들어 있다)
3. `POST /documents/{id}/complete` → 202. 서버가 S3 객체의 크기·형식을 발급 때 값과 비교한다
4. DOCUMENT_EXTRACT 작업: 텍스트 레이어(pypdf) 먼저, 부족하면 Textract OCR → 정규화 텍스트 저장 → PROFILE_EXTRACT 작업을 이어서 보낸다
5. 화면은 `GET /documents/{id}`의 `extractionStatus`를 2초마다 본다: `UPLOADED → EXTRACTING → EXTRACTED → ANALYZING → COMPLETED`
   (`REQUIRES_USER_REVIEW` 사유 `TOO_LITTLE_TEXT`이면 텍스트 직접 입력을 안내, `FAILED`는 `errorCode`·`retryable`로 안내)

presigned URL은 응답에만 넣고 DB·멱등 결과·로그에 남기지 않는다. 같은 `Idempotency-Key`로 다시 요청하면 같은 문서에 URL을 새로 서명한다.

## 지표

`core/metrics.py`가 CloudWatch EMF 형식 JSON 한 줄을 stdout에 쓴다 (PutMetricData 권한 불필요). 네임스페이스는 설정 `metrics.namespace`,
차원은 `feature`. `DocumentParseFailure`, `LLMSchemaFailure`, `EvidenceValidationFailure`, `AnalysisLatency`(ms).

## 구조

| 경로 | 내용 |
|---|---|
| `src/mentoring/models/` | Pydantic 모델. 데이터 계약의 기준이다 |
| `src/mentoring/config/` | `mentoring_config.json`과 로더. 한도·재시도 횟수는 여기서만 읽는다 |
| `src/mentoring/ports.py`, `deps.py` | 저장소·S3·모델·작업 전송·기준 데이터 인터페이스와 의존성 묶음 |
| `src/mentoring/text_tools.py` | 정규화·개인정보 가리기·근거 검증 묶음. 실제 구현은 아래 Codex 모듈 |
| `src/mentoring/core/` | 비즈니스 함수. 문서 등록, 작업 실행, 역량 추출, 프로필 확인, 면접 요약 |
| `src/mentoring/llm/` | 역량 추출 프롬프트, MockLLM |
| `src/mentoring/store/` | 저장소 구현. `memory.py`는 테스트용 |
| `src/mentoring/api/` | REST 입구, 작업 입구, 오류 변환 |
| `src/mentoring/extract/` | (#41) PDF 텍스트 추출과 정규화 |
| `src/mentoring/privacy/` | (#42) 개인정보 가리기 |
| `src/mentoring/verify/` | (#43) 근거 인용·지어낸 수치 검사 |
| `src/mentoring/reference/` | (#37) NCS 기준 데이터 적재·조회 |
| `src/mentoring/stories/` | (#62) 경험 블록 모델·저장소·규칙. `flow.py`가 REST 입구용 순서(멱등·재시도)를 정한다 |
| `evals/` | (#44) 가상 이력서 정답셋, KB 검색 평가 도구 |

`mentoring`은 네임스페이스 패키지다(`src/mentoring/__init__.py`가 없다). 여러 작업이 하위 패키지를 따로 만들어도
충돌하지 않게 하려는 것이다. 하위 패키지는 각자 `__init__.py`를 가진다.

## 역량 추출 순서 (고정)

텍스트 읽기 → 개인정보 가리기(길이 보존) → 모델 호출 → 형식 검사(실패 시 1회 재시도) → 근거 인용 대조 →
원문에 없는 수치·날짜·자격 검사(있으면 1회 재요청) → 프로필 새 버전 저장

- 근거 인용이 원문에 없으면 근거로 저장하지 않는다. 근거가 하나도 남지 않은 역량은 프로필에 넣지 않고 `needsConfirmation`으로 돌린다
- 재요청 뒤에도 원문에 없는 내용이 남은 항목은 빼고, 작업과 문서를 `REQUIRES_USER_REVIEW`(사유 `EVIDENCE_MISMATCH`)로 둔다
- 모델이 고른 확인 상태는 쓰지 않는다. 확인 전 역량은 모두 `NEEDS_CONFIRMATION`이고 `VERIFIED`는 사용자 확인(`POST /profiles/{id}/confirm`)으로만 생긴다
- 새 문서를 분석하면 같은 프로필의 다음 버전이 된다. 버전은 고치지 않고 쌓는다

## 아직 정하지 않은 것

- 면접 요약 한도를 넘을 때 고르는 규칙 (M-5): 지금은 저장 순서대로 앞에서부터 자른다
- 추출 텍스트 확인·수정 경로 (M-2), 개별 삭제 (M-3), 완료 이벤트 (M-4)
