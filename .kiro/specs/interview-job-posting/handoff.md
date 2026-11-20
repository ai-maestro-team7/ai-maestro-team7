# 채용공고 입력 인계 (#158)

대상: 백엔드 담당, 프론트 담당, B 담당. 작성: C 담당.

C 쪽(`ai/interview/`)은 끝났다. 아래를 연결하면 `/start`에 넣은 채용공고가 기본 질문에 반영된다. 연결하기 전에도 지금과 똑같이 동작한다 (백엔드가 6개 인자로 부르면 공고 없이 질문을 만든다).

C가 바꾼 것:
- `start_interview(session_id, job, resume_text, interview_type, camera_consent, profile=None, job_posting=None)`: 7번째 위치 인자 추가
- 새 함수 `impl.normalize_job_posting(value)`: `/start`의 `jobPosting` 검사
- 새 함수 `impl.job_posting_from_posting(posting)`: B 공고 상세를 `jobPosting` 값으로 변환
- 둘 다 AWS를 부르지 않는다
- Session·리포트 형식은 그대로다. `promptVersion`만 `A-v3/B-v2`로 바뀐다

`jobPosting` 형식:

| 키 | 필수 | 규칙 |
| --- | --- | --- |
| `text` | O | 공고 본문. 앞뒤 공백을 지운 뒤 30~4,000자 |
| `title` | X | 200자 이하. 빈 값은 null |
| `company` | X | 100자 이하. 빈 값은 null |
| 그 밖의 키 | - | 거절 (`requirements`, `jobPostingId` 등) |

업무·자격 요건·우대 사항·인재상은 따로 받지 않는다. AI가 본문에서 찾는다.

## 1. 백엔드 (`backend/interview_api.py`)

C는 이 파일을 고치지 않았다. 아래는 제안 코드다.

`h_start`: 자소서 검사 다음, `put_item` 전에 검사한다. 잘못된 공고로 세션이 만들어지지 않게 하기 위해서다.

```python
    profile = data.get("profile") or load_latest_profile(user_id)
    job_posting = impl.normalize_job_posting(data.get("jobPosting"))  # 없으면 None
```

- 어긋나면 `InterviewError(INVALID_INPUT)`가 올라온다. `handle()`이 이미 400과 공통 오류 형식으로 바꾸므로 따로 잡지 않아도 된다.
- 메시지: "채용공고 내용을 확인해 주세요. 공고 본문은 30자 이상 4,000자 이하로 넣어 주세요."

같은 함수의 `enqueue` 입력에 공고를 더한다.

```python
             "input": {"job": job, "resumeText": resume_text, "interviewType": interview_type,
                       "cameraConsent": data["cameraConsent"], "profile": profile, "jobPosting": job_posting}})
```

`task_start`: 7번째 위치 인자로 넘긴다.

```python
    result = call_ai(impl.start_interview, iv_id, inp["job"], inp["resumeText"], inp["interviewType"], inp["cameraConsent"],
                     inp.get("profile"), inp.get("jobPosting"))
```

지킬 것:
- 공고는 비동기 호출 입력에만 넣는다. `INTERVIEW#` 항목에 넣을지는 백엔드 담당이 정한다. C는 공고를 Session에 넣지 않는다.
- 공고 본문·제목·회사 이름을 로그에 남기지 않는다.
- `call_ai`가 `AI_OUTPUT_INVALID`로 다시 부를 때도 같은 7개 인자를 넘긴다. 지금 코드 그대로면 된다.

## 2. 백엔드 대역 (`backend/interview_stub.py`)

실제 함수가 import되지 않을 때 쓰는 대역도 맞춰야 한다. 그대로 두면 다음 두 곳에서 깨진다.
- 7개 인자 호출이 `TypeError`가 된다.
- `impl.normalize_job_posting`이 없어 `AttributeError`(500)가 난다.

```python
def start_interview(session_id, job, resume_text, interview_type, camera_consent, profile=None, job_posting=None):
    ...  # 공고는 쓰지 않는다


def normalize_job_posting(value):
    return value if isinstance(value, dict) else None  # 대역은 검사하지 않는다


def job_posting_from_posting(data):
    return None
```

## 3. 프론트 (면접 설정 화면)

- 선택 입력 "채용공고 붙여넣기"를 둔다. 본문은 여러 줄 입력이고, 제목·회사는 선택이다.
- 본문 글자 수와 "30~4,000자"를 보여 준다.
- 비워 두면 `jobPosting` 키를 보내지 않는다(또는 null). 빈 문자열 `text`를 보내면 400이다.
- 400이면 `error.message`를 그대로 보여 준다.
- 안내 문구 예: "공고에 맞춰 면접 질문을 만들어요. 공고 내용은 질문을 만드는 데만 써요."
  - "저장하지 않아요"는 백엔드가 공고를 저장하지 않기로 정한 뒤에만 쓴다.

