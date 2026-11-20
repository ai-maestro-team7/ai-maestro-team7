---
inclusion: always
---

# Tech

기준: 개발계획서1(A)·2(B)·3(C), 제안서 7~8장, 이전 뼈대 커밋 `4aa11cc`의 `README.md`·`team-guide.md`·`api.md`·`db-schema.md`·`backend/`·`infra/`.
이전 뼈대는 정리해 PR #9~#14로 다시 들어왔다. 2026-11-20 결정 기록으로 대부분 확정됐고, 확정 내용은 `docs/api.md`, `docs/db-schema.md`, 아래 "기술 결정 상태"가 기준이다. 남은 미확정 항목만 임의로 정하지 말고 사용자에게 확인한다.

## 이전 뼈대에서 정한 환경 (유지 여부 확인 필요)
- 리전 `ap-northeast-2`는 B·C 명세에도 팀 규칙으로 적혀 있다.
- 이 문서에 나오는 AWS 자원(Lambda, HTTP API, 실행 역할, 테이블, 버킷)은 이전 스크립트로 만든 것이다. 저장소 초기화 뒤에도 계정에 남아 있는지는 확인하지 않았다.
- 자원 이름 접두사 `team07-`, 태그 `team=team07`
- 다른 팀과 같이 쓰는 계정이다. 다른 팀 자원은 건드리지 않는다.
- 자격 증명은 `aws login`. 액세스 키를 만들지 않는다. 로컬 Python에서 쓰려면 `botocore[crt]`가 필요하다 (Lambda는 실행 역할 사용).
- 공개 저장소다. 계정 ID, API 주소, API 키, 개인정보를 커밋하지 않는다. 스크립트는 계정 ID를 실행할 때 조회한다.
- Python 3.13 (`.python-version`, Lambda `python3.13` arm64), 실행 도구 `uv`
- IaC: CloudFormation 권한이 없어 AWS CLI 셸 스크립트를 썼다. 이 제약이 그대로라면 CDK·SAM처럼 CloudFormation을 거치는 도구는 쓸 수 없다.
- 배포: 단일 Lambda `team07-api`(타임아웃 30초) + HTTP API `team07-http-api`, 공용 실행 역할 `team07-lambda-role`. 모든 경로가 mock 응답이었다. 새 Lambda와 권한은 백엔드 담당에게 요청한다.
- Bedrock 모델 (이전 team-guide, 2026-11-20 확인): `global.anthropic.claude-haiku-5-5`(라우팅·짧은 답변), `global.anthropic.claude-sonnet-5-5`(분석·첨삭). 임베딩 후보 `global.cohere.embed-v4:0`, `amazon.titan-embed-text-v2:0`. 코드에는 환경변수나 설정 파일로 넣는다 (C `MODEL_ID`, B `opportunity_config.json`).

## 라이브러리 (명세 기준)
- boto3, Pydantic v2(입출력·LLM 출력 검사), pytest
- C: `strands-agents`. B: AWS Lambda Powertools (`APIGatewayRestResolver`, `BedrockAgentResolver`, 멱등 유틸, EMF 지표)
- 프론트엔드 (D-24 CONFIRMED, 프론트 담당 2026-11-20): Next.js 16 App Router, React 19, TypeScript strict, Tailwind CSS v4, lucide-react, 글꼴 Noto Sans KR. `output: "export"` 정적 내보내기(`frontend/out/`)를 S3 `team07-web-<계정ID>` + CloudFront로 배포한다 (이전 api.md). 정적 내보내기와 함께 쓸 수 없어 `cacheComponents`(PPR)는 끈다. 명령은 `frontend/`에서 `npm run lint`, `npm run typecheck`, `npm run build`. 설계는 `.kiro/specs/frontend-ui/`
- 프론트 CI/CD: `.github/workflows/frontend-ci.yml`(PR 검사), `frontend-deploy.yml`(main 머지 → S3 sync + CloudFront 무효화, OIDC 역할 `team07-github-deploy`). 웹 자원은 `infra/setup-web.sh`(사람이 실행)가 만들고 Secrets `WEB_BUCKET`·`WEB_DISTRIBUTION_ID`를 등록한다

