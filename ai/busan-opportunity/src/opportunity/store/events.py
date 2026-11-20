"""CloudWatch EMF 지표. 한 줄 JSON을 stdout에 찍으면 Lambda가 CloudWatch Logs로 보내고, 지표로 바뀐다.

네임스페이스 `Team07/Opportunity`. 지표는 `EventCount`(값 1) 하나이고, 이벤트 이름은 `event` 차원으로 구분한다.
사용자 ID, 원문, 긴 문자열은 넣지 않는다 (지표 차원은 낮은 가짓수 값만).
"""

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..core import clock

NAMESPACE = "Team07/Opportunity"
MAX_DIMENSION_LENGTH = 64  # 이보다 긴 문자열은 원문일 수 있어 뺀다
MAX_DIMENSIONS = 29        # EMF 차원 집합 한도(30)에서 `event` 하나를 뺀 수
_BLOCKED_PARTS = ("user", "email", "text", "body", "content", "quote", "prompt", "name", "title", "token", "key")


RESERVED = ("event", "EventCount", "_aws")


def _allowed(key: str, value: Any) -> bool:
    lowered = key.lower()
    if key in RESERVED:
        return False
    if any(part in lowered for part in _BLOCKED_PARTS):
        return False
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and 0 < len(value) <= MAX_DIMENSION_LENGTH


def _text(value: Any) -> str:
    """EMF 차원 값은 문자열이어야 한다."""
    return str(value).lower() if isinstance(value, bool) else str(value)


class EmfEvents:
    def __init__(self, *, namespace: str = NAMESPACE, out: Callable[[str], None] = print,
                 now: Callable[[], datetime] = clock.now_kst):
        self.namespace = namespace
        self.out = out
        self.now = now

    def emit(self, event: str, **dimensions: Any) -> None:
        event = str(event)
        dims = {k: v for k, v in dimensions.items() if _allowed(k, v)}
        dims = dict(list(dims.items())[:MAX_DIMENSIONS])
        record = {
            "_aws": {
                "Timestamp": int(self.now().timestamp() * 1000),
                "CloudWatchMetrics": [{
                    "Namespace": self.namespace,
                    "Dimensions": [["event", *dims]],
                    "Metrics": [{"Name": "EventCount", "Unit": "Count"}],
                }],
            },
            "event": event,
            "EventCount": 1,
            **{k: _text(v) for k, v in dims.items()},
        }
        self.out(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
