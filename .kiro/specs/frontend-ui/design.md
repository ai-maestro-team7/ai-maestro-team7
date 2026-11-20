# Design Document
## Overview
`frontend/`에 Next.js App Router 앱을 만들고 Figma_V2 화면 16개를 라우트 13개로 옮긴다. 홈의 "AI 멘토 답변"은 홈의 상태 하나이고, 모의면접의 질문 3화면(음성 + 카메라, 추가 질문, 텍스트)은 면접 라우트 하나의 상태다. 모든 화면은 정적으로 내보내고, 데이터는 `features/*/data/`의 Mock 데이터에서 읽는다.

## 기술 결정
| 항목 | 결정 | 이유 |
|---|---|---|
| 프레임워크 | Next.js(App Router, 최신 안정판) + React + TypeScript strict | 사용자 지정. D-24 CONFIRMED (2026-11-20) |
| 스타일 | Tailwind CSS v4, 토큰은 `globals.css`의 `@theme` | create-next-app 기본. 설정 파일 없이 CSS 한 곳에 토큰을 둔다 |
| 아이콘 | `lucide-react` | Figma 아이콘(bell, bookmark, chevron-right, search, check, user, file-text, external-link, arrow-right)의 SVG 경로가 Lucide와 같다. SVG를 따로 내려받아 관리할 필요가 없다 |
| 글꼴 | `next/font/google`의 Noto Sans KR (400·500·700) | Figma 글꼴. 빌드 때 받아 정적 파일로 넣는다 |
| 내보내기 | `output: "export"`, `trailingSlash: true`, `images.unoptimized` | S3 + CloudFront 정적 배포 계획 |
| Cache Components | create-next-app 기본값 `cacheComponents`·`partialPrefetching`을 끔 | Next 16.4 빌드가 "PPR cannot be enabled in export mode"로 실패한다. 정적 내보내기가 우선이다 |
| 클래스 결합 | `lib/cn.ts`의 작은 함수 | 클래스 조건 결합만 필요해서 `clsx` 같은 의존성을 추가하지 않는다 |
| shadcn/ui | 쓰지 않음 | Figma 컴포넌트가 단순해 직접 만드는 쪽이 코드가 적다 |
| 상태 관리 | 컴포넌트 `useState`, 화면 사이 값은 URL 쿼리 | 전역 상태가 필요한 흐름이 없다 |

## 라우트
| 경로 | Figma 화면 | 렌더링 |
|---|---|---|
| `/` | 홈(29:1584), 홈 · AI 멘토 답변(29:1817) | 서버. 멘토 영역만 클라이언트 |
| `/jobs` | 채용 공고 목록(29:1960) | 서버 껍데기 + 클라이언트 목록(필터·정렬·검색어) |
| `/jobs/[id]` | 채용 공고 상세(30:1898) | 서버, `generateStaticParams` |
| `/policies` | 청년 지원 정책 목록(29:2081) | 서버 |
| `/policies/[id]` | 지원 정책 상세(30:1989) | 서버 + 클라이언트 체크리스트 |
| `/diagnosis` | 이력서·직무 진단(30:2069) | 클라이언트 폼 |
| `/diagnosis/result` | 직무 진단 결과(30:2199) | 서버 |
| `/review` | AI 서류 첨삭(30:2269) | 서버 껍데기 + 클라이언트 탭 |
| `/roadmap` | 학습 로드맵(30:2364) | 서버 |
| `/interview` | 모의면접 · 설정(33:2162) | 클라이언트 폼 |
| `/interview/check` | 모의면접 · 장비 점검(33:2254) | 클라이언트(쿼리 `mode`) |
| `/interview/session` | 질문 음성 + 카메라(33:2389), 추가 질문(33:2466), 질문 텍스트(33:2556) | 클라이언트 상태 |
| `/interview/report` | 모의면접 · 리포트(33:2676) | 서버 |

- 화면 사이 값: 면접은 `?job=&mode=`(mode = `camera` | `voice` | `text`), 공고 검색은 `/jobs?q=`. 정적 내보내기에서 `useSearchParams`를 쓰는 컴포넌트는 `<Suspense>`로 감싼다.
- 공고 상세 "이 공고로 모의면접"은 `/interview?job=<공고명>`으로 직무를 미리 채운다 (구조 §5.3 1단계).

