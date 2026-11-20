# 멘토링 프론트용 가짜 응답

`build_mocks.py`가 테스트용 의존성과 실제 REST 핸들러를 호출해 만든 결정적 응답이다. JSON을 손으로 수정하지 말고 생성 스크립트를 다시 실행한다.

## 화면 흐름

1. 이력서 입력 화면에서 `POST /documents/text`를 호출한다. 응답은 `202 PENDING`이다.
2. `documentId`로 2초마다 `GET /documents/{documentId}`를 호출한다.
3. `EXTRACTED`·`ANALYZING`은 진행 상태로 표시한다. `COMPLETED` 또는 `REQUIRES_USER_REVIEW`가 되면 폴링을 멈춘다.
4. `GET /profiles/me`로 근거가 붙은 역량을 표시한다.
5. 역량별 확인 버튼은 `POST /profiles/{profileId}/confirm`을 호출한다.

`REQUIRES_USER_REVIEW`는 실패가 아니라 사용자 확인이 필요한 상태다. 해당 근거에는 “확인 필요”를 표시하고 원문 근거를 여는 버튼은 “근거 보기”로 쓴다.

이어지는 화면 (모두 202 → 2초마다 GET, 상태가 `PENDING`·`PROCESSING`이 아니면 멈춤)

| 화면 | 요청 | 가짜 응답 |
|---|---|---|
| PDF 업로드 | `POST /documents/upload-url` → 브라우저가 `uploadUrl`로 PUT → `POST /documents/{id}/complete` | `POST_documents_upload_url` |
| 경험 블록 | `POST /stories`(201, 질문 최대 3개) · `GET /stories` · `PATCH /stories/{id}` | `POST_stories`, `GET_stories`, `PATCH_stories_id` |
| 직무 적합도 | `POST /analyses` `{profileId, jobPostingId 또는 targetNcsCode}` → `GET /analyses/{id}` | `POST_analyses`, `GET_analyses_id_PENDING`, `GET_analyses_id_COMPLETED` |
| 첨삭 | `POST /reviews` `{inputText 또는 documentId, analysisId?, questionText?, maxCharacters?, storyIds?}` → `GET /reviews/{id}` | `POST_reviews`, `GET_reviews_id_COMPLETED` |
| 학습 경로 | `POST /learning-paths` `{analysisId, weeklyStudyHours, targetDate?}` → `GET /learning-paths/{id}` | `POST_learning_paths`, `GET_learning_paths_id_COMPLETED` |

- 적합도: `eligibility`를 점수보다 먼저 보여 준다. `unverifiedSkills[].question`은 "확인 질문"으로 보여 준다.
- 첨삭: 각 `issues[]`의 `sourceSpan`으로 원문에 밑줄을 긋는다. `factCheck: REJECTED`이면 수정 예시 대신 `questions`를 보여 준다.
  제안일 뿐이라 원문을 자동으로 바꾸지 않는다.
- 학습 경로: `verificationTasks`(먼저 확인할 것)를 주차 계획보다 앞에 둔다. 자격의 `verificationStatus: SCHEDULE_UNVERIFIED`이면
  날짜 대신 `officialUrl`만 보여 준다. 기간·시간에는 "추정"을 붙인다.

## 문구와 상태

- 적합도 화면에는 “적합도는 실제 합격 확률이 아닙니다”를 함께 표시한다.
- 서류에 없는 역량은 “부족” 대신 “미확인” 또는 “확인 필요”로 표시한다.
- 확인되지 않은 수치와 성과를 완성된 사실처럼 보여 주지 않는다.
- `COMPLETED`: 분석 완료
- `REQUIRES_USER_REVIEW`: 근거 또는 수치 확인 필요
- `FAILED`: 재시도 가능 여부를 오류의 `retryable`로 판단

## 오류 처리

| 코드 | 화면 처리 |
| --- | --- |
| `INVALID_INPUT` | 입력 필드를 강조하고 `details`의 필드·길이 기준을 안내한다. 자동 재시도하지 않는다. |
| `DOCUMENT_NOT_FOUND` | 문서 목록으로 돌아가는 동작을 제공한다. 자동 재시도하지 않는다. |
| `PRECONDITION_NOT_MET` | 최신 프로필을 다시 조회한 뒤 사용자가 확인 내용을 다시 선택하게 한다. |
| `NOT_IMPLEMENTED` | 준비 중인 기능으로 표시한다. 자동 재시도하지 않는다. |
| `AWS_SERVICE_ERROR`, `INTERNAL_ERROR` | `retryable=true`일 때만 잠시 뒤 재시도 버튼을 제공한다. |

## 다시 생성

`ai/mentoring`에서 다음 명령을 실행한다.

```bash
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_REGION=ap-northeast-2 \
uv run --no-project --python 3.13 \
  --with-requirements requirements-dev.txt \
  --with-requirements ../../contracts/requirements.txt \
  python mocks/build_mocks.py
```
