# frontend

부산커리어 화면. Figma "v2 · AI 티 걷어낸 버전"(파일 `orxq9z9EWqrYDNVviAG1aW`, 페이지 `27:1331`)을 Next.js로 옮겼다.
로그인(카카오·Google)과 채용 공고·청년 정책 화면(홈 요약 포함)은 B 부산 기회 추천 API(`/api/v1/opportunities/*`)에 연결했다.
진단·첨삭·학습 로드맵은 `/api/v1/mentoring` API를 부른다.
모의면접은 `/api/v1/interview/*`를 부른다: 설정에서 세션을 만들고, 장비 점검에서 마이크·카메라를 확인하고(정면 보정), 면접에서 질문 음성 재생·녹음·2초 간격 캡처·답변 제출을 하고, 리포트에서 채점 결과를 보여준다 (`src/features/interview/`).
홈의 AI 멘토만 아직 `src/features/mentor/data.ts`의 Mock 데이터를 읽는다.
요구사항·설계·작업 목록은 `.kiro/specs/frontend-ui/`에 있다.

## 실행

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run typecheck  # next typegen && tsc --noEmit
npm run build      # 정적 파일을 out/ 에 만든다 (S3 + CloudFront 배포용)
```

- 정적 내보내기(`output: "export"`, `trailingSlash: true`)라 `next start`는 쓰지 않는다. `out/`을 아무 정적 서버로 열면 된다.
- 녹음·카메라는 HTTPS에서만 동작하므로 CloudFront 주소로 확인한다 (AGENTS.md).

### API 연결

- 배포에서는 CloudFront가 같은 주소의 `/api/*`를 API Gateway(`team07-http-api`)로 넘긴다 (`infra/setup-web.sh`). 그래서 코드는 `/api/v1/...` 상대 경로로 부르고 API 주소를 저장소에 적지 않는다.
- 로컬 개발에서는 `frontend/.env.local`에 API Gateway 주소를 넣는다. `.env*`는 커밋하지 않는다 (공개 저장소). 주소는 팀 채널 공지 참고.

  ```bash
  NEXT_PUBLIC_API_BASE=https://<API Gateway 주소>
  ```

- 로그인은 카카오·Google 소셜 로그인이다 (`/login/`). 처음 들어오면 기본 정보(`/profile/`)를 먼저 받는다. 시연 계정(`demo1`~`demo3`)은 메뉴에 없는 `/login/demo/`에서 아이디로 들어간다. 비밀번호는 Secrets Manager `team07/demo-accounts`에 있다. 토큰은 브라우저 localStorage에 두고, 401이 오면 `/auth/refresh`로 한 번 갱신한다 (`src/lib/api.ts`).
- 멘토링 화면도 같은 `team07.session`을 읽는다. 이력서·자기소개서 원문은 브라우저 저장소에 보관하지 않는다.
- 공고·정책 ID는 B가 매일 새로 모으는 값이라 빌드 때 알 수 없다. 상세는 `/jobs/detail/?id=…`, `/policies/detail/?id=…` 한 화면을 내보내고 브라우저에서 `?id=`를 읽어 부른다.

## CI/CD

| 워크플로 | 언제 | 하는 일 |
|---|---|---|
| `.github/workflows/frontend-ci.yml` | `frontend/`를 바꾼 PR | `npm ci` → lint → typecheck → build, `out/`을 아티팩트로 남김 |
| `.github/workflows/frontend-deploy.yml` | `frontend/` 변경이 `main`에 머지될 때, 수동 실행 | 같은 검사 뒤 `out/`을 S3 `team07-web-<계정ID>`에 올리고 CloudFront 캐시를 비움 |

- AWS는 OIDC 역할 `team07-github-deploy`(main 브랜치만)를 쓴다. 액세스 키는 없다.
- 웹 자원(버킷, CloudFront, `/api/*` 연결, 배포 권한)은 `infra/setup-web.sh`를 사람이 한 번 실행해 만든다 (2026-11-20 실행됨). 끝나면 출력되는 값으로 GitHub Secrets `WEB_BUCKET`, `WEB_DISTRIBUTION_ID`를 등록한다. 둘이 없으면 배포 단계는 건너뛴다.
- 캐시: `_next/static/*`은 1년(파일 이름에 해시), 나머지 HTML·RSC 데이터는 매번 확인. `/api/*`는 캐시하지 않는다.

## 기술

Next.js 16 (App Router) · React 19 · TypeScript strict · Tailwind CSS v4 · lucide-react · Noto Sans KR(`next/font`)

## 폴더

```text
src/
├── app/                 라우트와 화면 조립
│   ├── page.tsx         홈 (AI 멘토, 이어서 하기, 공고·정책 요약)
│   ├── login/           로그인
│   ├── jobs/            채용 공고 목록, detail 상세 (?id=)
│   ├── policies/        청년 지원 정책 목록, detail 상세 (?id=)
│   ├── diagnosis/       이력서·직무 진단, result 결과
│   ├── review/          AI 서류 첨삭
│   ├── roadmap/         학습 로드맵
│   └── interview/       모의면접 설정, check 장비 점검, session 면접, report 리포트
├── components/
│   ├── ui/              범용 UI (Button, Chip, TextField, TextArea, Checkbox, RadioList, SubTabs,
│   │                    Steps, Stats, DataTable, Panel, Breadcrumb, StatusDot, ProgressBar ...)
│   └── layout/          Gnb, Footer, PageContainer(TwoColumn), 메뉴 정의
├── features/<기능>/      components/, data.ts(API 호출 또는 Mock), types.ts, lib.ts(순수 함수)
│   └── auth/            로그인 폼, 로그인 상태, API 불러오는 중·오류 안내
└── lib/                 cn, 날짜 표시, api(토큰 붙인 호출·갱신), session(토큰 보관), useApi
```

## 규칙

- 디자인 토큰은 `src/app/globals.css`의 `@theme` 한 곳에 있다. 화면 코드에서 16진수 색을 쓰지 않는다 (Tailwind 기본 색은 지워 두었다).
  - 색 `grey-50~900`, `blue-50/500`, `orange-500`, `green-500`, `red-500`, `dark`
  - 글꼴 `text-title`, `text-num`, `text-question`, `text-logo`, `text-h2`, `text-h3`, `text-body`, `text-btn`, `text-btn-s`, `text-small` (굵기는 `font-normal/medium/bold`)
  - 모서리 `rounded-control`(8) · `rounded-field`(10) · `rounded-card`(12) · `rounded-check`(5), 폭 `max-w-content`(1080) · `max-w-main`(700) · `w-rail`(332)
- 컴포넌트는 데이터를 props로만 받는다. API를 붙일 때는 `features/*/data.ts`를 바꾸는 쪽에서 시작한다.
- 기본은 Server Component다. 상태·이벤트·URL 쿼리·API 호출이 필요한 곳만 `"use client"`를 붙인다.
- API 응답 타입은 B 모델(`ai/busan-opportunity/src/opportunity/models/api.py`)을 따른다. 서버가 null 필드를 빼고 보내므로 선택 필드로 둔다.
- 공고 원문·정책 원문은 글자로만 넣는다 (`dangerouslySetInnerHTML` 금지). 출처와 기준일이 없는 배지·숫자는 B가 응답에서 뺀다.
- 화면 문구는 개발계획서2 §4.7 문구 규칙과 `docs/api.md` §6.3 점수 표시 규칙을 따른다 ("합격 확률이 아니에요").

## 아직 하지 않은 것

- 공고 저장(`POST /saved`), 부산 대안 전체 화면·나란히 비교, 정책 알림 신청, 정책 총액(`totals`). 저장 아이콘은 아직 화면 안에서만 바뀐다.
- 멘토·진단·첨삭·로드맵·모의면접 API 연동, 실제 녹음·카메라·파일 업로드 (C §5.6 전달 규칙은 연동 단계에서 구현)
- GNB "저장한 공고" 화면 (Figma에 없음). "알림"은 GNB에서 뺐다.
