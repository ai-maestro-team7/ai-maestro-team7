# 채팅 Agent (`supervisor`)

명세: [`docs/개발계획서4.md`](../../docs/개발계획서4.md) · 결정: D-38(Strands), D-39(채팅 입구), D-40(조건 저장은 사용자에게 묻기)

채팅으로 받은 조건(직무, 기업명, 지역, 연봉, 신입/경력)이나 이력서로 채용공고와 청년정책을 함께 찾고, 모의면접 체험으로 이어 준다.

| 파일 | 하는 일 |
| --- | --- |
| `service.py` | `start_turn`(202), `run_turn`(비동기 한 턴), `get_message`, `get_session` |
| `tools.py` | 도구 5개: `get_my_status`, `search_job_postings`, `find_youth_policies`, `ask_youth_policy`, `prepare_mock_interview` |
| `compose.py` | 도구 기록으로 카드(`POSTING`, `POLICY`)와 행동(`SAVE_CONDITIONS`, `SUGGEST_INTERVIEW`, `START_INTERVIEW`, `REQUEST_COVER_LETTER`) 만들기 |
| `checks.py` | 답 검사: 길이, 금지 문구, 근거 없는 숫자 |
| `runner.py` | Strands 실행기 (`structured_output_model=ChatReply`) |
| `ports.py` | 바깥 의존성 인터페이스. 구현은 `backend/agent_api.py` |
| `store/` | `SESSION#`·`CHAT#` 저장소 (DynamoDB, 메모리) |
| `config/supervisor_config.json` | 한도·버전·금지 문구 |
| `prompts/system_v1.md` | 시스템 프롬프트 (`promptVersion` `chat-v1`) |

- 이 패키지는 `backend/`와 다른 파트 패키지를 import하지 않는다. B 함수와 A 문서는 포트로 받는다.
- 도구에는 userId 인자가 없다. 백엔드가 확인한 사용자를 클로저로 넣는다.
- 카드·숫자는 도구 결과로 코드가 만든다. 모델 답은 `reply`와 `followUps`뿐이다.

테스트 (외부 서비스 없이)

```bash
cd ai/supervisor
uv run --no-project --python 3.13 --with-requirements requirements-dev.txt python -m pytest
```
