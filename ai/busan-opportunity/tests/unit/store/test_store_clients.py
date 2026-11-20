"""S3 Vectors, Scheduler, SES, S3, Secrets Manager, EMF: 클라이언트를 주입해 요청 인자만 확인한다.

Stubber는 실제 서비스 모델로 인자를 검사하므로 이름이나 형식이 틀리면 여기서 걸린다. 네트워크는 쓰지 않는다.
"""

import json
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

from opportunity.core import clock
from opportunity.models import OppError
from opportunity.store.events import EmfEvents
from opportunity.store.mailer import SesMailer, cognito_email_resolver
from opportunity.store.s3 import S3RawStore
from opportunity.store.scheduler import EventBridgeScheduler
from opportunity.store.secrets import SecretsManagerSecrets
from opportunity.store.vectors import S3VectorIndex

REGION = "ap-northeast-2"


def stubbed(service: str):
    client = boto3.client(service, region_name=REGION)
    return client, Stubber(client)


# ---------------------------------------------------------------- S3 Vectors
@pytest.fixture
def vec():
    client, stub = stubbed("s3vectors")
    with stub:
        yield S3VectorIndex(client, "team07-opp-vectors", "postings-v1"), stub


def test_vector_query_converts_distance_to_similarity(vec):
    index, stub = vec
    stub.add_response("query_vectors", {"distanceMetric": "cosine", "vectors": [
        {"key": "wk24-B", "distance": 0.30, "metadata": {"isBusan": True, "sido": "26", "title": "B"}},
        {"key": "wk24-A", "distance": 0.10, "metadata": {"isBusan": False}},
        {"key": "wk24-C", "distance": 0.30},
        {"key": "wk24-FAR", "distance": 1.4},  # 반대 방향이어도 유사도는 0 아래로 내려가지 않는다
        {"key": "wk24-SAME", "distance": -0.0000001},
    ]}, expected_params={
        "vectorBucketName": "team07-opp-vectors", "indexName": "postings-v1", "topK": 30,
        "queryVector": {"float32": [1.0, 0.0, 0.5]}, "returnMetadata": True, "returnDistance": True,
        "filter": {"$and": [{"isBusan": {"$eq": True}}, {"active": {"$eq": True}}, {"deadline": {"$gte": 20261121}}]}})
    flt = {"$and": [{"isBusan": {"$eq": True}}, {"active": {"$eq": True}}, {"deadline": {"$gte": 20261121}}]}
    hits = index.query([1, 0, 0.5], top_k=30, filter=flt)
    assert [h.key for h in hits] == ["wk24-SAME", "wk24-A", "wk24-B", "wk24-C", "wk24-FAR"]
    assert [round(h.similarity, 2) for h in hits] == [1.0, 0.9, 0.7, 0.7, 0.0]  # 같은 유사도는 키순
    assert hits[2].metadata == {"isBusan": True, "sido": "26", "title": "B"} and hits[3].metadata == {}
    stub.assert_no_pending_responses()


def test_vector_query_without_filter_and_top_k_cap(vec):
    index, stub = vec
    stub.add_response("query_vectors", {"distanceMetric": "cosine", "vectors": []}, expected_params={
        "vectorBucketName": "team07-opp-vectors", "indexName": "postings-v1", "topK": 100,
        "queryVector": {"float32": [0.25]}, "returnMetadata": True, "returnDistance": True})
    assert index.query([0.25], top_k=500) == []  # 질의 한 번에 100개까지. 필터가 없으면 filter를 보내지 않는다
    stub.assert_no_pending_responses()


