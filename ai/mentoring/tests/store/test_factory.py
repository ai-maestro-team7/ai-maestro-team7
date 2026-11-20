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