## AWS 서비스
| 서비스 | 용도 | 파트 | 이전 뼈대 현황 (스크립트·IAM 정책 기준) |
|---|---|---|---|
| Bedrock LLM | 문서·공고 분석, 첨삭, 설명 문장, 면접 질문·평가 | A·B·C | Anthropic 모델 호출 권한 있음 |
| Bedrock 임베딩 | 공고·프로필 벡터, KB | A·B | 호출 권한 없음 |
| Bedrock Knowledge Bases | NCS·공정채용·상담 방법론 검색, 정책 원문(B P1) | A·B | S3 Vectors 권한이 없어 생성 대기, CSV 폴백으로 개발 |
| Bedrock Agents + Action Group | 통합 Agent, `BusanOpportunity` 툴 | A·B | 없음 (프레임워크 미확정) |
| Bedrock Guardrails | 보조 안전 검사 (한국어 지원 확인 후) | A, B(P1) | 없음 |
| S3 | 업로드, 개인 문서, KB 원천, 원본 데이터, 데모 스냅샷 | 전체 | `uploads`·`career-docs`·`kb-source` 버킷 |
| S3 Vectors | 공고 벡터 검색, KB 벡터 저장소 후보 | B·A | 권한 없음 |
| DynamoDB | 사용자·문서·분석·공고·정책·면접 데이터 | 전체 | 테이블 6개 (아래) |
| Lambda, API Gateway(HTTP API) | API·워커·수집·알림 | 전체 | `team07-api` 하나 |
| SQS + DLQ | 비동기 작업 | A, B(P1), C(검토) | 없음 |
| Step Functions | A 분석 순서(선택), B 수집(P1) | A·B | 없음 |
| EventBridge Scheduler, 이벤트 버스 | 매일 수집, 일회성 알림, 주간 리포트, 이벤트 발행(P1) | B | 없음 |
| DynamoDB Streams | 새 부산 공고 매칭 (P1) | B | 없음 |
| Textract | 스캔 PDF OCR (텍스트 레이어 우선) | A, B(P2) | 권한 있음 |
| Transcribe, Polly, Rekognition | 답변 음성 변환, 질문 음성, 얼굴 각도 | C | 권한 있음 |
| Cognito | 사용자 인증 | 공통 | 사용자 풀 `team07-users`, API JWT 검사 (D-07) |
| Secrets Manager | 외부 API 인증키 | A·B | 권한 없음 |
| CloudWatch, SNS, SES | 로그·지표·알람, 운영 알림, 사용자 메일(샌드박스) | 전체 | 로그 권한만 |
| X-Ray(P1), Data Firehose + Athena(P2) | 요청 추적, 유도 지표 집계 | B | 없음 |

- B 명세가 쓰지 않기로 한 것: Amazon Personalize, OpenSearch Serverless, Neptune, Bedrock AgentCore, 다른 채용 사이트 크롤링. 제안서는 OpenSearch·Neptune을 선택 도입으로 두었고, A는 OpenSearch를 벡터 저장소 후보로 둔다.

