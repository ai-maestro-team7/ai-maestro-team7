"""AI 모의면접 함수 (C 파트, docs/개발계획서3.md ★ 함수 명세).

배포 때 infra/package.sh가 이 폴더를 `interview` 패키지로 묶고, backend/interview_api.py가
`import interview as impl`로 부른다. 아래 8개 함수와 InterviewError가 백엔드와의 계약이다.
"""

from .errors import InterviewError
from .flow import process_answer, start_interview
from .placeholders import (analyze_face, compute_baseline, generate_report, get_transcription_result,
                           start_transcription, synthesize_question)

__all__ = [
    "InterviewError",
    "start_interview",
    "process_answer",
    "synthesize_question",
    "start_transcription",
    "get_transcription_result",
    "analyze_face",
    "compute_baseline",
    "generate_report",
]
