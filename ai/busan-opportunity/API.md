# 부산 기회 추천 API 안내 (프론트용)

경로·필드는 `src/opportunity/api/rest_handler.py`와 `src/opportunity/models/api.py`에서 확인한 것만 적었다. 응답 예시는 `mocks/`의 JSON이다. `mocks/build_mocks.py`가 응답 모델로 검사한 뒤 만들고, 모델이 바뀌면 `tests/contract/test_mocks.py`가 알려 준다. 회사·기관 이름은 가상이다.

## 공통 규칙

- 주소는 `/api/v1/opportunities/...`다.
- 모든 요청에 `Authorization: Bearer <토큰>`을 붙인다. 사용자 ID는 토큰에서만 읽는다. 본문이나 쿼리에 `userId`를 넣지 않는다.
- JSON 키는 카멜 표기다. 값이 없는 필드는 `null`이 아니라 키 자체가 빠진다.
- 주소의 ID에 `#`이 들어가면 400이다.
- 오류는 이 모양이다. 화면에는 `message`를 그대로 보여 주고, `retryable`이 true일 때만 다시 시도 버튼을 둔다.

```json
{"error": {"code": "POSTING_NOT_FOUND", "message": "공고를 찾을 수 없어요.", "requestId": "req-demo", "retryable": false, "details": {}}}
```

  주요 코드: `INVALID_INPUT`(400), `POSTING_NOT_FOUND`·`POLICY_NOT_FOUND`·`NOTIFICATION_NOT_FOUND`·`NOT_FOUND`(404), `PRECONDITION_NOT_MET`(409), `PROFILE_INCOMPLETE`(422), `AI_OUTPUT_INVALID`(500, 다시 시도 가능), `AWS_SERVICE_ERROR`(503, 다시 시도 가능). 예시는 `ERROR_404.json`.
- 저장 계열(`POST /saved`, `POST /policies/{id}/alerts`)에는 `Idempotency-Key` 헤더를 붙인다. 같은 키와 같은 본문을 다시 보내면 저장된 결과를 돌려주고, 같은 키에 다른 본문을 보내면 409다. 키에 `#`을 넣지 않는다. 새로 만들면 201, 이미 있으면 200이고 본문의 `created`도 같은 뜻이다.

## 경로

앞의 `/api/v1/opportunities`는 줄였다. 파일은 모두 `mocks/` 아래에 있다.

