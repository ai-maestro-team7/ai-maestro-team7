"""수집 배치 입구: 한 걸음씩 실행하고 다음 이벤트를 돌려준다."""

import pytest

from opportunity import batch
from opportunity.models.errors import OppError
from opportunity.store.memory import MemoryRawStore, MemorySecrets


@pytest.fixture
def fakes(monkeypatch):
    calls = {"ingest": [], "enrich": []}

    def fake_ingest(config, catalog, raw_store, secrets, *, sources, as_of=None, **kwargs):
        calls["ingest"].append(list(sources))
        name = sources[0]
        if name == "klid":
            return {"sources": {name: {"status": "FAILED", "error": "FetchError"}}}
        return {"sources": {name: {"status": "OK", "created": 2, "needsEnrich": [f"{name}-1", f"{name}-2"]}}}

    def fake_enrich(deps, ids, *, as_of=None):
        calls["enrich"].append(list(ids))
        return {"enriched": len(ids), "failed": 0, "alts": 0}

    monkeypatch.setattr(batch, "run_ingest", fake_ingest)
    monkeypatch.setattr(batch, "enrich_postings", fake_enrich)
    return calls


def run_all(deps, event):
    steps = []
    while event:
        out = batch.run_batch(event, deps, MemoryRawStore(), MemorySecrets())
        steps.append(out)
        event = out["next"]
    return steps


def test_daily_ingest_runs_one_source_per_step_then_enriches(deps, fakes):
    steps = run_all(deps, {"step": "ingest"})
    assert fakes["ingest"] == [[s] for s in deps.config.batch.daily_sources]  # 출처 하나에 한 걸음
    assert [s.get("source") for s in steps[:4]] == deps.config.batch.daily_sources
    assert steps[1]["result"]["status"] == "FAILED"  # 한 출처가 실패해도 다음 출처로 간다
    assert fakes["enrich"] == [["alio-1", "alio-2", "worldjob-1", "worldjob-2", "youthcenter-1", "youthcenter-2"]]
    assert steps[-1]["next"] is None
    assert "needsEnrich" not in steps[0]["result"]


def test_enrich_runs_in_chunks(deps, fakes):
    chunk = deps.config.batch.enrich_chunk
    ids = [f"p-{i}" for i in range(chunk * 2 + 3)]
    steps = run_all(deps, {"step": "enrich", "ids": ids})
    assert [len(c) for c in fakes["enrich"]] == [chunk, chunk, 3]
    assert len(steps) == 3 and steps[-1]["next"] is None


def test_chosen_sources_and_nothing_to_enrich(deps, fakes, monkeypatch):
    monkeypatch.setattr(batch, "run_ingest", lambda *a, sources, **k: {"sources": {sources[0]: {"status": "EMPTY"}}})
    steps = run_all(deps, {"step": "ingest", "sources": ["work24_gangso"]})
    assert len(steps) == 1 and steps[0]["next"] is None and fakes["enrich"] == []


def test_bad_step_and_unknown_source(deps, fakes):
    with pytest.raises(OppError) as e:
        batch.run_batch({"step": "nope"}, deps, MemoryRawStore(), MemorySecrets())
    assert e.value.code == "INVALID_INPUT"
    with pytest.raises(OppError):
        batch.run_batch({"step": "ingest", "sources": ["saramin"]}, deps, MemoryRawStore(), MemorySecrets())
    assert fakes["ingest"] == []
