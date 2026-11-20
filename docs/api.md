# 팀 공통 API 규칙 (v1.0)

7팀 · 공통 백엔드 담당 · 2026-11-20
A(멘토링), B(부산 기회 추천), C(AI 모의면접) 명세의 공통 부분과, 세 명세가 충돌하던 부분의 결정을 모았다.
각 절의 `D-xx`는 `.kiro/specs/common-foundation/requirements.md` 결정 기록(Decision_Log) 항목이다.
기능별 API 상세는 각 파트 명세를 따른다. DB는 `docs/db-schema.md`.

## 1. 주소 (D-01 CONFIRMED)

| 경로 | 파트 | 상태 |
|---|---|---|
| `/api/v1/interview/*` | C 모의면접 | ✅ 배포 (면접 함수는 대역, `interview/` 패키지가 들어오면 교체) |
| `/api/v1/mentoring/*` | A 멘토링 (`/profiles/me`는 **역량 프로필**) | 백엔드 연결 (`backend/mentoring_api.py`). A 패키지, AWS 의존성 팩터리 또는 필수 AWS 설정이 없으면 501 |
| `/api/v1/opportunities/*` | B 부산 기회 추천 | 연결됨 (`backend/opportunities_api.py`). 배포는 백엔드 담당 확인 후 |
| `/api/v1/agent/chat` (POST 202) · `/api/v1/agent/chat/{sessionId}` (GET) · `/api/v1/agent/chat/{sessionId}/messages/{messageId}` (GET) | 채팅 Agent (D-38, `docs/개발계획서4.md` §7) | 연결 (`backend/agent_api.py`). `supervisor` 패키지가 없으면 501 |
| `/api/v1/me/profile` (GET, PUT) | 공통 **기본 프로필** (`PROFILE#BASIC`). PUT은 보낸 필드만 수정, `null`이면 삭제 | ✅ |
| `/api/v1/me/workspaces` (GET `?status=`, POST) · `/api/v1/me/workspaces/{wsId}` (GET, PATCH) | 워크스페이스 목록·생성(중복이면 기존 것)·상세(연결된 분석·첨삭·학습·면접)·상태와 문서 버전 변경 | ✅ |
| `/api/v1/auth/*`, `/api/v1/me` | 로그인 | ✅ |
| `/api/v1/health` | 상태 확인 | ✅ |

API 주소(`API_BASE`)는 팀 채널 공지 참고. 저장소가 공개라 적지 않는다.
API Gateway는 **HTTP API** (payload v2.0). Powertools를 쓰면 `APIGatewayHttpResolver`를 쓴다 (`APIGatewayRestResolver` 아님).

A의 REST 요청은 백엔드에서 확인한 사용자 ID를 `mentoring.api.rest_handler.handle`에 넘긴다.
`mentoringTask` 키가 있는 Lambda 내부 이벤트는 `mentoring.api.task_handler.handle`에 넘긴다.
두 입구는 `mentoring.store.factory.build_aws_deps()`가 만든 `Deps`를 재사용하고, `Deps.hash_user_id`는 백엔드 공통 함수를 사용한다.

## 2. 형식 (카멜 표기 D-02 · 시각 `+09:00` D-29 · 금액 D-30 CONFIRMED)

- JSON, UTF-8, **카멜 표기** 필드
- 날짜 `YYYY-MM-DD`, 시각 ISO 8601 `+09:00`
- 금액은 정수 + 단위 필드 (`MANWON_YEAR`, `MANWON_MONTH`, `WON`)
- 저장 계열 POST는 `Idempotency-Key` 헤더 (서버는 `IDEM#` 조건부 쓰기)
- ID 안에 `#` 금지 (주소에 들어가면 요청이 깨짐). 받으면 400

## 3. 로그인과 사용자 식별 (D-07 · D-35 CONFIRMED)

**아이디·비밀번호 로그인 (Cognito)** · 데모 계정 `demo1` `demo2` `demo3` (B 페르소나 ①②③, 기본 프로필 채워 둠)

