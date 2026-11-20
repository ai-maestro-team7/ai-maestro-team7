"""AI 모의면접 함수 (C 파트, docs/개발계획서3.md ★ 함수 명세).

배포 때 infra/package.sh가 이 폴더를 `interview` 패키지로 묶고, backend/interview_api.py가
`import interview as impl`로 부른다. 아래 8개 함수와 InterviewError가 백엔드와의 계약이다.
음성 함수 3개는 2차(voice.py)부터 Polly·Transcribe를 실제로 부른다. 카메라·리포트 함수는 아직 임시 구현이다.
"""

from .errors import InterviewError
from .flow import process_answer, start_interview
from .placeholders import analyze_face, compute_baseline, generate_report
from .voice import get_transcription_result, start_transcription, synthesize_question

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
