"""A 공용 테스트 준비. 메모리 저장소와 MockLLM을 쓰고 AWS·네트워크는 부르지 않는다.
여러 작업(Codex 모듈 포함)이 같이 쓰는 파일이다. 더 필요한 준비는 각자 테스트 폴더 안에 둔다.
"""
import pytest

from support.factory import make_deps


@pytest.fixture
def deps():
    return make_deps()
