# Implementation Plan

## Overview

이 작업 목록은 `design.md`의 "Foundation 내부 작업 순서"에 맞춰 네 트랙으로 나눈다. 트랙 1은 문서, 트랙 2는 계약(`contracts/`), 트랙 3은 검사 도구(`tools/`), 트랙 4는 사용자 식별(`backend/common.py`)이다. 첫 2시간 목표(설계 "첫 2시간 목표")인 계약 C1~C6(작업 1~6), 식별 트랙(작업 8), `docs/api.md` 보강(작업 9)을 앞에 두었다. 이 작업들이 끝나면 A·B·C·FRONTEND는 예시 데이터로, backend-platform은 식별·오류 형식으로 개발을 시작할 수 있다. 검사 도구(작업 16~21)는 그 뒤에 붙여도 다른 파트를 막지 않는다. 각 최상위 작업의 "트랙·병렬·선행·소유" 줄을 보고 여러 개발자나 AI 에이전트가 겹치지 않게 작업을 고른다. 같은 파일을 고치는 작업은 그 줄에 적어 두었다. `*`가 붙은 작업은 테스트만 하는 선택 작업이다. 모든 작업은 저장소 파일만 다루고 AWS 자원 생성·배포·권한 변경은 하지 않는다. `infra/package.sh`는 이 스펙에서 고치지 않는다 (D-41 PROPOSED).

## Tasks

- [x] 1. Contract_Package 기반 만들기 (C1: base·validation·errors·document·registry)
  - 트랙: 2 · 병렬: 8, 9.1~9.3, 11~15 · 선행: 없음 · 소유: COMMON
  - 이 작업이 만드는 `registry.py`, `__init__.py`, `testing/strategies.py`에는 작업 2~5가 항목을 하나씩 더한다. 작업 2~5를 동시에 할 때는 자기 항목 줄만 더하고 머지 때 충돌을 정리한다.

  - [x] 1.1 패키지 뼈대, 공통 타입, 검사 오류 형식 만들기
    - `contracts/requirements.txt`(`pydantic>=2.7,<3`), `tools/test-tools.txt`(pytest, hypothesis)를 만든다.
    - `contracts/src/team07_contracts/__init__.py`, `base.py`를 만든다. `ContractModel`(`extra="forbid"`, `alias_generator=to_camel`, `validate_by_alias=True`, `validate_by_name=False`, `frozen=True`), `Part` 열거형, 공통 타입 `KstDateTime`, `IsoDate`, `YearMonth`, `SidoCode`, `SigunguCode`, `Code20`, `SafeId`, `Money`, `ExtractedBy`를 설계 "공통 타입" 표대로 둔다.
    - 정수·불리언은 `StrictInt`·`StrictBool`로, 날짜·시각은 형식 검사기를 붙인 문자열로 둔다.
    - `validation.py`에 `FieldError(path, rule, message)`, `ContractValidationError(code="INVALID_INPUT", contract, errors)`, `ContractVersionError(received, supported)`와 Pydantic `loc` → 카멜 경로 변환(`extra_forbidden`→`unknownField`, `missing`→`required`)을 둔다. 오류 메시지에 입력 값 원문을 넣지 않는다.
    - _Requirements: 3.3, 3.4, 3.5, 4.6, 7.5, 9.6_

  - [x] 1.2 Error_Envelope와 Error_Code_Catalog 구현
    - `contracts/src/team07_contracts/errors.py`에 `ErrorBody{code, message, requestId, retryable, details?}`, `ErrorEnvelope{error}`를 만든다. `code`는 `ERROR_CODES`에 있는 값만 받는다.
    - `ERROR_CODES: dict[str, ErrorCodeSpec{http, retryable, parts, alias_of, decisions}]`를 설계 Error_Code_Catalog 표의 27개 코드 그대로 채운다. 별칭(`VALIDATION_ERROR`→`INVALID_INPUT`, `MODEL_UNAVAILABLE`·`SOURCE_UNAVAILABLE`→`AWS_SERVICE_ERROR`)에는 `D-04`, HTTP·retryable을 정한 칸에는 `D-32`를 붙인다.
    - `normalize_code(code)`(별칭 → 대표 코드)와 `interview_error_to_envelope(err, request_id)`를 만든다. `err`는 `code`·`message`·`retryable` 속성만 읽고 `interview` 패키지를 import하지 않는다. 코드가 목록에 없으면 `["code"]`, `request_id`가 비면 `["requestId"]`를 담은 `ContractValidationError`를 낸다.
    - _Requirements: 3.8, 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 4.9_

  - [x] 1.3 계약 목록과 문서 함수 구현
    - `contracts/src/team07_contracts/registry.py`에 `ContractMeta{name, model, schema_version, owner, consumers, sources}`와 `CONTRACTS`를 만들고 `ErrorEnvelope`(1.0, BACKEND, 소비 A·B·C·FRONTEND, 근거 A §6.6·B §5.8·C §5.1·D-03)를 등록한다.
    - `contracts/src/team07_contracts/document.py`에 `validate(contract, data, *, schema_version, part=None)`, `dump(model)`(`mode="json"`, `by_alias=True`, `exclude_unset=True`), `check_schema_version(contract, value)`, `load_document(doc)`(봉투 `{contract, schemaVersion, examples|data}`)를 만든다.
    - `check_schema_version`은 문자열이 아니거나 `^\d+\.\d+$`가 아니거나 주 버전이 다르면 `ContractVersionError(contract, received, supported="1.x")`를 내고, 부 버전만 다르면 통과시킨다.
    - _Requirements: 10.1, 10.3, 10.4, 10.6_

  - [x] 1.4 오류 계약용 Hypothesis 전략 만들기
    - `contracts/src/team07_contracts/testing/strategies.py`에 유효한 ErrorEnvelope(별칭 코드, `details` 유무 포함) 전략과 `schemaVersion` 문자열 전략을 둔다. 실행 코드는 이 모듈을 import하지 않는다.
    - _Requirements: 4.5_

  - [ ]* 1.5 오류 응답 왕복 속성 테스트 작성
    - `contracts/tests/test_errors.py`, `max_examples=100`, `deadline=None`, `derandomize=True`, 주석 `# Feature: common-foundation, Property 1: 오류 응답 왕복`
    - **Property 1: 오류 응답 왕복**
    - **Validates: Requirements 4.1, 4.5**

  - [ ]* 1.6 오류 응답 형식 위반 거부 속성 테스트 작성
    - 필수 필드 삭제, 타입 변경, 목록에 없는 `code`, 정의되지 않은 키 추가(`requestId`를 최상위로 옮기기 포함)를 무작위로 가한다.
    - **Property 2: 오류 응답 형식 위반 거부**
    - **Validates: Requirements 4.6, 4.7**

  - [ ]* 1.7 InterviewError 변환 속성 테스트 작성
    - `code`·`message`·`retryable` 속성을 가진 가짜 객체로 확인한다.
    - **Property 3: InterviewError 변환**
    - **Validates: Requirements 4.8, 4.9**

  - [ ]* 1.8 계약 버전 검사 속성 테스트 작성
    - `contracts/tests/test_document.py`
    - **Property 20: 계약 버전 검사**
    - **Validates: Requirements 10.1, 10.3, 10.6**

  - [ ]* 1.9 오류 코드 목록 완전성 예시 테스트 작성
    - A §6.6, B §5.8, C §5.1 표의 코드를 테스트 안에 고정 목록으로 두고 `ERROR_CODES`에 모두 있는지, 별칭의 `alias_of`·`D-04`, D-32 표시가 맞는지 확인한다.
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 2. Async_Task_Status 계약 구현 (C5)
  - 트랙: 2 · 병렬: 3, 4, 5, 8, 9, 11~15 · 선행: 1 · 소유: COMMON
  - `registry.py`, `__init__.py`, `testing/strategies.py`에 항목을 더한다 (작업 3~5와 같은 파일, 자기 줄만 수정).

  - [x] 2.1 상태 값, Part 확장, 판정 함수 구현
    - `contracts/src/team07_contracts/async_status.py`에 `COMMON_STATUSES`(PENDING·PROCESSING 비종료, COMPLETED·FAILED 종료), `PartStatusSpec{id_field, extra_statuses, field_extensions}`, `STATUS_EXTENSIONS`(A `taskId` + `REQUIRES_USER_REVIEW`·`PARTIAL_SUCCESS` 종료, B `jobId`, C `sessionId` + `stage` 허용 값 6개)를 둔다.
    - 모듈을 읽을 때 확장 상태 이름이 공통 값과 겹치면 `ValueError`로 멈춘다.
    - `parse_async_status(part, data)`: `status` 대소문자 정확 일치, ID 필드 필수(`SafeId`), `FAILED`면 `error`가 필수이고 `ErrorBody` 검사 통과, 필드 확장 값 검사. 그 밖의 Part 결과 필드(`progress`, `report: null` 등)는 검사 없이 그대로 보존한다.
    - `is_terminal(part, status)`는 `status`만으로 정한다 (`stage == REPORT_READY`여도 `COMPLETED`가 아니면 비종료).
    - `CONTRACTS`에 `AsyncTaskStatus`(1.0, BACKEND, 근거 A §6·B §5.1·C §5.1·D-05)를 등록한다.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.8_

  - [ ]* 2.2 비동기 상태 왕복 속성 테스트 작성
    - `contracts/tests/test_async_status.py`, 값이 `null`인 결과 필드를 포함한다.
    - **Property 4: 비동기 상태 왕복**
    - **Validates: Requirements 5.6**

  - [ ]* 2.3 비동기 상태 값 판정 속성 테스트 작성
    - **Property 5: 비동기 상태 값 판정**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.7, 5.8**

  - [ ]* 2.4 FAILED 오류 객체 필수 속성 테스트 작성
    - **Property 6: FAILED에는 오류 객체가 필요하다**
    - **Validates: Requirements 5.4**

  - [ ]* 2.5 확장 이름 충돌 예시 테스트 작성
    - 임시 `STATUS_EXTENSIONS`에 `COMPLETED`를 넣고 검사 함수가 `ValueError`를 내는지 확인한다.
    - _Requirements: 5.3_

