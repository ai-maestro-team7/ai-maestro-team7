"""공용 테스트 준비. 데모 데이터가 든 메모리 저장소를 쓰고 AWS는 부르지 않는다.

이 파일과 `opportunity.seeds.demo_world`는 여러 워크트리가 같이 쓴다. 고치지 말고, 더 필요한 데이터는
각자 테스트 폴더(`tests/rules`, `tests/unit/<영역>` …) 안에서 deps에 더 넣어 쓴다.
"""

import pytest

from opportunity.config import load_config
from opportunity.seeds import demo_world


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def deps(config):
    """테스트마다 새로 만든다. 저장소를 바꿔도 다른 테스트에 영향이 없다."""
    return demo_world.build_deps(config)


@pytest.fixture
def as_of():
    return demo_world.DEMO_AS_OF