## AI Agent 구조
- 방향 (제안서 7.3): 통합 멘토링 Agent 하나와 기능별 도구·워크플로를 조합한다. 기능마다 독립 Agent를 만들지 않는다.
- 지금 (D-38, `docs/개발계획서4.md`): 통합 Agent는 Strands로 `team07-api` 안에서 돈다. 패키지 `ai/supervisor/`, 입구 `POST /api/v1/agent/chat`(202 + 조회). 도구 5개(내 상태, 공고 검색, 정책 매칭, 정책 질문, 면접 준비). 아래 Bedrock Agents·Action Group 설명은 이전 계획이며 B Action Group 경로는 남아 있다.
- A F-06: `CareerMentoringAgent` + Action Group. 상위 지침 `CAREER_MENTOR_AGENT_PROMPT.md`와 라우터 `00_PROMPT_ROUTER.md`가 요청마다 primary_intent 1개와 기능 프롬프트(01~07) 1개만 적용한다 (프롬프트는 지식 패키지 ZIP에 있음).
- B §5.9: `BusanOpportunity` Action Group. REST와 같은 비즈니스 함수를 입구만 달리해 노출하고, 사실 목록만 돌려준다 (공고 최대 5개). 저장 동작은 사용자 확인 후 실행한다 (P1).
- C: Strands Agents SDK 면접관 에이전트 (질문 생성, 꼬리질문 판단, 내용 평가, 피드백). AWS 호출·측정·점수 계산은 에이전트 툴이 아닌 일반 코드로 한다. 통합 Agent와는 페이지 이동으로만 연결한다.
- 이전 뼈대: `POST /chat`이 대화형 기능의 단일 입구였고 `backend/app.py`에 "Strands 에이전트 호출로 교체" TODO가 있었다. `examples/strands_hello.py`가 Strands + Bedrock 예제였다.
- 공통 규칙
  - Agent는 고정 파이프라인의 검증·저장 순서를 건너뛰지 않는다. Agent가 실패해도 기능별 API는 따로 동작한다.
  - Agent 도구는 userId를 모델 파라미터로 받지 않고, 백엔드가 넣은 세션 값만 쓴다 (A F-06, B §5.9·T-20).
  - 점수·금액·합계·날짜는 도구(코드)가 계산하고, LLM은 도구가 준 사실만 설명한다.
  - 대화 문맥은 사용자·공고 세션 단위로 나누고, 이력서 전문 대신 필요한 근거 요약만 넘긴다.

## LLM·데이터 처리 규칙
- LLM 출력은 고정 JSON 스키마로 받고 Pydantic으로 검사한다. 실패하면 재시도 1회 후 실패 또는 확인 필요 상태로 남긴다. 조용히 통과시키지 않는다.
- 근거 인용(quote, sourceQuote, evidence)은 원문에 실제로 있는지 대조한다. 없으면 근거로 저장하지 않는다.
- API에서 받은 값(마감일·근무지·급여)은 LLM 결과로 덮어쓰지 않는다. 값을 만든 주체(API/LLM/MANUAL)를 남긴다.
- 외부 텍스트는 태그로 감싸 데이터로만 넘긴다 (프롬프트 인젝션 방어).
- 결과에는 modelId, promptVersion, 규칙·점수 정책 버전, 기준일을 남긴다.
- 날짜 계산은 asOf를 받아서 한다. 가중치·임계값은 설정 파일에서 읽고, 읽을 때 검증한다 (B: 가중치 합 1, busanBoost < inversionGuard).
- KB에는 지식 패키지 `bedrock/documents/`의 13쌍(`.md` + `.md.metadata.json`)만 올린다. 개인 문서, 평가셋, 프롬프트, 재배포 조건이 확인되지 않은 원본(`raw/`)은 색인하지 않는다.
- NCS 코드·자격 연계·점수 규칙은 정형 데이터(CSV·DB)로 정확히 조회한다. 의미 검색은 설명 근거를 찾을 때만 쓴다.
- 공고·교육과정·시험일정·정책 모집처럼 자주 바뀌는 값은 DB·API에서 읽고 출처·기준일을 붙인다. 확인하지 못한 일정·모집 상태는 만들지 않는다. B는 새벽 수집 데이터만 읽고 시연 중 공공 API를 부르지 않는다.
- 외부 데이터 (승인·실호출 검증 필요): 고용24(채용정보·공통코드·강소기업·직무·직업·훈련과정), 잡알리오, NCS(공공데이터포털), 국가자격 종목·시험일정, 온통청년, 부산광역시 청년지원프로그램·공공부문 일자리, 인사혁신처 공공취업정보, 국토부 전월세 실거래가(B 비교 패널). 저장·재배포 조건을 지키고 공고 원문 전체를 다시 내보내지 않는다.