| 경로 | 토큰 | 하는 일 |
|---|---|---|
| `POST /api/v1/auth/login` `{username, password}` | 없이 | `{accessToken, idToken, refreshToken, expiresIn}` (액세스 토큰 1시간) |
| `POST /api/v1/auth/refresh` `{refreshToken}` | 없이 | 새 `accessToken` (갱신 토큰 30일) |
| `GET /api/v1/me` | 필요 | `{userId, username}` |
| `GET /api/v1/health` | 없이 | 상태 확인 |
| **그 밖의 모든 경로** | **필요** | `Authorization: Bearer {accessToken}`. 없거나 틀리면 API Gateway가 401 |

- 데모 계정 비밀번호는 **AWS 콘솔 → Secrets Manager → `team07/demo-accounts`**에서 본다. 저장소·채팅에 적지 않는다.
- userId = 토큰의 `sub`. 서버는 `backend/common.py`의 `get_user_id()`로만 읽고, 요청 본문·쿼리의 userId는 무시한다.
- `X-User-Id` 헤더는 **배포 환경에서 꺼졌다** (로컬 테스트에서만 `ALLOW_DEV_USER_HEADER=1`).
- 로그인 실패는 아이디가 없든 비밀번호가 틀리든 같은 `401 INVALID_CREDENTIALS` (아이디 존재 여부를 숨김).
- 계정은 관리자만 만든다 (회원가입 없음). 계정 추가: `infra/seed_demo.py`에 추가 후 실행.
- 채팅 Agent(D-38) 도구에는 userId 인자가 없다. 백엔드가 토큰의 sub를 도구에 넣는다. B의 Bedrock Action Group 경로(남겨 둠)는 `sessionAttributes.userId`만 쓴다.

