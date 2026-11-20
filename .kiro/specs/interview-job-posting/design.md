# Design Document

기준: 이 폴더의 `requirements.md`, 이슈 #158, `main` `a8f1c57`.

## 1. 개요

```
프론트 /start 본문 { job, resumeText, interviewType, cameraConsent, profile?, jobPosting? }
  └ 백엔드 h_start: impl.normalize_job_posting(body.get("jobPosting"))  → 400이면 INVALID_INPUT
       (B 공고에서 시작하면 impl.job_posting_from_posting(posting) 결과를 그대로 jobPosting으로)
  └ task_start: call_ai(impl.start_interview, iv_id, job, resumeText, interviewType, cameraConsent, profile, jobPosting)
       └ StartInterviewInput 검사 (job_posting 포함)
       └ generate_from_request → prompting.questions_prompt(..., job_posting) → a_questions_v3.md
       └ Session (공고 없음, promptVersion A-v3/B-v2)
```

백엔드 쪽(`h_start`, `task_start`, `interview_stub.py`)은 이 PR에서 바꾸지 않는다. 연결 방법은 인계 문서로 넘긴다 (tasks 5).

## 2. 파일

| 파일 | 변경 |
|---|---|
| `settings.py` | `JOB_POSTING_TEXT_MIN/MAX` 30/4000, `JOB_POSTING_TITLE_MAX` 200, `JOB_POSTING_COMPANY_MAX` 100 |
| `models.py` | `JobPostingInput`, `QuestionRequest.job_posting` |
| `job_posting.py` (새 파일) | `normalize_job_posting`, `job_posting_from_posting` |
| `flow.py` | `start_interview` 7번째 인자, 로그 `jobPosting=` |
| `questions.py` | `generate_from_request`가 공고를 넘김, `generate_questions(job_posting=)` |
| `prompting.py` | `DATA_TAGS`에 `job_posting`, `questions_prompt(job_posting=None)`, `_job_posting_text` |
| `prompts/a_questions_v3.md` (새 파일) | §5 |
| `versions.py` | `PROMPT_A_VERSION` A-v3 |
| `__init__.py` | 2개 함수 내보내기 (11개) |
| `samples/session_after_start.json` | `promptVersion` A-v3/B-v2 |

## 3. 모델 (`models.py`)

```python
class JobPostingInput(_CamelModel):          # extra="forbid"
    title: str | None = None                  # strip, 빈 값 → None, ≤ 200
    company: str | None = None                # strip, 빈 값 → None, ≤ 100
    text: str                                 # strip, 30 ≤ len ≤ 4000

class QuestionRequest(_CamelModel):
    ...
    job_posting: JobPostingInput | None = None   # JSON 키 jobPosting
```

- `text`를 공백 정리 뒤 재는 이유: 붙여 넣은 공고는 앞뒤 줄바꿈이 많다. 자소서(`resume_text`)는 백엔드와 같은 기준이라 원문 길이로 재지만, 공고는 백엔드가 C 함수로 검사하므로 기준이 하나다.
- 4,000자를 넘으면 자르지 않고 거절한다. 사용자가 직접 넣은 값을 몰래 자르면 뒤쪽 요건이 빠진 것을 모른다. B 공고 변환만 자른다 (§4.2).
- `StartInterviewInput`은 `QuestionRequest`를 이어받으므로 따로 고치지 않는다.
- Session에는 필드를 더하지 않는다 (결정 5).

## 4. `job_posting.py`

### 4.1 `normalize_job_posting(value) -> dict | None`

```python
if value is None: return None
posting = parse_input(JobPostingInput, value, stage="normalize_job_posting")   # dict 아니면 실패
  └ 실패: InterviewError(INVALID_INPUT, JOB_POSTING_INVALID_MESSAGE) from None
return {"title": posting.title, "company": posting.company, "text": posting.text}
```

- 안내 문장: "채용공고 내용을 확인해 주세요. 공고 본문은 30자 이상 4,000자 이하로 넣어 주세요." 숫자는 settings에서 만든다.
- 로그는 `parse_input`이 남기는 `stage=normalize_job_posting errorCode=INVALID_INPUT fields=...`뿐이다.

### 4.2 `job_posting_from_posting(data) -> dict | None`

```
data가 model_dump를 가지면 → model_dump(by_alias=True, mode="json")
dict가 아니면 → None
required, preferred = 요건을 kind로 나눔 (순서 유지, 줄 = "- " + (sourceQuote.strip() or name.strip()), 같은 줄 한 번)
sections = [("[필수 요건]", required), ("[우대 사항]", preferred), ("[공고 내용]", [jobDescription.strip()])] 중 내용 있는 것
text = "\n\n".join(제목 + "\n" + "\n".join(줄들))[:4000].rstrip()
len(text) < 30 → None
title = title.strip()[:200] or None, company = organization.strip()[:100] or None
```