## 점수 (파트마다 다르다)
| 이름 | 파트 | 범위 | 뜻 |
|---|---|---|---|
| fitScore / potentialUpperBound | A | 0~100 | 서류에 나온 근거 기준 일치도 하한 / 미확인 역량을 고려한 상한 |
| matchScore | B | 0~1 | 공고 적합도. 부산 가산점 없음. 화면에는 3단계 문구 |
| rankScore | B | - | 정렬 전용. 부산 우선 정렬일 때만 가산점 |
| 면접 종합 점수 | C | 0~100 | 내용·전달력·태도 가중 합 (`ai/interview/config/scoring_v1.json`) |
| 서류 준비도 1~9칸 | B-16 | 1~9 | 공기업 서류 준비도 |

- 점수는 코드로만 계산하고 같은 입력이면 같은 값이 나와야 한다. 측정하지 못한 항목은 빼고 남은 가중치로 다시 나눈다. 합격 확률로 표현하지 않는다. 수식과 값은 각 명세와 설정 파일이 기준이다.

## API (D-01~D-05 확정: `docs/api.md`. 아래 표는 확정 전 비교 기록)
| 항목 | 이전 뼈대 `api.md` v0.2 · `app.py` | 개발계획서 1~3 |
|---|---|---|
| 경로 | `/chat`, `/upload-url`, `/profile/{user_id}`, `/resume/analyze`, `/interviews`, `/jobs/{job_id}` | `/api/v1/mentoring/*`, `/api/v1/opportunities/*`, `/api/v1/interview/*` |
| 필드 | snake_case | camelCase |
| 사용자 식별 | 로그인 없음. 브라우저가 만든 UUID `user_id`를 요청에 넣음 | A·B: Cognito JWT `sub`, 요청 본문 userId 불신. C: MVP 인증 없음 |
| 오류 | `{"error": "CODE", "message": ...}` | `{"error": {code, message, requestId, retryable}}` (A는 requestId를 밖에 두고 details 추가) |
| 오래 걸리는 작업 | 202 + `job_id` → `GET /jobs/{id}`, `pending/processing/done/failed` | 202 + 리소스 ID → 리소스 조회, `PENDING/PROCESSING/COMPLETED/FAILED` (A는 `REQUIRES_USER_REVIEW`·`PARTIAL_SUCCESS` 추가, C는 `stage` 추가) |
| 금액 | 원 단위 정수 | B: 정수 + 단위 필드 |

- 양쪽 공통: JSON UTF-8, 시각 ISO 8601(+09:00), 30초를 넘길 수 있는 작업은 202 후 상태 조회, 사용자에게 보여줄 오류 문구는 한국어
- 명세 쪽 추가 규칙: 생성·저장 POST에 `Idempotency-Key` (A·B), 응답에 데이터 기준일 (A `checkedAt`, B `dataAsOf`)
- 새 엔드포인트는 어느 규약을 따를지 확인한 뒤 만든다. 프론트는 `API_BASE`와 응답 파싱을 한곳에 모은다 (이전 team-guide).

