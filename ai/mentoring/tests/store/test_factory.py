import pytest

from mentoring.config import MissingEnvError
from mentoring.store.factory import build_aws_deps


@pytest.mark.parametrize(
    "missing",
    ["TABLE_CAREER_MENTOR", "CAREER_DOCS_BUCKET", "MODEL_ID", "AWS_LAMBDA_FUNCTION_NAME", "AWS_REGION"],
)
def test_factory_reports_missing_environment_name(monkeypatch, missing):
    values = {
        "TABLE_CAREER_MENTOR": "table",
        "CAREER_DOCS_BUCKET": "bucket",
        "MODEL_ID": "model",
        "AWS_LAMBDA_FUNCTION_NAME": "function",
        "AWS_REGION": "ap-northeast-2",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)
    with pytest.raises(MissingEnvError) as caught:
        build_aws_deps(hash_user_id=lambda value: value)
    assert missing in str(caught.value)


def _set_required_env(monkeypatch):
    for key, value in {
        "TABLE_CAREER_MENTOR": "table",
        "CAREER_DOCS_BUCKET": "bucket",
        "MODEL_ID": "model",
        "AWS_LAMBDA_FUNCTION_NAME": "function",
        "AWS_REGION": "ap-northeast-2",
    }.items():
        monkeypatch.setenv(key, value)


def test_factory_builds_without_arguments_like_backend(monkeypatch):
    # backend/mentoring_api.py는 인자 없이 부르고 hash_user_id를 공통 함수로 바꿔 넣는다 (#78)
    _set_required_env(monkeypatch)
    deps = build_aws_deps()
    with pytest.raises(RuntimeError):
        deps.hash_user_id("user-1")


def test_factory_wires_pdf_extractor_with_textract_ocr(monkeypatch):
    from mentoring.core.pdf_extractor import PdfExtractor
    from mentoring.extract import TextractOcr

    _set_required_env(monkeypatch)
    deps = build_aws_deps(hash_user_id=lambda value: value)
    assert isinstance(deps.extractor, PdfExtractor)
    assert isinstance(deps.extractor.ocr, TextractOcr)
    assert deps.extractor.bucket == "bucket"


def test_factory_wires_story_repo(monkeypatch):
    from mentoring.stories.dynamo import DynamoStoryRepo

    _set_required_env(monkeypatch)
    assert isinstance(build_aws_deps().stories, DynamoStoryRepo)
