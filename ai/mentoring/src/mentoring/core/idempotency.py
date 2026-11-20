"""생성 요청의 멱등 처리 (docs/api.md §2 `Idempotency-Key`, D-31).
같은 키·같은 본문이면 처음 결과를 돌려주고, 같은 키·다른 본문이면 409 `PRECONDITION_NOT_MET`이다.
"""
import hashlib
import json
from collections.abc import Callable
from datetime import timedelta

from ..errors import invalid_input, precondition_not_met


def request_hash(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_idempotent(deps, user_id: str, key: str | None, payload: dict, create: Callable[[], dict]) -> dict:
    if key is None:
        return create()
    key = key.strip()
    if not key or "#" in key or len(key) > deps.config.idempotency.key_max_chars:
        raise invalid_input("Idempotency-Key 형식이 올바르지 않아요.", field="Idempotency-Key")
    expires = (deps.now() + timedelta(hours=deps.config.idempotency.ttl_hours)).isoformat(timespec="seconds")
    begun = deps.users.idem_begin(user_id, key, request_hash(payload), expires)
    if begun.state == "CONFLICT":
        raise precondition_not_met("같은 Idempotency-Key로 다른 요청이 이미 왔어요.")
    if begun.state == "REPLAY":
        if begun.result is None:
            raise precondition_not_met("같은 요청을 아직 처리하고 있어요. 잠시 후 다시 확인해 주세요.")
        return dict(begun.result)
    result = create()
    deps.users.idem_complete(user_id, key, result)
    return result