def test_vector_put_get_delete(vec):
    index, stub = vec
    meta = {"isBusan": True, "sido": "26", "jobMajor": "D", "active": True, "deadline": 20261130, "title": "t",
            "dropped": None}
    stub.add_response("put_vectors", {}, expected_params={
        "vectorBucketName": "team07-opp-vectors", "indexName": "postings-v1",
        "vectors": [{"key": "wk24-1", "data": {"float32": [0.5, 0.25]},
                     "metadata": {k: v for k, v in meta.items() if v is not None}}]})
    index.put("wk24-1", [0.5, 0.25], meta)
    stub.add_response("get_vectors", {"vectors": [{"key": "wk24-1", "data": {"float32": [0.5, 0.25]}}]},
                      expected_params={"vectorBucketName": "team07-opp-vectors", "indexName": "postings-v1",
                                       "keys": ["wk24-1"], "returnData": True})
    assert index.get("wk24-1") == [0.5, 0.25]
    stub.add_response("get_vectors", {"vectors": []}, expected_params={
        "vectorBucketName": "team07-opp-vectors", "indexName": "postings-v1", "keys": ["nope"], "returnData": True})
    assert index.get("nope") is None
    stub.add_response("delete_vectors", {}, expected_params={
        "vectorBucketName": "team07-opp-vectors", "indexName": "postings-v1", "keys": ["wk24-1"]})
    index.delete("wk24-1")
    stub.assert_no_pending_responses()


def test_vector_errors_become_aws_service_error(vec):
    index, stub = vec
    stub.add_client_error("query_vectors", service_error_code="AccessDeniedException",
                          service_message="arn:aws:... denied")
    with pytest.raises(OppError) as caught:
        index.query([1.0], top_k=5)
    assert caught.value.code == "AWS_SERVICE_ERROR" and caught.value.details == {"service": "s3vectors"}
    assert "arn" not in caught.value.message


def test_vector_names_come_from_env(monkeypatch):
    monkeypatch.setenv("OPP_VECTOR_BUCKET", "b")
    monkeypatch.setenv("OPP_VECTOR_INDEX", "i")
    index = S3VectorIndex(boto3.client("s3vectors", region_name=REGION))
    assert (index.bucket, index.index) == ("b", "i")
    monkeypatch.delenv("OPP_VECTOR_INDEX")
    with pytest.raises(Exception, match="OPP_VECTOR_INDEX"):
        S3VectorIndex(boto3.client("s3vectors", region_name=REGION))


# ---------------------------------------------------------------- EventBridge Scheduler
ARN = "arn:aws:lambda:ap-northeast-2:123456789012:function:team07-api"
ROLE = "arn:aws:iam::123456789012:role/team07-scheduler-role"


@pytest.fixture
def sched():
    client, stub = stubbed("scheduler")
    with stub:
        yield EventBridgeScheduler(client, target_arn=ARN, role_arn=ROLE), stub


def test_scheduler_create_once_request(sched):
    scheduler, stub = sched
    payload = {"type": "TARGET_DEADLINE", "jobPostingId": "wk24-1", "메모": "한글"}
    stub.add_response("create_schedule", {"ScheduleArn": "arn:aws:scheduler:x"}, expected_params={
        "Name": "opp-abc", "ScheduleExpression": "at(2026-11-23T09:00:00)",
        "ScheduleExpressionTimezone": "Asia/Seoul", "ActionAfterCompletion": "DELETE",
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": {"Arn": ARN, "RoleArn": ROLE,
                   "Input": json.dumps({"oppSchedule": payload}, ensure_ascii=False, separators=(",", ":"))}})
    assert scheduler.create_once("opp-abc", clock.parse_as_of("2026-11-23T09:00:00+09:00"), payload) is True
    stub.assert_no_pending_responses()


def test_scheduler_converts_other_zones_to_seoul_time(sched):
    scheduler, stub = sched
    utc = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)  # 서울 09:30
    stub.add_response("create_schedule", {"ScheduleArn": "a"}, expected_params={
        "Name": "n", "ScheduleExpression": "at(2026-11-23T09:30:00)", "ScheduleExpressionTimezone": "Asia/Seoul",
        "ActionAfterCompletion": "DELETE", "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": {"Arn": ARN, "RoleArn": ROLE, "Input": "{\"oppSchedule\":{}}"}})
    assert scheduler.create_once("n", utc, {}) is True


def test_scheduler_duplicate_name_is_false_not_error(sched):
    scheduler, stub = sched
    stub.add_client_error("create_schedule", service_error_code="ConflictException", http_status_code=409)
    assert scheduler.create_once("opp-abc", clock.parse_as_of("2026-11-23T09:00:00+09:00"), {}) is False


