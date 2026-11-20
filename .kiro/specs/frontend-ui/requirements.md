# Requirements Document
## Introduction
frontend-ui는 `frontend/`에 Next.js 화면을 만드는 FRONTEND 파트의 첫 스펙이다. Figma 파일 `orxq9z9EWqrYDNVviAG1aW`의 "v2 · AI 티 걷어낸 버전" 페이지(노드 `27:1331`)에 있는 화면 16개와 공통 컴포넌트를 그대로 옮기고, 화면 데이터는 로컬 Mock 데이터로 채운다. 백엔드 API는 이번 단계에서 연결하지 않는다.

근거와 전제:
- 프론트엔드 프레임워크(D-24)는 프론트 담당이 이 스펙에서 Next.js App Router · React · TypeScript · Tailwind CSS · Lucide React로 정했다 (2026-11-20, CONFIRMED). `tech.md` 결정 표 12번, `AGENTS.md`, common-foundation 결정 기록에 반영했다.
- 화면 데이터는 통합 데모 페르소나 ①(부산 소재 대학 4학년, 통계학 전공, 희망 직무 데이터 분석, NCS 20010105)에 맞춘다 (D-37, `docs/architecture.md` §5.3, `docs/api.md` §6.2). Figma 예시 문구의 "백엔드 개발자"는 화면 틀로만 쓴다. 공고는 B 데모 데이터(`ai/busan-opportunity/src/opportunity/seeds/demo_world.py`)의 부산 공고와 이름·근무지·마감·요건을 맞춘다.
- 화면 배포 계획은 S3 `team07-web-<계정ID>` + CloudFront다 (이전 `api.md`, AGENTS.md "녹음과 카메라는 HTTPS에서만 돌아서 화면은 CloudFront로 배포"). 그래서 서버 없이 정적 파일로 내보낼 수 있어야 한다.
- 문구는 B §4.7 문구 규칙과 제품 원칙(product.md)을 따른다. 점수 표시는 `docs/api.md` §6.3을 따른다.
- 문서 표기: 제안서 = `docs/프로젝트_제안서.md`, B = `docs/개발계획서2.md`, C = `docs/개발계획서3.md`, 구조 = `docs/architecture.md`.

범위에서 제외:
- API 호출, API Client, 응답 스키마 설계, 인증(Cognito 로그인), DB, 서버 상태 라이브러리
- 실제 녹음·카메라 캡처·파일 업로드 (C §5.6 전달 규칙은 API 연동 스펙에서 구현)
- Figma에 화면이 없는 기능: 저장한 공고 목록, 알림 목록, 로그인, 워크스페이스, 기업 관계 그래프, 캘린더

## Glossary
- **App**: `frontend/`의 Next.js 애플리케이션
- **Figma_V2**: Figma 페이지 `27:1331`. 화면 16개와 `Components v2` 섹션(Button, Steps, JobRow, PolicyRow, Footer, GNB)을 담는다
- **Design_Token**: Figma_V2 변수에서 가져온 색·글꼴·간격·모서리 값
- **Mock_Data**: `features/*/data/`에 두는 화면용 예시 데이터. 모든 값은 가상이다
- **GNB**: 상단 공통 메뉴. 로고, 검색, 저장한 공고, 사용자 표시, 메뉴 탭 6개. Figma의 "알림"은 프론트 담당 결정으로 뺀다
- **Interview_Flow**: 모의면접 4단계 (설정 → 장비 점검 → 면접 → 리포트)

## Requirements
### Requirement 1: 프로젝트 구성
**User Story:** As a 프론트 담당 개발자, I want 표준 Next.js 구성과 실행 명령을, so that 혼자서 바로 개발하고 배포 산출물을 만들 수 있다.
출처: 사용자 요청 §3·§4, AGENTS.md "환경·보안", 이전 `api.md` 배포 계획
#### Acceptance Criteria
1. THE App SHALL `frontend/` 안에서만 소스와 설정을 관리하고, 저장소의 다른 폴더를 수정하지 않는다.
2. THE App SHALL Next.js App Router, React, TypeScript(strict), Tailwind CSS, Lucide React를 쓰고, 그 밖의 런타임 의존성을 추가하지 않는다.
3. WHEN 개발자가 `frontend/`에서 `npm run build`를 실행하면, THE App SHALL 정적 내보내기(`output: "export"`) 결과를 `frontend/out/`에 만든다.
4. WHEN 개발자가 `npm run lint`와 `npm run typecheck`를 실행하면, THE App SHALL 오류 없이 끝난다.
5. THE App SHALL 계정 ID, API 주소, 키, 실제 개인정보를 소스에 넣지 않는다.