- [x] 3. Common_Profile 계약 구현 (C2)
  - 트랙: 2 · 병렬: 2, 4, 5, 8, 9, 11~15 · 선행: 1 · 소유: COMMON
  - `registry.py`, `__init__.py`, `testing/strategies.py`에 항목을 더한다 (작업 2·4·5와 같은 파일).

  - [x] 3.1 `CommonProfile`, `DesiredJob` 모델 구현
    - `contracts/src/team07_contracts/profile.py`에 설계 Common_Profile 표의 16개 필드를 모두 선택 필드로 둔다. `null`은 받아서 그대로 직렬화한다 (PUT의 "필드 삭제").
    - `birthYear` `StrictInt` 1950~2015, `desiredJobs` 0~3개(`name` 1~50자, `work24Code?`·`ncsCode?` `Code20`), `priorities` 허용 값 6개 중 0~3개, 열거형은 D-33 목록, `desiredRegion`은 `"ALL"` 또는 `SidoCode`, `monthlyIncome` 원 단위 정수(단위 필드 없는 예외).
    - 값 규칙이 `backend/me_api.py`의 `PROFILE_FIELDS`와 같은지 대조한다 (`backend/` 파일은 고치지 않는다).
    - 검사 오류는 필드마다 `FieldError{path, rule}`를 모두 담는다.
    - `CONTRACTS`에 `CommonProfile`(1.0, BACKEND, 소비 A·B·C·FRONTEND, 근거 B §10.3·db-schema §2.1·D-08)을 등록한다.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 7.8, 7.9, 7.10_

  - [ ]* 3.2 공통 프로필 왕복 속성 테스트 작성
    - `contracts/tests/test_profile.py`, 임의의 선택 필드 부분집합으로 만들고 없던 필드가 `null`로 생기지 않는지 확인한다.
    - **Property 11: 공통 프로필 왕복**
    - **Validates: Requirements 7.6**

  - [ ]* 3.3 공통 프로필 위반 거부 속성 테스트 작성
    - **Property 12: 공통 프로필 위반 거부**
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.8, 7.9, 7.10**

- [x] 4. Posting_For_Analysis 계약과 변환 함수 구현 (C3)
  - 트랙: 2 · 병렬: 2, 3, 5, 8, 9, 11~15 · 선행: 1 · 소유: COMMON
  - `registry.py`, `__init__.py`, `testing/strategies.py`에 항목을 더한다 (작업 2·3·5와 같은 파일).

  - [x] 4.1 공고 모델 구현
    - `contracts/src/team07_contracts/posting.py`에 `PostingForAnalysis`, `Requirement`, `EligibilityRule`, `WorkRegion`, `PostingJob`을 설계 표대로 만든다. 필드 이름은 `docs/db-schema.md` §3 catalog `SNAP#`과 `LATEST.isExpired`를 따른다.
    - `snapshotId` `^\d{8}-[0-9a-f]{8}$`, `officialUrl`은 `https://`, `workRegion.unknown == false`면 `sido` 필수, `requirementId`는 공고 안에서 서로 다름, `sourceQuote` 1자 이상, `extractedBy`는 `API`·`LLM`·`MANUAL`, `weight` > 0(기본 1.0).
    - `JobRequirementView`, `InterviewJobContext{job: 1~50자}` 모델을 만든다.
    - `CONTRACTS`에 `PostingForAnalysis`(1.0, B, 소비 A·C), `JobRequirementView`(1.0, B, 소비 A), `InterviewJobContext`(1.0, C, 소비 BACKEND)를 근거와 함께 등록한다.
    - _Requirements: 8.1, 8.2, 8.3, 8.9, 8.10, 8.12_

  - [x] 4.2 변환 함수와 내용 해시 구현
    - `to_job_requirement_view(p)`: 요건 순서와 `requirementId`·`kind`·`name`·`sourceQuote`·`weight`·`extractedBy`, `sourceType`, `isExpired`를 그대로 옮긴다. 마감 공고도 오류 없이 변환한다.
    - `to_interview_job_context(p)`: `len(p.job.name)`이 1~50이면 공백 정리 없이 그대로 옮기고, 아니면 `fields=["job.name"]`의 `INVALID_INPUT` `ContractValidationError`를 낸다.
    - `compute_content_hash(p)`: `snapshotId`·`checkedAt`·`updatedAt`·`isExpired`를 뺀 나머지를 키 정렬 JSON(UTF-8, 공백 없음)으로 만들어 sha256 hex 64자를 돌려준다 [D-39 PROPOSED].
    - 입력 모델은 `frozen`이라 변환 함수가 바꾸지 못한다.
    - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.7, 8.9, 8.11_

  - [ ]* 4.3 공고 왕복 속성 테스트 작성
    - `contracts/tests/test_posting.py`, 요건 0개·근무지 미상·마감 공고를 포함한다.
    - **Property 13: 공고 왕복**
    - **Validates: Requirements 8.8, 8.12**

  - [ ]* 4.4 공고 위반 거부 속성 테스트 작성
    - **Property 14: 공고 위반 거부**
    - **Validates: Requirements 8.2, 8.10**

  - [ ]* 4.5 Job_Requirement_View 변환 불변 속성 테스트 작성
    - **Property 15: Job_Requirement_View 변환 불변**
    - **Validates: Requirements 8.4, 8.5, 8.9, 8.11**

  - [ ]* 4.6 Interview_Job_Context 변환 속성 테스트 작성
    - **Property 16: Interview_Job_Context 변환**
    - **Validates: Requirements 8.6, 8.7, 8.9**

  - [ ]* 4.7 공고 내용 해시 속성 테스트 작성
    - **Property 17: 공고 내용 해시**
    - **Validates: Requirements 8.3**

