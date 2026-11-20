"""메모리 구현. DynamoDB 키 구조(db-schema §2.1·§2.5)를 그대로 흉내 내서, AWS 구현과 같은 조건을 테스트한다.
값은 저장할 때와 읽을 때 모두 복사해 호출한 쪽이 저장된 값을 몰래 바꾸지 못하게 한다.
"""
from collections import deque

from ..models import CareerProfile, DocumentLatest, DocumentVersion, ProfilePointer, Task, TaskStatus
from ..ports import AlreadyExists, IdemResult, VersionConflict


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


class MemoryUserRepo:
    def __init__(self):
        self.items: dict[tuple[str, str], object] = {}

    def _put(self, user_id: str, sk: str, value) -> None:
        self.items[(_pk(user_id), sk)] = value.model_copy(deep=True) if hasattr(value, "model_copy") else dict(value)

    def _get(self, user_id: str, sk: str):
        value = self.items.get((_pk(user_id), sk))
        if value is None:
            return None
        return value.model_copy(deep=True) if hasattr(value, "model_copy") else dict(value)

    # ---------------------------------------------------------------- 문서
    def create_document(self, latest: DocumentLatest, version: DocumentVersion) -> None:
        uid = latest.owner_user_id
        if self._get(uid, f"DOC_LATEST#{latest.document_id}") is not None:
            raise AlreadyExists(latest.document_id)
        self._put(uid, f"DOC_LATEST#{latest.document_id}", latest)
        self._put(uid, f"DOC#{version.document_id}#V#{version.version:04d}", version)

    def save_document(self, latest: DocumentLatest, version: DocumentVersion) -> None:
        uid = latest.owner_user_id
        self._put(uid, f"DOC_LATEST#{latest.document_id}", latest)
        self._put(uid, f"DOC#{version.document_id}#V#{version.version:04d}", version)

    def get_document_latest(self, user_id: str, document_id: str) -> DocumentLatest | None:
        return self._get(user_id, f"DOC_LATEST#{document_id}")

    def get_document_version(self, user_id: str, document_id: str, version: int) -> DocumentVersion | None:
        return self._get(user_id, f"DOC#{document_id}#V#{version:04d}")

    # ---------------------------------------------------------------- 역량 프로필
    def get_profile_pointer(self, user_id: str) -> ProfilePointer | None:
        return self._get(user_id, "PROFILE#LATEST")

    def get_profile_version(self, user_id: str, profile_id: str, version: int) -> CareerProfile | None:
        return self._get(user_id, f"PROFILE#{profile_id}#V#{version:04d}")

    def put_profile_version(self, profile: CareerProfile, *, expected_version: int | None) -> None:
        uid = profile.owner_user_id
        pointer = self.get_profile_pointer(uid)
        current = pointer.latest_version if pointer else None
        if current != expected_version:
            raise VersionConflict(f"expected {expected_version}, found {current}")
        sk = f"PROFILE#{profile.profile_id}#V#{profile.profile_version:04d}"
        if self._get(uid, sk) is not None:
            raise VersionConflict(f"version {profile.profile_version} exists")
        self._put(uid, sk, profile)
        self._put(uid, "PROFILE#LATEST", ProfilePointer(owner_user_id=uid, latest_profile_id=profile.profile_id,
                                                        latest_version=profile.profile_version))

    def list_profile_versions(self, user_id: str) -> list[CareerProfile]:
        """테스트 확인용 (Query `begins_with(SK, "PROFILE#")`)."""
        pk = _pk(user_id)
        found = [v for (p, sk), v in self.items.items() if p == pk and sk.startswith("PROFILE#") and "#V#" in sk]
        return sorted((v.model_copy(deep=True) for v in found), key=lambda p: p.profile_version)

    # ---------------------------------------------------------------- 작업
    def create_task(self, task: Task) -> None:
        if self._get(task.owner_user_id, f"TASK#{task.task_id}") is not None:
            raise AlreadyExists(task.task_id)
        self._put(task.owner_user_id, f"TASK#{task.task_id}", task)

    def get_task(self, user_id: str, task_id: str) -> Task | None:
        return self._get(user_id, f"TASK#{task_id}")

    def update_task(self, task: Task, *, expected_status: TaskStatus) -> bool:
        stored = self.get_task(task.owner_user_id, task.task_id)
        if stored is None or stored.status != expected_status:
            return False
        self._put(task.owner_user_id, f"TASK#{task.task_id}", task)
        return True

    # ---------------------------------------------------------------- 멱등 키
    def idem_begin(self, user_id: str, key: str, request_hash: str, expires_at: str) -> IdemResult:
        stored = self._get(user_id, f"IDEM#{key}")
        if stored is None:
            self._put(user_id, f"IDEM#{key}", {"requestHash": request_hash, "result": None, "expiresAt": expires_at})
            return IdemResult("NEW")
        if stored["requestHash"] != request_hash:
            return IdemResult("CONFLICT")
        return IdemResult("REPLAY", stored["result"])

    def idem_complete(self, user_id: str, key: str, result: dict) -> None:
        stored = self._get(user_id, f"IDEM#{key}") or {}
        stored["result"] = dict(result)
        self._put(user_id, f"IDEM#{key}", stored)


class MemoryObjectStore:
    def __init__(self):
        self.objects: dict[str, str] = {}

    def put_text(self, key: str, text: str) -> None:
        self.objects[key] = text

    def get_text(self, key: str) -> str | None:
        return self.objects.get(key)


class QueueDispatcher:
    """보낸 작업을 쌓아 두기만 한다. 테스트가 `drain()`으로 꺼내 작업 입구에 넣는다."""

    def __init__(self):
        self.queue: deque[dict] = deque()
        self.sent: list[dict] = []

    def dispatch(self, message: dict) -> None:
        self.queue.append(message)
        self.sent.append(message)

    def drain(self) -> list[dict]:
        items = list(self.queue)
        self.queue.clear()
        return items
