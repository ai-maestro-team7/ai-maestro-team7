"""Generate deterministic frontend fixtures through the real mentoring REST entry point.

Run from ``ai/mentoring`` with the same dependencies as the test suite:
``python mocks/build_mocks.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
sys.path.insert(0, str(PACKAGE_ROOT / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "tests"))
sys.path.insert(0, str(PACKAGE_ROOT.parent.parent / "contracts" / "src"))

from mentoring.api import rest_handler  # noqa: E402
from support.data import DATA_ANALYST_RESUME, good_output  # noqa: E402
from support.factory import make_deps, run_pending  # noqa: E402

BASE = "/api/v1/mentoring"
USER_ID = "mock-user"
DEMO_RESUME = "\n".join(
    line
    for line in DATA_ANALYST_RESUME.splitlines()
    if not line.startswith("가상 지원자") and not line.startswith("연락처:")
).strip()


def _event(method: str, path: str, body: dict | None = None) -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": BASE + path,
        "rawQueryString": urlencode({}),
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "requestId": "req-mock",
            "stage": "$default",
            "http": {
                "method": method,
                "path": BASE + path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "mock-builder",
            },
        },
        "body": json.dumps(body, ensure_ascii=False) if body is not None else None,
        "isBase64Encoded": False,
    }


def _call(deps, method: str, path: str, body: dict | None = None) -> tuple[dict, dict]:
    request = {"method": method, "path": path}
    if body is not None:
        request["body"] = body
    response = rest_handler.handle(_event(method, path, body), deps, USER_ID)
    return request, {
        "status": response["statusCode"],
        "body": json.loads(response["body"]) if response.get("body") else None,
    }


def _fixture(request: dict, response: dict) -> dict:
    return {"request": request, "response": response}


def _review_output() -> dict:
    output = good_output()
    output["projects"][0]["summary"] = "정류장별 이용량을 99% 개선"
    return output


def build() -> dict[str, dict]:
    deps = make_deps()
    create_body = {"text": DEMO_RESUME, "documentType": "RESUME", "title": "가상 데이터 분석 이력서"}
    request, response = _call(deps, "POST", "/documents/text", create_body)
    document_id = response["body"]["documentId"]
    fixtures = {"POST_documents_text": _fixture(request, response)}

    request, response = _call(deps, "GET", f"/documents/{document_id}")
    fixtures["GET_documents_id_EXTRACTED"] = _fixture(request, response)

    run_pending(deps)
    request, response = _call(deps, "GET", f"/documents/{document_id}")
    fixtures["GET_documents_id_COMPLETED"] = _fixture(request, response)

    request, response = _call(deps, "GET", "/profiles/me")
    fixtures["GET_profiles_me"] = _fixture(request, response)
    profile = response["body"]
    first_skill = profile["skills"][0]["skillId"]

    confirm_body = {
        "baseVersion": profile["profileVersion"],
        "decisions": [{"skillId": first_skill, "action": "CONFIRM"}],
    }
    request, response = _call(deps, "POST", f"/profiles/{profile['profileId']}/confirm", confirm_body)
    fixtures["POST_profiles_id_confirm"] = _fixture(request, response)

    error_cases = [
        ("ERROR_400_INVALID_INPUT", "POST", "/documents/text", {"text": "짧음"}),
        ("ERROR_404_DOCUMENT_NOT_FOUND", "GET", "/documents/doc-none", None),
        (
            "ERROR_409_PRECONDITION_NOT_MET",
            "POST",
            f"/profiles/{profile['profileId']}/confirm",
            {"baseVersion": 1, "decisions": []},
        ),
        ("ERROR_501_NOT_IMPLEMENTED", "POST", "/analyses", {}),
    ]
    for name, method, path, body in error_cases:
        request, response = _call(deps, method, path, body)
        fixtures[name] = _fixture(request, response)

    review_deps = make_deps(responses=[_review_output()])
    request, response = _call(review_deps, "POST", "/documents/text", create_body)
    review_document_id = response["body"]["documentId"]
    run_pending(review_deps)
    request, response = _call(review_deps, "GET", f"/documents/{review_document_id}")
    fixtures["GET_documents_id_REQUIRES_USER_REVIEW"] = _fixture(request, response)
    return fixtures


def write(output_dir: Path = HERE) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = build()
    for path in output_dir.glob("*.json"):
        if path.stem not in generated:
            path.unlink()
    for name, value in generated.items():
        (output_dir / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write()