**소셜 로그인 (Google·카카오, Cognito 외부 로그인 · 이슈 #98)** · OAuth 2.0 인가 코드 + PKCE

| 경로 | 토큰 | 하는 일 |
|---|---|---|
| `GET /api/v1/auth/social/providers` | 없이 | `{providers: [{id, label}]}`. 설정이 없으면 빈 목록 (오류 아님) |
| `POST /api/v1/auth/social/start` `{provider, redirectUri, state, codeChallenge}` | 없이 | `{authorizeUrl}` (Cognito `/oauth2/authorize`, `scope=openid`, `S256`). 모르는 제공자·형식 오류는 400, 설정이 없으면 503 |
| `POST /api/v1/auth/social/token` `{code, redirectUri, codeVerifier}` | 없이 | 로그인 응답 + `username`("Google 계정", "카카오 계정"). 코드가 틀리거나 만료면 `401 INVALID_CREDENTIALS`, Cognito 연결 실패는 503 |

흐름: 화면의 버튼 → `start` → `authorizeUrl`로 이동 → 제공자 로그인 → `/login/callback/?code=…&state=…` → 화면이 `state`를 확인하고 `token` → 그다음은 아이디 로그인과 같다 (갱신도 `/auth/refresh`).
- 제공자에게는 `openid`만 요청한다. 이름·이메일·전화번호는 받지도 저장하지도 로그에 남기지도 않는다. 인가 코드와 토큰도 로그에 남기지 않는다.
- `redirectUri`는 `https://`(로컬 개발은 `http://localhost`)여야 하고 경로가 `/login/callback/`로 끝나야 한다. Cognito 앱 클라이언트에 등록한 주소와 글자까지 같아야 한다.
- 설정은 `infra/setup-social-login.sh`로 한다. 클라이언트 ID와 비밀값은 Secrets Manager `team07/social-login`에만 둔다.
- 소셜 로그인 사용자 계정은 처음 들어올 때 Cognito가 만든다고 보고 있다. 관리자만 계정을 만드는 지금 설정에서도 그런지는 미확인이다.

## 4. 오래 걸리는 처리 (상태 값 D-05 · 처리 방식 D-19 CONFIRMED)

- `202` + 리소스 ID (`taskId`, `sessionId` 등) → 화면이 상태 API를 2초마다 조회
- 공통 `status`: `PENDING` / `PROCESSING` / `COMPLETED` / `FAILED`
- 파트별 추가 값은 그대로 쓴다: A `REQUIRES_USER_REVIEW`, `PARTIAL_SUCCESS` · C `stage`(`QUESTION_GENERATING` …)
- 뒤에서 처리: SQS 권한이 없어 **Lambda 비동기 자기 호출**로 한다 (면접에서 동작 중). 권한이 나오면 SQS로 바꾸고, 함수 입출력은 그대로다.

## 5. 오류 (형식 D-03 · 코드 별칭 D-04 CONFIRMED)

```json
{ "error": { "code": "INVALID_INPUT", "message": "사용자에게 보여 줄 한국어 문장", "requestId": "req-…", "retryable": false, "details": {} } }
```

- `requestId`는 **`error` 안**에 둔다. `details`는 선택 (A의 `sourceType` 등)
- 공통 코드 (세 파트 모두 같은 이름으로)

| 코드 | HTTP | 상황 | retryable |
|---|---|---|---|
| `INVALID_INPUT` | 400 | 필수 값 누락, 형식 오류. 별칭: A `VALIDATION_ERROR` | false |
| `UNAUTHORIZED` | 401 | 토큰 없음·만료 (API Gateway가 막으면 본문 없이 401) | false |
| `INVALID_CREDENTIALS` | 401 | 로그인 실패 | false |
| `NOT_FOUND` / `{리소스}_NOT_FOUND` | 404 | 없거나 **남의 리소스** (존재 여부를 숨기려고 403 대신 404) | false |
| `PRECONDITION_NOT_MET` | 409 | 선행 작업 미완료, 동시 수정 | false |
| `FILE_TOO_LARGE` | 413 | 크기 초과 | false |
| `RATE_LIMITED` | 429 | 호출 한도 | true |
| `AI_OUTPUT_INVALID` | 500 | AI 출력 형식 검사 실패 (재시도 후) | true |
| `INTERNAL_ERROR` | 500 | 기타 | true |
| `AWS_SERVICE_ERROR` | 503 | Bedrock·S3·Transcribe 등 실패. 별칭: A `MODEL_UNAVAILABLE`, `SOURCE_UNAVAILABLE` (`details.sourceType`에 원래 코드) | true |
| `NOT_IMPLEMENTED` | 501 | 아직 연결 안 된 경로 | false |

별칭 코드는 파트 코드가 그대로 내도 되고, 백엔드가 응답할 때 대표 코드로 바꾼다 (D-04). 파트 전용 코드는 그대로 쓴다: A `DOCUMENT_UNREADABLE`, `EVIDENCE_MISMATCH` · B `POSTING_NOT_FOUND`, `PROFILE_INCOMPLETE`, `URL_NOT_ALLOWED` · C `SESSION_NOT_FOUND`, `INVALID_STATE`, `ANSWER_ALREADY_SUBMITTED`

## 6. 파트 간 결정 사항

### 6.0 워크스페이스는 공통 함수로

- B의 `POST /saved`는 `backend/workspace.py`의 `workspace_put()`을 `OPP#SAVED#`와 **한 트랜잭션**으로 쓴다. 지원 상태는 `set_status()`로 워크스페이스에만 쓴다.
- B의 `DELETE /saved/{id}`는 `OPP#SAVED#`와 마감 일정만 지우고 워크스페이스는 지우지 않는다. 분석·첨삭·면접 기록이 붙어 있을 수 있어서다. 다시 저장하면 같은 워크스페이스에 이어 붙는다.
- A·C는 결과를 저장할 때 `GSI1PK = USER#{userId}#WS#{workspaceId}`, `GSI1SK = {ANALYSIS|REVIEW|PATH|INTERVIEW}#{createdAt}#{id}`를 넣으면 워크스페이스 상세에 자동으로 나온다.


### 6.1 지원 자격 판정은 한 함수로

- 공고의 자격 조건은 B가 catalog 스냅샷 `eligibilityRules[]`에 저장한다.
- **판정은 `backend/eligibility.py`의 `evaluate_eligibility(profile, rules)` 하나만 쓴다.** A(직무 적합도)와 B(공고 상세)가 같은 공고에 다른 결과를 내지 않게 하려는 것.
- 조건별 결과는 B 방식(`MET`/`NOT_MET`/`UNKNOWN`), 전체 결과는 A 방식(`ELIGIBLE`/`INELIGIBLE`/`NEEDS_VERIFICATION`). 프로필에 없는 자격증은 `NOT_MET`이 아니라 `UNKNOWN` (A 원칙 "서류에 없음 ≠ 없음").

### 6.2 직무 코드와 데모 직무

- 공고·프로필에 **고용24 직종 코드와 NCS 코드를 둘 다** 둔다 (`job.code`, `job.ncsCodes[]` / `desiredJobs[{work24Code, ncsCode, name}]`).
- 둘을 잇는 표는 `team07-reference`의 `MAP#WORK24#{직종코드}` (B가 고용24 직무정보 API로 채움). A는 NCS 코드로, B는 직종 코드로 계산한다.
- C는 직무 이름 문자열을 쓴다 (워크스페이스의 공고에서 넘김).
- **데모 직무는 "데이터 분석" 하나로 통일**: B 페르소나 ①, A NCS 빅데이터분석(20010105), C는 데이터 분석 가상 자소서.

### 6.3 점수 이름

| 점수 | 파트 | 화면 표시 |
|---|---|---|
| `matchScore` (0~1) | B | 숫자 없이 "잘 맞아요 / 맞는 편이에요 / 조금 맞아요" |
| `fitScore` (0~100) | A | "서류 기반 일치도". 합격 확률 아님 문구 필수 |
| `totalScore` (0~100) + `grade` | C | "면접 연습 점수" |

### 6.4 공고 요건 종류

`requirements[].kind` = `REQUIRED_SKILL` / `PREFERRED_SKILL` (A 계약 값). 각 항목에 `sourceQuote`(공고 원문 인용).

### 6.5 프로필 두 가지

| 이름 | 저장 | API | 내용 |
|---|---|---|---|
| 기본 프로필 | `PROFILE#BASIC` | `/api/v1/me/profile` | 나이, 거주지, 학교, 학력, 전공, 희망 직무, 취업 상태 (온보딩), 희망 최소 연봉·신입/경력 (D-40) |
| 역량 프로필 | `PROFILE#LATEST` → `PROFILE#{id}#V#n` | `/api/v1/mentoring/profiles/me` | 이력서에서 뽑은 역량과 근거 (A) |

### 6.6 에이전트

- 통합 Agent (D-38): Strands Agents를 `team07-api` 안에서 돌린다 (`ai/supervisor/` → `supervisor` 패키지, 입구 `/api/v1/agent/chat`). 도구는 B `agent_feed`·`agent_policies`·`ask_policies`(Bedrock Action Group 경로와 같은 함수)와 A 문서·프로필을 부른다. C 면접관은 Strands이고 Agent끼리 직접 부르지 않는다 (면접 화면 이동, `docs/개발계획서4.md` §10).
- 채팅 조건 저장 (D-40): Agent가 말로 묻고, 사용자가 채팅으로 승낙하면 저장 도구가(`me_api.update_profile`), [저장하기]를 누르면 화면이 `PUT /api/v1/me/profile`로 저장. 기본 프로필에 `desiredSalaryMin`(만 원/년), `desiredCareerType` 추가.
- 채팅 공고 검색 순서 (`docs/개발계획서4.md` §9.1): 공식 데이터(공공 API 수집) → 없으면 그렇다고 말하고 팀 데이터. 시연 중 공공 API 실시간 호출은 없다.
- 모델: `global.anthropic.claude-haiku-5-5`, `global.anthropic.claude-sonnet-5-5` (서울 리전에서 호출 확인). 모델 ID는 환경 변수·설정 파일로.

### 6.7 배포

- CloudFormation 권한이 없어 CDK·SAM 대신 `infra/*.sh` (AWS CLI)로 배포한다.
- Lambda 실행 역할은 공용 `team07-lambda-role` (`team07-*` 자원으로 제한). 새 권한이 필요하면 백엔드 담당에게 요청.
- 런타임 Python 3.13 (A·B의 3.12 이상 요구 충족).