- [x] 5. Career_Profile_Summary 계약 구현 (C4)
  - 트랙: 2 · 병렬: 2, 3, 4, 8, 9, 11~15 · 선행: 1 · 소유: COMMON
  - `registry.py`, `__init__.py`, `testing/strategies.py`에 항목을 더한다 (작업 2~4와 같은 파일).

  - [x] 5.1 `CareerProfileSummary` 모델 구현
    - `contracts/src/team07_contracts/career_summary.py`에 필수 `projects`·`skills`·`needsConfirmation`(문자열 목록, 빈 목록 허용)과 선택 `profileId`(`SafeId`)·`profileVersion`(`StrictInt` 1 이상)을 둔다.
    - `CAREER_SUMMARY_LIMITS` 상수에 `projects` 10개·200자, `skills` 30개·50자, `needsConfirmation` 10개·200자를 두고 `[D-40 PROPOSED]` 주석을 붙인다.
    - 항목은 `strip()` 뒤 빈 문자열이면 거부한다. `resumeText`, `targetJob`, `strengths`, `gapsToVerify`는 정의되지 않은 필드로 거부된다 (D-12 결정 반영). C → A 방향 필드나 변환 함수는 만들지 않는다.
    - `CONTRACTS`에 `CareerProfileSummary`(1.0, A, 소비 C·BACKEND, 근거 A §12.2·C §5.2·D-12)를 등록한다.
    - _Requirements: 9.1, 9.2, 9.4, 9.6, 9.7_

  - [ ]* 5.2 역량 요약 왕복 속성 테스트 작성
    - `contracts/tests/test_career_summary.py`, 선택 필드 없음과 빈 목록을 포함하고 목록 순서를 비교한다.
    - **Property 18: 역량 요약 왕복**
    - **Validates: Requirements 9.5**

  - [ ]* 5.3 역량 요약 위반 거부 속성 테스트 작성
    - **Property 19: 역량 요약 위반 거부**
    - **Validates: Requirements 9.6, 9.7**

- [x] 6. Fixture_Set과 JSON Schema 만들기 (C6)
  - 트랙: 2 · 병렬: 8, 9, 11~15 · 선행: 2, 3, 4, 5 · 소유: COMMON

  - [x] 6.1 JSON Schema 생성 스크립트와 스키마 파일 만들기
    - `contracts/src/team07_contracts/export_schemas.py`를 만들어 `python -m team07_contracts.export_schemas`가 `CONTRACTS`의 계약마다 `contracts/schemas/<Contract>.schema.json`(UTF-8, 카멜 이름)을 쓰게 한다.
    - 스크립트를 실행해 생성한 스키마 파일 7개를 저장소에 둔다.
    - _Requirements: 11.7_

  - [x] 6.2 유효한 예시 데이터 작성
    - `contracts/fixtures/valid/<contract>.json`을 계약마다 하나씩, 봉투 `{contract, schemaVersion, examples: [{name, data}]}` 형식으로 만든다.
    - `ErrorEnvelope`: `ERROR_CODES`의 코드마다 1개. `AsyncTaskStatus`: 공통 4개 + A 확장 2개 + C `stage` 값 6개마다 1개, `context: {"part": ...}`, `FAILED`에 `error`, C 예시 하나에 `"report": null`.
    - `CommonProfile`: 설계 "페르소나" 3명(B §7.1 프로필 칸 값만)과 빈 객체.
    - `PostingForAnalysis`: 부산 데이터 분석(`sido "26"`, `job.name "데이터 분석"`), 서울 데이터 분석(`sido "11"`), 근무지 미상(`unknown: true`), 마감 공고(`isExpired: true`). `organization`은 "가상"이 든 이름, `sourceType` `DEMO`, `officialUrl` `https://example.com/...`.
    - `JobRequirementView`·`InterviewJobContext`: 공고 예시마다 변환 결과와 `derivedFrom: "PostingForAnalysis/<예시 이름>"`.
    - `CareerProfileSummary`: C §5.2 예시 값, 같은 값 + `profileId: "profile-demo"`·`profileVersion: 1`, 데이터 분석 데모(각 목록 1개 이상, D-37), 빈 목록.
    - 모든 숫자·숫자 문자열의 연속 숫자는 11자리 이하로 두고, 이메일·전화번호·주민등록번호 형태 문자열을 넣지 않는다.
    - _Requirements: 9.9, 11.1, 11.2, 11.3, 11.4, 11.6, 11.7, 11.9, 11.11_

  - [x] 6.3 잘못된 예시 데이터 작성
    - `contracts/fixtures/invalid/<contract>.json`에 설계 "Fixture_Set 구성" 표의 잘못된 예시를 넣고, 예시마다 `expectedErrorFields`와 `stage`(`validate` 또는 `to_interview_job_context`)를 적는다.
    - `job.name` 51자 공고(`to_interview_job_context` 단계), `CareerProfileSummary`의 `resumeText`·`strengths`·`skills: [""]`·`projects` 없음을 포함한다.
    - _Requirements: 11.8_

  - [x] 6.4 예시 데이터 검사 테스트 작성
    - `contracts/tests/test_fixtures.py`: 유효 예시는 모두 통과, 잘못된 예시는 `expectedErrorFields`를 담은 오류로 거부, `derivedFrom` 예시는 변환 함수 결과와 같음, 예시 `schemaVersion`은 현재 버전과 정확히 같음, 연속 숫자 12자리 이상 없음.
    - 실패하면 파일 경로, 계약 이름, 기대 결과, 실제 결과를 assert 메시지로 출력한다.
    - 페르소나 3명, 부산·수도권 공고, 코드마다 오류 예시, 상태마다 예시, 데이터 분석 역량 요약이 있는지 구성도 확인한다.
    - _Requirements: 9.9, 10.7, 11.1, 11.2, 11.3, 11.4, 11.5, 11.8, 11.9, 11.10, 11.11_

  - [x] 6.5 계약 목록·스키마 일치·`score` 금지 검사 작성
    - `contracts/tests/test_registry.py`: `CONTRACTS`마다 소유 Part 1개, 소비 Part 1개 이상, 근거 1개 이상, 버전 `주.부` 형식. 커밋된 `contracts/schemas/*.schema.json`이 `export_schemas` 결과와 같은지 비교한다.
    - `contracts/tests/test_schema_rules.py`에 `find_score_fields(contract_name, schema) -> list[str]`를 두고(중첩 `properties`, `items`, `$defs` 포함), 모든 계약 스키마에서 결과가 빈 목록인지 확인한다. 오류에는 계약 이름과 속성 경로를 담는다.
    - _Requirements: 3.11, 7.7, 8.9, 9.4, 10.4, 11.7_

  - [ ]* 6.6 `score` 필드 금지 속성 테스트 작성
    - 무작위 JSON Schema 트리에 `score`·`fitScore`·`matchScore` 같은 이름을 섞어 `find_score_fields`를 확인한다.
    - **Property 21: `score` 필드 금지**
    - **Validates: Requirements 3.11**

