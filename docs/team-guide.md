# 팀 개발 환경 안내

7팀 · 백엔드/인프라 담당 정리 · 2026-11-20

## 1. 에이전트 담당: Bedrock 호출

| 항목 | 값 |
|---|---|
| 리전 | `ap-northeast-2` |
| 빠른 모델 | `global.anthropic.claude-haiku-5-5` (라우팅, 짧은 답변) |
| 정확한 모델 | `global.anthropic.claude-sonnet-5-5` (분석, 첨삭) |
| 임베딩 (KB용) | `cohere.embed-v4:0` (다국어), `amazon.titan-embed-text-v2:0` |

바로 돌려 보기 (`aws login` 후):

```bash
uv run --python 3.13 --with strands-agents --with "botocore[crt]" examples/strands_hello.py
```

> **`botocore[crt]` 꼭 넣기.** 없으면 `aws login` 자격 증명을 Python이 못 읽어서 `MissingDependencyException`이 난다.
> Lambda에 배포할 때는 역할 자격 증명을 쓰므로 필요 없다.

예제는 도구(`@tool`) 하나를 가진 에이전트다. 에이전트가 도구를 골라 호출하고 한국어로 답하는 것까지 확인됨.

## 2. 프론트 담당: API

```
API_BASE = <팀 채널 공지 참고>   # 저장소가 공개라 주소를 적지 않음
```

- 지금 동작하는 경로: `/api/v1/interview/*` (모의면접, 면접 함수는 대역), `/api/v1/health`. 나머지 파트 경로는 `501 NOT_IMPLEMENTED`
- 규칙(경로, 카멜 표기, 오류 형식, 사용자 식별): `docs/api.md`
- **로그인 후 모든 요청에 `Authorization: Bearer {accessToken}`**. 데모 계정 `demo1`~`demo3`, 비밀번호는 Secrets Manager `team07/demo-accounts`
- 호출 제한: 초당 20건. 시연 때 부족하면 백엔드 담당에게

```js
// 로그인
const { accessToken, refreshToken } = await (await fetch(`${API_BASE}/api/v1/auth/login`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password }),
})).json();

// 이후 요청 (401이면 /api/v1/auth/refresh 로 새 accessToken)
const res = await fetch(`${API_BASE}/api/v1/interview/start`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
  body: JSON.stringify({ job: "데이터 분석", interviewType: "MIXED", cameraConsent: true, resumeText }),
});
// 202 → { sessionId } → GET /api/v1/interview/{sessionId}/status 를 2초마다
```

## 3. 멘토링 담당: S3와 Knowledge Base

| 버킷 | 용도 |
|---|---|
| `team07-kb-source-<계정ID>` | KB 원천 문서. ZIP의 `bedrock/documents/` 13쌍을 `docs/` 아래에 |
| `team07-career-docs-<계정ID>` | 개인 문서(이력서 등). `users/{hashedUserId}/...` |

```bash
aws s3 cp bedrock/documents/ s3://team07-kb-source-<계정ID>/docs/ --recursive \
  --exclude "*" --include "*.md" --include "*.md.metadata.json"
```

현재 S3 Vectors 권한이 없어 KB 생성은 대기 중. 그동안은 명세 §10.3 폴백(CSV·문서 로컬 검색)으로 개발.

## 4. 배포

- 백엔드 Lambda: `infra/deploy.sh` (코드만 바뀌었을 때)
- 새 Lambda가 필요하면 백엔드 담당에게 요청 (실행 역할 `team07-lambda-role` 공용)

## 5. 규칙

- 리전은 서울, 자원 이름은 `team07-` 접두사
- 액세스 키를 만들지 않는다. API 키는 저장소·채팅에 올리지 않는다
- 공유 계정이다. 다른 팀 자원은 건드리지 않는다
