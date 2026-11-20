"""모의면접 함수 대역(stub).

현지 담당의 실제 함수(저장소 ai/interview/)가 들어오기 전까지 백엔드·프론트가
전체 흐름을 돌려 볼 수 있게, 함수 명세(★ 함수 명세)와 같은 입출력만 흉내 낸다.
AI·Polly·Transcribe·Rekognition을 실제로 부르지 않는다.
"""

QUESTIONS = [
    ("q1", "experience", "최근 프로젝트에서 맡은 역할과 해결한 문제를 설명해 주세요."),
    ("q2", "knowledge", "{job} 직무에서 중요하다고 생각하는 기술 한 가지를 설명해 주세요."),
    ("q3", "situation", "팀원과 의견이 갈렸을 때 어떻게 결정하시겠어요?"),
]


class InterviewError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def _question(q, answer_no=1, follow_up=False, text=None):
    qid = q["questionId"] + ("-f" if follow_up else "")
    return {"questionId": qid, "answerId": f"a-{q['questionId']}-{answer_no}", "text": text or q["question"], "isFollowUp": follow_up}


def start_interview(session_id, job, resume_text, interview_type, camera_consent, profile=None):
    questions = [{"questionId": i, "questionType": t, "question": s.format(job=job)} for i, t, s in QUESTIONS]
    session = {
        "sessionId": session_id, "job": job, "interviewType": interview_type, "cameraConsent": camera_consent,
        "resumeText": resume_text, "profile": profile, "scoringVersion": "stub",
        "questions": questions, "currentIndex": 0, "followUpUsed": False, "answers": [], "baseline": None,
    }
    return {"session": session, "nextQuestion": _question(questions[0])}


def synthesize_question(text):
    return None  # 대역은 음성을 만들지 않는다 → audioUrl = null (명세상 허용)


def start_transcription(s3_uri, job_name, media_format, output_bucket, output_key):
    """실제 함수처럼 변환 결과 JSON을 백엔드가 정한 위치에 쓴다 (내용은 가짜)."""
    import json

    import boto3

    boto3.client("s3").put_object(Bucket=output_bucket, Key=output_key, ContentType="application/json",
                                  Body=json.dumps({"jobName": job_name, "results": {"transcripts": [{"transcript": "(대역)"}]}}).encode())
    return job_name


def get_transcription_result(job_name):
    return {"status": "COMPLETED", "text": "(대역) 저는 캡스톤 프로젝트에서 API 서버를 맡았습니다.",
            "words": [{"word": "저는", "start": 0.4, "end": 0.7}]}


def process_answer(session, answer_result):
    idx = session["currentIndex"]
    q = session["questions"][idx]
    text = (answer_result.get("transcription") or {}).get("text") or ""
    failed = (answer_result.get("transcription") or {}).get("status") == "FAILED"
    evaluable = bool(text) and not failed
    reason = None if evaluable else ("TRANSCRIBE_FAILED" if failed else "NO_ANSWER")
    session["answers"].append({"answerId": answer_result["answerId"], "questionId": q["questionId"], "evaluable": evaluable, "reason": reason})
    last = {"answerId": answer_result["answerId"], "evaluable": evaluable, "reason": reason}

    # 대역 규칙: 1번 질문에서만 꼬리질문 1개
    if idx == 0 and not session["followUpUsed"] and evaluable:
        session["followUpUsed"] = True
        return {"session": session, "action": "FOLLOW_UP", "lastAnswer": last,
                "nextQuestion": _question(q, 2, True, "(대역 꼬리질문) 그 과정에서 가장 어려웠던 점은 무엇이었나요?")}
    session["currentIndex"] = idx + 1
    session["followUpUsed"] = False
    if session["currentIndex"] >= len(session["questions"]):
        return {"session": session, "action": "REPORT", "nextQuestion": None, "lastAnswer": last}
    return {"session": session, "action": "NEXT_QUESTION", "lastAnswer": last,
            "nextQuestion": _question(session["questions"][session["currentIndex"]])}


def analyze_face(image_bytes):
    if not image_bytes:
        return {"valid": False, "reason": "NO_FACE", "gaze": None, "head": None, "eyesOpen": None}
    return {"valid": True, "reason": None, "gaze": {"yaw": 1.5, "pitch": -2.0}, "head": {"yaw": 0.5, "pitch": 3.0},
            "eyesOpen": {"value": True, "confidence": 98.5}}


def compute_baseline(results):
    valid = [r for r in results if r.get("valid")]
    if len(valid) < 3:  # C 명세: 유효 3장 미만이면 None → 태도 미측정
        return None
    return {"gaze": {"yaw": 0.0, "pitch": 0.0}, "head": {"yaw": 0.0, "pitch": 0.0}}


def generate_report(session, frames):
    answered = sum(1 for a in session["answers"] if a["evaluable"])
    return {
        "job": session["job"], "interviewType": session["interviewType"], "evaluatedBaseQuestions": answered,
        "totalScore": None, "grade": None, "weightBasis": "(대역) 실제 점수는 면접 함수 연결 후 계산",
        "areas": {}, "questions": [], "frameCount": len(frames), "scoringVersion": "stub",
    }