### Requirement 2: 디자인 시스템
**User Story:** As a 프론트 담당 개발자, I want Figma 변수를 한곳의 토큰으로, so that 화면마다 색과 크기를 다시 적지 않는다.
출처: Figma_V2 변수, 사용자 요청 §5
#### Acceptance Criteria
1. THE App SHALL Figma_V2 색 변수(`grey/50~900`, `blue/50`, `blue/500`, `orange/500`, `green/500`, `red/500`, `bg/dark`, `white`)를 같은 값의 Tailwind 테마 토큰으로 정의한다.
2. THE App SHALL Figma_V2 글꼴 스타일(Title, Num, Question, H2, Logo, H3, Body, Btn, Btn S, Small)을 크기·줄 높이 토큰으로 정의하고, 글꼴은 Noto Sans KR, 자간은 -1.5%로 둔다.
3. THE App SHALL 모서리 8·10·12px과 본문 폭 1080px을 토큰으로 정의한다.
4. THE App SHALL 화면 코드에서 16진수 색 값을 직접 쓰지 않고 토큰 클래스만 쓴다.

### Requirement 3: 공통 컴포넌트
**User Story:** As a 프론트 담당 개발자, I want Figma에서 반복되는 요소를 컴포넌트로, so that 같은 모양을 한 번만 만든다.
출처: Figma_V2 `Components v2`(27:1656), 화면 16개의 반복 패턴
#### Acceptance Criteria
1. THE App SHALL Button을 Figma 변형 Type(Primary, Secondary, Line) × Size(L 48px, M 38px)로 제공하고, 링크와 버튼 두 형태로 렌더링할 수 있게 한다. 텍스트 링크 형태(예: "카메라 없이 계속", "면접 종료")도 같은 컴포넌트의 변형으로 둔다.
2. THE App SHALL Steps를 단계 1~4 변형으로 제공한다. 현재 단계는 blue/500 Bold, 지난 단계는 grey/800, 다음 단계는 grey/500로 표시한다.
3. THE App SHALL JobRow와 PolicyRow를 데이터 객체 하나를 받는 컴포넌트로 만들고, 홈과 목록 화면에서 같은 컴포넌트를 쓴다.
4. THE App SHALL GNB와 Footer를 모든 화면의 공통 레이아웃으로 렌더링한다.
5. THE App SHALL 둘 이상의 화면에서 반복되는 Chip, 입력칸, 글자 수가 보이는 여러 줄 입력칸, 체크박스, 라디오 목록, 상태 점, 하위 탭, 경로 표시(Breadcrumb), 테두리 상자, 숫자 요약(Stats), 표 머리줄을 공통 컴포넌트로 둔다. 한 화면에서만 쓰는 모양은 해당 기능 폴더에 둔다.

### Requirement 4: 공통 레이아웃과 메뉴
**User Story:** As a 사용자, I want 어느 화면에서든 같은 메뉴로 이동하기를, so that 기능 사이를 쉽게 오간다.
출처: Figma_V2 GNB(27:1616, 변형 6개), Footer(27:1621)
#### Acceptance Criteria
1. THE GNB SHALL 탭 6개(홈, 채용·정책, AI 모의면접, 이력서·직무 진단, AI 서류 첨삭, 학습 로드맵)를 보여주고, 현재 경로에 해당하는 탭을 blue/500 Bold와 2px 밑줄로 표시하고 `aria-current="page"`를 붙인다.
2. WHEN 경로가 `/jobs` 또는 `/policies`로 시작하면, THE GNB SHALL "채용·정책" 탭을 현재 탭으로 표시한다.
3. WHEN 사용자가 GNB 검색칸에 검색어를 넣고 제출하면, THE App SHALL 채용 공고 목록으로 이동해 기업명·공고명·기술에 검색어가 들어간 Mock 공고만 보여준다.
4. THE GNB SHALL 사용자 이름 옆에 "시연 모드"를, THE Footer SHALL "시연용 화면이에요. 실제 지원·신청 페이지와는 연결되어 있지 않아요."를 표시한다.
5. WHILE 화면 폭이 1080px보다 좁으면, THE App SHALL 본문 좌우 여백을 두고, 탭과 표는 가로 스크롤로 내용을 잘리지 않게 보여주고, 2단 배치는 1단으로 쌓는다.