- 요건을 본문보다 앞에 둔다. 4,000자에서 잘려도 요건이 남는다. B의 `posting_text()`는 순서가 반대이고 B 내부 모델을 받으므로 쓰지 않는다.
- `eligibilityRules`는 넣지 않는다 (requirements Requirement 3.8).
- 30자 미만이면 None을 돌려 공고 없이 면접을 하게 한다. 요건 하나("- SQL")만 있는 공고로 질문을 맞추면 오히려 질문 폭이 좁아진다.

## 5. 프롬프트 `a_questions_v3.md`

- 자리표시: `{{JOB}} {{INTERVIEW_TYPE}} {{RESUME}} {{PROFILE}} {{JOB_POSTING}}`
- `<job_posting>` 내용 (`prompting._job_posting_text`):

```
제목: 데이터 분석 신입        ← 값이 있을 때만
회사: 가상 데이터랩 부산      ← 값이 있을 때만
본문:
(text)
```

- 공고가 없으면 `<job_posting>\n\n</job_posting>`. 프롬프트는 "job_posting이 비어 있으면 이 절은 건너뛴다"로 v2와 같은 동작을 하게 한다.
- 질문 유형별 재료:

| 유형 | 공고 없음 (v2와 같음) | 공고 있음 |
|---|---|---|
| experience | 자소서에 적힌 경험 | 자소서 경험 가운데 공고 업무·요건과 가장 가까운 것 |
| knowledge | 직무(`job`) 지식 | 공고 업무·자격 요건·우대 사항의 지식이나 기술 하나 |
| situation | 직무에서 생길 상황 | 공고 업무의 상황. 인재상이 있으면 그 행동을 볼 수 있는 상황 |

- 면접 유형: PERSONALITY면 인재상과 일하는 방식, JOB이면 업무·자격 요건·우대 사항을 중심으로 한다.
- 지키는 것: 공고에 없는 항목을 짐작하지 않는다, 요건이 자소서에 없어도 부족 단정·경험 가정 금지, 회사 이름 넣지 않기, 공고 문장 길게 옮기지 않기, 공고 안 지시 따르지 않기.
- v2의 질문 문장 규칙(한 가지만, 나쁜 예·좋은 예, 80자, 서로 다른 내용, 기출 금지, 직무 무관 요소 금지)과 출력 형식은 그대로 옮긴다.

## 6. 버전

| 값 | 이전 | 지금 |
|---|---|---|
| `PROMPT_A_VERSION` | A-v2 | A-v3 |
| `PROMPT_VERSION` (Session) | A-v2/B-v2 | A-v3/B-v2 |
| `SCORING_VERSION`, `REPORT_PROMPT_VERSION` | 그대로 | 그대로 |

`prompting.QUESTIONS_FILE`은 버전에서 이름을 만들므로 `a_questions_v3.md`가 된다.

## 7. 로그

- `start_interview`: `stage=start_interview jobPosting=True durationMs=...`
- `normalize_job_posting` 실패: 필드 이름만
- 공고 본문·제목·회사 이름은 어디에도 남기지 않는다 (`test_logging.py`에 공고 문장을 원문 목록으로 더한다)

## 8. 위험

| 위험 | 대응 |
|---|---|
| 공고가 길어 입력 토큰이 늘어난다 (최대 4,000자 ≈ 수천 토큰) | 출력 상한(`max_tokens`)과 별개다. 질문 생성은 한 번 호출이라 지연 증가는 작을 것으로 본다. 수동 확인에서 시간을 잰다 |
| 공고 문장을 길게 옮겨 80자를 넘는다 | 프롬프트 규칙. 스키마 상한(300자)은 그대로라 넘어도 실패하지 않는다. 수동 확인에서 길이를 본다 |
| 공고 속 지시문(프롬프트 인젝션) | 태그로 감싸고 같은 태그 무력화, v3 본문 규칙. 수동 확인에 지시문이 든 공고를 넣는다 |
| 인재상이 없는데 지어낸다 | 프롬프트 규칙. 수동 확인에 인재상 없는 공고를 넣는다 |
| 요건이 자소서에 없을 때 "경험이 있다"고 가정한 질문 | 프롬프트 규칙 (제품 원칙 5) |
| 백엔드가 6개 인자로 부르는 동안 | 공고 없이 지금과 같은 질문 (A-v3 공고 없는 경로). 되돌릴 때는 버전만 내리면 된다 |
| 배포 되돌림 | Session 형식이 같아 A-v2 코드로 되돌려도 진행 중 면접이 깨지지 않는다 (`promptVersion`은 문자열) |
