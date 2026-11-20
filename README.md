# 7팀 · 부산 청년 취업 맞춤형 멘토링 Agent

2026 PNU X AWS AI 마에스트로 해커톤

## 처음 왔다면

1. [`docs/team-guide.md`](docs/team-guide.md): AWS 접속, 로그인·데모 계정, Bedrock 모델, 규칙
2. [`docs/api.md`](docs/api.md): 팀 공통 API 규칙과 파트 간 결정 사항
3. [`docs/db-schema.md`](docs/db-schema.md): DB 스키마 v1.3
4. [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md): 이슈·브랜치·커밋·PR 규칙
5. 기획·파트 명세: [`docs/프로젝트_제안서.md`](docs/프로젝트_제안서.md), `docs/개발계획서1~3.md` · AI 에이전트 규칙: [`AGENTS.md`](AGENTS.md), `.kiro/steering/`

## 폴더

| 경로 | 내용 |
|---|---|
| `backend/` | API Lambda: 라우터 `app.py`, 로그인 `auth_api.py`, 프로필·워크스페이스 `me_api.py`·`workspace.py`, 자격 판정 `eligibility.py`, 모의면접 `interview_api.py`, 테스트 `test_*.py` |
| `ai/mentoring/`, `ai/busan-opportunity/`, `ai/interview/` | 파트별 AI 코드 (A·B·C). 배포 때 `ai/interview/` → `interview`, `ai/busan-opportunity/src/opportunity/` → `opportunity` 패키지로 백엔드와 함께 묶인다 |
| `contracts/` | 파트 간 데이터 계약 패키지 `team07_contracts` (스키마·예시 데이터·검사, D-18). 배포 묶음에도 들어간다 |
| `tools/` | 개발 도구 목록 |
| `frontend/` | 화면 |
| `infra/` | AWS 자원 생성·배포 스크립트 (CloudFormation 권한이 없어 AWS CLI 스크립트) |
| `examples/` | Strands Agents + Bedrock 예제 |
| `docs/` | 기획·명세·규칙 문서 |

## 자주 쓰는 명령 (`aws login` 후)

```bash
# 로컬 테스트 (라우터 · 자격 판정 · 프로필·워크스페이스 · 모의면접)
cd backend
uv run --no-project --python 3.13 --with boto3 python test_app.py
uv run --no-project --python 3.13 python test_eligibility.py
uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb]" python test_me.py
uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb,s3]" python test_interview.py
uv run --no-project --python 3.13 --with boto3 --with "moto[dynamodb,scheduler]" --with-requirements ../ai/busan-opportunity/requirements.txt python test_opportunities.py

# 코드 배포 (Lambda만)
infra/deploy.sh

# 에이전트 예제
uv run --python 3.13 --with strands-agents --with "botocore[crt]" examples/strands_hello.py
```

처음 한 번만: `infra/setup-role.sh` → `infra/setup-data.sh` → `infra/setup-api.sh` → `infra/setup-auth.sh` → `uv run --python 3.13 --with boto3 --with "botocore[crt]" infra/seed_demo.py` (모두 실행됨)

## 보안

이 저장소는 **공개**입니다. AWS 계정 ID, API 주소, API 키, 비밀번호, 개인정보를 커밋하지 않습니다.
스크립트는 계정 ID를 실행할 때 조회하고, 비밀값은 Secrets Manager에만 둡니다.