- [ ] 7. Checkpoint - 계약 테스트 통과 확인
  - 트랙: 2 · 병렬: 8, 9 · 선행: 1~6 · 소유: COMMON
  - `uv run --no-project --with-requirements contracts/requirements.txt --with-requirements tools/test-tools.txt python -m pytest contracts/tests -q -p no:cacheprovider`를 `PYTHONPATH=contracts/src`로 실행한다.
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 묻는다.

- [ ] 8. Identity_Resolver 보완 (식별 트랙)
  - 트랙: 4 · 병렬: 1~7, 9, 11~15 · 선행: 없음 · 소유: BACKEND
  - 인증·보안 변경이므로 PR에서 BACKEND 담당에게 리뷰를 요청한다 (CONTRIBUTING). 배포와 Lambda 설정 변경은 이 작업 범위가 아니다.
  - `backend/common.py`는 이 작업만 고친다. 표준 라이브러리만 쓰고 `team07_contracts`를 import하지 않는다.

  - [ ] 8.1 식별 설정 읽기 구현
    - `backend/common.py`에 `Entry`(REST, AGENT_TOOL), `IdentityMode`(COGNITO_JWT, DEV_HEADER), `IdentityConfigError`(설정 값 이름만 담음), `IdentityConfig`, `load_identity_config(environ)`, 모듈 수준 `IDENTITY_CONFIG = load_identity_config(os.environ)`를 더한다.
    - 규칙: `ALLOW_DEV_USER_HEADER`가 없음·`""`·`"0"` → COGNITO_JWT, `"1"`이고 `AWS_LAMBDA_FUNCTION_NAME` 없음 → DEV_HEADER, `"1"`이고 `AWS_LAMBDA_FUNCTION_NAME` 있음 또는 그 밖의 값 → `IdentityConfigError("ALLOW_DEV_USER_HEADER")`.
    - 기존 `backend/test_me.py`·`test_interview.py`는 import 전에 `ALLOW_DEV_USER_HEADER="1"`을 넣으므로 `AWS_LAMBDA_FUNCTION_NAME`이 없을 때 그대로 동작하는지 확인한다.
    - _Requirements: 6.6, 6.7, 6.9, 6.10, 6.11_

  - [ ] 8.2 `get_user_id` 출처 고정과 검사 구현
    - 서명을 `get_user_id(event, entry=Entry.REST, config=None)`로 늘린다. 기존 호출 `get_user_id(event)`는 그대로 동작한다.
    - 출처는 하나만 읽는다: REST + COGNITO_JWT → `requestContext.authorizer.jwt.claims.sub`, REST + DEV_HEADER → 헤더 `x-user-id`, AGENT_TOOL → `sessionAttributes.userId`. DEV_HEADER 모드에서 JWT `sub`를 먼저 읽던 동작을 없앤다.
    - 출처 값이 없음·문자열 아님·`strip()` 뒤 1~128자 밖 → `TeamError(401, "UNAUTHORIZED")`. 통과 뒤 `#` 포함 → `TeamError(400, "INVALID_INPUT")`. 원래 문자열을 바꾸지 않고 돌려준다.
    - 본문·쿼리·경로·모델 파라미터의 `userId`와 면접 `sessionId`는 읽지 않는다. 오류 `message`·`details`에 사용자 ID를 넣지 않는다.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.9, 6.10, 6.12_

  - [ ] 8.3 `hash_user_id` 구현
    - `hash_user_id(user_id) = "u_" + sha256("team07-user:" + user_id).hexdigest()[:32]`
    - _Requirements: 6.8_

  - [ ] 8.4 식별 예시 테스트 작성
    - `backend/tests/test_identity.py`(pytest)를 만든다. COGNITO_JWT 모드에서 `x-user-id` 헤더 무시, AGENT_TOOL은 `sessionAttributes.userId`만 읽음, `inspect.signature(get_user_id)`가 모드와 무관하게 같음, 오류 메시지에 사용자 ID가 없음을 고정 이벤트로 확인한다.
    - 기존 `backend/test_*.py` 스크립트를 실행해 모두 통과하는지 확인한다.
    - _Requirements: 6.1, 6.2, 6.3, 6.9, 6.12_

  - [ ]* 8.5 사용자 ID 출처 고정 속성 테스트 작성
    - **Property 7: 사용자 ID 출처 고정**
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.6, 6.10**

  - [ ]* 8.6 잘못된 사용자 ID 거부 속성 테스트 작성
    - **Property 8: 잘못된 사용자 ID 거부**
    - **Validates: Requirements 6.5, 6.12**

  - [ ]* 8.7 식별 설정 검사 속성 테스트 작성
    - **Property 9: 식별 설정 검사**
    - **Validates: Requirements 6.7, 6.11**

  - [ ]* 8.8 사용자 ID 해시 속성 테스트 작성
    - **Property 10: 사용자 ID 해시**
    - **Validates: Requirements 6.8**

- [ ] 9. `docs/api.md` 보강 (API_Convention_Doc)
  - 트랙: 1 · 병렬: 1~8, 11~15 · 선행: 9.3·9.4는 1.2 · 소유: COMMON
  - `docs/api.md`는 이 작업만 고친다. 결정이 `CONFIRMED`인 항목은 결정 값을 그대로 적는다.

  - [ ] 9.1 공통 규약을 항목별 절로 나누기
    - §2를 경로 접두사(D-01), JSON 키(D-02), 인코딩(`application/json; charset=utf-8`), 날짜·시각(D-29, `+09:00`), 금액(D-30), `Idempotency-Key`, 데이터 기준일(D-06) 절로 나누고, 절마다 근거 명세 절과 결정 ID·상태를 적는다.
    - 금액 단위를 `MANWON_YEAR`, `MANWON_MONTH`, `MANWON`, `WON` 네 값으로 맞추고, `monthlyIncome`은 원 단위 정수이고 단위 필드가 없는 예외로 적는다 ("확인 필요: B 정책 소득 판정").
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.12_

  - [ ] 9.2 비동기·멱등성·Part 확장·점수 절 보강
    - 비동기: 202 본문 `{<리소스 ID>, status: "PENDING"}`, Part별 ID 필드(A `taskId`, B `jobId`, C `sessionId`), 처리 방식은 D-19 참조.
    - `Idempotency-Key`: 같은 키 + 같은 본문 → 첫 결과, 다른 본문 → 409 `PRECONDITION_NOT_MET`(D-31). 보존 기간은 공통 `IDEM#` 24시간, A "지원 권장", B §6.4 1시간은 B 절에 "확인 필요".
    - Part 확장 절: A `REQUIRES_USER_REVIEW`·`PARTIAL_SUCCESS`, B `stale`, C `stage`를 소유 Part·근거와 함께 추가 값으로만 적는다.
    - 점수·자격 상태 표: A `fitScore`·`potentialUpperBound` 0~100, B `matchScore` 0~1, `rankScore` "명세에 없음", C 종합 점수 0~100, B-16 1~9칸, 자격 상태 세 종류와 소유 Part (D-11).
    - _Requirements: 3.6, 3.7, 3.9, 3.10, 3.13_

  - [ ] 9.3 오류 코드 표를 `ERROR_CODES`와 맞추기
    - §5 오류 코드 표를 `team07_contracts.errors.ERROR_CODES`와 같은 코드·HTTP·retryable·별칭으로 맞춘다. `message`는 한국어, `code`는 영문 대문자라고 적는다.
    - _Requirements: 3.8, 4.2_

  - [ ] 9.4 `docs/api.md` 일치 테스트 작성
    - `contracts/tests/test_api_doc.py`: §5 표의 코드 집합이 `ERROR_CODES`와 같은지, R3 절 제목과 D-01·D-02·D-06·D-11·D-19·D-29·D-30·D-31이 문서에 있는지 확인한다.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.10, 3.12, 3.13, 4.2_

