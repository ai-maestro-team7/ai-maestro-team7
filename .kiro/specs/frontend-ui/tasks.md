# Implementation Plan
## Overview
프론트 담당 한 명이 위에서 아래 순서로 진행한다. 1~2는 공통 기반, 3~9는 화면, 10은 검증이다. 모든 작업은 `frontend/` 안에서만 한다.

## Tasks
- [x] 1. 프로젝트 구성
  - [x] 1.1 `create-next-app`(TypeScript, Tailwind, ESLint, App Router, `src/`, `@/*`)으로 `frontend/` 생성, `lucide-react` 추가
  - [x] 1.2 `next.config.ts`에 정적 내보내기 설정, `package.json`에 `typecheck` 스크립트 추가
  - [x] 1.3 `frontend/README.md`에 실행·빌드 명령과 폴더 구조 정리
  - _Requirements: 1.1~1.5_
- [x] 2. 디자인 시스템과 공통 레이아웃
  - [x] 2.1 `globals.css`에 색·글꼴·모서리·폭 토큰 정의, Noto Sans KR 연결
  - [x] 2.2 `components/ui` 공통 컴포넌트 (Button, Chip, TextField, TextArea, Checkbox, RadioList, StatusDot, SubTabs, Breadcrumb, Panel, Stats, Steps, ProgressBar, TableHead, PageHeader, SectionHeader)
  - [x] 2.3 `components/layout` Gnb(현재 탭, 검색 제출), Footer, PageContainer와 `app/layout.tsx`
  - _Requirements: 2.1~2.4, 3.1~3.5, 4.1~4.5, 12.1~12.3_
- [x] 3. 채용 공고: 타입·Mock 데이터·JobRow·목록(필터, 정렬, 검색어)·상세
  - _Requirements: 6.1~6.7, 4.3, 11.1~11.2_
- [x] 4. 청년 지원 정책: 타입·Mock 데이터·PolicyRow·목록·상세(체크리스트)
  - _Requirements: 7.1~7.4_
- [x] 5. 홈: 이어서 하기, 공고·정책 요약, AI 멘토 대화 상태
  - _Requirements: 5.1~5.6_
- [x] 6. 이력서·직무 진단: 입력 폼(탭, 파일 이름, 검사)과 결과 화면
  - _Requirements: 8.1~8.5_
- [x] 7. AI 서류 첨삭: 하위 탭, 비교 상자, 다음 단계 줄
  - _Requirements: 9.1~9.3_
- [x] 8. 학습 로드맵: 추천 순서, 주차 목록, 이동 버튼
  - _Requirements: 9.4_
- [x] 9. AI 모의면접
  - [x] 9.1 타입·Mock 데이터(질문 3개, 추가 질문, 리포트), 진행 방식 쿼리 파싱
  - [x] 9.2 설정 화면 (입력 검사, 동의 검사, 요약 상자)
  - [x] 9.3 장비 점검 화면 (카메라 자리, 점검 상태)
  - [x] 9.4 면접 진행 화면 (음성·카메라·텍스트, 추가 질문, 다음 질문, 리포트 이동)
  - [x] 9.5 리포트 화면
  - _Requirements: 10.1~10.12_
- [x] 10. 검증
  - [x] 10.1 `npm run lint`, `npm run typecheck`, `npm run build` 통과
  - [x] 10.2 라우트별로 Figma 스크린숏과 비교해 차이 수정
  - [x] 10.3 중복 컴포넌트·하드코딩 색 점검 (`#[0-9a-f]{6}` 검색이 `globals.css`에서만 나와야 함)
  - [ ] 10.4 좁은 화면(375px)과 키보드 이동 확인 (600px 폭은 확인함. 375px와 키보드 이동은 실제 브라우저에서 확인 필요)
  - _Requirements: 1.3, 1.4, 2.4, 4.5, 12.1_
- [ ] 11. CI/CD
  - [x] 11.1 `frontend-ci.yml`(PR 검사), `frontend-deploy.yml`(main → S3 + CloudFront) 작성
  - [x] 11.2 `infra/setup-web.sh`, `infra/iam/github-deploy-web-policy.json`, `infra/web/index-rewrite.js` 작성
  - [ ] 11.3 `infra/setup-web.sh` 실행과 Secrets `WEB_BUCKET`·`WEB_DISTRIBUTION_ID` 등록 (AWS 자원 생성, 사용자 확인 후)
  - [ ] 11.4 main 머지 후 Frontend Deploy 실행 결과와 CloudFront 주소 확인
  - _Requirements: 1.3_
