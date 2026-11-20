"""면접 진행 규칙: start_interview, process_answer (design §5). tasks 7.3, 8.2에서 채운다."""


def start_interview(session_id, job, resume_text, interview_type, camera_consent, profile=None, *, llm=None):
    raise NotImplementedError


def process_answer(session, answer_result, *, llm=None):
    raise NotImplementedError
