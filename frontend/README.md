# frontend

부산커리어 화면. Figma "v2 · AI 티 걷어낸 버전"(파일 `orxq9z9EWqrYDNVviAG1aW`, 페이지 `27:1331`)을 Next.js로 옮겼다.
지금은 UI 단계라 백엔드 API를 부르지 않고, 화면 데이터는 `src/features/*/data.ts`의 Mock 데이터에서 읽는다.
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
- 녹음·카메라는 HTTPS에서만 동작하므로 API 연동 뒤에는 CloudFront 주소로 확인한다 (AGENTS.md).

## 기술

Next.js 16 (App Router) · React 19 · TypeScript strict · Tailwind CSS v4 · lucide-react · Noto Sans KR(`next/font`)

## 폴더

```text
src/
├── app/                 라우트와 화면 조립
│   ├── page.tsx         홈 (AI 멘토, 이어서 하기, 공고·정책 요약)
│   ├── jobs/            채용 공고 목록, [id] 상세
│   ├── policies/        청년 지원 정책 목록, [id] 상세
│   ├── diagnosis/       이력서·직무 진단, result 결과
│   ├── review/          AI 서류 첨삭
│   ├── roadmap/         학습 로드맵
│   └── interview/       모의면접 설정, check 장비 점검, session 면접, report 리포트
├── components/
│   ├── ui/              범용 UI (Button, Chip, TextField, TextArea, Checkbox, RadioList, SubTabs,
│   │                    Steps, Stats, DataTable, Panel, Breadcrumb, StatusDot, ProgressBar ...)
│   └── layout/          Gnb, Footer, PageContainer(TwoColumn), 메뉴 정의
├── features/<기능>/      components/, data.ts(Mock), types.ts, lib.ts(순수 함수)
└── lib/                 cn, 날짜 표시
```

## 규칙

- 디자인 토큰은 `src/app/globals.css`의 `@theme` 한 곳에 있다. 화면 코드에서 16진수 색을 쓰지 않는다 (Tailwind 기본 색은 지워 두었다).
  - 색 `grey-50~900`, `blue-50/500`, `orange-500`, `green-500`, `red-500`, `dark`
  - 글꼴 `text-title`, `text-num`, `text-question`, `text-logo`, `text-h2`, `text-h3`, `text-body`, `text-btn`, `text-btn-s`, `text-small` (굵기는 `font-normal/medium/bold`)
  - 모서리 `rounded-control`(8) · `rounded-field`(10) · `rounded-card`(12) · `rounded-check`(5), 폭 `max-w-content`(1080) · `max-w-main`(700) · `w-rail`(332)
- 컴포넌트는 데이터를 props로만 받는다. API를 붙일 때는 `features/*/data.ts`를 바꾸는 쪽에서 시작한다.
- 기본은 Server Component다. 상태·이벤트·URL 쿼리가 필요한 곳만 `"use client"`를 붙인다.
- 화면 문구는 개발계획서2 §4.7 문구 규칙과 `docs/api.md` §6.3 점수 표시 규칙을 따른다 ("합격 확률이 아니에요").

## 아직 하지 않은 것

- API 연동, 로그인, 실제 녹음·카메라·파일 업로드 (C §5.6 전달 규칙은 연동 단계에서 구현)
- GNB "저장한 공고"·"알림" 화면 (Figma에 없음)
- 데모 직무: Mock 데이터는 Figma대로 "백엔드 개발자"다. 통합 데모 직무는 "데이터 분석"(D-37)이라 바꿀지 정해야 한다.
