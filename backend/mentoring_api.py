"""A 멘토링과 공통 백엔드 사이의 REST·비동기 작업 연결."""

from dataclasses import replace
from functools import lru_cache

from common import TeamError, error_response, get_user_id, hash_user_id, new_request_id


def aws_factory():
    try:
        from mentoring.store.factory import build_aws_deps
    except ModuleNotFoundError as error:
        if error.name not in {"mentoring", "mentoring.store", "mentoring.store.factory"}:
            raise
        return None
    return build_aws_deps


@lru_cache(maxsize=1)
def deps(factory):
    # A 패키지가 backend/를 import하지 않고도 회원 탈퇴와 같은 해시를 쓰게 한다.
    return replace(factory(), hash_user_id=hash_user_id)


def not_ready():
    return error_response(
        TeamError(501, "NOT_IMPLEMENTED", "아직 연결되지 않은 기능이에요."),
        new_request_id(),
    )


def handle(event, method, path):
    factory = aws_factory()
    if factory is None:
        return not_ready()
    try:
        user_id = get_user_id(event)
    except TeamError as error:
        return error_response(error, new_request_id())

    from mentoring.api import rest_handler
    from mentoring.config import MissingEnvError

    try:
        aws_deps = deps(factory)
    except MissingEnvError:
        return not_ready()
    return rest_handler.handle(event, aws_deps, user_id)


def run_task(event):
    factory = aws_factory()
    if factory is None:
        # Lambda 비동기 호출에서 성공으로 처리되어 작업이 사라지지 않게 한다.
        raise RuntimeError("멘토링 AWS 의존성이 준비되지 않았어요.")

    from mentoring.api import task_handler

    return task_handler.handle(event, deps(factory))