- [ ] 10. Checkpoint - 첫 2시간 목표 확인
  - 트랙: 전체 · 병렬: 11~15 · 선행: 7, 8, 9 · 소유: COMMON
  - `contracts/tests`, `backend/tests/test_identity.py`, 기존 `backend/test_*.py`를 실행한다.
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 묻는다.

- [ ] 11. README와 `.gitignore` 보강 (Repository_Baseline)
  - 트랙: 1 · 병렬: 1~9, 12~15 · 선행: 없음 · 소유: COMMON
  - `README.md`는 작업 23.3도 고친다. 이 작업이 먼저 끝나야 한다.

  - [ ] 11.1 README 폴더·소유, Python 버전, 파트 규칙, 예시 데이터 절 추가
    - 기존 내용을 유지하고 "폴더와 소유" 표를 추가한다. 행: `.kiro/`, `ai/`, `ai/mentoring/`, `ai/busan-opportunity/`, `ai/interview/`, `backend/`, `contracts/`, `docs/`, `examples/`, `frontend/`, `infra/`, `tools/`, 열: 경로, 소유 Part, 근거 문서와 절. 세부 소유는 `docs/conventions/ownership.md`를 가리킨다.
    - "Python 버전" 줄: `Python 3.13 — 선언 위치는 .python-version 하나 (D-15 CONFIRMED)`.
    - "파트 폴더 규칙": Part 폴더마다 `requirements.txt` 하나와 `tests/` 하나, 테스트 전용 패키지는 `local-check.toml`의 `test-requirements`, 다른 Part 의존성을 설치하지 않음, 내부 구조는 후속 스펙.
    - "예시 데이터": `contracts/fixtures/{valid,invalid}/`(UTF-8 JSON, 봉투 형식), `contracts/schemas/`.
    - _Requirements: 1.1, 1.3, 1.4, 11.7_

  - [ ] 11.2 `.gitignore` 범주 채우기
    - 설계 표의 패턴을 넣는다: `.env`, `.env.*`, `.aws/`, `*.pem`, `*.key`, `credentials`, `.venv/`, `venv/`, `build/`, `dist/`, `function.zip`, `*.egg-info/`, `node_modules/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.hypothesis/`, `.DS_Store`.
    - `contracts/fixtures/**`, `contracts/schemas/**`, `docs/decisions/*.yaml`이 걸리지 않게 한다.
    - _Requirements: 1.2_

- [ ] 12. `docs/conventions/ownership.md` 작성 (Ownership_Map, Contract_Change_Procedure)
  - 트랙: 1 · 병렬: 1~9, 11, 13~15 · 선행: 없음 · 소유: COMMON

  - [ ] 12.1 소유 표와 후속 스펙 표 작성
    - 설계 2절의 소유 표를 `` | `경로` | PART | 근거 | `` 형식 한 행 한 경로로 적는다 (R2.1의 공통 파일 포함, `contracts/`·`tools/`·`docs/conventions/`·`docs/decisions/` 포함).
    - 후속 스펙 10개마다 주 폴더와 소유 Part를 적고 내부 구조는 적지 않는다.
    - 규칙: 자기 소유 경로만 직접 수정, 가장 구체적인(긴) 항목 우선, 소유가 없는 경로는 COMMON 절차 + 같은 PR에서 소유 항목 추가.
    - _Requirements: 2.1, 2.2, 2.3, 2.7, 2.8_

  - [ ] 12.2 Contract_Change_Procedure 작성
    - 설계 "Contract_Change_Procedure" 표를 옮긴다: 계약 문서 커밋을 코드 커밋보다 앞에, CONTRIBUTING 규칙과 "참고 사항"의 영향 Part·Decision_Log ID("없음" 허용), 영향 Part 리뷰 요청과 팀 채널 공지(승인은 머지 조건 아님), 주·부 버전 올리기 규칙, `CONFIRMED` 전환 때 관련 문서 수정, 무효 항목은 `SUPERSEDED` + `supersededBy`.
    - 버전 올림 여부는 리뷰로 확인하고 Local_Check는 예시 버전만 본다고 적는다.
    - _Requirements: 2.4, 2.5, 2.6, 10.2, 10.5, 14.4, 14.8_

- [ ] 13. `docs/conventions/resources.md` 작성 (Resource_Naming_Convention)
  - 트랙: 1 · 병렬: 1~9, 11, 12, 14, 15 · 선행: 없음 · 소유: COMMON

  - [ ] 13.1 이름·태그·설정·자원 표와 비밀정보 규칙 작성
    - 리전 `ap-northeast-2`, 접두사 `team07-`, 태그 `team=team07` (D-21 CONFIRMED).
    - Part별 환경변수·설정 파일 표(BACKEND 변수, 런타임 제공 `AWS_REGION`·`AWS_LAMBDA_FUNCTION_NAME`, C `MODEL_ID`·`ai/interview/config/scoring_v1.json`, B `opportunity_config.json`, A 미정). 계정 ID가 든 이름은 `team07-<이름>-<계정ID>`.
    - 필수 값이 없으면 이름을 담은 오류로 멈추고 코드 안 기본값으로 대체하지 않는다는 규칙. 현재 `backend/me_api.py`·`interview_api.py`의 기본값은 backend-platform에서 고친다고 적는다.
    - 테이블·버킷 표(소유 Part, 읽기 Part, D-13·D-14·D-22 참조, 생성 상태는 `docs/db-schema.md` §8).
    - D-35의 배포 설정 값 이름으로 `AWS_LAMBDA_FUNCTION_NAME`을 쓴다고 적는다.
    - 비밀정보 규칙(Secrets Manager·IAM 역할, `aws login`, 액세스 키 금지, 값·계정 ID·API 주소 미기재), `team07-`·`team=team07`가 없는 자원은 건드리지 않고 생성·삭제·권한 변경은 사용자에게 먼저 확인.
    - 모델 제공자 접두사 목록 `anthropic.`, `cohere.`, `amazon.titan-`을 작업 20이 읽을 수 있는 고정 형식(예: 한 줄에 하나인 목록 절)으로 적는다.
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.8, 13.9_

  - [ ]* 13.2 `resources.md` 키워드 테스트 작성
    - `tools/tests/test_docs.py`에 리전·접두사·태그·D-21·변수 표·비밀정보 규칙·제공자 접두사 확인을 넣는다 (작업 14.3과 같은 파일, 함수만 따로 추가).
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.9_