| 메서드 | 경로 | 하는 일 | 쿼리·본문 | 응답 예시 |
|---|---|---|---|---|
| GET | `/postings` | 맞춤 피드 | 쿼리 `region`(`ALL`·`BUSAN`·`CAPITAL`·`OVERSEAS`·시도 코드, 기본 `ALL`), `sort`(`BUSAN_FIRST`·`MATCH`·`DEADLINE`·`RECENT`), `jobCodes`(쉼표), `keyword`(제목·회사·직무 이름에 들어 있는 글자. 프로필 후보 밖의 공고도 이름 색인에서 찾는다, B-D08), `sector`(`ALL`·`PUBLIC` 공기업·`PRIVATE` 사기업, B-D11), `cursor`, `limit`, `regionalTalent`(`true`면 공고문의 지역 조건이 학교 지역·사는 곳과 맞을 수 있는 공고만. 카드의 `regionalTalent`가 `LIKELY`, B-D09). 공공기관 카드에는 `orgPay{average, year, yearNote, unit, source, asOf, sourceUrl}`(기관 직원 평균보수, 공고 급여 아님, B-D11)가 붙는다 | `GET_postings.json` |
| GET | `/public/postings` | 로그인 없이 보는 공고 목록 (토큰 없음, B-D10). 마감 임박순, 적합도 같은 개인 값 없음 | 쿼리 `keyword`, `region`(피드와 같음), `sector`(`ALL`·`PUBLIC` 공기업: 공공기관·지방공공기관·`PRIVATE` 사기업), `orgType`(한 가지만), `career`(`ALL`·`NEW`·`EXPERIENCED`, 신입·경력 무관 공고는 둘 다), `employment`(`ALL`·`FULL_TIME`·`CONTRACT`·`PART_TIME`·`INTERN`), `cursor`, `limit`(1~50, 기본 20). 응답 `{items, total, nextCursor, dataAsOf, stale}` | `GET_public_postings.json` |
| GET | `/postings/{id}` | 공고 상세. 공공기관·지방출자출연기관이면 `orgPay`에 연도별 기관 직원 평균보수가 있다 (B-D11) | - | 서울 `GET_postings_id.json`, 부산 `GET_postings_id_busan.json` |
| GET | `/postings/{id}/explanation` | 추천 이유 문장 | - | `GET_postings_id_explanation.json` |
| POST | `/postings/{id}/ask` | 이 공고에 질문 | 본문 `{"question"}` (300자까지) | `POST_postings_id_ask.json`, `POST_postings_id_ask_unanswered.json` |
| GET | `/postings/{id}/alternatives` | 같은 일, 부산에서 | 쿼리 `leaveReason`, `limit` | `GET_postings_id_alternatives.json` |
| GET | `/compare` | 두 공고 나란히 비교 | 쿼리 `baseJobPostingId`, `altJobPostingId`, `familyHousing` | `GET_compare.json` |
| GET | `/companies` | 부산 기업 둘러보기 | 쿼리 `category`(`SALARY`·`WELFARE`·`WORK_LIFE`·`FUTURE`), `limit`(1~50) | `GET_companies.json` |
| GET | `/policies` | 정책 지갑 | 쿼리 `stage`(`PREPARE`·`EMPLOYED`·`SETTLE`) | `GET_policies.json` |
| POST | `/policies/ask` | 정책 전체에 질문 | 본문 `{"question"}` | `POST_policies_ask.json`, `POST_policies_ask_unanswered.json` |
| GET | `/policies/{id}` | 정책 상세 | - | `GET_policies_id.json` |
| POST | `/policies/{id}/ask` | 이 정책에 질문 | 본문 `{"question"}` | `POST_policies_id_ask.json` |
| POST | `/policies/{id}/alerts` | 정책 신청 알림 받기 | `Idempotency-Key` | `POST_policies_id_alerts.json` |
| GET | `/me/preferences` | 설정 조회 | - | `GET_me_preferences.json` |
| PUT | `/me/preferences` | 설정 변경. 보낸 필드만 바뀐다 | 본문 `sort`, `leaveReason`, `notifications`, `receivingPolicies` | `PUT_me_preferences.json` |
| GET | `/saved` | 저장한 공고 | - | `GET_saved.json` |
| POST | `/saved` | 공고 저장·목표 담기 | `Idempotency-Key`, 본문 `jobPostingId`, `kind`(`INTEREST`·`TARGET`), `fromAlternativeOf` | `POST_saved.json` |
| DELETE | `/saved/{id}` | 저장 풀기. 목표 공고의 마감 일정도 지운다. 워크스페이스는 남는다. 저장돼 있지 않았으면 200에 `deleted: false` | - | `DELETE_saved_id.json` |
| GET | `/notifications` | 알림 목록 | 쿼리 `cursor`, `limit` | `GET_notifications.json` |
| POST | `/notifications/{id}/read` | 알림 읽음 | - | `POST_notifications_id_read.json` |
| POST | `/track` | 화면 이벤트 기록 | 본문 `event`(`ALT_CLICKED`·`COMPARE_OPENED`·`COST_TOGGLE_ON`·`BUSAN_FIRST_OFF`·`POLICY_LINK_CLICKED`), `jobPostingId`, `policyId` | `POST_track.json` |
| POST | `/admin/demo-clock` | 데모 시간 앞당기기. 데모 계정만, 아니면 404 | 본문 `{"asOf"}` (`YYYY-MM-DD` 또는 ISO 8601) | `POST_admin_demo-clock.json` |

`POST /track`은 `ALT_SHOWN`·`SAVED`·`NO_ALTERNATIVE`를 받지 않는다(400). 서버가 남기는 이벤트다.

## 화면에서 지킬 문구

