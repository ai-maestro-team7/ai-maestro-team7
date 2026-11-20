# 수집 배치 연결 안내 (백엔드 담당용)

B의 공공 데이터 수집을 매일 새벽에 돌리려면 백엔드에서 붙일 것을 정리했다. B 쪽 코드는 준비돼 있고, 일정·환경변수·권한·Lambda 입구는 백엔드가 붙인다.

## B가 준비한 것

`opportunity.batch.run_batch(event, deps, raw_store, secrets)`를 부르면 한 걸음을 실행하고 `{"step", "result", "next"}`를 돌려준다. `next`가 있으면 그 값으로 다시 부른다. `next`가 `None`이면 끝난 것이다.

| 이벤트 | 하는 일 |
|---|---|
| `{"step": "ingest"}` | 매일 수집. 출처를 하나씩 받아 온다 (잡알리오, 지방공공기관, 해외취업, 온통청년) |
| `{"step": "ingest", "sources": ["work24_gangso"]}` | 출처를 골라 수집. 강소기업은 주 1회면 된다 |
| `{"step": "enrich", "ids": [...]}` | 바뀐 공고 보강. 수집이 끝나면 `next`로 자동으로 이어진다 |

- 한 출처가 실패해도 다음 출처로 넘어간다. 실패는 `result.status = "FAILED"`로 남고, 날짜별 기록은 S3 `runs/{날짜}.json`에 쌓인다.
- 보강은 한 번에 100건씩 한다 (`opportunity_config.json`의 `batch.enrichChunk`).
- 수집이 하나라도 성공해야 데이터 기준 시각이 올라간다. 36시간 넘게 멈추면 API 응답에 `stale: true`가 붙는다.

## 백엔드에서 붙일 것

1. `backend/opportunities_api.py`에 입구 추가

```python
from opportunity import batch
from opportunity.store.factory import build_raw_store, build_secrets

def run_batch(event):
    out = batch.run_batch(event["oppBatch"], deps(), build_raw_store(), build_secrets())
    if out.get("next"):  # 남은 일은 비동기 자기 호출로 이어 간다 (면접 처리와 같은 방식)
        boto3.client("lambda").invoke(FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"], InvocationType="Event",
                                      Payload=json.dumps({"oppBatch": out["next"]}).encode())
    return {"step": out["step"], "next": bool(out.get("next"))}
```

2. `backend/app.py`의 `lambda_handler` 앞부분에 분기 추가

```python
if "oppBatch" in event:
    return part("opportunities_api").run_batch(event)
```

3. Lambda 환경변수: `OPP_SECRET_ID=team07/opp-api-keys` (공공 API 인증키를 읽는 시크릿. 이미 만들어 두었다)

4. EventBridge Scheduler 일정 두 개 (역할은 기존 `team07-scheduler-role`, 대상은 `team07-api`)

| 이름 | 식 | 시간대 | Input |
|---|---|---|---|
| `team07-opp-daily-ingest` | `cron(30 4 * * ? *)` | `Asia/Seoul` | `{"oppBatch": {"step": "ingest"}}` |
| `team07-opp-weekly-companies` | `cron(0 5 ? * MON *)` | `Asia/Seoul` | `{"oppBatch": {"step": "ingest", "sources": ["work24_gangso"]}}` |

5. Lambda 제한 시간: 온통청년 정책 약 4,000건을 받아 쓰는 걸음이 가장 길다. 로컬에서 수집 1분, 저장 2~3분쯤 걸렸다. 지금 300초면 빠듯하니 900초로 올리는 것을 권한다.

## 알아 둘 것

- 고용24 채용정보는 개인회원 키로 부를 수 없어 매일 수집 목록에서 뺐다. 기관 키가 생기면 `batch.dailySources`에 `work24`를 넣는다.
- 권한은 더 필요 없다. Lambda 역할에 Secrets Manager 읽기(`team07/*`), `team07-catalog` 쓰기, `team07-opp-data` 버킷 쓰기, S3 Vectors 쓰기, Bedrock 임베딩 호출이 이미 있다.
- 시연 중에는 수집을 돌리지 않는다. 시연 직전에는 일정을 잠깐 꺼 두거나 시연 시간을 피한다.
- 손으로 한 번 돌려 볼 때: `aws lambda invoke --function-name team07-api --invocation-type Event --cli-binary-format raw-in-base64-out --payload '{"oppBatch":{"step":"ingest","sources":["alio"]}}' /dev/null`
