"""Bedrock Knowledge Base 검색 어댑터와 factory의 retriever 조립. 네트워크는 쓰지 않는다.

Stubber는 실제 서비스 모델로 요청 인자와 응답 모양을 검사한다.
"""

import json
import sys
import types

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

from opportunity.models import OppError
from opportunity.store import factory
from opportunity.store.kb import BedrockKbRetriever
from opportunity.store.memory import MemoryWorkspaces

REGION = "ap-northeast-2"
KB_ID = "KBTEST1234"
FILTER = {"andAll": [
    {"orAll": [{"equals": {"key": "regionKey", "value": "26"}}, {"equals": {"key": "regionKey", "value": "00"}}]},
    {"notEquals": {"key": "scope", "value": "SIGUNGU"}},
]}


@pytest.fixture
def kb():
    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    stub = Stubber(client)
    with stub:
        yield BedrockKbRetriever(client, knowledge_base_id=KB_ID), stub


def row(policy_id, text, score, uri=None):
    result = {"content": {"text": text}, "score": score,
              "metadata": {"x-amz-bedrock-kb-source-uri": uri or f"s3://bucket/kb/policies/{policy_id}.md"}}
    if policy_id:
        result["metadata"].update(policyId=policy_id, regionKey="26", applyEnd=20261231)
    if uri is not False:
        result["location"] = {"type": "S3", "s3Location": {"uri": uri or f"s3://bucket/kb/policies/{policy_id}.md"}}
    return result


def test_retrieve_sends_filter_and_converts_results(kb):
    retriever, stub = kb
    stub.add_response("retrieve", {"retrievalResults": [
        row("ythc-B002", "# 부산 청년 월세 지원", 0.71),
        row(None, "다른 문서", 0.5, uri="s3://bucket/other.md"),  # policyId가 없으면 버린다
        row("ythc-N001", "# 전국 구직활동 지원", 0.42, uri=False),
    ]}, expected_params={
        "knowledgeBaseId": KB_ID, "retrievalQuery": {"text": "월세 지원"},
        "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 20, "filter": FILTER}},
    })
    docs = retriever.retrieve("월세 지원", top_k=20, filter=FILTER)
    assert [(d.doc_id, d.text, d.score) for d in docs] == [("ythc-B002", "# 부산 청년 월세 지원", 0.71),
                                                          ("ythc-N001", "# 전국 구직활동 지원", 0.42)]
    assert docs[0].source_uri == "s3://bucket/kb/policies/ythc-B002.md" and docs[1].source_uri is None
    assert docs[0].metadata["regionKey"] == "26"
    stub.assert_no_pending_responses()


def test_retrieve_without_filter_has_no_filter_key(kb):
    retriever, stub = kb
    stub.add_response("retrieve", {"retrievalResults": []}, expected_params={
        "knowledgeBaseId": KB_ID, "retrievalQuery": {"text": "청년 정책"},
        "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 100}},
    })
    assert retriever.retrieve("청년 정책", top_k=500) == []  # 상한 100으로 줄인다
    stub.assert_no_pending_responses()


def test_retrieve_error_becomes_aws_service_error(kb):
    retriever, stub = kb
    stub.add_client_error("retrieve", service_error_code="ThrottlingException", http_status_code=429)
    with pytest.raises(OppError) as e:
        retriever.retrieve("월세", top_k=5)
    assert e.value.code == "AWS_SERVICE_ERROR" and e.value.details == {"service": "bedrock-kb"}
    assert e.value.retryable is True


# ---------------------------------------------------------------- factory
ENV = {
    "TABLE_CATALOG": "team07-catalog", "TABLE_CAREER_MENTOR": "team07-career-mentor",
    "OPP_VECTOR_BUCKET": "team07-opp-vectors", "OPP_VECTOR_INDEX": "postings-v1",
    "MODEL_ID": "global.test-llm", "EMBEDDING_MODEL_ID": "test.embed",
    "SCHEDULER_TARGET_ARN": "arn:aws:lambda:ap-northeast-2:123456789012:function:team07-api",
    "SCHEDULER_ROLE_ARN": "arn:aws:iam::123456789012:role/team07-scheduler",
}
BUCKET = "team07-opp-data-123456789012"


class _Fake:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def env(monkeypatch):
    factory._client.cache_clear()
    factory._dynamodb.cache_clear()
    for name in ("OPP_KB_ID", "OPP_DATA_BUCKET", "SES_FROM_ADDRESS", "COGNITO_USER_POOL_ID"):
        monkeypatch.delenv(name, raising=False)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    fake = types.ModuleType("opportunity.enrich.bedrock")
    fake.BedrockLlm = fake.BedrockEmbedder = _Fake
    monkeypatch.setitem(sys.modules, "opportunity.enrich.bedrock", fake)
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        yield monkeypatch
    factory._client.cache_clear()
    factory._dynamodb.cache_clear()


def build(config):
    return factory.build_aws_deps(eligibility=lambda p, r: {}, workspaces=MemoryWorkspaces(), config=config)


def put_seed(body: bytes):
    boto3.client("s3", region_name=REGION).put_object(Bucket=BUCKET, Key=factory.KB_SEED_KEY, Body=body)


def test_kb_id_from_env_wins(env, config):
    env.setenv("OPP_KB_ID", KB_ID)
    env.setenv("OPP_DATA_BUCKET", BUCKET)
    put_seed(json.dumps({"knowledgeBaseId": "KBFROMS3"}).encode())
    retriever = build(config).retriever
    assert isinstance(retriever, BedrockKbRetriever) and retriever.knowledge_base_id == KB_ID
    assert retriever.client.meta.region_name == config.region


def test_kb_id_from_s3_seed(env, config):
    env.setenv("OPP_DATA_BUCKET", BUCKET)
    put_seed(json.dumps({"knowledgeBaseId": "KBFROMS3"}).encode())
    assert build(config).retriever.knowledge_base_id == "KBFROMS3"


@pytest.mark.parametrize("seed", [None, b"not json", b"{}", json.dumps({"knowledgeBaseId": "  "}).encode(),
                                  json.dumps({"knowledgeBaseId": 3}).encode()])
def test_missing_or_broken_seed_turns_ask_off(env, config, seed):
    env.setenv("OPP_DATA_BUCKET", BUCKET)
    if seed is not None:
        put_seed(seed)
    deps = build(config)
    assert deps.retriever is None and deps.catalog is not None  # 나머지는 정상으로 만든다


def test_no_bucket_and_no_env_turns_ask_off(env, config):
    assert build(config).retriever is None
