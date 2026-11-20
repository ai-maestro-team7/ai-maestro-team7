"""Secrets Manager 구현. 인증키는 여기서만 읽는다. 값과 이름은 로그와 오류 메시지에 남기지 않는다.

`json_secret_id`를 주면 그 시크릿 하나(JSON)에서 이름으로 값을 꺼낸다 (예: `team07/opp-api-keys`).
주지 않으면 이름마다 시크릿을 따로 읽는다.
"""

import json
import time
from collections.abc import Callable

from ..models.errors import aws_service_error
from .dynamo import aws_errors

SERVICE = "secretsmanager"
CACHE_SECONDS = 300  # 5분


class SecretsManagerSecrets:
    def __init__(self, client=None, *, ttl_seconds: float = CACHE_SECONDS,
                 monotonic: Callable[[], float] = time.monotonic, json_secret_id: str | None = None):
        if client is None:
            import boto3
            client = boto3.client(SERVICE)
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.monotonic = monotonic
        self.json_secret_id = json_secret_id
        self._cache: dict[str, tuple[float, str]] = {}

    def get(self, name: str) -> str:
        if self.json_secret_id:
            try:
                return json.loads(self._read(self.json_secret_id))[name]
            except (KeyError, ValueError):
                raise aws_service_error(SERVICE) from None  # 이름과 값은 오류에 남기지 않는다
        return self._read(name)

    def _read(self, name: str) -> str:
        hit = self._cache.get(name)
        if hit and self.monotonic() < hit[0]:
            return hit[1]
        with aws_errors(SERVICE):
            value = self.client.get_secret_value(SecretId=name)["SecretString"]
        self._cache[name] = (self.monotonic() + self.ttl_seconds, value)
        return value