## 디렉터리
```text
frontend/
├── src/
│   ├── app/                      라우트와 화면 조립만
│   │   ├── layout.tsx            글꼴, GNB, Footer
│   │   ├── globals.css           Tailwind + 디자인 토큰
│   │   ├── page.tsx              홈
│   │   ├── jobs/ policies/ diagnosis/ review/ roadmap/ interview/
│   ├── components/
│   │   ├── ui/                   범용 UI (Button, Chip, TextField, TextArea, Checkbox, RadioList,
│   │   │                         StatusDot, SubTabs, Breadcrumb, Panel, Stats, Steps, ProgressBar,
│   │   │                         TableHead, PageHeader, SectionHeader, LinkWithChevron)
│   │   └── layout/               Gnb, Footer, PageContainer
│   ├── features/
│   │   ├── jobs/                 components(JobRow, JobTable, JobList), data, types
│   │   ├── policies/             components(PolicyRow, PolicyTable, PolicyChecklist), data, types
│   │   ├── mentor/               components(MentorPanel, ContinueList), data, types
│   │   ├── diagnosis/            components(DiagnosisForm, RequirementTable), data, types
│   │   ├── review/               components(ReviewTabs, CompareBox), data, types
│   │   ├── roadmap/              components(RoadmapWeek), data, types
│   │   ├── interview/            components(SetupForm, DeviceCheck, InterviewSession, CameraPreview,
│   │   │                         Recorder, FeedbackList), data, types, lib(mode 파싱)
│   │   └── user/                 data(시연 사용자 표시 정보)
│   └── lib/                      cn.ts, format.ts(마감일 표시)
```
- `hooks/`는 재사용 훅이 생길 때 만든다. 이번 범위에는 없다.
- 기능 폴더의 컴포넌트가 다른 기능 폴더를 import하는 경우는 홈(`app/page.tsx`)이 jobs·policies·mentor를 조립하는 것뿐이다. 화면 조립은 `app/`에서 한다.