def test_scheduler_other_errors_are_aws_errors(sched):
    scheduler, stub = sched
    stub.add_client_error("create_schedule", service_error_code="ValidationException")
    with pytest.raises(OppError) as caught:
        scheduler.create_once("n", clock.parse_as_of("2020-01-01"), {})
    assert caught.value.code == "AWS_SERVICE_ERROR" and caught.value.details == {"service": "scheduler"}


def test_scheduler_delete_ignores_missing_schedule(sched):
    scheduler, stub = sched
    stub.add_response("delete_schedule", {}, expected_params={"Name": "opp-abc"})
    scheduler.delete("opp-abc")
    stub.add_client_error("delete_schedule", service_error_code="ResourceNotFoundException", http_status_code=404)
    scheduler.delete("opp-gone")
    stub.add_client_error("delete_schedule", service_error_code="InternalServerException", http_status_code=500)
    with pytest.raises(OppError):
        scheduler.delete("opp-abc")


def test_scheduler_group_name_is_passed_when_given():
    client, stub = stubbed("scheduler")
    scheduler = EventBridgeScheduler(client, target_arn=ARN, role_arn=ROLE, group_name="team07-opp")
    with stub:
        stub.add_response("create_schedule", {"ScheduleArn": "a"}, expected_params={
            "Name": "n", "GroupName": "team07-opp", "ScheduleExpression": "at(2026-11-23T09:00:00)",
            "ScheduleExpressionTimezone": "Asia/Seoul", "ActionAfterCompletion": "DELETE",
            "FlexibleTimeWindow": {"Mode": "OFF"}, "Target": {"Arn": ARN, "RoleArn": ROLE, "Input": "{\"oppSchedule\":{}}"}})
        scheduler.create_once("n", clock.parse_as_of("2026-11-23T09:00:00+09:00"), {})
        stub.add_response("delete_schedule", {}, expected_params={"Name": "n", "GroupName": "team07-opp"})
        scheduler.delete("n")


# ---------------------------------------------------------------- SES
def test_mailer_sends_to_resolved_address():
    client, stub = stubbed("sesv2")
    mailer = SesMailer(client, from_address="noreply@example.com", resolve_email={"u1": "a@example.com"}.get)
    with stub:
        stub.add_response("send_email", {"MessageId": "m"}, expected_params={
            "FromEmailAddress": "noreply@example.com", "Destination": {"ToAddresses": ["a@example.com"]},
            "Content": {"Simple": {"Subject": {"Data": "마감 D-3", "Charset": "UTF-8"},
                                   "Body": {"Text": {"Data": "본문", "Charset": "UTF-8"}}}}})
        assert mailer.send("u1", "마감 D-3", "본문") is True
        assert mailer.send("u2", "s", "b") is False  # 주소를 못 찾으면 보내지 않는다
        stub.assert_no_pending_responses()


def test_mailer_sandbox_rejection_is_false_and_other_errors_raise():
    client, stub = stubbed("sesv2")
    mailer = SesMailer(client, from_address="n@example.com", resolve_email=lambda u: "a@example.com",
                       configuration_set="team07")
    with stub:
        stub.add_client_error("send_email", service_error_code="MessageRejected")
        assert mailer.send("u1", "s", "b") is False
        stub.add_client_error("send_email", service_error_code="AccountSuspendedException")
        with pytest.raises(OppError) as caught:
            mailer.send("u1", "s", "b")
        assert caught.value.details == {"service": "ses"} and "a@example.com" not in caught.value.message


