"""A의 상태 값. 근거는 개발계획서1 §4.2(증거·역량 상태), F-01(문서 상태 전이), §6(작업 상태)."""
from enum import Enum


class DocumentType(str, Enum):
    RESUME = "RESUME"
    COVER_LETTER = "COVER_LETTER"
    CAREER_HISTORY = "CAREER_HISTORY"
    PORTFOLIO = "PORTFOLIO"


class DocumentSource(str, Enum):
    TEXT = "TEXT"      # POST /documents/text
    UPLOAD = "UPLOAD"  # presigned URL 업로드 (Requirement 3, 다음 작업)


class ExtractionStatus(str, Enum):
    """문서 버전의 처리 단계 (A F-01 "상태 전이"). PENDING은 업로드 URL만 발급한 상태다 (A §6.2)."""
    PENDING = "PENDING"
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    ANALYZING = "ANALYZING"
    REQUIRES_USER_REVIEW = "REQUIRES_USER_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvidenceLevel(str, Enum):
    EVIDENCED = "EVIDENCED"                    # 수행 행동·산출물 근거
    PARTIAL = "PARTIAL"                        # 부분 근거
    SELF_REPORTED = "SELF_REPORTED"            # 보유 선언만 있음
    NOT_FOUND = "NOT_FOUND"                    # 서류에 미기재. 실력이 없다는 뜻이 아니다
    USER_CONFIRMED_GAP = "USER_CONFIRMED_GAP"  # 사용자가 미보유를 확인


class FactStatus(str, Enum):
    VERIFIED = "VERIFIED"                      # 사용자가 확인한 사실. 사용자 확인으로만 생긴다
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    SUGGESTION = "SUGGESTION"


class TaskStatus(str, Enum):
    """공통 4개 + A 확장 2개 (D-05, contracts `async_status.py`)."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REQUIRES_USER_REVIEW = "REQUIRES_USER_REVIEW"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REQUIRES_USER_REVIEW,
                          TaskStatus.PARTIAL_SUCCESS}


class TaskType(str, Enum):
    """db-schema §2.5 `taskType` 값."""
    DOCUMENT_EXTRACT = "DOCUMENT_EXTRACT"  # 업로드한 PDF → 정규화 텍스트
    PROFILE_EXTRACT = "PROFILE_EXTRACT"    # 정규화 텍스트 → 역량 프로필
    JOB_FIT = "JOB_FIT"                    # 역량 프로필 + 공고(또는 NCS 직무) → 적합도 분석
    REVIEW = "REVIEW"                      # 자기소개서·이력서 첨삭
    LEARNING_PATH = "LEARNING_PATH"        # 역량 격차 → 학습·자격 경로


class ConfirmAction(str, Enum):
    CONFIRM = "CONFIRM"    # 맞다 → VERIFIED
    NOT_HELD = "NOT_HELD"  # 갖고 있지 않다 → USER_CONFIRMED_GAP
    DELETE = "DELETE"      # 잘못 뽑힌 역량 → 삭제
    RENAME = "RENAME"      # 이름을 고쳐서 확인 → VERIFIED
