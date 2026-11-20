"""store 테스트 공용 준비. moto로 `infra/setup-data.sh`와 같은 키 구조의 테이블을 만든다. 실제 AWS는 부르지 않는다."""

from datetime import datetime, timedelta

import boto3
import pytest
from moto import mock_aws

from opportunity.core import clock
from opportunity.store.dynamo import DynamoCatalog, DynamoUsers

REGION = "ap-northeast-2"
CATALOG_TABLE = "team07-catalog"
USERS_TABLE = "team07-career-mentor"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    """진짜 자격 증명이나 프로필이 섞이지 않게 한다."""
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_ENDPOINT_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


def create_table(resource, name: str) -> None:
    """setup-data.sh의 pk_sk_table과 같다: PK/SK + GSI1(ALL), TTL 속성 expiresAt."""
    resource.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                               {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}])
    resource.meta.client.update_time_to_live(
        TableName=name, TimeToLiveSpecification={"Enabled": True, "AttributeName": "expiresAt"})


class FakeClock:
    """테스트가 움직이는 시계. 저장소의 `now`로 넣는다."""

    def __init__(self, start: str = "2026-11-21T10:00:00+09:00"):
        self.current: datetime = clock.parse_as_of(start)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture
def ddb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name=REGION)
        create_table(resource, CATALOG_TABLE)
        create_table(resource, USERS_TABLE)
        yield resource


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def catalog(ddb, fake_clock):
    return DynamoCatalog(ddb, CATALOG_TABLE, now=fake_clock, sleep=lambda _: None)


@pytest.fixture
def users(ddb, fake_clock, config):
    return DynamoUsers(ddb, USERS_TABLE, retention_days=config.notifications.retention_days, now=fake_clock)


@pytest.fixture
def raw(ddb):
    """저장소를 거치지 않고 아이템을 그대로 읽는 함수: raw(table, pk, sk)."""

    def read(table: str, pk: str, sk: str) -> dict | None:
        return ddb.Table(table).get_item(Key={"PK": pk, "SK": sk}).get("Item")

    return read