def test_cognito_email_resolver():
    client, stub = stubbed("cognito-idp")
    resolve = cognito_email_resolver(client, "ap-northeast-2_abc")
    with stub:
        stub.add_response("admin_get_user", {"Username": "u1", "UserAttributes": [
            {"Name": "sub", "Value": "u1"}, {"Name": "email", "Value": "a@example.com"}]},
            expected_params={"UserPoolId": "ap-northeast-2_abc", "Username": "u1"})
        assert resolve("u1") == "a@example.com"
        stub.add_response("admin_get_user", {"Username": "u2", "UserAttributes": [{"Name": "sub", "Value": "u2"}]},
                          expected_params={"UserPoolId": "ap-northeast-2_abc", "Username": "u2"})
        assert resolve("u2") is None
        stub.add_client_error("admin_get_user", service_error_code="UserNotFoundException")
        assert resolve("u3") is None
        stub.add_client_error("admin_get_user", service_error_code="InternalErrorException")
        with pytest.raises(OppError):
            resolve("u4")


# ---------------------------------------------------------------- S3
def test_s3_raw_store_roundtrip():
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket="team07-opp-data-test", CreateBucketConfiguration={"LocationConstraint": REGION})
        store = S3RawStore(client, "team07-opp-data-test")
        store.put("raw/work24/2026-11-21/list.json", b'{"a":1}')
        store.put("raw/work24/2026-11-21/detail.json", "한글".encode())
        store.put("raw/alio/2026-11-21/list.xml", b"<a/>", "application/xml")
        assert store.get("raw/work24/2026-11-21/list.json") == b'{"a":1}'
        assert store.get("raw/work24/2026-11-21/detail.json").decode() == "한글"
        assert store.get("raw/work24/none.json") is None
        assert store.list("raw/work24/") == ["raw/work24/2026-11-21/detail.json", "raw/work24/2026-11-21/list.json"]
        assert store.list("nothing/") == []
        assert client.head_object(Bucket="team07-opp-data-test", Key="raw/alio/2026-11-21/list.xml")["ContentType"] \
            == "application/xml"
        for i in range(1005):  # list_objects_v2는 1000개씩 끊어 준다
            store.put(f"runs/{i:04d}.json", b"{}")
        assert len(store.list("runs/")) == 1005


def test_s3_raw_store_errors_become_aws_service_error():
    with mock_aws():
        store = S3RawStore(boto3.client("s3", region_name=REGION), "bucket-that-does-not-exist")
        with pytest.raises(OppError) as caught:
            store.get("raw/x.json")
        assert caught.value.details == {"service": "s3"}
        with pytest.raises(OppError):
            store.put("raw/x.json", b"{}")


def test_s3_bucket_comes_from_env(monkeypatch):
    monkeypatch.setenv("OPP_DATA_BUCKET", "team07-opp-data-123")
    assert S3RawStore(boto3.client("s3", region_name=REGION)).bucket == "team07-opp-data-123"


# ---------------------------------------------------------------- Secrets Manager
def test_secrets_are_cached_for_five_minutes():
    client, stub = stubbed("secretsmanager")
    now = [1000.0]
    secrets = SecretsManagerSecrets(client, monotonic=lambda: now[0])
    with stub:
        stub.add_response("get_secret_value", {"SecretString": "key-1"}, expected_params={"SecretId": "team07/work24"})
        assert secrets.get("team07/work24") == "key-1"
        now[0] += 299
        assert secrets.get("team07/work24") == "key-1"  # 캐시에서. 호출을 더 등록하지 않았으니 부르면 실패한다
        now[0] += 2
        stub.add_response("get_secret_value", {"SecretString": "key-2"}, expected_params={"SecretId": "team07/work24"})
        assert secrets.get("team07/work24") == "key-2"
        stub.assert_no_pending_responses()


def test_secret_errors_do_not_leak_names_and_are_not_cached():
    client, stub = stubbed("secretsmanager")
    secrets = SecretsManagerSecrets(client)
    with stub:
        stub.add_client_error("get_secret_value", service_error_code="ResourceNotFoundException",
                              service_message="Secrets Manager can't find the specified secret team07/work24")
        with pytest.raises(OppError) as caught:
            secrets.get("team07/work24")
        assert "team07/work24" not in caught.value.message and caught.value.details == {"service": "secretsmanager"}
        stub.add_response("get_secret_value", {"SecretString": "ok"}, expected_params={"SecretId": "team07/work24"})
        assert secrets.get("team07/work24") == "ok"


