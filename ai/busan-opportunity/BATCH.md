# 정기 수집 연결과 운영

근거: B 개발계획서 §2.1(매일 04:30 KST), §3.1(강소기업 주 1회), §9(수동 수집 후 정기 일정 연결), 이슈 #83.

## 연결된 코드

- backend/app.py가 내부 oppBatch 이벤트를 opportunities_api.run_batch로 보낸다.
- opportunity.batch.run_batch가 출처 하나 또는 보강 100건을 처리하고 next를 반환한다. 백엔드는 남은 이벤트를 같은 Lambda에 InvocationType=Event로 호출한다.
- 수집 시작의 asOf를 다음 단계에도 전달한다. 한 출처가 실패해도 다른 출처와 보강을 이어 간다.
- 매일·매주 출처 목록은 opportunity_config.json의 batch.dailySources, batch.weeklySources에서 읽는다.
- B의 설정·환경변수·역할은 기존 단일 Lambda team07-api를 사용한다. Step Functions나 별도 Lambda를 만들지 않는다.
- infra/setup_opp_batch.py는 AWS CLI로 기존 환경변수를 보존하면서 OPP_SECRET_ID(기본 team07/opp-api-keys)와 제한 시간 900초를 설정하고, 다음 두 일정을 생성하거나 갱신한다.

| 일정 | 실행 시간(Asia/Seoul) | 식 | Input |
|---|---|---|---|
| team07-opp-daily-ingest | 매일 04:30 | cron(30 4 * * ? *) | {"oppBatch":{"step":"ingest"}} |
| team07-opp-weekly-companies | 월요일 05:00 | cron(0 5 ? * MON *) | {"oppBatch":{"step":"ingest","frequency":"weekly"}} |

일정은 위 스크립트를 AWS에 적용해야 활성화된다. 소스 병합만으로 일정이 생기지는 않는다.

## 적용 순서

AWS에 로그인한 배포 담당이 저장소 루트에서 실행한다. 먼저 최신 코드를 배포한 뒤 일정을 활성화해야 한다.

~~~bash
aws login
# 기존 Lambda 역할에 catalog GSI Query 권한 반영. Scheduler 역할은 team07-api 호출만 허용
bash infra/setup-role.sh
# 최신 main의 전체 배포 묶음을 사용 (일부 파일만 Lambda에 올리지 않는다)
bash infra/deploy.sh
# 기존 Cognito·A·B 환경변수를 보존하며 설정 및 일정 적용
python3 infra/setup_opp_batch.py
~~~

setup_opp_batch.py는 로그인·권한 오류를 "자원이 없음"으로 처리하지 않는다. 기존 설정의 RevisionId로 동시 변경을 감지하며, 필수 환경변수·시크릿·일정 역할을 확인한 뒤 적용한다. 환경변수 값과 인증키는 출력하지 않는다.

일정 역할은 기존 team07-scheduler-role, 대상은 team07-api다. 적용 계정에는 Lambda 설정 갱신, Scheduler Get/Create/Update, 지정 역할의 iam:PassRole, 시크릿 메타데이터 조회 권한이 필요하다. 코드만 배포하는 GitHub Actions 역할의 권한은 확장하지 않는다.

## 확인

~~~bash
aws scheduler get-schedule --name team07-opp-daily-ingest --region ap-northeast-2 \
  --query '{state:State,expression:ScheduleExpression,timezone:ScheduleExpressionTimezone}' --output json
aws scheduler get-schedule --name team07-opp-weekly-companies --region ap-northeast-2 \
  --query '{state:State,expression:ScheduleExpression,timezone:ScheduleExpressionTimezone}' --output json
aws lambda get-function-configuration --function-name team07-api --region ap-northeast-2 \
  --query '{timeout:Timeout,status:LastUpdateStatus}' --output json
~~~

첫 실행 후에는 B 데이터 버킷의 runs/{한국 날짜 YYYY-MM-DD}.json, 출처별 raw/ 객체와 CloudWatch에서 실패를 확인한다. 피드 응답의 dataAsOf가 새벽 수집 시각이고 stale=false인지 확인한다. 기준 시각이 올라가도 일부 출처가 실패했을 수 있으므로 출처별 결과도 확인한다. 현재 일별 runs/ 파일은 각 수집 단계가 같은 키를 덮어쓰므로 전체 출처 이력은 CloudWatch도 함께 본다.

수동 검증은 시연 외 시간에 잡알리오 한 출처로만 실행할 수 있다. 비동기 호출 접수(202)와 수집 완료는 별개다.

~~~bash
aws lambda invoke --function-name team07-api --region ap-northeast-2 \
  --invocation-type Event --cli-binary-format raw-in-base64-out \
  --payload '{"oppBatch":{"step":"ingest","sources":["alio"]}}' /tmp/team07-opp-invoke.json
~~~

## 시연 중 중지·재개

~~~bash
python3 infra/setup_opp_batch.py --disabled
# 시연 뒤 재개
python3 infra/setup_opp_batch.py
~~~

두 정기 일정만 변경한다. 사용자별 마감·정책 일회성 알림은 유지한다. 이미 실행 중인 Lambda 작업은 일정 중지로 취소되지 않으므로 시연 전에 수집 종료도 확인한다.

## 수집 범위와 남은 항목

- 매일: 잡알리오(alio), 지방공공기관(klid), 해외취업(worldjob), 온통청년(youthcenter).
- 매주: 고용24 강소기업(work24_gangso).
- 고용24 일반 채용정보: 개인회원 키로 호출할 수 없어 제외. 기관 키와 실제 응답 매핑 검증 후 batch.dailySources에 work24를 추가한다.
- 월별 직종·지역 코드, 월세 실거래, 주별 시험 일정, 부산 청년 프로그램 및 A 기준정보·훈련과정의 정기 갱신은 이 배치에 연결돼 있지 않다. 별도 수집기·접근 권한·실제 응답 확인 후 연결한다.
- 바뀐 공고만 보강하며 원문 스냅샷은 삭제하지 않는다. 36시간 넘게 수집이 멈추면 API에 stale=true가 붙는다.
- 정책 검색용 KB 재색인은 이 배치에 포함되지 않는다.

## AWS 없이 검증

~~~bash
cd backend
uv run --no-project --with boto3 --with pydantic --with aws-lambda-powertools \
  python -m unittest test_opp_batch
cd ..
python3 -m unittest discover -s infra -p test_setup_opp_batch.py
~~~
