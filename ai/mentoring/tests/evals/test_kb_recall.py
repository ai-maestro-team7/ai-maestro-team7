from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "evals" / "kb_recall.py"
SPEC = importlib.util.spec_from_file_location("kb_recall", MODULE_PATH)
kb_recall = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kb_recall)


class FakeClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def retrieve(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _queries() -> list[dict]:
    return [
        {
            "query_id": "q-1",
            "query": "가상 데이터 분석 질문",
            "expected_document_id": "doc-data.md",
            "expected_job_role": "데이터 분석",
        },
        {
            "query_id": "q-2",
            "query": "가상 공통 질문",
            "expected_document_id": "doc-common.md",
            "expected_job_role": "인사",
        },
        {
            "query_id": "q-3",
            "query": "가상 미검색 질문",
            "expected_document_id": "doc-missing.md",
            "expected_job_role": "회계·감사",
        },
    ]


def test_recall_at_k_counts_hits_empty_and_misses() -> None:
    client = FakeClient(
        [
            {"retrievalResults": [{"metadata": {"document_id": "doc-data.md"}}]},
            {"retrievalResults": [{"location": {"s3Location": {"uri": "s3://virtual/doc-other.md"}}}]},
            {"retrievalResults": []},
        ]
    )

    report = kb_recall.recall_at_k(client, "virtual-kb", _queries(), 5, False)

    assert report.hits == 1
    assert report.total == 3
    assert report.recall == 1 / 3
    assert report.empty == 1
    assert [miss.query_id for miss in report.misses] == ["q-2", "q-3"]
    assert report.misses[0].got == ["doc-other.md"]


def test_role_filter_includes_expected_role_and_common() -> None:
    client = FakeClient([{"retrievalResults": [{"metadata": {"documentId": "doc-data.md"}}]}])

    kb_recall.recall_at_k(client, "virtual-kb", _queries()[:1], 3, True)

    vector = client.requests[0]["retrievalConfiguration"]["vectorSearchConfiguration"]
    assert vector["numberOfResults"] == 3
    assert vector["filter"] == {
        "orAll": [
            {"equals": {"key": "job_role", "value": "데이터 분석"}},
            {"equals": {"key": "job_role", "value": "공통"}},
        ]
    }


def test_empty_query_list_has_zero_recall() -> None:
    report = kb_recall.recall_at_k(FakeClient([]), "virtual-kb", [], 5, False)

    assert report.model_dump() == {"hits": 0, "total": 0, "recall": 0.0, "empty": 0, "misses": []}