# ---------------------------------------------------------------- EMF
def test_emf_line_shape_and_privacy():
    lines = []
    when = datetime(2026, 11, 21, 10, 0, tzinfo=timezone(timedelta(hours=9)))
    events = EmfEvents(out=lines.append, now=lambda: when)
    events.emit("feed_viewed", sort="BUSAN_FIRST", isBusan=True, count=3, userId="u-secret-1", user_id="u-secret-2",
                note="x" * 200, resume_text="이력서 원문", nested={"a": 1}, email="a@example.com")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert "\n" not in lines[0] and "u-secret" not in lines[0] and "이력서" not in lines[0]
    assert "a@example.com" not in lines[0] and "xxxx" not in lines[0]
    metrics = record["_aws"]["CloudWatchMetrics"][0]
    assert metrics["Namespace"] == "Team07/Opportunity"
    assert metrics["Metrics"] == [{"Name": "EventCount", "Unit": "Count"}]
    assert metrics["Dimensions"] == [["event", "sort", "isBusan", "count"]]
    assert record["_aws"]["Timestamp"] == int(when.timestamp() * 1000)
    assert (record["event"], record["EventCount"]) == ("feed_viewed", 1)
    assert (record["sort"], record["isBusan"], record["count"]) == ("BUSAN_FIRST", "true", "3")


def test_emf_ignores_reserved_dimension_names():
    lines = []
    events = EmfEvents(out=lines.append)
    events.emit("saved", EventCount=99, _aws="x")
    record = json.loads(lines[0])
    assert record["event"] == "saved" and record["EventCount"] == 1
    assert record["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [["event"]]


def test_emf_default_output_is_one_stdout_line(capsys):
    EmfEvents().emit("alert_created", policy="seed-busan-joy-double")
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and json.loads(out)["policy"] == "seed-busan-joy-double"


def test_vector_filter_wraps_multiple_conditions_in_and():
    """core가 만드는 평평한 필터를 S3 Vectors가 받는 `$and` 형식으로 바꾼다 (서울 리전에서 평평한 필터는 Invalid filter)."""
    from opportunity.core.ranking import active_filter
    from opportunity.store.vectors import to_s3_filter

    flat = {"isBusan": True, "active": True, "deadline": {"$gte": 20261121}}
    assert to_s3_filter(flat) == {"$and": [{"isBusan": True}, {"active": True}, {"deadline": {"$gte": 20261121}}]}
    assert to_s3_filter({"isBusan": True}) == {"isBusan": True}  # 조건 하나는 그대로
    already = {"$and": [{"isBusan": {"$eq": True}}]}
    assert to_s3_filter(already) is already  # 이미 묶인 필터는 그대로
    from datetime import datetime, timedelta, timezone
    built = to_s3_filter(active_filter(datetime(2026, 11, 21, 10, tzinfo=timezone(timedelta(hours=9))), isBusan=True))
    assert set(built) == {"$and"} and len(built["$and"]) == 3  # core 필터가 실제로 S3 형식이 된다


def test_json_secret_returns_named_field_and_hides_missing_name():
    class Client:
        calls = 0

        def get_secret_value(self, SecretId):
            Client.calls += 1
            assert SecretId == "team07/opp-api-keys"
            return {"SecretString": '{"YOUTHCENTER_API_KEY": "v1", "WORK24_GANGSO_KEY": "v2"}'}

    from opportunity.models.errors import OppError
    from opportunity.store.secrets import SecretsManagerSecrets

    secrets = SecretsManagerSecrets(Client(), json_secret_id="team07/opp-api-keys")
    assert secrets.get("YOUTHCENTER_API_KEY") == "v1" and secrets.get("WORK24_GANGSO_KEY") == "v2"
    assert Client.calls == 1  # 시크릿은 한 번만 읽고 5분 캐시한다
    try:
        secrets.get("NOPE")
    except OppError as e:
        assert e.code == "AWS_SERVICE_ERROR" and "NOPE" not in e.message
    else:
        raise AssertionError("없는 이름은 오류여야 한다")