### Requirement 5: 홈과 AI 멘토
**User Story:** As a 부산 취업 준비생, I want 홈에서 맞는 공고·정책과 이어서 할 일을 보고 AI 멘토에게 묻기를, so that 다음에 할 일을 바로 고른다.
출처: Figma 홈(29:1584), 홈 · AI 멘토 답변(29:1817), 구조 §5.3(챗 칩 1단계), 제안서 7.3
#### Acceptance Criteria
1. THE App SHALL 홈에 "AI 멘토에게 물어보기", "이어서 하기"(4개 항목), "나와 맞는 부산 공고"(3건), "부산 청년 지원 정책"(3건)을 Figma 배치대로 보여준다.
2. WHEN 사용자가 질문을 입력해 보내기를 누르거나 예시 질문 Chip을 누르면, THE App SHALL 입력 화면을 대화 화면으로 바꾸고 내 질문과 Mock 답변을 보여준다. 답변 아래에는 "시연용 답변이에요."를 표시한다.
3. IF 질문이 공백뿐이면, THEN THE App SHALL 보내기를 막고 입력칸에 머문다.
4. WHEN 답변에 추천 항목이 있으면, THE App SHALL 추천 카드와 이동 버튼(공고 보기, 정책 보기, 모의면접 시작하기)을 보여준다.
5. WHEN 사용자가 "새 질문"을 누르면, THE App SHALL 대화를 지우고 처음 입력 화면으로 돌아간다.
6. THE App SHALL 실제 네트워크 요청을 보내지 않고, 답변이 미리 준비된 예시임을 화면에 밝힌다.

### Requirement 6: 채용 공고
**User Story:** As a 사용자, I want 부산 공고를 거르고 정렬하고 상세를 보기를, so that 지원할 공고를 고른다.
출처: Figma 채용 공고 목록(29:1960), 채용 공고 상세(30:1898), B §4.7, `docs/api.md` §6.3
#### Acceptance Criteria
1. THE App SHALL 공고 목록에 하위 탭(채용 공고/청년 지원 정책), 고용 형태 Chip(전체/정규직/계약직/인턴), 정렬 표시, 건수와 기준일, 공고 표, 적합도 안내 문구를 보여준다.
2. WHEN 사용자가 고용 형태 Chip을 누르면, THE App SHALL 해당 형태의 공고만 보여주고 건수를 다시 센다. 선택된 Chip은 grey/900 배경으로 표시하고 `aria-pressed`를 붙인다.
3. WHEN 사용자가 정렬 "바꾸기"를 누르면, THE App SHALL "추천순(부산 우선)"과 "마감순"을 번갈아 적용한다. 마감순에서 상시 공고는 맨 뒤에 둔다.
4. IF 조건에 맞는 공고가 없으면, THEN THE App SHALL 빈 결과 안내를 보여준다.
5. THE App SHALL 적합도를 숫자 없이 "잘 맞아요 / 맞는 편이에요 / 조금 맞아요" 중 하나로 표시하고, "합격 확률이 아니에요" 문구를 함께 둔다.
6. WHEN 사용자가 공고 행을 누르면, THE App SHALL 공고 상세로 이동한다. 상세는 기업, 공고명, 근무지·형태·마감, 주요 업무, 요구 역량, 지원 전 확인, 적합도 상자(맞는 역량, 보완할 역량, 이동 버튼 2개)를 보여준다.
7. WHEN 사용자가 저장 아이콘을 누르면, THE App SHALL 그 화면 안에서만 저장 상태를 바꿔 보여주고 `aria-pressed`로 상태를 알린다.

### Requirement 7: 청년 지원 정책
**User Story:** As a 사용자, I want 정책 목록과 확인할 조건을 보기를, so that 신청 전에 자격을 스스로 확인한다.
출처: Figma 청년 지원 정책 목록(29:2081), 지원 정책 상세(30:1989), 제품 원칙 1·2
#### Acceptance Criteria
1. THE App SHALL 정책 목록에 하위 탭, 건수와 안내 문구, 정책 표(정책, 지원 내용, 추천 대상, 확인할 조건, 상태), "신청 전에 확인하세요" 상자를 보여준다.
2. WHEN 사용자가 정책 행을 누르면, THE App SHALL 정책 상세로 이동한다. 상세는 지원 조건 체크리스트, 상태, 추천한 이유, 공식 정보 확인처, "다른 지원 정책 보기" 버튼을 보여준다.
3. WHEN 사용자가 체크리스트 항목을 누르면, THE App SHALL 그 항목의 체크 상태를 바꾼다. 체크 상태는 저장하지 않는다.
4. THE App SHALL 공식 정보 확인처를 새 창 외부 링크로 열고, 확인되지 않은 금액·일정은 표시하지 않는다.