## 4. B 공고에서 면접 시작 (정할 것)

`job_posting_from_posting`은 Python 함수라 프론트에서 부를 수 없다. 방법은 둘이다. 백엔드·B 담당이 정한다.

| 방법 | 흐름 | 비고 |
| --- | --- | --- |
| (가) 백엔드가 공고를 읽음 | 프론트가 `/start`에 `jobPostingId`를 보냄 → 백엔드가 catalog `POSTING#{id}` `LATEST`를 읽어 `impl.job_posting_from_posting(posting)` → 결과를 `jobPosting`으로 사용 | `/start` 요청 형식이 바뀌므로 `docs/api.md`를 먼저 고친다. 사용자 것이 아닌 공고 ID도 공개 공고라 문제는 없지만 ID 형식은 검사한다 |
| (나) 프론트가 본문을 채움 | 공고 상세 화면에서 면접으로 갈 때 프론트가 제목·회사·본문을 입력칸에 미리 채움 → 사용자가 고칠 수 있음 → 그대로 `jobPosting` | 변환 함수를 쓰지 않는다. 요건 순서·자르기 규칙이 C와 달라질 수 있다 |

변환 규칙 (가):
- `title` → `title`, `organization` → `company`
- `text`는 다음 순서로 만든다.
  - `[필수 요건]`: `REQUIRED_SKILL` 요건마다 `- ` + `sourceQuote`(없으면 `name`)
  - `[우대 사항]`: `PREFERRED_SKILL` 요건을 같은 방식으로
  - `[공고 내용]`: `jobDescription`
- 4,000자를 넘으면 자른다. 요건을 앞에 두므로 잘려도 요건은 남는다.
- 30자 미만이면 None을 돌려준다. 그러면 공고 없이 면접을 진행한다.
- `eligibilityRules`·마감일·근무지·급여는 넣지 않는다.

## 5. B 담당께

- `job_posting_from_posting`이 읽는 필드는 `title`, `organization`, `jobDescription`, `requirements[].kind`·`sourceQuote`·`name`이다. 이 이름이 바뀌면 C에 알려 주세요.
- 수동 확인에서 업무 설명이 한 문장뿐인 계약 예시 공고(`busan-data-analysis`)는 질문이 공고 없음과 비슷하게 나왔다. 업무 내용(`jobDescription`)이 구체적일수록 질문이 공고에 맞춰진다.
- B 데이터에는 인재상 필드가 없다. 그래서 B 공고로 시작하면 인재상에 맞춘 상황 질문은 나오지 않는다 (지어내지 않는다).

## 6. 문서 담당께 (AGENTS.md)

`AGENTS.md` "B 작업 기준 > 명세보다 나중에 바뀐 것" 표의 다음 행은 #158 팀 합의로 바뀌었다.

> C `/start`에 직무와 요건을 넘김 → 면접 페이지로 이동하고 `job` 칸(1~50자)만 채운다

바뀐 내용: `job`(1~50자, 필수)은 그대로 두고, 채용공고 `jobPosting{title?, company?, text}`를 선택으로 더한다. C는 이 PR에서 `AGENTS.md`를 고치지 않았다.

## 7. 연결 뒤 확인

| 확인 | 기대 |
| --- | --- |
| 공고 없이 시작 | 지금과 같음 (`promptVersion` A-v3/B-v2) |
| 공고를 넣고 시작 | 지식·상황 질문이 공고 업무·요건을 반영 |
| 본문 29자 / 4,001자 | 400 `INVALID_INPUT`, 세션이 만들어지지 않음 |
| 모르는 키(`requirements`) | 400 |
| 대역(stub) 모드로 시작 | 공고가 있어도 오류 없이 대역 질문 |
| CloudWatch 로그 | 공고 원문 없음, `stage=start_interview jobPosting=True` |

## 8. 되돌림

- C 코드만 되돌릴 때: Session 형식이 같아서 진행 중인 면접은 깨지지 않는다.
  - 단, 백엔드가 이미 7개 인자로 부르는 상태에서 C를 #158 이전으로 되돌리면 `start_interview`가 `TypeError`를 낸다.
  - `normalize_job_posting`이 없어서 `/start`는 500이 된다.
  - 그러니 백엔드 연결과 C 코드는 같이 되돌린다.
- 백엔드만 되돌릴 때: 6개 인자 호출로 돌아가므로 공고 없이 동작한다.
