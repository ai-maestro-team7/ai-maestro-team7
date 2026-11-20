"""build_aws_deps: 환경변수를 읽어 AWS 구현으로 Deps를 만든다. 호출은 하지 않고 조립만 확인한다.

`opportunity.enrich.bedrock`은 다른 워크트리 몫이라 가짜 모듈로 대신한다.
"""

import sys
import types

import pytest

from opportunity.config import ConfigError
from opportunity.store import factory
from opportunity.store.dynamo import DynamoCatalog, DynamoUsers
from opportunity.store.events import EmfEvents
from opportunity.store.factory import build_aws_deps, build_raw_store, build_secrets
from opportunity.store.mailer import SesMailer
from opportunity.store.memory import MemoryWorkspaces
from opportunity.store.s3 import S3RawStore
from opportunity.store.scheduler import EventBridgeScheduler
from opportunity.store.secrets import SecretsManagerSecrets
from opportunity.store.vectors import S3VectorIndex

ENV = {
    "TABLE_CATALOG": "team07-catalog", "TABLE_CAREER_MENTOR": "team07-career-mentor",
    "OPP_VECTOR_BUCKET": "team07-opp-vectors", "OPP_VECTOR_INDEX": "postings-v1",
    "MODEL_ID": "global.test-llm", "EMBEDDING_MODEL_ID": "test.embed",
    "SCHEDULER_TARGET_ARN": "arn:aws:lambda:ap-northeast-2:123456789012:function:team07-api",
    "SCHEDULER_ROLE_ARN": "arn:aws:iam::123456789012:role/team07-scheduler",
    "OPP_DATA_BUCKET": "team07-opp-data-123456789012",
}


class FakeLlm:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeEmbedder:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    factory._client.cache_clear()
    factory._dynamodb.cache_clear()
    for name in ("SES_FROM_ADDRESS", "COGNITO_USER_POOL_ID", "SCHEDULER_GROUP", *ENV):
        monkeypatch.delenv(name, raising=False)
    fake = types.ModuleType("opportunity.enrich.bedrock")
    fake.BedrockLlm, fake.BedrockEmbedder = FakeLlm, FakeEmbedder
    monkeypatch.setitem(sys.modules, "opportunity.enrich.bedrock", fake)
    yield
    factory._client.cache_clear()
    factory._dynamodb.cache_clear()


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


def build(config):
    return build_aws_deps(eligibility=lambda profile, rules: {}, workspaces=MemoryWorkspaces(), config=config)


def test_builds_every_part_from_env(env, config):
    deps = build(config)
    assert isinstance(deps.catalog, DynamoCatalog) and deps.catalog.t.name == "team07-catalog"
    assert isinstance(deps.users, DynamoUsers) and deps.users.t.name == "team07-career-mentor"
    assert deps.users.retention_days == config.notifications.retention_days
    assert isinstance(deps.vectors, S3VectorIndex) and (deps.vectors.bucket, deps.vectors.index) == (
        "team07-opp-vectors", "postings-v1")
    assert isinstance(deps.scheduler, EventBridgeScheduler) and deps.scheduler.group_name is None
    assert deps.scheduler.target_arn == ENV["SCHEDULER_TARGET_ARN"]
    assert deps.scheduler.role_arn == ENV["SCHEDULER_ROLE_ARN"]
    assert isinstance(deps.events, EmfEvents)
    assert isinstance(deps.llm, FakeLlm) and deps.llm.kwargs["model_id"] == "global.test-llm"
    assert isinstance(deps.embedder, FakeEmbedder)
    assert deps.embedder.kwargs["model_id"] == "test.embed" and deps.embedder.kwargs["config"] is config
    assert deps.llm.kwargs["client"] is deps.embedder.kwargs["client"]  # bedrock-runtime 클라이언트는 하나만
    assert deps.mailer is None  # 메일 설정이 없으면 알림함만
    assert deps.region_stats.rent == {} and deps.region_stats.commute == {}
    assert deps.config is config and callable(deps.eligibility) and isinstance(deps.workspaces, MemoryWorkspaces)


def test_clients_are_created_once(env, config):
    first, second = build(config), build(config)
    assert first.catalog.resource is second.catalog.resource is first.users.resource
    assert first.vectors.client is second.vectors.client
    assert first.scheduler.client is second.scheduler.client
    assert first.llm.kwargs["client"] is second.llm.kwargs["client"]


def test_uses_region_from_config(env, config):
    deps = build(config)
    assert deps.vectors.client.meta.region_name == config.region == "ap-northeast-2"
    assert deps.scheduler.client.meta.region_name == config.region


def test_mailer_needs_both_ses_and_cognito_settings(env, config, monkeypatch):
    monkeypatch.setenv("SES_FROM_ADDRESS", "noreply@example.com")
    assert build(config).mailer is None
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "ap-northeast-2_abc")
    mailer = build(config).mailer
    assert isinstance(mailer, SesMailer) and mailer.from_address == "noreply@example.com"
    assert callable(mailer.resolve_email)


def test_scheduler_group_is_optional(env, config, monkeypatch):
    monkeypatch.setenv("SCHEDULER_GROUP", "team07-opp")
    assert build(config).scheduler.group_name == "team07-opp"


@pytest.mark.parametrize("missing", sorted(set(ENV) - {"OPP_DATA_BUCKET"}))
def test_missing_env_names_the_variable(env, config, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(ConfigError, match=missing):
        build(config)


def test_bedrock_import_failure_is_not_hidden(env, config, monkeypatch):
    monkeypatch.setitem(sys.modules, "opportunity.enrich.bedrock", None)  # import 실패를 흉내 낸다
    with pytest.raises(ImportError):
        build(config)


def test_batch_helpers(env, config):
    raw = build_raw_store(config)
    assert isinstance(raw, S3RawStore) and raw.bucket == ENV["OPP_DATA_BUCKET"]
    assert isinstance(build_secrets(config), SecretsManagerSecrets)