### Requirement 8: 이력서·직무 진단
**User Story:** As a 사용자, I want 이력서와 목표 직무로 진단 결과를 보기를, so that 보완할 역량을 안다.
출처: Figma 이력서·직무 진단(30:2069), 직무 진단 결과(30:2199), `docs/api.md` §6.3(fitScore)
#### Acceptance Criteria
1. THE App SHALL 진단 화면에 하위 탭(PDF 업로드/직접 입력), 파일 카드, 목표 직무 입력, "이 이력서로 진단하기" 버튼, "진단하면 알 수 있어요" 안내를 보여준다.
2. WHEN 사용자가 파일 카드의 "바꾸기"로 PDF를 고르면, THE App SHALL 파일 이름만 화면에 바꿔 보여주고 파일을 어디에도 보내지 않는다.
3. WHEN 사용자가 "직접 입력" 탭을 고르면, THE App SHALL 이력서 내용을 적는 여러 줄 입력칸을 보여준다.
4. IF 목표 직무가 비었거나 이력서(파일 또는 직접 입력 내용)가 없으면, THEN THE App SHALL 진단으로 넘어가지 않고 해당 칸 아래에 오류 문구를 보여준다.
5. WHEN 입력이 유효한 상태로 진단을 누르면, THE App SHALL 진단 결과 화면으로 이동한다. 결과는 요약 문장, 숫자 요약 4개, 직무 요구 역량 비교 표(충족 green, 보완 필요 red, 증빙 보완 orange), "다음에 할 일" 상자를 보여주고 "합격 확률이 아니에요" 문구를 둔다.

### Requirement 9: AI 서류 첨삭과 학습 로드맵
**User Story:** As a 사용자, I want 문장 개선 예시와 주차별 학습 계획을 보기를, so that 서류와 역량을 보완한다.
출처: Figma AI 서류 첨삭(30:2269), 학습 로드맵(30:2364), 제품 원칙 5
#### Acceptance Criteria
1. THE App SHALL 첨삭 화면에 하위 탭(자기소개서/이력서), 목표 직무, 원문과 개선 예시를 나란히 놓은 비교 상자, "면접에 활용하기" 줄을 보여준다.
2. WHEN 사용자가 첨삭 하위 탭을 바꾸면, THE App SHALL 해당 문서 종류의 Mock 원문·개선 예시로 바꿔 보여준다.
3. THE App SHALL 개선 예시 아래에 "원문과 이력서에 있는 사실만 썼어요" 안내를 보여준다.
4. THE App SHALL 학습 로드맵에 추천 순서, 주차별 항목(주차, 제목, 설명, 산출물, 보완 역량), 이동 버튼 2개를 보여준다.

