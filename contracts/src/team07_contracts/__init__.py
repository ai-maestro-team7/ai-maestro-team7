"""팀 7 파트 간 데이터 계약 (common-foundation Contract_Package, 위치 D-18).

import 이름은 team07_contracts 하나다. 위치를 옮겨도 import 문은 그대로 둔다.
"""
from .async_status import COMMON_STATUSES, STATUS_EXTENSIONS, AsyncTaskStatus, PartStatusSpec, is_terminal, parse_async_status
from .base import ContractModel, Money, Part
from .career_summary import CAREER_SUMMARY_LIMITS, CareerProfileSummary
from .document import check_schema_version, dump, load_document, validate
from .errors import ERROR_CODES, ErrorBody, ErrorCodeSpec, ErrorEnvelope, interview_error_to_envelope, normalize_code
from .posting import (EligibilityRule, InterviewJobContext, JobRequirementView, PostingForAnalysis, PostingJob,
                      Requirement, WorkRegion, compute_content_hash, to_interview_job_context, to_job_requirement_view)
from .profile import CommonProfile, DesiredJob
from .registry import CONTRACTS, ContractMeta
from .validation import ContractValidationError, ContractVersionError, FieldError

__all__ = [
    "AsyncTaskStatus", "CAREER_SUMMARY_LIMITS", "COMMON_STATUSES", "CONTRACTS", "CareerProfileSummary",
    "CommonProfile", "ContractMeta", "ContractModel", "ContractValidationError", "ContractVersionError",
    "DesiredJob", "ERROR_CODES", "EligibilityRule", "ErrorBody", "ErrorCodeSpec", "ErrorEnvelope", "FieldError",
    "InterviewJobContext", "JobRequirementView", "Money", "Part", "PartStatusSpec", "PostingForAnalysis",
    "PostingJob", "Requirement", "STATUS_EXTENSIONS", "WorkRegion", "check_schema_version",
    "compute_content_hash", "dump", "interview_error_to_envelope", "is_terminal", "load_document",
    "normalize_code", "parse_async_status", "to_interview_job_context", "to_job_requirement_view", "validate",
]
