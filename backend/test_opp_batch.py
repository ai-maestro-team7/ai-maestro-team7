"""정기 수집 라우터·비동기 연결. AWS·공공 API는 호출하지 않는다."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai/busan-opportunity/src"))
import opportunities_api as api
from app import lambda_handler

AS_OF = "2026-11-21T04:30:00+09:00"


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.deps = SimpleNamespace(catalog=object(), config=SimpleNamespace(batch=SimpleNamespace(weekly_sources=["work24_gangso"])))
        self.patches = [
            patch.object(api, "deps", return_value=self.deps),
            patch.object(api, "build_raw_store", return_value="raw"),
            patch.object(api, "build_secrets", return_value="secrets"),
            patch.object(api, "batch_lambda"),
            patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-api"}),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.client = self.mocks[3].return_value
        self.client.invoke.return_value = {"StatusCode": 202}

    def test_router_continues_with_asynchronous_invocation_and_fixed_as_of(self):
        nxt = {"step": "ingest", "sources": ["youthcenter"], "ids": ["alio-1"]}
        with patch.object(api.batch, "run_batch", return_value={"step": "ingest", "next": nxt}) as run:
            result = lambda_handler({"oppBatch": {"step": "ingest", "asOf": AS_OF}}, None)
        self.assertEqual(result, {"step": "ingest", "next": True})
        run.assert_called_once_with({"step": "ingest"}, self.deps, "raw", "secrets", as_of=AS_OF)
        kwargs = self.client.invoke.call_args.kwargs
        self.assertEqual(kwargs["FunctionName"], "test-api")
        self.assertEqual(kwargs["InvocationType"], "Event")
        self.assertEqual(json.loads(kwargs["Payload"]), {"oppBatch": {**nxt, "asOf": AS_OF}})

    def test_weekly_sources_come_from_configuration(self):
        with patch.object(api.batch, "run_batch", return_value={"step": "ingest", "next": None}) as run:
            api.run_batch({"oppBatch": {"step": "ingest", "frequency": "weekly", "asOf": AS_OF}})
        self.assertEqual(run.call_args.args[0], {"step": "ingest", "sources": ["work24_gangso"]})
        self.client.invoke.assert_not_called()

    def test_empty_weekly_list_does_not_fall_back_to_daily_sources(self):
        self.deps.config.batch.weekly_sources = []
        with patch.object(api.batch, "run_batch") as run:
            result = api.run_batch({"oppBatch": {"step": "ingest", "frequency": "weekly"}})
        self.assertFalse(result["next"])
        run.assert_not_called()

    def test_failure_is_not_reported_as_success(self):
        with patch.object(api.batch, "run_batch", side_effect=RuntimeError("storage unavailable")):
            with self.assertRaises(RuntimeError):
                api.run_batch({"oppBatch": {"step": "ingest"}})
        self.client.invoke.assert_not_called()

    def test_rejected_continuation_raises_for_lambda_retry(self):
        self.client.invoke.return_value = {"StatusCode": 200}
        with patch.object(api.batch, "run_batch", return_value={"step": "ingest", "next": {"step": "enrich", "ids": ["a"]}}):
            with self.assertRaises(RuntimeError):
                api.run_batch({"oppBatch": {"step": "ingest"}})

    def test_unknown_frequency_stops_before_any_collection(self):
        with patch.object(api.batch, "run_batch") as run, self.assertRaises(ValueError):
            api.run_batch({"oppBatch": {"step": "ingest", "frequency": "monthly"}})
        run.assert_not_called()

    def test_actual_batch_module_chains_daily_collection_and_enrichment(self):
        self.deps.config.batch.daily_sources = ["alio", "klid"]
        self.deps.config.batch.enrich_chunk = 1
        def ingest(*args, sources, **kwargs):
            if sources == ["klid"]:
                return {"sources": {"klid": {"status": "FAILED"}}}
            return {"sources": {"alio": {"status": "OK", "needsEnrich": ["alio-1", "alio-2"]}}}
        with patch.object(api.batch, "run_ingest", side_effect=ingest) as collect, \
             patch.object(api.batch, "enrich_postings", return_value={"enriched": 1}) as enrich:
            event = {"oppBatch": {"step": "ingest", "asOf": AS_OF}}
            outcomes = []
            for _ in range(10):
                self.client.invoke.reset_mock()
                out = lambda_handler(event, None)
                outcomes.append(out)
                if not out["next"]:
                    break
                event = json.loads(self.client.invoke.call_args.kwargs["Payload"])
            else:
                self.fail("수집 체인이 종료되지 않았습니다")
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(enrich.call_count, 2)
        self.assertEqual(len(outcomes), 4)
        self.assertFalse(outcomes[-1]["next"])
        self.assertTrue(all(c.kwargs["as_of"] == AS_OF for c in collect.call_args_list))


if __name__ == "__main__":
    unittest.main()
