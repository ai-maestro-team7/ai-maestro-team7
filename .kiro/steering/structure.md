---
inclusion: always
---

# Structure

## 저장소 구성 (2026-11-20)
```
docs/
  프로젝트_제안서.md    기획 전체
  개발계획서1.md        A 파트 명세
  개발계획서2.md        B 파트 명세
  개발계획서3.md        C 파트 명세
  CONTRIBUTING.md      협업 규칙
.kiro/steering/         product.md, tech.md, structure.md
AGENTS.md               AI 코딩 에이전트 규칙 (steering 요약)
ai/
  mentoring/            A 역량 분석·첨삭·학습 경로·통합 Agent
  busan-opportunity/    B 부산 기회 추천
  interview/            C AI 모의면접 함수
backend/                공통 백엔드·인프라 (API, 인증, DB·S3, 배포)
frontend/               프론트엔드 화면
```
- 최상위 폴더는 PR #1(커밋 `9d5958c` "Ai·Backend·Frontend 폴더 구조 추가")에서 만들고, PR #2(커밋 `b941a68` "최상위 폴더 이름을 소문자로 변경")에서 이름을 소문자로 바꿨다. 다섯 폴더 모두 `.gitkeep`만 있고 코드는 아직 없다.
- 폴더와 파트 연결은 폴더 이름과 명세 기준이다: `mentoring` = A(`/api/v1/mentoring`), `busan-opportunity` = B(개발계획서2 §13), `interview` = C(개발계획서3).
- 아직 README, 설정 파일(.gitignore 포함), 빌드·테스트 명령, CI가 없다.
- 이전 뼈대: 커밋 `4aa11cc` "백엔드·인프라 뼈대 추가"가 `README.md`, `.gitignore`, `.python-version`(3.13), `backend/`(단일 Lambda `app.py`, 로컬 확인 스크립트), `infra/`(AWS CLI 생성·배포 스크립트, IAM 정책), `examples/strands_hello.py`, `docs/api.md`·`db-schema.md`·`team-guide.md`를 담고 있었다. 2026-11-20 11:05 "저장소 초기화" 커밋(`089499a`)으로 `main`에서 빠졌다. steering에서 "이전 뼈대"라고 적은 내용은 이 커밋 기준이며, 팀이 그 결정을 유지하는지 확인해야 한다.
- 문서에 나오지만 저장소에 없는 것: 지식 패키지 `team7-career-mentor-knowledge-package-2026-11-20.zip`(`README_START_HERE.md`, 스켈레톤, `bedrock/documents/`, `structured/` CSV, `agent/` 프롬프트, `validation/`, `integrations/collect_official_apis.py`), A의 `openapi.yaml`, B 아키텍처 그림(노션 임베드), C 기능 정리 페이지(노션)

## 문서 지도
| 문서 | 볼 때 |
|---|---|
| `docs/프로젝트_제안서.md` | 서비스 목적, 기능 4.1~4.13, 아키텍처, MVP 범위 판단 |
| `docs/개발계획서1.md` | A: 이력서·Story Bank·적합도·첨삭·역량 격차·학습 경로·통합 Agent·AI 검증·운영 |
| `docs/개발계획서2.md` | B: 공고·정책 수집, 부산 우선 추천, 비교, 정책 지갑, 저장·알림, Action Group |
| `docs/개발계획서3.md` | C: AI 모의면접 함수 명세 |
| `docs/CONTRIBUTING.md` | 이슈·브랜치·커밋·PR·리뷰 |

- API 계약·DB 설계·팀 환경 안내 문서(이전 뼈대의 `api.md`, `db-schema.md`, `team-guide.md`)는 지금 저장소에 없다.

