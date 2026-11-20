"""Asynchronous self-invocation adapter for mentoring tasks."""
import json
from typing import Any

from mentoring.errors import aws_service_error


class LambdaTaskDispatcher:
    def __init__(self, client: Any, function_name: str) -> None:
        self._client = client
        self._function_name = function_name

    def dispatch(self, message: dict) -> None:
        try:
            self._client.invoke(
                FunctionName=self._function_name,
                InvocationType="Event",
                Payload=json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
        except Exception as error:
            raise aws_service_error("lambda") from error
