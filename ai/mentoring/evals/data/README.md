# 가상 이력서 정답셋

멘토링 역량 추출의 근거 연결과 미기재 역량 처리를 검사하는 완전한 가상 데이터다. 실제 사람·회사·학교·연락처를 포함하지 않는다.

각 `resumes/*.json`은 다음 필드를 가진다.

- `resumeId`: 정답셋 안에서 유일한 ID
- `jobRole`, `ncsCode`, `documentType`: 목표 직무와 문서 종류
- `text`: 평가 입력 원문
- `expectedSkills[]`: 기대 역량의 `name`, 원문에 그대로 있는 `quote`, `evidenceLevel`
- `notMentioned[]`: 원문에 없으므로 `NOT_FOUND`로 다뤄야 할 역량 이름
- `notes`: 평가 시 주의점

연락처는 `010-0000-XXXX`, 이메일은 `@example.com`, 이름·회사·학교는 모두 `가상` 표시를 사용한다. 이 데이터는 모델 학습이나 공용 Knowledge Base 적재 대상이 아니다.