## 저장 자원
- DynamoDB (이전 스크립트가 생성): `team07-users`·`team07-chat`·`team07-jobs`(TTL)·`team07-interviews`·`team07-cache`(TTL), `team07-career-mentor`(PK/SK + GSI1, TTL `expiresAt`). 이전 `app.py`는 앞의 5개 이름만 참조했다.
- 테이블 구성안 (미확정): 이전 `db-schema.md`는 `career-mentor`(사용자 데이터 전부, PK `USER#{userId}`)·`catalog`(공고 스냅샷·정책·기업)·`reference`(NCS·자격)·`cache` 4개로 통합하자고 제안한다. B 명세는 `Postings`·`Policies`·`OppUserState`·`OppIdempotency`, C 명세는 `InterviewSessions`(PK sessionId)를 따로 둔다. → D-13 확정: 4개 통합 구성 (`docs/db-schema.md` v1.3, B·C 동의). 키 구조를 바꿀 때는 db-schema를 먼저 고친다.
- 원칙 (A §7, db-schema): 사용자 데이터는 사용자 키 아래에 두고 Scan 없이 GetItem·Query로 조회한다. 400KB를 넘을 수 있는 원문은 S3에 두고 키만 저장한다. 분석 결과는 덮어쓰지 않고 버전으로 쌓는다. 사용자 문서·분석 결과에는 TTL 자동 삭제를 쓰지 않는다.
- S3 (이전 `infra/config.sh`): `team07-uploads-<계정ID>`(업로드, `uploads/` 7일 뒤 삭제), `team07-career-docs-<계정ID>`(개인 문서, `users/{hashedUserId}/`), `team07-kb-source-<계정ID>`(KB 원천 `docs/`), `team07-web-<계정ID>`(화면, 생성 스크립트 없음). 앞의 세 버킷은 퍼블릭 액세스 차단.

## 보안·개인정보
- 비밀정보는 Secrets Manager나 IAM 역할로만 다룬다. 코드·Git·`.env`·로그·채팅·문서에 실제 키, 계정 ID, API 주소를 남기지 않는다.
- 로그에는 requestId, 해시한 사용자 ID, 단계, 처리 시간, 오류 코드만 남긴다. 이력서·자소서·면접 답변 원문, 얼굴 이미지, presigned URL, 키가 들어간 URL은 남기지 않는다.
- 다른 사용자의 데이터를 읽거나 바꿀 수 없어야 한다. 요청으로 받은 S3 key는 서버가 발급했고 요청한 사용자 것인지 확인한 뒤 쓴다 (A는 S3 key를 요청으로 받지 않는 방식).
- 개인 문서를 공용 KB에 넣거나 다른 사용자 추천 근거로 쓰지 않는다.
- 얼굴 이미지는 저장하지 않고 각도 값만 쓴다. 녹음은 변환 후 지운다 (제안서 7.2, C).
- 개발용 설정(CORS `*`, B의 개발용 사용자 헤더)은 공개 배포 전에 좁히거나 없앤다.
- IAM은 최소 권한으로 준다. 지금은 공용 역할 하나라서 A §11의 역할 분리와 다르다.

## 착수 전 확인 (문서 기재 항목과 코드 비교 결과)
- 이전 실행 역할 정책에 없던 권한: 임베딩 모델 호출, S3 Vectors, Secrets Manager, SQS, EventBridge Scheduler, SES, SNS, CloudWatch 지표 전송, (Bedrock Agents를 쓰면) Agent 호출
- 한국어 처리: Textract OCR, Guardrails(Standard tier), Transcribe(단어별 시간, 브라우저 녹음 형식), Polly 음성(지혜/서연), Rekognition EyeDirection·Pose
- 외부 API: 승인 상태, 일일 한도, 응답 필드 (첫 응답을 S3에 저장한 뒤 매핑 확정). 잡알리오·국가자격 시험일정은 승인 확인 필요, 부산 청년지원프로그램·국토부 전월세는 신청 필요 (B §3.1)
- SES 샌드박스 수신 주소 검증, AWS Budgets 알림