## 파트와 소유 범위
| 파트 | 담당 | 소유 | 연결 |
|---|---|---|---|
| A 역량 분석·첨삭·학습 경로 | 문서에 이름 없음 | CareerProfile, Story Bank, 적합도, 첨삭, 역량 격차, 학습 경로, 통합 Agent, AI 검증·운영 지표 | 공고는 B에서 읽고, 면접에 프로필 요약을 준다 (A §12) |
| B 부산 기회 추천 | 박상원 | 공고·정책 수집·보강, 피드·대안·비교, 정책 지갑, 저장·알림, BusanOpportunity 툴 | 공고·정책 데이터는 A·C에 읽기 전용 (B §10) |
| C AI 모의면접 | 현지 | 면접 함수 (질문, 꼬리질문, 음성, 시선, 점수, 리포트) | 백엔드가 세션을 꺼내고, 함수를 부르고, 결과를 저장한다 |
| 백엔드·인프라 | 문서에 이름 없음 | API Gateway, Lambda 배포, DB·S3, 인증, 공통 프로필, IAM | 새 Lambda·권한 요청 창구 (이전 team-guide §4) |
| 프론트엔드 | 문서에 이름 없음 | 화면, 녹음·타이머, 카메라 캡처, 문구 | B 문구 규칙(§4.7), C 전달 규칙(§5.6) 적용 |
| 워크스페이스·문서 버전 | 미정 | 공고별 워크스페이스, 지원서 최종본·버전 | A는 workspaceId, B는 저장 이벤트(P1)로 연결 예정 |

- 다른 파트의 기능을 중복 구현하지 않고 계약(API, 읽기 권한, 이벤트)으로 연결한다.

## 파트별 코드 구조 (최상위 폴더는 PR #1·#2 기준, 내부 구조는 명세 기준)
- B (개발계획서2 §13): `ai/busan-opportunity/` 아래 `src/opportunity/{models, config, seeds, ingest, enrich, core, api, notify}`, `mocks/`, `tests/{unit, rules, personas, contract}`, `AGENTS.md`, `infra/`(CDK)
  - `models/`는 Pydantic 계약, `config/`는 `opportunity_config.json`, `core/`는 순수 규칙(LLM 호출 금지), `enrich/`는 LLM 추출·설명·임베딩, `api/`는 REST 입구와 Agent 입구가 같은 함수를 부른다.
- C (개발계획서3): `ai/interview/` 폴더 (`config/scoring_v1.json`, `samples/`). 백엔드가 import해서 부른다. 함수는 DB·API를 직접 부르지 않고 Bedrock·Polly·Transcribe·Rekognition만 부른다. 단계별 PR로 전달한다.
- A (개발계획서1): 위치는 `ai/mentoring/`. 내부 폴더 구조는 명세에 없다. 구성 단위는 멘토링 API, 분석 워커(Extract → Validate → Profile → Retrieve → Calculate → Save 순서 고정), 공식 데이터 어댑터 `OfficialDataPort`, 지식 패키지의 수집 스크립트 재사용이다.
- 이전 뼈대는 `backend/app.py` 단일 Lambda에 `ROUTES` 표로 경로를 붙이는 방식이었고, `infra/package.sh`가 `backend/` 바로 아래의 `.py`만 묶었다. 지금 백엔드 폴더도 이름이 `backend/`로 같다. 이 방식을 그대로 다시 쓰면 `ai/` 아래 코드는 패키징에 포함되지 않으므로 백엔드 담당과 맞춘다.
- `busan-opportunity`처럼 하이픈이 든 폴더 이름은 Python 패키지로 바로 import할 수 없다. B 명세처럼 그 아래 `src/opportunity/`에 패키지를 둔다.

## 코딩 규칙
- 비즈니스 로직은 입력·출력이 분명한 함수로 두고, 입구(REST 핸들러, Agent 툴, 백엔드 호출부)는 얇게 유지한다.
- Pydantic 모델을 데이터 계약의 기준으로 삼고 입력, 출력, LLM 응답을 모두 검사한다.
- 모델 ID, 가중치, 임계값, 버킷·테이블 이름은 설정 파일이나 환경변수에서 읽는다.
- 날짜는 asOf를 받아 계산한다. 상태는 DB에만 둔다. 저장 요청은 멱등하게 처리한다 (Idempotency-Key, 조건부 쓰기).
- 조회와 저장을 나눈다. Agent 툴 설명에는 무엇을, 언제, 입출력을 적고, 툴 응답은 문장보다 사실 목록으로 준다.
- 오류는 원인이 드러나는 코드로 낸다. C 함수는 `InterviewError(code, message, retryable)`를 던지고 백엔드가 공통 오류 형식으로 바꾼다.
- Python 함수·인자는 snake_case. JSON 키 표기는 API 규약 합의를 따른다 (`tech.md`).
- 테스트는 외부 서비스 없이 돌도록 mock·fixture를 쓴다 (A MockLLM·CSV 폴백, B `mocks/`·데모 스냅샷, C `ai/interview/samples/`). 명세의 시나리오(A UT·INT·EVAL, B T-01~T-22·페르소나, C 연결 시나리오)를 완료 기준으로 쓴다.
- 빌드·테스트·배포 명령은 아직 저장소에 없다. 이전 뼈대는 `uv`로 로컬 확인 스크립트를 돌리고 `infra/deploy.sh`로 배포했다.

