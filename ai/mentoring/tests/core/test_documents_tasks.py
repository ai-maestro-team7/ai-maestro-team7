"""텍스트 문서 등록과 작업 실행 (Requirement 4, UT-17)."""
import pytest

from mentoring.core.documents import create_text_document, get_document
from mentoring.errors import MentoringError
from mentoring.models import TextDocumentRequest
from support.data import DATA_ANALYST_RESUME
from support.factory import make_deps, run_pending, small_config

USER = "user-a"


def req(**kwargs):
    return TextDocumentRequest.model_validate({"text": DATA_ANALYST_RESUME, **kwargs})


def test_text_document_starts_extracted_and_queues_one_task(deps):
    body = create_text_document(deps, USER, req())
    assert body["status"] == "PENDING" and body["extractionStatus"] == "EXTRACTED"
    assert len(deps.tasks.sent) == 1
    message = deps.tasks.sent[0]["mentoringTask"]
    assert set(message) == {"taskId", "taskType", "userId", "resourceId", "resourceVersion"}  # 원문을 담지 않는다
    view = get_document(deps, USER, body["documentId"])
    assert view.extraction_status.value == "EXTRACTED" and view.task_status == "PENDING"


def test_text_saved_under_hashed_user_prefix(deps):
    body = create_text_document(deps, USER, req())
    (key,) = deps.objects.objects
    assert key.startswith(f"users/{deps.hash_user_id(USER)}/documents/{body['documentId']}/v1/")
    assert USER not in key


def test_text_length_limits_come_from_config():
    deps = make_deps(config=small_config(textMaxChars=60))
    with pytest.raises(MentoringError) as error:
        create_text_document(deps, USER, req())
    assert error.value.code == "INVALID_INPUT" and error.value.details["maxChars"] == 60
    assert "text" not in str(error.value.details.get("length", "")) and DATA_ANALYST_RESUME not in str(error.value.details)


def test_default_config_requires_1000_chars():
    from mentoring.config import get_config

    deps = make_deps(config=get_config())
    with pytest.raises(MentoringError):
        create_text_document(deps, USER, req())


def test_idempotency_replay_and_conflict(deps):
    first = create_text_document(deps, USER, req(), "key-1")
    again = create_text_document(deps, USER, req(), "key-1")
    assert again == first and len(deps.tasks.sent) == 1
    with pytest.raises(MentoringError) as error:
        create_text_document(deps, USER, req(title="다른 제목"), "key-1")
    assert error.value.status == 409


def test_idempotency_key_is_per_user(deps):
    a = create_text_document(deps, USER, req(), "same-key")
    b = create_text_document(deps, "user-b", req(), "same-key")
    assert a["documentId"] != b["documentId"]


def test_ut17_duplicate_task_message_saves_once(deps):
    create_text_document(deps, USER, req())
    message = deps.tasks.sent[0]
    deps.tasks.queue.append(message)  # 같은 이벤트가 한 번 더 온다 (at-least-once)
    results = run_pending(deps)
    assert [r["status"] for r in results] == ["COMPLETED", "SKIPPED"]
    assert len(deps.users.list_profile_versions(USER)) == 1


def test_task_for_other_user_is_skipped(deps):
    create_text_document(deps, USER, req())
    message = deps.tasks.drain()[0]
    message["mentoringTask"]["userId"] = "user-b"
    deps.tasks.queue.append(message)
    assert run_pending(deps)[0]["reason"] == "TASK_NOT_FOUND"
    assert deps.users.get_profile_pointer("user-b") is None


def test_document_status_follows_task(deps):
    body = create_text_document(deps, USER, req())
    run_pending(deps)
    view = get_document(deps, USER, body["documentId"])
    assert view.extraction_status.value == "COMPLETED" and view.task_status == "COMPLETED"


def test_failed_task_marks_document_failed():
    deps = make_deps(["nope", "still nope"])
    body = create_text_document(deps, USER, req())
    run_pending(deps)
    view = get_document(deps, USER, body["documentId"])
    assert view.extraction_status.value == "FAILED" and view.error_code == "AI_OUTPUT_INVALID"


def test_workspace_id_with_hash_is_rejected(deps):
    with pytest.raises(MentoringError):
        create_text_document(deps, USER, req(workspaceId="ws#1"))
