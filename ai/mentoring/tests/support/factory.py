"""테스트용 Deps 만들기. 메모리 저장소·MockLLM·가짜 텍스트 도구를 묶는다. AWS·네트워크는 부르지 않는다."""
import hashlib
import json
from datetime import datetime
from itertools import count

from mentoring.config import CONFIG_PATH, load_config
from mentoring.deps import KST, Deps
from mentoring.llm.mock import MockLlm
from mentoring.store.memory import MemoryObjectStore, MemoryUserRepo, QueueDispatcher

from .data import good_output
from .fake_text_tools import fake_text_tools

FIXED_NOW = datetime(2026, 11, 21, 10, 0, 0, tzinfo=KST)
KNOWN_UNIT = "2001010501_23v2"


class FakeReference:
    """NCS 기준 데이터 대역. 아는 능력단위 코드만 있다고 답한다."""

    def __init__(self, known: set[str]):
        self.known = known

    def get_competency_unit(self, unit_code: str):
        return {"unitCode": unit_code} if unit_code in self.known else None


def small_config(**document):
    """테스트 이력서가 짧아서 최소 글자 수만 낮춘다. 나머지는 실제 설정 파일 그대로다."""
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["document"]["textMinChars"] = 50
    data["document"].update(document)
    return load_config(data=data)


def hash_user(user_id: str) -> str:
    return hashlib.sha256(f"test:{user_id}".encode()).hexdigest()


def make_deps(responses=None, *, reference="default", config=None) -> Deps:
    counter = count(1)
    return Deps(
        config=config or small_config(),
        users=MemoryUserRepo(),
        objects=MemoryObjectStore(),
        llm=MockLlm(responses or [good_output()], model_id="mock-llm"),
        tasks=QueueDispatcher(),
        text=fake_text_tools(),
        hash_user_id=hash_user,
        reference=FakeReference({KNOWN_UNIT}) if reference == "default" else reference,
        now=lambda: FIXED_NOW,
        new_id=lambda prefix: f"{prefix}-{next(counter):04d}",
    )


def run_pending(deps) -> list[dict]:
    """대기열에 쌓인 작업을 작업 입구로 실행한다 (Lambda 비동기 자기 호출 대신)."""
    from mentoring.api import task_handler

    return [task_handler.handle(message, deps) for message in deps.tasks.drain()]
