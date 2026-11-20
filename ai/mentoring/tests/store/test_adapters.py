import io
import json

import boto3
import pytest
from botocore.stub import Stubber

from mentoring.errors import MentoringError
from mentoring.store.dispatch import LambdaTaskDispatcher
from mentoring.store.reference_adapter import ReferenceUnitAdapter


class Lookup:
    def __init__(self):
        self.calls = []

    def get_unit(self, ncs_code, unit_code):
        self.calls.append((ncs_code, unit_code))
        return {"unitCode": unit_code}


def test_reference_unit_adapter_derives_ncs_code():
    lookup = Lookup()
    adapter = ReferenceUnitAdapter(lookup)
    assert adapter.get_competency_unit("2001010501_23v2") == {"unitCode": "2001010501_23v2"}
    assert lookup.calls == [("20010105", "2001010501_23v2")]
    assert adapter.get_competency_unit("bad-code") is None


def test_lambda_dispatch_request(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    client = boto3.client("lambda", region_name="ap-northeast-2")
    payload = {"mentoringTask": {"taskId": "task-1"}}
    with Stubber(client) as stubber:
        stubber.add_response(
            "invoke",
            {"StatusCode": 202, "Payload": io.BytesIO(b"")},
            {
                "FunctionName": "team07-api",
                "InvocationType": "Event",
                "Payload": json.dumps(payload, separators=(",", ":")).encode(),
            },
        )
        LambdaTaskDispatcher(client, "team07-api").dispatch(payload)


def test_lambda_error_is_safe(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    client = boto3.client("lambda", region_name="ap-northeast-2")
    with Stubber(client) as stubber:
        stubber.add_client_error("invoke", service_error_code="ServiceException")
        with pytest.raises(MentoringError) as caught:
            LambdaTaskDispatcher(client, "team07-api").dispatch({})
    assert caught.value.details == {"service": "lambda"}