## 디자인 토큰 (`globals.css` `@theme`)
| 종류 | 토큰 | 값 (Figma 변수) |
|---|---|---|
| 색 | `grey-50` ~ `grey-900` | #f9fafb, #f2f4f6, #e5e8eb, #d1d6db, #b0b8c1, #8b95a1, #6b7684, #4e5968, #333d4b, #191f28 |
| 색 | `blue-50`, `blue-500` | #e8f3ff, #3182f6 |
| 색 | `orange-500`, `green-500`, `red-500` | #fe9800, #03b26c, #f04452 |
| 색 | `dark` | #191f28 (`bg/dark`, 카메라 자리) |
| 글꼴 | `text-title` 26/36, `text-num` 30/38, `text-question` 24/36, `text-logo` 20/28, `text-h2` 19/28, `text-h3` 16/24, `text-body` 15/24, `text-btn` 15/22, `text-btn-s` 14/20, `text-small` 13/20 | v2/* 스타일. 굵기는 `font-normal`/`font-medium`/`font-bold`로 따로 준다 |
| 자간 | `body`에 `letter-spacing: -0.015em` | 모든 스타일 -1.5% |
| 모서리 | `rounded-control` 8px, `rounded-field` 10px, `rounded-card` 12px | 버튼 M·Chip·검색 8, 버튼 L·입력칸·라디오 목록 10, 상자 12 |
| 폭 | `max-w-content` 1080px | GNB·본문·Footer 공통 |
| 간격 | Tailwind 기본 4px 단위 | Figma 간격(2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 40, 48, 96)이 모두 0.5단위로 맞는다 |

- Tailwind 기본 색(`gray-*`, `blue-*` 등)은 `--color-*: initial`로 지워 토큰 밖 색을 못 쓰게 한다.
- 반응형: Tailwind 기본 `lg`(1024px)에서 2단 배치(본문 700px + 오른쪽 332px, 간격 48px)를 켠다. 그보다 좁으면 1단으로 쌓는다. 본문 좌우 여백은 `px-5`, `xl` 이상에서 0이다.

## 공통 컴포넌트
| 컴포넌트 | Figma 근거 | props 요약 |
|---|---|---|
| `Button` | Button(27:1350) | `variant: primary \| secondary \| line \| text`, `size: L \| M`, `href?`(있으면 Link), `fullWidth`, 나머지는 button 속성 |
| `Chip` | 홈 예시 질문, 공고 필터 | `selected?`, `onClick`/`href` |
| `TextField` | 목표 직무, 희망 직무 | `label`, `error?`, input 속성 |
| `TextArea` | 자기소개서, 내 답변 | `label`, `error?`, `counterSuffix?`(예: "· 예시"), `active?`(파란 테두리), textarea 속성 |
| `Checkbox` | 동의, 정책 체크리스트 | `checked`, `onChange`, `label`, `description` |
| `RadioList` | 진행 방식 | `options[{value, label, badge?, description}]`, `value`, `onChange`, `name` |
| `StatusDot` | 정책 상태, 진단 상태 | `tone: orange \| green \| red \| blue`, `label` |
| `SubTabs` | 채용/정책, PDF/직접 입력, 자기소개서/이력서 | `items[{key, label, href?}]`, `activeKey`, `onChange?` |
| `Breadcrumb` | 상세·결과 화면 | `items[{label, href?}]` |
| `Panel` | 오른쪽 상자, 신청 전 확인 | `tone: outline \| muted`, `className` |
| `Stats` | 진단 결과, 리포트 | `items[{label, value, unit}]` |
| `Steps` | Steps(27:1399) | `current: 1..4` |
| `ProgressBar` | 면접 진행률 | `value`(0~1), `label` |
| `TableHead` | 공고·정책·진단 표 머리줄 | `columns[{label, className}]` |
| `PageHeader` | 화면 제목(+설명, +Steps) | `title`, `description?`, `aside?` |
| `SectionHeader` | "나와 맞는 부산 공고" | `title`, `href?`, `linkLabel?` |

- `Gnb`는 `usePathname`으로 현재 탭을 정해야 해서 클라이언트 컴포넌트다. 검색은 `<form>` 제출로 `/jobs?q=`에 이동한다.
- 표 열 폭은 Figma 값(기업 180, 근무지 140, 마감 100, 적합도 170, 정책 표 170·190·200·140)을 `features/*/components`의 열 정의 한곳에 둔다. 머리줄과 행이 같은 정의를 쓴다.

## 데이터 모델 (`features/*/types.ts`)
- `JobPosting { id, company, companyInitial, title, skills[], district, employmentType: "정규직" | "계약직" | "인턴", deadline: string | null(상시), match: { level: "GOOD" | "FAIR" | "LOW", reason }, duties[], requirements[], matchedSkills[], gapAdvice, recommendRank }`
- `MatchLevel` 문구 표: GOOD "잘 맞아요"(blue-500), FAIR "맞는 편이에요", LOW "조금 맞아요" (`docs/api.md` §6.3)
- `Policy { id, name, benefit, target, conditions, status: "CHECK_NEEDED", summary, checklist[{title, description}], reason, officialSource{label, url}, note }`
- 진단: `DiagnosisResult { headline, summary, stats[], requirements[{name, status: "MET" | "GAP" | "EVIDENCE", evidence}], nextAction{title, description} }`
- 첨삭: `ReviewSample { kind: "COVER_LETTER" | "RESUME", original, originalNote, improved, improvedNote }`
- 로드맵: `Roadmap { target, order[], weeks[{week, title, description, deliverable, gap}] }`
- 면접: `InterviewQuestion { id, topic, question, hint, followUp{question, hint, sampleAnswer, reason} }`, `InterviewReport { stats[], feedback[{id, topic, comment, speakingSeconds, frontGazeRate, gazeNeedsAttention}], next{title, description} }`, `InterviewMode = "camera" | "voice" | "text"`
- 멘토: `MentorReply { prompt, answer, recommendation?{title, meta, actionLabel, href} }`, `ContinueItem { title, description, href }`
- 날짜 기준: Mock 기준일 `2026-11-21`(`features/jobs/data`의 `DATA_AS_OF`, B 데모 데이터 기준일과 같음). D-day는 `lib/format.ts`가 기준일로 계산한다. 화면 코드에서 `new Date()`를 쓰지 않아 빌드 시각과 관계없이 같은 값이 나온다.

## 상호작용 설계
- 홈 멘토(`MentorPanel`): 상태 `messages: {question, reply}[]`. 보내기·Chip → 질문 문자열로 Mock 답변 찾기(일치하는 Chip 답변, 없으면 기본 답변). "새 질문" → 초기 상태. 대화 화면 입력칸으로 이어서 물을 수 있다.
- 공고 목록(`JobList`): 상태 `type`, `sort`, 검색어는 URL `q`. 필터 → 정렬 → 렌더링 순서의 순수 함수(`filterJobs`, `sortJobs`)를 `features/jobs/lib.ts`에 둔다.
- 진단 폼: 상태 `tab`, `fileName`(기본 "김하늘_백엔드_이력서.pdf"), `text`, `job`, `errors`. 제출 시 검사 후 `router.push("/diagnosis/result")`.
- 면접 설정: 상태 `job`, `coverLetter`, `mode`, `consent`, `errors`. 쿼리 `job`이 있으면 초기값으로 쓴다. 제출 → `/interview/check?job=&mode=`.
- 면접 진행(`InterviewSession`): 상태 `index`(0~2), `phase: "main" | "followUp"`, `answer`(텍스트), `seconds`(녹음 타이머, 1초 간격 `setInterval`, 화면 표시용). 음성·카메라: main → followUp → 다음 index. 텍스트: main → 다음 index. 마지막 뒤 `/interview/report?mode=`.
- 저장 아이콘(`SaveToggle`): 행마다 `useState`. 행 전체 링크와 겹치지 않게 저장 버튼은 링크 밖 형제로 둔다.

## Figma와 다르게 하는 부분
- Figma는 1440px 데스크톱 한 크기다. 좁은 화면 규칙(1단 쌓기, 표 가로 스크롤, 탭 가로 스크롤, GNB 검색칸 줄바꿈)은 이 설계가 정했다.
- 오류 문구, 빈 결과, 포커스 표시는 Figma에 없다. 기존 토큰(`red-500` `text-small`, `grey-600`)으로 만든다.
- 녹음 타이머는 Figma에 01:42로 고정돼 있다. 화면에서는 0부터 올라가게 해 녹음 중 상태를 보여주되 "예시" 표시는 유지한다.
- 파형 막대는 Figma 높이 48개를 데이터 배열로 옮긴다. 앞 30개는 blue-500, 나머지는 grey-300이다.

## CI/CD
- CI `.github/workflows/frontend-ci.yml`: `frontend/**` 변경 PR에서 `npm ci` → lint → typecheck → build. 결과 `out/`을 아티팩트 `frontend-out`으로 남긴다. 기존 `ci.yml`(Python 파트)과 나눠 서로 기다리지 않는다.
- CD `.github/workflows/frontend-deploy.yml`: `main` 푸시(`frontend/**`)와 수동 실행. CI를 `workflow_call`로 다시 돌린 뒤 같은 아티팩트를 S3에 `sync --delete`하고 CloudFront `/*`를 무효화한다. `_next/static`은 `max-age=31536000,immutable`, 나머지는 `max-age=0,must-revalidate`.
- 자격 증명: 기존 OIDC 역할 `team07-github-deploy`(신뢰 조건 main 브랜치만). 웹 권한은 별도 인라인 정책 `team07-github-deploy-web-policy`(`infra/iam/github-deploy-web-policy.json`)로 붙여 Lambda 배포 정책 파일을 건드리지 않는다. 버킷·배포 ID는 계정 ID가 드러나지 않게 Secrets로 받는다.
- 자원 `infra/setup-web.sh` (AWS CLI, 반복 실행 안전): 버킷(퍼블릭 차단, 소유권 강제) → OAC → CloudFront 함수(`infra/web/index-rewrite.js`, 폴더 경로 → `index.html`) → 배포(HTTPS 넘김, 403·404 → `/404.html`, 관리형 CachingOptimized) → 버킷 정책(이 배포만 읽기) → 역할 정책. AWS 자원 생성이라 사람이 실행한다 (AGENTS.md "환경·보안").

## 검증
- `npm run lint`, `npm run typecheck`(`tsc --noEmit`), `npm run build`(정적 내보내기)
- 로컬 실행 후 각 라우트를 1440px 폭으로 Figma 스크린숏과 비교 (배치, 간격, 색, 글꼴)
- 키보드로 GNB → 본문 → 버튼 순서 이동과 포커스 표시 확인