### Requirement 10: AI 모의면접
**User Story:** As a 사용자, I want 설정부터 리포트까지 모의면접 흐름을 시연하기를, so that 실제 면접 연습 화면을 미리 확인한다.
출처: Figma AI 모의면접 6화면(33:2162, 33:2254, 33:2389, 33:2466, 33:2556, 33:2676), C §1·§5.6, 제안서 7.2
#### Acceptance Criteria
1. THE App SHALL 모든 Interview_Flow 화면 제목 줄 오른쪽에 Steps를 두고 현재 단계를 표시한다.
2. THE App SHALL 설정 화면에 희망 직무, 자기소개서(글자 수 표시), 진행 방식 라디오 3개(음성 + 카메라 "추천", 음성만, 텍스트), 카메라 분석 동의, "장비 점검하기"·"카메라 없이 계속", "이번 면접" 요약 상자를 보여준다. 요약 상자는 입력한 직무와 진행 방식을 바로 반영한다.
3. IF 희망 직무나 자기소개서가 비었으면, THEN THE App SHALL 다음 단계로 넘어가지 않고 오류 문구를 보여준다.
4. IF "음성 + 카메라"를 골랐는데 카메라 분석 동의가 없으면, THEN THE App SHALL 장비 점검으로 넘어가지 않고 동의가 필요하다는 문구를 보여준다.
5. WHEN 사용자가 "카메라 없이 계속"을 누르면, THE App SHALL 진행 방식을 "음성만"으로 바꿔 장비 점검으로 이동한다.
6. THE App SHALL 장비 점검 화면에 카메라 자리(어두운 배경, 점선 얼굴 안내), 점검 상태 3개, "면접 시작", "설정으로 돌아가기"를 보여준다. 카메라를 쓰지 않는 방식이면 카메라 자리 대신 그 사실을 알린다. 실제 카메라·마이크 권한은 요청하지 않는다.
7. THE App SHALL 면접 화면에서 질문 진행률, AI 면접관 질문, 방식별 답변 영역(음성: 녹음 상태·파형·타이머, 텍스트: 글자 수가 보이는 입력칸)과 오른쪽 안내(카메라 미리보기 또는 답변 가이드)를 보여준다.
8. WHEN 음성 방식에서 사용자가 "답변 완료하고 추가 질문 받기"를 누르면, THE App SHALL 같은 질문 번호의 추가 질문 화면(예시 답변, "왜 이 질문인가요?")을 보여준다. 추가 질문은 질문당 최대 1개다 (C §1).
9. WHEN 사용자가 "답변 완료하고 다음 질문으로"를 누르면, THE App SHALL 다음 질문으로 넘어가고, 마지막 질문 뒤에는 리포트 화면으로 이동한다.
10. IF 텍스트 방식에서 답변이 비었으면, THEN THE App SHALL 다음 질문으로 넘어가지 않는다.
11. THE App SHALL 리포트 화면에 점수 요약 4개, "면접 점수는 연습용 지표예요. 합격 확률이 아니에요.", 질문별 피드백(말하기 시간, 정면 응시 비율, 주의 항목은 red/500), "다음 연습에서는" 상자와 "다시 연습하기"·"홈으로"를 보여준다.
12. THE App SHALL 얼굴 이미지나 녹음을 만들거나 저장하지 않는다.

### Requirement 11: Mock 데이터와 UI 분리
**User Story:** As a 프론트 담당 개발자, I want 화면 데이터를 컴포넌트 밖에 두기를, so that API를 붙일 때 UI를 크게 고치지 않는다.
출처: 사용자 요청 §7
#### Acceptance Criteria
1. THE App SHALL 화면에 보이는 도메인 데이터(공고, 정책, 진단, 첨삭, 로드맵, 면접 질문·리포트, 멘토 답변, 사용자 표시 정보)를 `features/*/data/`의 Mock_Data로 두고 컴포넌트는 props로만 받는다.
2. THE App SHALL 각 Mock_Data의 형태를 `features/*/types.ts`의 TypeScript 타입으로 정의한다.
3. THE App SHALL API Endpoint, API Client, 가짜 네트워크 지연·응답 흉내를 만들지 않는다.
4. THE App SHALL Mock_Data 화면에 "예시 데이터" 또는 "시연" 표시를 Figma에 있는 위치 그대로 유지한다.

### Requirement 12: 접근성
**User Story:** As a 키보드·스크린리더 사용자, I want 기본 접근성을, so that 모든 기능을 쓸 수 있다.
출처: 사용자 요청 §6-7
#### Acceptance Criteria
1. THE App SHALL 이동은 `<a>`(Next Link), 동작은 `<button>`으로 렌더링하고, 모든 대화형 요소에 보이는 포커스 표시를 둔다.
2. THE App SHALL 입력칸에 연결된 `<label>`을, 오류 문구에 `aria-describedby`·`aria-invalid`를 붙인다.
3. THE App SHALL 아이콘만 있는 버튼에 `aria-label`을, 장식 아이콘에 `aria-hidden`을 붙인다.
4. THE App SHALL 표 형태 목록을 표 의미(`role="table"` 또는 `<table>`)로 읽히게 한다.

## 결정 기록 (프론트 담당, 2026-11-20)
- 데모 직무: Mock_Data를 Figma의 "백엔드 개발자" 대신 통합 데모 직무 "데이터 분석"으로 쓴다 (D-37).
- GNB "알림"은 뺀다. "저장한 공고"는 Figma에 이동할 화면이 없어 동작하지 않는 표시로 둔다.
- 첨삭 "이력서" 탭, 진단 "직접 입력" 탭, 면접 질문 2·3과 추가 질문, 공고·정책 상세 2·3번째 항목은 Figma에 내용이 없어 같은 틀에 데모 직무에 맞춘 예시 데이터를 채운다.
