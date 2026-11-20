"""아직 없는 공개 함수 6개의 임시 구현 (design §9, 결정 6).

backend/interview_stub.py(PR #31 반영본)와 같은 입출력이다. backend/를 import하지 않고 동작을 옮겨 적었다.
1차 머지 뒤 배포해도 백엔드의 음성·카메라·리포트 호출에서 면접이 깨지지 않게 하려는 것이다.

실제 구현과 다른 점:
- 모두 고정 값을 돌려준다. Polly·Transcribe·Rekognition·Bedrock을 부르지 않는다.
- start_transcription만 대역처럼 output_bucket/output_key에 가짜 결과 JSON을 쓴다 (S3 호출 하나).
- get_transcription_result는 S3 결과 파일을 읽지 않고 고정 문장을 돌려준다.
"""

import json


def _s3_client():
    import boto3  # 지연 import. 테스트는 이 함수를 가짜 클라이언트로 바꾼다

    return boto3.client("s3")


def synthesize_question(text):
    """임시 구현, 2차 PR에서 Polly로 교체. 음성을 만들지 않는다 → 백엔드는 audioUrl을 null로 둔다."""
    return None


def start_transcription(s3_uri, job_name, media_format, output_bucket, output_key):
    """임시 구현, 2차 PR에서 Transcribe로 교체. 백엔드가 정한 위치에 가짜 결과 JSON을 쓴다."""
    body = json.dumps({"jobName": job_name, "results": {"transcripts": [{"transcript": "(대역)"}]}}).encode()
    _s3_client().put_object(Bucket=output_bucket, Key=output_key, ContentType="application/json", Body=body)
    return job_name


def get_transcription_result(job_name):
    """임시 구현, 2차 PR에서 교체. 결과 파일을 읽지 않고 늘 같은 문장을 돌려준다."""
    return {"status": "COMPLETED", "text": "(대역) 저는 캡스톤 프로젝트에서 API 서버를 맡았습니다.",
            "words": [{"word": "저는", "start": 0.4, "end": 0.7}]}


def analyze_face(image_bytes):
    """임시 구현, 4차 PR에서 Rekognition으로 교체. 고정 각도를 돌려준다."""
    if not image_bytes:
        return {"valid": False, "reason": "NO_FACE", "gaze": None, "head": None, "eyesOpen": None}
    return {"valid": True, "reason": None, "gaze": {"yaw": 1.5, "pitch": -2.0}, "head": {"yaw": 0.5, "pitch": 3.0},
            "eyesOpen": {"value": True, "confidence": 98.5}}


def compute_baseline(results):
    """임시 구현, 4차 PR에서 교체. 유효 3장 미만이면 None (태도 미측정, C 명세), 아니면 고정 기준값."""
    valid = [r for r in results if r.get("valid")]
    if len(valid) < 3:
        return None
    return {"gaze": {"yaw": 0.0, "pitch": 0.0}, "head": {"yaw": 0.0, "pitch": 0.0}}


def generate_report(session, frames):
    """임시 구현, 3차 PR에서 교체. 점수 없이 대역과 같은 형태를 돌려준다."""
    answered = sum(1 for a in session["answers"] if a["evaluable"])
    return {
        "job": session["job"], "interviewType": session["interviewType"], "evaluatedBaseQuestions": answered,
        "totalScore": None, "grade": None, "weightBasis": "(대역) 실제 점수는 면접 함수 연결 후 계산",
        "areas": {}, "questions": [], "frameCount": len(frames), "scoringVersion": "stub",
    }
