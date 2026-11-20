"""In-memory Story Bank used by tests."""
from mentoring.ports import AlreadyExists, VersionConflict

from .models import StoryLatest, StoryVersion


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


class MemoryStoryRepo:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], StoryLatest | StoryVersion] = {}

    def _get(self, user_id: str, sk: str):
        value = self.items.get((_pk(user_id), sk))
        return value.model_copy(deep=True) if value is not None else None

    def _put(self, user_id: str, sk: str, value) -> None:
        self.items[(_pk(user_id), sk)] = value.model_copy(deep=True)

    def create_story(self, latest: StoryLatest, version: StoryVersion) -> None:
        if self.get_latest(latest.owner_user_id, latest.story_id) is not None:
            raise AlreadyExists(latest.story_id)
        self._put(latest.owner_user_id, f"STORY_LATEST#{latest.story_id}", latest)
        self._put(version.owner_user_id, f"STORY#{version.story_id}#V#{version.version:04d}", version)

    def put_story_version(
        self,
        latest: StoryLatest,
        version: StoryVersion,
        *,
        expected_version: int,
    ) -> None:
        pointer = self.get_latest(latest.owner_user_id, latest.story_id)
        if pointer is None or pointer.latest_version != expected_version:
            raise VersionConflict(f"expected {expected_version}")
        sk = f"STORY#{version.story_id}#V#{version.version:04d}"
        if self._get(version.owner_user_id, sk) is not None:
            raise VersionConflict(f"version {version.version} exists")
        self._put(latest.owner_user_id, f"STORY_LATEST#{latest.story_id}", latest)
        self._put(version.owner_user_id, sk, version)

    def get_latest(self, user_id: str, story_id: str) -> StoryLatest | None:
        return self._get(user_id, f"STORY_LATEST#{story_id}")

    def get_version(self, user_id: str, story_id: str, version: int) -> StoryVersion | None:
        return self._get(user_id, f"STORY#{story_id}#V#{version:04d}")

    def list_latest(self, user_id: str) -> list[StoryLatest]:
        pk = _pk(user_id)
        values = [
            item.model_copy(deep=True)
            for (item_pk, sk), item in self.items.items()
            if item_pk == pk and sk.startswith("STORY_LATEST#")
        ]
        return sorted(values, key=lambda item: (item.updated_at, item.story_id), reverse=True)
