"""적합도 분석이 바깥에 기대는 것 (Requirement 15 기준 1). 테스트는 메모리 구현, 운영은 DynamoDB·Bedrock KB를 쓴다."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .records import JobFitAnalysis

# 공고 자격 판정. 백엔드가 `backend/eligibility.py`의 `evaluate_eligibility(profile, rules)`를 넣는다 (D-11, BE-8).
# A는 backend/를 import하지 않는다 (기반 Requirement 12).
EligibilityFn = Callable[[dict, list[dict]], dict]


class AnalysisStore(Protocol):
    """`team07-career-mentor`, PK = `USER#{userId}`."""

    def create_analysis(self, analysis: JobFitAnalysis) -> None:
        """같은 ID가 있으면 AlreadyExists."""
        ...

    def save_analysis(self, analysis: JobFitAnalysis) -> None: ...

    def get_analysis(self, user_id: str, analysis_id: str) -> JobFitAnalysis | None: ...

    def get_basic_profile(self, user_id: str) -> dict | None:
        """기본 프로필 `PROFILE#BASIC` (BACKEND 소유, 읽기만, D-08)."""
        ...


class CatalogReader(Protocol):
    """`team07-catalog` (B 소유, 읽기만, db-schema §3). 값은 DynamoDB 숫자를 일반 숫자로 바꾼 dict다."""

    def get_latest(self, job_posting_id: str) -> dict | None: ...

    def get_snapshot(self, job_posting_id: str, snapshot_id: str) -> dict | None: ...


class NcsLookup(Protocol):
    """NCS 정확 조회 (`mentoring.reference.lookup`의 CSV·DynamoDB 구현)."""

    def get_job_profile(self, ncs_code: str) -> Any | None: ...

    def list_units(self, ncs_code: str) -> list[Any]: ...


class KnowledgeSearch(Protocol):
    """Bedrock KB 검색 (`mentoring.knowledge.KnowledgeRetriever`)."""

    def retrieve(self, query: str, *, job_role: str | None = None, k: int | None = None) -> list[Any]: ...
