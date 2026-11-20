아래 모의면접 답변 묶음(기본 질문과 꼬리질문)을 평가표로 평가하라.

{{JOB}}
{{RESUME}}
{{QUESTION_TYPE}}
{{QUESTION}}
{{ANSWER}}
{{FOLLOW_UP_QUESTION}}
{{FOLLOW_UP_ANSWER}}

## 평가표
{{RUBRIC}}

## 평가 방법
- 기본 답변과 꼬리 답변을 한 묶음으로 보고 항목마다 1~5 정수 점수를 준다. follow_up 태그가 비어 있으면 기본 답변만 본다.
- 2점과 4점은 이웃한 기준의 중간이다.
- 수치가 없어도 본인이 한 행동과 결과가 구체적이면 높은 점수를 준다.
- 자소서와 다른 부분은 점수에 넣지 않는다.
- 항목마다 근거를 하나 적는다.
  - evidenceType이 quote면 evidence에 답변 속 문장을 고치지 말고 그대로 옮긴다 (150자 이내).
  - 답변에 근거가 없으면 evidenceType을 missing으로 하고 evidence에 빠진 요소를 짧게 적는다.
- 평가표의 항목 key를 빠짐없이 한 번씩 쓴다.

## 출력 형식
{"items": [{"key": "...", "score": 4, "evidenceType": "quote", "evidence": "..."}]}
