"""프롬프트 파일 읽기. 버전은 설정 `promptVersion`과 파일 이름이 함께 바뀐다."""

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent
_FILES = {"chat-v1": "system_v1.md", "chat-v2": "system_v2.md", "chat-v3": "system_v3.md", "chat-v4": "system_v4.md",
          "chat-v5": "system_v5.md", "chat-v6": "system_v6.md",
          "chat-v7": "system_v7.md"}


@lru_cache(maxsize=None)
def system_prompt(prompt_version: str) -> str:
    try:
        name = _FILES[prompt_version]
    except KeyError:
        raise ValueError(f"모르는 promptVersion: {prompt_version}") from None
    return (_DIR / name).read_text(encoding="utf-8").strip()
