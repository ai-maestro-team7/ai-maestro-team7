# 부산 기회 추천 (B)

부산 채용공고와 청년정책을 맞춤 추천하는 B 파트 코드다. 규칙은 루트 `AGENTS.md`의 "B 작업 기준"을, 명세는 `docs/개발계획서2.md`를 본다.

## 테스트

```bash
cd ai/busan-opportunity
uv run --no-project --python 3.13 --with-requirements requirements-dev.txt pytest
```

AWS와 공공 API를 부르지 않는다. 데모 데이터(`src/opportunity/seeds/demo_world.py`)가 든 메모리 저장소로 돈다.

## 구조

| 경로 | 내용 |
|---|---|
| `src/opportunity/models/` | Pydantic 모델. 데이터 계약의 기준이다 |
| `src/opportunity/config/` | `opportunity_config.json`과 로더. 숫자는 여기서만 읽는다 |
| `src/opportunity/ports.py`, `deps.py` | 저장소·벡터·모델·일정 인터페이스와 의존성 묶음 |
| `src/opportunity/core/` | 규칙 코드 (피드, 대안, 비교, 정책, 저장). LLM을 부르지 않는다 |
| `src/opportunity/ingest/` | 공공 API 수집과 정규화 |
| `src/opportunity/enrich/` | 요건 추출, 임베딩, 배지, 대안 후보, 설명 문장. LLM은 여기서만 부른다 |
| `src/opportunity/store/` | 저장소 구현. `memory.py`는 테스트용, 나머지는 AWS |
| `src/opportunity/notify/` | 일정 예약과 알림 |
| `src/opportunity/api/` | REST와 Action Group 입구 |
| `mocks/` | 프론트용 가짜 응답. `build_mocks.py`로 만든다 |
| `tests/` | `unit/`, `rules/`(T-01~T-22), `personas/`, `contract/` |

## 함께 쓰는 파일

아래 파일은 여러 작업이 기대고 있다. 고쳐야 하면 따로 PR을 올려 먼저 맞춘다.

- `models/`, `config/`, `ports.py`, `deps.py`
- `core/clock.py`, `core/context.py`, `core/copy_rules.py`, `core/eligibility.py`, `core/regions.py`, `core/texts.py`
- `store/memory.py`, `seeds/demo_world.py`, `tests/conftest.py`

## 지킬 것

- `backend/`를 import하지 않는다. 지원 자격 판정과 워크스페이스는 입구가 `Deps`로 넣어 준다.
- userId는 입구가 인증 정보에서 읽어 넘긴다. 요청 본문이나 모델 파라미터의 값은 쓰지 않는다.
- 날짜는 `core/clock.py`의 `as_of`로만 계산한다.
- 출처와 기준일이 없는 배지·숫자는 응답에서 뺀다. `verified=false` 정책은 내보내지 않는다.
- 적합도(matchScore)에는 부산 가산점을 넣지 않는다. 가산점은 정렬 점수(rankScore)에만 넣는다.
