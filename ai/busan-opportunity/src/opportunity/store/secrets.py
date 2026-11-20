"""Secrets Manager 구현. 인증키는 여기서만 읽는다. 값과 이름은 로그와 오류 메시지에 남기지 않는다."""

import time
from collections.abc import Callable

from .dynamo import aws_errors

SERVICE = "secretsmanager"
CACHE_SECONDS = 300  # 5분


class SecretsManagerSecrets:
    def __init__(self, client=None, *, ttl_seconds: float = CACHE_SECONDS,
                 monotonic: Callable[[], float] = time.monotonic):
        if client is None:
            import boto3
            client = boto3.client(SERVICE)
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.monotonic = monotonic
        self._cache: dict[str, tuple[float, str]] = {}

    def get(self, name: str) -> str:
        hit = self._cache.get(name)
        if hit and self.monotonic() < hit[0]:
            return hit[1]
        with aws_errors(SERVICE):
            value = self.client.get_secret_value(SecretId=name)["SecretString"]
        self._cache[name] = (self.monotonic() + self.ttl_seconds, value)
        return value
