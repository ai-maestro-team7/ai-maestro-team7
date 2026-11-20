"""계약 목록 (R10.1, R10.4). 계약마다 버전, 소유 Part, 소비 Part, 근거 절을 둔다."""
from __future__ import annotations

from dataclasses import dataclass

from .async_status import AsyncTaskStatus
from .base import ContractModel, Part
from .career_summary import CareerProfileSummary
from .errors import ErrorEnvelope
from .posting import InterviewJobContext, JobRequirementView, PostingForAnalysis
from .profile import CommonProfile

A, B, C, BE, FE = Part.A, Part.B, Part.C, Part.BACKEND, Part.FRONTEND


@dataclass(frozen=True)
class ContractMeta:
    name: str
    model: type[ContractModel]
    schema_version: str  # "주.부"
    owner: Part
    consumers: tuple[Part, ...]
    sources: tuple[str, ...]

    @property
    def major(self) -> int:
        return int(self.schema_version.split(".")[0])


def _meta(name, model, version, owner, consumers, sources):
    return ContractMeta(name, model, version, owner, tuple(consumers), tuple(sources))


CONTRACTS: dict[str, ContractMeta] = {m.name: m for m in (
    _meta("ErrorEnvelope", ErrorEnvelope, "1.0", BE, (A, B, C, FE), ("A §6.6", "B §5.8", "C §5.1", "D-03")),
    _meta("AsyncTaskStatus", AsyncTaskStatus, "1.0", BE, (A, B, C, FE), ("A §6", "B §5.1", "C §5.1", "D-05")),
    _meta("CommonProfile", CommonProfile, "1.0", BE, (A, B, C, FE), ("B §10.3", "db-schema §2.1", "D-08")),
    _meta("PostingForAnalysis", PostingForAnalysis, "1.0", B, (A, C), ("B §10.2", "db-schema §3", "D-09")),
    _meta("JobRequirementView", JobRequirementView, "1.0", B, (A,), ("A §4.4", "D-10")),
    _meta("InterviewJobContext", InterviewJobContext, "1.0", C, (BE,), ("C §5.2",)),
    _meta("CareerProfileSummary", CareerProfileSummary, "1.0", A, (C, BE), ("A §12.2", "C §5.2", "D-12")),
)}