- [ ] 14. `docs/conventions/integration-seam.md`와 `tools/parts.toml` 작성 (Integration_Seam_Doc)
  - 트랙: 1 · 병렬: 1~9, 11~13, 15 · 선행: 없음 · 소유: COMMON

  - [ ] 14.1 입구 목록·공통 규칙·오류 대응표 작성
    - 설계 6절의 입구 표(C 함수 8개와 호출 경로, B `opportunity.api.rest_handler`·`agent_handler`, A 미정 + 후속 스펙 이름, COMMON `team07_contracts`)와 패키지 이름·소스 위치를 적는다. 패키징은 D-17 결정 ID와 상태로만 참조한다.
    - 공통 규칙: Agent 입구와 REST 입구는 같은 비즈니스 함수, 사용자 ID는 백엔드가 `get_user_id()`로 읽어 넘김, D-23 OPEN(A 소유), C는 Agent 입구 없음, 자격 판정은 D-41 확정 전까지 "백엔드가 판정해 결과를 넘긴다".
    - 오류 대응표: C `InterviewError` → `INVALID_INPUT` 400, `AI_OUTPUT_INVALID` 500, `AWS_SERVICE_ERROR` 503, `retryable` 그대로. B·A는 미정 + 후속 스펙 이름.
    - 설계 Career_Profile_Summary "A → C 대응표"를 옮긴다 (`skills`는 `factStatus == VERIFIED`만, `needsConfirmation`은 확인이 필요한 역량).
    - _Requirements: 9.3, 9.8, 12.1, 12.2, 12.3, 12.6, 12.9_

  - [ ] 14.2 `tools/parts.toml` 작성
    - 설계 6절의 `[common]`, `[parts.A]`~`[parts.FRONTEND]`, `[import-aliases]`를 그대로 적는다.
    - _Requirements: 12.2, 12.5, 12.7_

  - [ ]* 14.3 Integration_Seam_Doc 키워드 테스트 작성
    - `tools/tests/test_docs.py`에 C 함수 8개, `parts.toml`의 `entries`가 문서에 모두 있는지, C 오류 코드 3개, D-17·D-23 표시를 확인하는 함수를 더한다 (작업 13.2와 같은 파일).
    - _Requirements: 12.1, 12.2, 12.3, 12.9_

- [ ] 15. `docs/decisions/decision-log.yaml` 작성 (Decision_Log)
  - 트랙: 1 · 병렬: 1~9, 11~14 · 선행: 없음 · 소유: COMMON
  - `requirements.md` 결정 표는 승인 시점 요약으로 두고 고치지 않는다.

  - [ ] 15.1 결정 항목 옮기기
    - `requirements.md` "결정 기록" 표의 D-01~D-37과 `design.md`의 D-38~D-41을 설계 "Decision_Log YAML" 스키마로 옮긴다. 필수 칸: `id`, `title`, `parts`, `options`(2개 이상, 각 `source`), `proposedDefault`, `owner`, `status`, `followUpSpecs`, `seam`, `origins`. `CONFIRMED`는 `decision{option, date: 2026-11-20, by}`.
    - OPEN 항목(D-23, D-24, D-27, D-38)은 `proposedDefault: {value: 없음, reason}`, PROPOSED 항목(D-39, D-40, D-41)은 선택지 중 하나와 출처. Seam은 설계 "OPEN·PROPOSED 항목의 Seam" 표대로.
    - 머리에 `requiredOrigins`(tech.md "기술 결정 상태" 1~14, structure.md "구조 결정" 항목, product.md "범위 관련 미확정" 항목)를 두고 설계 "출처 대응" 표대로 각 항목 `origins`를 채운다. 항목 이름은 현재 steering 파일의 제목을 읽고 맞춘다.
    - `AGENTS.md` "결정 상태"의 기준 문서 안내를 이 YAML 파일로 바꾼다 (COMMON 변경).
    - _Requirements: 1.3, 14.1, 14.2, 14.3, 14.5, 14.7_

- [ ] 16. Local_Check 실행기와 외부 접속 차단 만들기
  - 트랙: 3 · 병렬: 11~15 · 선행: 7 · 소유: COMMON
  - `tools/local_check.py`는 작업 23.1도 고친다. 이 작업은 실행기와 Part 테스트 단계만 만들고 검사 단계 연결은 23.1에서 한다.
  - `tools/tests`는 `PYTHONPATH`에 `tools`를 넣어 `local_check`, `checks.*`를 import한다.

  - [ ] 16.1 외부 접속 차단 모듈 구현
    - `tools/requirements.txt`(pyyaml)를 만든다.
    - `tools/guard/sitecustomize.py`: `TEAM07_NETWORK_GUARD=1`일 때만 `socket.socket.connect`, `connect_ex`, `socket.create_connection`, `socket.getaddrinfo`를 바꿔, 루프백(127.0.0.0/8, `::1`)·AF_UNIX가 아니면 `TEAM07_GUARD_LOG`에 `대상, 테스트 이름`(`PYTEST_CURRENT_TEST` 또는 스크립트 이름)을 쓰고 `ExternalAccessBlocked`를 바로 던진다.
    - _Requirements: 1.5, 1.9_

  - [ ] 16.2 실행기 뼈대와 환경 정리 구현
    - `tools/local_check.py`에 `StepResult{name, outcome: "성공"|"실패"|"테스트 없음", details}`, `summarize(results) -> (출력 줄, 종료 코드)`, 하위 프로세스용 환경 만들기(설계 9.2 표: AWS 자격 증명 변수 제거, `AWS_CONFIG_FILE`·`AWS_SHARED_CREDENTIALS_FILE`을 없는 경로로, `AWS_EC2_METADATA_DISABLED=true`, `AWS_MAX_ATTEMPTS=1`, `TEAM07_NETWORK_GUARD=1`, `TEAM07_GUARD_LOG`, `HTTP(S)_PROXY=http://127.0.0.1:9`)를 만든다.
    - 단계가 실패해도 다음 단계를 계속 실행하고, 실패 목록과 `전체: 실패 (N개 단계)`를 출력한다. 파일은 고치지 않는다.
    - _Requirements: 1.5, 1.8_

  - [ ] 16.3 Part 테스트 단계 구현
    - `tools/parts.toml`의 Part(A, B, C, BACKEND, FRONTEND)와 COMMON(`tools/tests`)마다 `<part>/local-check.toml`을 읽는다 (없으면 `[[test]] kind="pytest", path="tests"`). `kind` `pytest`·`script`·`command`를 설계 9.1의 `uv run --no-project ...` 명령으로 실행하고 `PYTHONPATH = tools/guard : contracts/src : <import-roots>`를 넣는다.
    - "테스트 없음": 폴더 없음, 테스트 파일 0개, glob 결과 0개, pytest 종료 코드 5.
    - 실패 테스트 이름은 pytest `-rf` 요약 줄, script는 파일 이름과 `FAIL` 줄에서 얻는다. `TEAM07_GUARD_LOG`에 기록이 있으면 "실패 (외부 접속 시도: 대상, 테스트 이름)".
    - 단계마다 300초 제한 시간, `uv` 없음·의존성 설치 실패·`local-check.toml` 형식 오류는 설계 "Local_Check 오류" 표의 문구로 기록한다.
    - _Requirements: 1.4, 1.5, 1.6, 1.8, 1.9_

  - [ ] 16.4 실행기 통합 테스트 작성
    - `tools/tests/test_local_check.py`: 임시 Part 폴더로 `tests/` 없음·0개 → "테스트 없음", 실패 테스트 이름 출력과 종료 코드 1, `socket.create_connection(("example.com", 443))` 테스트가 기다리지 않고 "외부 접속 시도"로 실패하는지 확인한다.
    - _Requirements: 1.5, 1.6, 1.8, 1.9_

  - [ ]* 16.5 Local_Check 결과 집계 속성 테스트 작성
    - **Property 26: Local_Check 결과 집계**
    - **Validates: Requirements 1.5, 1.6, 1.8**