## 협업 규칙 (`docs/CONTRIBUTING.md`)
- 흐름: 이슈 생성 → 최신 `main`에서 브랜치 → 커밋·푸시 → `main` 대상 PR → (CI가 있으면 결과 확인) → 필요하면 리뷰 → 작성자가 Squash and merge → 브랜치 삭제
- `main`에 직접 커밋하지 않는다. `main`은 늘 시연·배포할 수 있는 상태로 둔다.
- 작업 타입 `feat` `fix` `docs` `style` `refactor` `test` `chore`, 영역 `fe` `be` `common`. 이슈와 PR에 타입 라벨과 영역 라벨을 각각 붙인다.
- 이슈 제목: `[FE|BE|COMMON|FE/BE] 타입: 한글 요약`. 본문: 작업 목적 / 구현 범위(체크리스트) / 완료 조건(체크리스트) / 참고 자료. 완료가 확인된 항목만 체크한다.
- 브랜치: `타입/영역/#이슈번호-영문-소문자-하이픈` (예: `feat/fe-be/#24-login-integration`). `#`이 있어 셸에서는 따옴표로 감싼다.
- 커밋: `타입: 한글 요약` (영역 표기 없음, 끝에 마침표 없음). 커밋 하나에 변경 의도 하나.
- PR 제목: `타입: 작업 요약` (이슈번호 없음). 본문: 작업 내용 / 테스트 및 확인(확인 못 한 항목은 이유와 위험) / 관련 이슈(`Closes #n` 또는 `Refs #n`) / 참고 사항
- 머지 전 확인: 대상이 `main`인지, 이슈·라벨 연결, 로컬 확인 결과 기록, CI 결과, 로그·비밀정보·임시 파일 제거, 관련 문서 수정, 충돌 해결, 필수 수정 의견 반영
- 리뷰는 선택이다. 다만 인증·인가·보안, 공통 API 규격·데이터 구조, DB 스키마, AWS 인프라·배포·비용, 여러 기능이 쓰는 공통 모듈, 팀 합의가 필요한 변경은 리뷰를 요청한다.
- CI가 없으면 PR에 직접 확인한 방법과 결과를 적는다. 문서만 바꾼 경우 테스트를 생략할 수 있지만 확인 방법은 적는다.
- API·DB 계약을 바꿀 때는 계약 문서를 먼저 고치고 팀 채널에 알린다 (이전 api.md 서두 규칙).

## Spec·작업 진행 원칙
- 요구사항과 설계는 해당 명세의 절을 근거로 쓰고 출처(문서와 절 번호)를 남긴다.
- 명세에 없는 기술·기능을 더하지 않는다. 필요하면 대안과 이유를 제시하고 확인받는다.
- `tech.md`·`product.md`의 미확정 항목에 걸리는 부분은 결정 전까지 인터페이스로 분리하거나 사용자에게 확인한다.
- 파트 경계를 넘는 변경은 계약 문서를 먼저 고치고 리뷰를 요청한다.

## 구조 미확정
- `backend/` Lambda가 `ai/` 아래 파트 코드를 import·패키징하는 방식 (경로 설정, 파트별 의존성 파일)
- B 명세의 `infra/`(CDK)를 `ai/busan-opportunity/` 안에 둘지, 인프라를 `backend/`로 모을지
- Lambda 분리와 패키징 방식 (이전 뼈대는 `team07-api` 하나)
- 이전 뼈대(`4aa11cc`)의 코드·문서를 다시 가져올지
- B가 계획한 `AGENTS.md`를 둘지, Kiro steering으로 대신할지
- AI·데이터·인프라 작업의 영역 라벨 (CONTRIBUTING에는 `fe`·`be`·`common`만 있다)
- `CONTRIBUTING.md` 위치 (지금은 `docs/` 아래이고 루트에는 없다)
