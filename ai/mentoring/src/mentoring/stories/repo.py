"""Storage contract for Story Bank versions."""
from typing import Protocol

from .models import StoryLatest, StoryVersion


class StoryRepo(Protocol):
    def create_story(self, latest: StoryLatest, version: StoryVersion) -> None: ...

    def put_story_version(
        self,
        latest: StoryLatest,
        version: StoryVersion,
        *,
        expected_version: int,
    ) -> None: ...

    def get_latest(self, user_id: str, story_id: str) -> StoryLatest | None: ...

    def get_version(self, user_id: str, story_id: str, version: int) -> StoryVersion | None: ...

    def list_latest(self, user_id: str) -> list[StoryLatest]: ...
