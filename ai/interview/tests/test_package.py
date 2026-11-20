import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

import interview
from conftest import REPO_ROOT

PACKAGE_DIR = Path(interview.__file__).resolve().parent

PUBLIC = {"InterviewError", "start_interview", "process_answer", "synthesize_question", "start_transcription",
          "get_transcription_result", "analyze_face", "compute_baseline", "generate_report"}

# backend/interview_api.py의 현재 호출 형태 (위치 인자 개수). 행 번호는 a556a31 기준
BACKEND_CALLS = [
    ("start_interview", 6),          # 244행: iv_id, job, resumeText, interviewType, cameraConsent, profile
    ("process_answer", 2),           # 270행: session, answer_result
    ("synthesize_question", 1),      # 234행
    ("start_transcription", 5),      # 387행: s3_uri, job_name, media_format, UPLOAD_BUCKET, transcript_key
    ("get_transcription_result", 1),  # 255행
    ("analyze_face", 1),             # 421행
    ("compute_baseline", 1),         # 288행
    ("generate_report", 2),          # 291행: session, answer_frames
]


def test_public_names():
    assert set(interview.__all__) == PUBLIC
    for name in PUBLIC:
        assert hasattr(interview, name)


@pytest.mark.parametrize("name, n_args", BACKEND_CALLS)
def test_backend_call_shapes_bind(name, n_args):
    sig = inspect.signature(getattr(interview, name))
    sig.bind(*range(n_args))  # TypeError면 백엔드 호출이 깨진다


def test_public_functions_come_from_real_modules():
    # 2차(#74): 음성 함수 3개는 voice.py, 3차(#92): generate_report는 report.py, 4차(#108): 카메라 2개는 camera.py
    for name in ("synthesize_question", "start_transcription", "get_transcription_result"):
        assert getattr(interview, name).__module__ == "interview.voice"
    assert interview.generate_report.__module__ == "interview.report"
    for name in ("analyze_face", "compute_baseline"):
        assert getattr(interview, name).__module__ == "interview.camera"
    assert not (PACKAGE_DIR / "placeholders.py").exists()  # 임시 구현은 모두 바뀌었다


def test_import_without_boto3():
    # boto3·botocore가 없는 환경에서도 import는 된다 (음성 함수는 처음 호출할 때 boto3를 부른다)
    code = (
        "import sys\n"
        "sys.modules['boto3'] = None\n"
        "sys.modules['botocore'] = None\n"
        "sys.modules['strands'] = None\n"
        "import interview\n"
        "assert interview.synthesize_question('질문입니다') is None\n"  # boto3가 없으면 음성 없이 진행
        "assert interview.analyze_face(b'img')['reason'] == 'ANALYSIS_FAILED'\n"  # 카메라 캡처만 빼고 진행
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "MODEL_ID"}
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "ai"), str(REPO_ROOT / "contracts" / "src")])
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_start_interview_profile_is_optional():
    inspect.signature(interview.start_interview).bind(*range(5))


def _source_files():
    return [p for p in PACKAGE_DIR.rglob("*.py") if "tests" not in p.relative_to(PACKAGE_DIR).parts]


FORBIDDEN_TOP = {"backend", "interview_stub", "common", "interview_api", "app"}


def test_no_backend_imports():
    found = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for n in names:
                if n.split(".")[0] in FORBIDDEN_TOP:
                    found.append(f"{path.name}: {n}")
    assert found == []


def test_internal_imports_are_relative():
    # 패키지 안의 모듈은 `from .x import` 로만 부른다 (배포 이름이 interview로 바뀌어도 동작)
    found = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "interview":
                found.append(path.name)
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "interview" for a in node.names):
                found.append(path.name)
    assert found == []


def test_import_without_model_id_and_strands():
    code = (
        "import sys\n"
        "sys.modules['strands'] = None\n"  # strands-agents가 없는 환경 흉내
        "import interview\n"
        "assert 'strands' not in sys.modules or sys.modules['strands'] is None\n"
        "assert 'boto3' not in sys.modules\n"
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "MODEL_ID"}
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "ai"), str(REPO_ROOT / "contracts" / "src")])
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
