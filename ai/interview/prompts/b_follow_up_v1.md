아래는 모의면접의 기본 질문과 지원자의 답변이다. 꼬리질문이 필요한지 판단하라.

{{JOB}}
{{RESUME}}
{{QUESTION}}
{{ANSWER}}

## 판단 기준
- ABSTRACT: 답변에 지원자 본인의 구체적 행동, 역할, 결과가 없다.
- INCONSISTENT: 답변 내용이 resume와 다르다.
- SUFFICIENT: 둘 다 아니다. 이때는 꼬리질문을 만들지 않는다.
- ABSTRACT 또는 INCONSISTENT이면 needFollowUp을 true로 하고 꼬리질문을 하나 만든다.
- 꼬리질문은 answer나 resume에 나온 내용만 근거로 하고, 짧게 하나만 묻는다.
- 답변을 평가하거나 정답을 알려 주지 않는다.
- 외모, 나이, 성별, 출신 지역, 가족, 종교, 혼인 여부처럼 직무와 무관한 요소는 판단 근거로 쓰지 않고, 꼬리질문으로도 묻지 않는다.
- 꼬리질문을 특정 기업의 실제 기출 문제라고 하거나 기출 문제처럼 지어내지 않는다.

## 출력 형식
{"needFollowUp": true, "reason": "ABSTRACT", "followUpQuestions": ["..."]}

꼬리질문이 필요 없으면 {"needFollowUp": false, "reason": "SUFFICIENT", "followUpQuestions": []}
