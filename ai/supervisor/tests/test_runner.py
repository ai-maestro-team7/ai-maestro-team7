"""Strands 연결 확인 (모델은 부르지 않는다). 도구 함수가 Strands 도구 스펙으로 바뀌는지, 생각 끄기 설정."""

from strands import tool

from fakes import build_deps
from supervisor.config import get_config
from supervisor.models import ChatReply
from supervisor.runner import StrandsRunner
from supervisor.tools import TurnTools


def test_tool_functions_become_strands_tools_without_user_id():
    turn = TurnTools(build_deps(None), "demo1")
    specs = {f.__name__: tool(f).tool_spec for f in turn.functions()}
    search = specs["search_job_postings"]["inputSchema"]["json"]["properties"]
    assert set(search) == {"job_name", "keyword", "organization", "region", "min_salary", "career_type", "use_resume"}
    assert search["min_salary"]["type"] == "integer" and "3000" in search["min_salary"]["description"]
    assert specs["get_my_status"]["inputSchema"]["json"].get("properties", {}) == {}
    assert all("user" not in name for spec in specs.values() for name in spec["inputSchema"]["json"].get("properties", {}))
    assert all(spec["description"] for spec in specs.values())


def test_thinking_by_model():
    config = get_config()
    assert config.thinking_for("global.anthropic.claude-haiku-5-5") == {"type": "disabled"}
    assert config.thinking_for("global.anthropic.claude-sonnet-5-5") == {"type": "between_tools"}
    assert config.thinking_for("other-model") is None


def test_runner_builds_model_once(monkeypatch, tmp_path):
    # 모델 객체만 만든다. 로컬 자격 증명(aws login)을 읽지 않게 가짜 값을 둔다
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    runner = StrandsRunner(model_id="global.anthropic.claude-haiku-5-5", region="ap-northeast-2", config=get_config())
    first = runner._get_model()
    assert runner._get_model() is first
    assert first.config["additional_request_fields"] == {"thinking": {"type": "disabled"}}
    assert first.config["max_tokens"] == get_config().max_tokens


def test_reply_schema_fields():
    assert set(ChatReply.model_json_schema()["properties"]) == {"reply", "follow_ups"}