- [ ] 17. 소유 경로 검사 구현 (`tools/checks/ownership.py`)
  - 트랙: 3 · 병렬: 18, 20, 21 · 선행: 12, 16 · 소유: COMMON

  - [ ] 17.1 `owner_of`와 소유 표 읽기 구현
    - `parse_ownership(md_text) -> list[Entry]`로 `docs/conventions/ownership.md` 표를 읽고, `owner_of(path, entries) -> Part | None`은 경로를 포함하는 항목 중 가장 긴 항목의 Part를 돌려준다.
    - `check(root) -> list[str]`: R2.1 대상 경로가 모두 표에 있고 각 항목에 Part가 하나인지, 후속 스펙 10개가 표에 있는지 확인한다. 각 검사 모듈은 이처럼 `check(root: Path) -> list[str]`(빈 목록이면 성공)과 단독 실행용 `main()`을 둔다.
    - _Requirements: 2.1, 2.3, 2.7, 2.8_

  - [ ]* 17.2 소유 경로 결정 속성 테스트 작성
    - `tools/tests/test_ownership.py`
    - **Property 27: 소유 경로 결정**
    - **Validates: Requirements 2.7, 2.8**

- [ ] 18. Secret_Scanner 구현 (`tools/checks/secrets.py`)
  - 트랙: 3 · 병렬: 17, 20, 21 · 선행: 16 · 소유: COMMON

  - [ ] 18.1 스캐너 구현
    - 대상: `git ls-files -z`와 `git diff --cached --name-only -z --diff-filter=ACMR`의 합집합 중 텍스트 파일(앞 8KB에 NUL 없음), `tools/secret-allowlist.toml` 제외. `git` 실패 시 "git 목록 없음".
    - 같은 줄의 `<...>` 구간을 같은 길이의 공백으로 바꾼 뒤 설계 9.3 정규식(계정 ID, 액세스 키는 모든 파일, 이메일·전화번호·주민등록번호는 `contracts/fixtures/**`만)을 적용한다.
    - 출력은 `경로:줄 종류`와 건수만, 찾은 값은 출력하지 않고 파일을 고치지 않는다.
    - _Requirements: 11.6, 13.5, 13.6, 13.7_

  - [ ] 18.2 허용 목록 만들기
    - `tools/secret-allowlist.toml`에 `{path, fingerprint, reason}` 형식을 정하고(`fingerprint` = 찾은 값 sha256 앞 16자), 스캐너가 이를 읽게 한다.
    - 현재 저장소에서 스캐너를 돌려 비밀이 아닌 값(예: `docs/개발계획서2.md` 공고 ID 예시, `backend/test_app.py`의 0 채운 UUID 끝 12자리)만 등록한다. 진짜 계정 ID나 키로 보이는 값이 나오면 등록하지 말고 사용자에게 알린다.
    - _Requirements: 13.5, 13.7_

  - [ ]* 18.3 비밀정보 검사 속성 테스트 작성
    - `tools/tests/test_secrets.py`
    - **Property 22: 비밀정보 검사**
    - **Validates: Requirements 11.6, 13.5, 13.6**

  - [ ]* 18.4 파일 비수정·건수 출력 예시 테스트 작성
    - 임시 git 저장소에서 검사 전후 파일 내용이 같고 건수가 출력되는지 확인한다.
    - _Requirements: 13.7_

- [ ] 19. Import_Rule_Checker 구현 (`tools/checks/imports.py`)
  - 트랙: 3 · 병렬: 20, 21 · 선행: 14, 16, 17 · 소유: COMMON

  - [ ] 19.1 import 분류와 위반 보고 구현
    - `ai/**/*.py`, `backend/**/*.py`, `contracts/**/*.py`(테스트 포함)를 `ast`로 읽어 `import`, `from … import`, `importlib.import_module("…")`, `__import__("…")`를 모은다.
    - 파일 Part는 `owner_of`로 정하고, 설계 9.4 표 순서(자기 Part → `team07_contracts` → `sys.stdlib_module_names` → BACKEND 모듈 → 다른 Part 패키지 → 자기 Part `requirements.txt`·`test-requirements` + `import-aliases` → 그 밖)로 판정한다. `backend/` 파일은 다른 Part의 `entries`(또는 패키지 루트)만 허용한다. `contracts/` 파일이 `ai/`·`backend/` 모듈을 import하면 위반이다.
    - 위반마다 `경로:줄  [Part] → 모듈`을 출력한다.
    - _Requirements: 12.4, 12.5, 12.7, 12.8_

  - [ ]* 19.2 import 규칙 속성 테스트 작성
    - `tools/tests/test_imports.py`, 임시 저장소에 가상 Part 파일을 만들어 확인한다.
    - **Property 23: import 규칙**
    - **Validates: Requirements 12.4, 12.5, 12.7, 12.8**

- [ ] 20. 모델 ID·Python 버전 검사 구현
  - 트랙: 3 · 병렬: 17, 18, 21 · 선행: 13, 16 · 소유: COMMON

  - [ ] 20.1 모델 ID 리터럴 검사 구현
    - `tools/checks/model_ids.py`: `ai/`·`backend/` 아래 `.py`의 `ast.Constant` 문자열(docstring 포함)에서 `(?:global\.)?(?:<제공자 접두사>)[A-Za-z0-9._:-]+`를 찾는다. 제공자 접두사는 `docs/conventions/resources.md` 목록에서 읽는다. `*.json`과 `examples/`는 대상이 아니다.
    - _Requirements: 13.8_

  - [ ] 20.2 Python 버전 검사 구현
    - `tools/checks/python_version.py`: 루트 `.python-version`이 하나이고 `X.Y` 형식인지, `pyproject.toml`의 `requires-python`(있으면)이 그 값을 포함하는지, `README.md`·`infra/*.sh`·`**/local-check.toml`의 `--python X.Y`, `--python-version X.Y`, `python3.XY`가 같은지 본다. `docs/개발계획서*.md`는 대상이 아니다.
    - _Requirements: 1.3_

  - [ ]* 20.3 모델 ID 리터럴 속성 테스트 작성
    - `tools/tests/test_model_ids.py`, 주석에만 있는 문자열은 보고하지 않는지 포함한다.
    - **Property 24: 모델 ID 리터럴**
    - **Validates: Requirements 13.8**

  - [ ]* 20.4 Python 버전 검사 예시 테스트 작성
    - 임시 저장소로 `.python-version` 두 개, 다른 버전 표기, 일치하는 경우를 확인한다.
    - _Requirements: 1.3_

- [ ] 21. 결정 기록 검사 구현 (`tools/checks/decisions.py`)
  - 트랙: 3 · 병렬: 17, 18, 20 · 선행: 15, 16 · 소유: COMMON

  - [ ] 21.1 Decision_Log 검사 구현
    - YAML을 읽어 필수 칸 빈칸 없음, ID 중복 없음, 상태 4개 중 하나, 상태별 규칙(OPEN "없음"+`reason`, PROPOSED 선택지 중 값+`source`, CONFIRMED `option`·`date`(`YYYY-MM-DD`)·`by`, SUPERSEDED 존재하는 `supersededBy`), `parts`·`followUpSpecs` 허용 값, `requiredOrigins`가 모두 어느 `origins`에 있는지 확인한다.
    - `requirements.md` "결정 기록" 표의 ID·상태가 YAML과 같은지 확인한다 (D-38~D-41은 표에 없으므로 표에 있는 ID만 비교).
    - 실패하면 `ID  칸 이름`을 모두 출력하고 파일은 고치지 않는다.
    - _Requirements: 14.1, 14.2, 14.6, 14.7, 14.9_

  - [ ]* 21.2 결정 기록 검사 속성 테스트 작성
    - `tools/tests/test_decisions.py`
    - **Property 25: 결정 기록 검사**
    - **Validates: Requirements 14.1, 14.6, 14.7, 14.9**