## 기술 결정 상태 (2026-11-20, 결정 기록 기준)
| 번호 | 결정 | 결정 기록 |
|---|---|---|
| 1 | Cognito JWT `sub`, 아이디·비밀번호 로그인, 데모 계정 `demo1`~`demo3` | D-07 CONFIRMED |
| 2 | Strands Agents를 `team07-api` 안에서 (`ai/supervisor/`, `/api/v1/agent/chat`). D-23(Bedrock Agents) 대체 | D-38 CONFIRMED |
| 2-1 | 홈은 채팅 입구, 조건 저장은 사용자에게 묻기 | D-39·D-40 CONFIRMED |
| 3 | `docs/api.md` | D-01~D-05 CONFIRMED |
| 4 | `career-mentor`·`catalog`·`reference`·`cache` | D-13 CONFIRMED |
| 5 | catalog `SNAP#`·`LATEST` 스냅샷, 요건 `requirements[]{kind REQUIRED_SKILL/PREFERRED_SKILL, sourceQuote}` | D-09·D-10 CONFIRMED |
| 6 | Part별 값 유지, 공고 자격 판정은 `backend/eligibility.py` 하나 | D-11 CONFIRMED |
| 7 | `PROFILE#BASIC` (db-schema §2.1) | D-08 CONFIRMED |
| 8 | C 명세 + 면접 담당 요청으로 구현·배포 | D-20 CONFIRMED |
| 9 | 이력서 `career-docs`, 면접 녹음 `uploads` | D-14 CONFIRMED |
| 10 | Lambda 비동기 자기 호출 | D-19 CONFIRMED |
| 11 | S3 Vectors 1024차원 코사인, `global.cohere.embed-v4:0` | D-22 CONFIRMED |
| 12 | Next.js 16 App Router + TypeScript + Tailwind CSS v4, 정적 내보내기 (`frontend/`) | D-24 CONFIRMED |
| 13 | Python 3.13, AWS CLI 스크립트 | D-15·D-16 CONFIRMED |
| 14 | 정리해 재사용 (PR #9~#14) | D-25 CONFIRMED |

확정 전 비교 기록 (참고):
1. 사용자 식별·인증: 로그인 없는 UUID(api.md) / Cognito JWT(A·B·제안서) / MVP 무인증(C)
2. 통합 Agent 프레임워크: Bedrock Agents + Action Group(A·B) / Strands(백엔드 뼈대)
3. API 규약: 위 API 표
4. DynamoDB 구성: 위 테이블 구성안
5. 공고 데이터 계약: A는 `jobPostingId` + `snapshotId`로 스냅샷 보존, B는 `postingId`로 같은 공고를 덮어쓰고 마감 + 14일 TTL, db-schema는 `team07-catalog`에 스냅샷 보존. 요건 구조도 A(`requirements[{kind, weight, sourceQuote}]`)와 B(`requirements{required, preferred, ..., evidence}`)가 다르다.
6. 상태 값: 지원자격이 A `ELIGIBLE/INELIGIBLE/NEEDS_VERIFICATION`, B 공고 `MET/NOT_MET/UNKNOWN`, B 정책 `ELIGIBLE/NOT_ELIGIBLE/CHECK_NEEDED`, api.md `eligible/ineligible/unknown`. api.md 공고 카드의 `fit_score`(0~100)와 A·B 점수의 관계
7. 공통 프로필 필드: api.md는 지역·직무를 이름으로, B §10.3은 지역 코드·직종 코드(최대 3개)와 `educationLevel`·`priorities`로 받는다.
8. 모의면접 API·저장: api.md는 질문을 동기로 만들고 5초마다 캡처를 S3에 올려 7일 보관, C 명세는 202 + `/status`, 2초마다 `/frame`, 이미지 미저장, Lambda 타임아웃 60초 이상 필요 (이전 뼈대는 30초)
9. 이력서 업로드 위치: api.md·코드는 `uploads` 버킷(7일 뒤 삭제), A·db-schema는 `career-docs` 버킷
10. 비동기 처리: SQS + DLQ(A) / 백엔드 `/jobs` 폴링 / C는 SQS 또는 상태 조회 때 다음 단계 진행
11. 벡터 저장소(S3 Vectors / OpenSearch)와 임베딩 모델(Cohere v4 / Titan v2, 차원)
12. 프론트엔드 프레임워크
13. 버전·도구: B 명세는 Python 3.12·CDK(Python), 이전 뼈대는 Python 3.13·AWS CLI 스크립트(CloudFormation 권한 없음)
14. 이전 뼈대(`4aa11cc`)의 환경·자원·문서를 계속 쓸지
