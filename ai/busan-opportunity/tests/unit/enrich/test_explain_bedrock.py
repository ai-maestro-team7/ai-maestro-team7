"""설명 문장 캐시와 Bedrock 요청 모양."""

import io
import json

import pytest
from unit.enrich import factories as f

from opportunity.config import ConfigError
from opportunity.core import posting_detail
from opportunity.enrich import explain
from opportunity.enrich.bedrock import BedrockEmbedder, BedrockLlm
from opportunity.models.errors import OppError
from opportunity.seeds import demo_world as w
from opportunity.store.memory import ScriptedLlm

FACTS = ["희망 직무 데이터 분석과 직종이 같아요", "연 3,400~3,800만 원", "마감 D-14"]
GOOD = f.explain_reply("희망하신 데이터 분석과 같은 직종이에요.", "급여는 연 3,400~3,800만 원이고 마감 D-14예요.")


@pytest.fixture
def facts(monkeypatch):
    """공고 상세는 다른 워크트리 몫이라 facts만 돌려주는 대역을 쓴다."""
    holder = {"facts": list(FACTS)}

    class Detail:
        def __init__(self):
            self.facts = list(holder["facts"])

    monkeypatch.setattr(posting_detail, "get_posting", lambda deps, user_id, pid, *, as_of=None: Detail())
    return holder


def test_explain_success_and_cache(deps, as_of, facts):
    deps.llm = ScriptedLlm([GOOD])
    first = explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=as_of)
    assert first.cached is False and len(first.sentences) == deps.config.explanation.sentences
    assert first.facts == FACTS
    second = explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=as_of)
    assert second.cached is True and second.sentences == first.sentences and len(deps.llm.calls) == 1
    system, user = deps.llm.calls[0]
    assert "<facts>" in user and all(fact in user for fact in FACTS)
    assert f"{deps.config.explanation.sentences}문장" in system


def test_explain_cache_rebuilt_when_facts_change(deps, as_of, facts):
    deps.llm = ScriptedLlm([GOOD, f.explain_reply("데이터 분석 직종이에요.", "마감 D-10이에요.")])
    explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=as_of)
    facts["facts"] = ["희망 직무 데이터 분석과 직종이 같아요", "마감 D-10"]
    again = explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=as_of)
    assert again.cached is False and len(deps.llm.calls) == 2
    assert deps.users.get_explanation("demo1", w.BUSAN_DATA).facts_hash == explain.facts_hash(facts["facts"])


def test_explain_cache_expires(deps, facts):
    deps.llm = ScriptedLlm([GOOD, GOOD])
    explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of="2026-11-21T10:00:00+09:00")
    later = "2026-11-22T10:00:00+09:00"  # cacheHours(24)이 지난 시각
    assert explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=later).cached is False


def test_explain_without_llm_is_service_error(deps, as_of, facts):
    deps.llm = None
    with pytest.raises(OppError) as e:
        explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=as_of)
    assert e.value.code == "AWS_SERVICE_ERROR"


def test_explain_bad_sentence_count_retries(deps, as_of, facts):
    deps.llm = ScriptedLlm([f.explain_reply("한 문장뿐이에요."), "not json", GOOD])
    with pytest.raises(OppError) as e:
        explain.explain_posting(deps, "demo1", w.BUSAN_DATA, as_of=as_of)
    assert e.value.code == "AI_OUTPUT_INVALID" and len(deps.llm.calls) == 2


def test_bedrock_llm_request_shape(monkeypatch, config):
    monkeypatch.setenv("MODEL_ID", "test-model")

    class Client:
        def __init__(self):
            self.requests = []

        def converse(self, **kwargs):
            self.requests.append(kwargs)
            return {"output": {"message": {"content": [{"text": "{\"ok\": "}, {"text": "true}"}]}}}

    client = Client()
    llm = BedrockLlm(client, config=config)
    assert llm.invoke("시스템", "사용자", max_tokens=256) == "{\"ok\": true}"
    request = client.requests[0]
    assert request["modelId"] == "test-model"
    assert request["system"] == [{"text": "시스템"}]
    assert request["messages"] == [{"role": "user", "content": [{"text": "사용자"}]}]
    assert request["inferenceConfig"] == {"maxTokens": 256}  # temperature는 보내지 않는다 (모델이 거절한다)


def test_bedrock_embedder_request_shape(monkeypatch, config):
    monkeypatch.setenv("EMBEDDING_MODEL_ID", "cohere.embed-v4:0")
    dim = config.models.embed_dim

    class Client:
        def __init__(self):
            self.requests = []

        def invoke_model(self, **kwargs):
            self.requests.append(kwargs)
            return {"body": io.BytesIO(json.dumps({"embeddings": {"float": [[0.1] * dim]}}).encode())}

    client = Client()
    embedder = BedrockEmbedder(client, config=config)
    assert len(embedder.embed("공고", kind="document")) == dim
    embedder.embed("프로필", kind="query")
    bodies = [json.loads(r["body"]) for r in client.requests]
    assert client.requests[0]["modelId"] == "cohere.embed-v4:0"
    assert [b["input_type"] for b in bodies] == ["search_document", "search_query"]
    assert bodies[0] == {"texts": ["공고"], "input_type": "search_document", "embedding_types": ["float"],
                         "output_dimension": dim}
    with pytest.raises(ValueError):
        embedder.embed("x", kind="other")


def test_bedrock_needs_model_env(monkeypatch, config):
    monkeypatch.delenv("MODEL_ID", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL_ID", raising=False)
    with pytest.raises(ConfigError, match="MODEL_ID"):
        BedrockLlm(object(), config=config)
    with pytest.raises(ConfigError, match="EMBEDDING_MODEL_ID"):
        BedrockEmbedder(object(), config=config)
