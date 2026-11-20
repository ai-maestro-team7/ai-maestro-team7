"""정규화된 문서 원문을 기준으로 모델 출력을 검증하는 순수 함수."""

from .evidence import EvidenceCheck, UnsupportedFact, check_evidence, find_unsupported_facts

__all__ = ["EvidenceCheck", "UnsupportedFact", "check_evidence", "find_unsupported_facts"]