- [ ] 22. Checkpoint - 검사 도구 테스트 통과 확인
  - 트랙: 3 · 병렬: 없음 · 선행: 16~21 · 소유: COMMON
  - `tools/tests`를 실행하고, 각 검사 모듈의 `main()`을 현재 저장소에 실행해 결과를 확인한다.
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 묻는다.

- [ ] 23. Local_Check에 모든 단계 연결하고 README 마무리
  - 트랙: 전체 · 병렬: 없음 · 선행: 10, 11, 22 · 소유: COMMON (23.2는 BACKEND)

  - [ ] 23.1 검사 단계를 실행기에 연결
    - `tools/local_check.py`에 단계 순서대로 연결한다: Part 테스트 6개, 계약 검사(`contracts/tests` pytest), 비밀정보 검사, import 규칙, 모델 ID, Python 버전, 결정 기록. 출력 이름은 설계 9.1 출력 예와 같게 한다.
    - `--only <A|B|C|BACKEND|FRONTEND|contracts|secrets|imports|model-ids|python-version|decisions>`와 `--offline`(`UV_OFFLINE=1`)을 지원한다.
    - _Requirements: 1.5, 1.7, 1.8, 10.7, 11.5, 11.10, 12.8, 13.7, 13.8, 14.6, 14.9_

  - [ ] 23.2 BACKEND 테스트 설정 추가
    - `backend/local-check.toml`: `test-requirements = ["boto3", "moto[dynamodb,s3]"]`(현재 테스트가 쓰는 것과 맞춤), `[[test]] kind="script" glob="test_*.py"`, `[[test]] kind="pytest" path="tests"`.
    - BACKEND 소유 파일이므로 PR에서 BACKEND 담당에게 리뷰를 요청한다. 배포는 범위가 아니다.
    - _Requirements: 1.4, 1.5_

  - [ ] 23.3 README "로컬 확인" 절 추가
    - 전체 명령 `uv run --no-project --with-requirements tools/requirements.txt python tools/local_check.py`와 Part별 `--only A`~`--only FRONTEND` 명령 다섯 개, 검사 단계 이름을 적는다.
    - _Requirements: 1.7_

  - [ ] 23.4 저장소 기본 구성 테스트 작성
    - `tools/tests/test_repository.py`: README "폴더와 소유" 표가 `git ls-files` 최상위 폴더 집합(`.git/` 제외)과 같은지, `.gitignore` 범주별 예시 경로(`.env.local`, `.aws/credentials`, `x.pem`, `.venv/bin/python`, `build/lambda/x.py`, `contracts/.pytest_cache/x`, `docs/.DS_Store`)가 `git check-ignore`로 제외되고 `contracts/fixtures/`·`contracts/schemas/`·`docs/decisions/decision-log.yaml`은 제외되지 않는지, README의 명령을 그대로 실행하면 단계마다 한 줄 결과가 나오는지 확인한다.
    - _Requirements: 1.1, 1.2, 1.7_

  - [ ] 23.5 전체 Local_Check 실행과 정리
    - README 전체 명령을 실행해 A·B·FRONTEND는 "테스트 없음", 나머지는 "성공"인지 확인한다. 실패하면 원인을 고치고, 비밀이 아닌 값이 걸리면 18.2 규칙대로 허용 목록에 등록한다.
    - _Requirements: 1.5, 1.6, 1.8_

- [ ] 24. Final Checkpoint - 전체 Local_Check 통과 확인
  - 트랙: 전체 · 병렬: 없음 · 선행: 23 · 소유: COMMON
  - README의 전체 명령으로 Local_Check를 실행해 종료 코드 0을 확인한다.
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 묻는다.

## Notes

- `*`가 붙은 작업은 선택이다. 빼도 기능은 완성되지만, 속성 테스트(Property 1~27)는 계약과 검사 도구의 정확성을 확인하는 주된 수단이므로 시간이 되면 함께 한다.
- 같은 파일을 고치는 작업: `contracts/src/team07_contracts/registry.py`·`__init__.py`·`testing/strategies.py`(작업 1~5), `README.md`(11.1, 23.3), `tools/local_check.py`(16, 23.1), `tools/tests/test_docs.py`(13.2, 14.3). 병렬로 할 때는 자기 항목 줄만 고치고 머지 때 충돌을 정리한다.
- 작업 8(`backend/common.py` 인증 변경)과 23.2(`backend/local-check.toml`)는 BACKEND 소유라 PR에서 BACKEND 담당에게 리뷰를 요청한다. 배포, Lambda 설정 변경, `infra/package.sh` 변경은 이 스펙 범위가 아니다.
- 각 검사 모듈은 `check(root: Path) -> list[str]`(빈 목록이면 성공)과 단독 실행용 `main()`을 두고, `tools/local_check.py`가 23.1에서 이를 `StepResult`로 감싼다. 설계에 없는 세부 사항이라 이 목록에서 정했다.
- OPEN 결정(D-23, D-24, D-27, D-38)에 걸리는 구현은 하지 않는다. PROPOSED 결정(D-39, D-40, D-41)은 설계의 Seam(`compute_content_hash`, `CAREER_SUMMARY_LIMITS`, `evaluate_eligibility` 서명) 뒤에 둔다.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "8.1", "9.1", "11.1", "11.2", "12.1", "13.1", "14.1", "14.2", "15.1"] },
    { "id": 1, "tasks": ["1.2", "8.2", "9.2", "12.2", "13.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "1.9", "8.3", "9.3", "14.3"] },
    { "id": 3, "tasks": ["1.5", "1.6", "1.7", "1.8", "2.1", "3.1", "4.1", "5.1", "8.4", "9.4"] },
    {
      "id": 4,
      "tasks": ["2.2", "2.3", "2.4", "2.5", "3.2", "3.3", "4.2", "5.2", "5.3", "8.5", "8.6", "8.7", "8.8"]
    },
    { "id": 5, "tasks": ["4.3", "4.4", "4.5", "4.6", "4.7", "6.1", "6.2", "6.3"] },
    { "id": 6, "tasks": ["6.4", "6.5"] },
    { "id": 7, "tasks": ["6.6"] },
    { "id": 8, "tasks": ["7"] },
    { "id": 9, "tasks": ["10", "16.1", "16.2"] },
    { "id": 10, "tasks": ["16.3", "17.1", "18.1", "20.1", "20.2", "21.1"] },
    {
      "id": 11,
      "tasks": ["16.4", "16.5", "17.2", "18.2", "18.3", "18.4", "19.1", "20.3", "20.4", "21.2", "23.2"]
    },
    { "id": 12, "tasks": ["19.2"] },
    { "id": 13, "tasks": ["22"] },
    { "id": 14, "tasks": ["23.1"] },
    { "id": 15, "tasks": ["23.3"] },
    { "id": 16, "tasks": ["23.4"] },
    { "id": 17, "tasks": ["23.5"] },
    { "id": 18, "tasks": ["24"] }
  ]
}
```