- 적합도는 숫자를 보여 주지 않는다. `matchLevel` 3단계만 쓴다: `GOOD` 잘 맞아요, `FAIR` 맞는 편이에요, `LOW` 조금 맞아요. 근처에 "적합도는 실제 합격 확률이 아닙니다"를 둔다. `matchScore`·`rankScore`는 정렬과 디버그용이다.
- "마감 임박", "놓치면", "후회", "손해", "떠나면", "합격에 유리해요", "부산이 이득이에요" 같은 표현은 쓰지 않는다. 마감은 "마감 D-3"처럼 사실만 적는다. 응답의 `facts`·`whyShown`·`sentences`는 서버가 이 규칙에 맞춰 만든 문장이니 고쳐 쓰지 않고 그대로 보여 준다.
- `isSample`이 true면 "데모 데이터"라고 표시한다.
- 알림의 `simulated`가 true면 "시뮬레이션"이라고 표시한다. 데모 시간 앞당기기로 만든 알림이다.
- 정책 금액은 `benefit.publicShareMax`(시 지원분)와 `benefit.selfShareMax`(본인 저축분)를 따로 보여 준다. 둘을 더해 "지원금"으로 쓰지 않는다. 지갑 합계는 `totals.guaranteedIfEligible`(자격이 맞으면 받는 지원)과 `totals.selectiveMax`(선정되면 최대)를 따로 쓴다.
- 배지는 응답에 온 것만 보여 준다. `source`와 `asOf`가 있는 값이다.
- 부산 공고를 앞세우는 문구는 만들지 않는다. 정렬 이유는 `ranking.basis`를 그대로 칩에 보여 준다. 부산 쪽에서 더 보이는 것은 통근 시간, 정책, 주변 생활 정보뿐이고, 다른 지역 공고의 정보를 줄이지 않는다.
- 해외 공고(`workRegion.overseas`가 true)는 `workRegion.label`을 그대로 보여 준다("해외 근무 · 베트남"). 부산도 수도권도 아니라서 `isBusan`·`isCapitalArea`가 모두 false다.
- 급여는 `salary.disclosed`가 false면 "공고에 없음"으로 보여 준다. `min`만 있으면 "연 3,200만 원 이상"처럼 하한만 적고 `max`를 추정하지 않는다. 단위는 `unit`(`MANWON_YEAR`)이다.

## 값이 없을 수 있는 필드

키가 없으면 그 칸이나 줄을 통째로 숨긴다. 빈 칸이나 "0"으로 채우지 않는다.

| 필드 | 없을 때 |
|---|---|
| `commuteMinutes` (피드 카드) | 통근 줄을 숨긴다. 거주 구와 근무 구 사이 시간이 통근 표에 없을 때, 근무지를 모르거나 해외 공고일 때 빠진다 |
| `localLife` (상세) | "이 동네에서 일하면" 묶음을 통째로 숨긴다. 부산 공고 상세에만 온다 |
| `localLife.commuteMinutes`·`commuteLabel` | 통근 줄만 숨긴다. 축제(`festivals`)와 대중교통(`transit`)은 있으면 따로 보여 준다. 각 항목에 `source`·`asOf`를 작게 붙인다 |
| `busanAlternativesCount` (피드 카드) | 수도권 공고에만 온다. 없으면 "부산 대안" 버튼을 두지 않는다 |
| `answer` (질문 응답) | `answered`가 false다. 아래 참고 |

`distanceKm`(직선거리)은 지금 응답 모델에 없다. 카드에도 `localLife`에도 오지 않으니 화면에서 기다리지 않는다. 모델에 들어오면 이 문서와 mocks를 함께 고친다.

`localLife.commuteLabel`은 "사는 구청에서 근무지 구청까지"의 시간이다. 집 주소에서 재지 않았으니 문구를 줄이지 않는다.

## 질문 응답 (`/ask` 3개)

세 경로가 같은 `AskResponse`를 돌려준다.

- `answered`가 true면 `answer`를 보여 주고 `sources`를 근거로 붙인다. 각 근거는 `title`, `quote`(원문 문장), `url`, `asOf`다. 정책 질문이면 `relatedPolicies`와 `manualChecks`(직접 확인할 조건)도 함께 보여 준다.
- `answered`가 false면 `answer`가 없다. 오류가 아니고 200이다. 답을 지어 채우지 말고 `notice`를 그대로 보여 준다. 근거를 못 찾았을 때는 "원문에서 확인되지 않아요. 공고문이나 담당 기관에 확인해 주세요"이고, 답을 만들지 못했을 때는 "지금은 답을 만들지 못했어요. 아래 정책 원문을 확인해 주세요"다. `relatedPolicies`가 같이 오면 그 목록은 그대로 보여 준다.
- 질문은 300자까지다. 넘으면 400 `INVALID_INPUT`이다.
- 없는 공고·정책이면 404다. `answered=false`와는 다르다.
