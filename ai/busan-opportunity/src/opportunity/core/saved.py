"""저장·목표 담기 (B-09).

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-09, `docs/db-schema.md` §2.3. 테스트: T-09, T-16.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import date, datetime

from ..deps import Deps
from ..models.api import SavedListResponse, SavedView, SaveRequest, SaveResponse, UnsaveResponse
from ..models.base import OppModel
from ..models.enums import SavedKind, TrackEvent, WorkspaceStatus
from ..models.errors import invalid_input, posting_not_found, precondition_not_met
from ..models.posting import PostingLatest
from ..models.user_state import SavedItem
from ..notify import scheduler
from . import clock
from .context import load_context

STATUS_BY_KIND = {SavedKind.INTEREST: WorkspaceStatus.INTEREST, SavedKind.TARGET: WorkspaceStatus.PLANNED}


# ---------------------------------------------------------------- 멱등 처리 (D-31)
def request_hash(scope: str, body: dict) -> str:
    text = json.dumps({"scope": scope, "body": body}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def idempotent[T: OppModel](deps: Deps, user_id: str, key: str | None, scope: str, body: dict, model: type[T],
               run: Callable[[], T]) -> T:
    """`IDEM#` 조건부 쓰기로 한 번만 반영한다. 같은 본문이면 저장된 결과를, 다른 본문이면 409를 돌려준다."""
    if not key:
        return run()
    if "#" in key:
        raise invalid_input("Idempotency-Key에 #을 넣을 수 없어요.", field="Idempotency-Key")
    begin = deps.users.idem_begin(user_id, key, request_hash(scope, body))
    if begin.state == "CONFLICT":
        raise precondition_not_met("같은 Idempotency-Key로 다른 요청을 보냈어요.", idempotencyKey=key)
    if begin.state == "REPLAY":
        if begin.result is None:
            raise precondition_not_met("같은 요청을 아직 처리하고 있어요.", idempotencyKey=key)
        return model.model_validate(begin.result)
    result = run()
    deps.users.idem_finish(user_id, key, result.to_api())
    return result


# ---------------------------------------------------------------- 저장
def _check_id(job_posting_id: str) -> str:
    if not job_posting_id or "#" in job_posting_id:
        raise invalid_input("공고 ID 형식이 올바르지 않아요.", field="jobPostingId")
    return job_posting_id


def _view(deps: Deps, user_id: str, item: SavedItem, posting: PostingLatest | None) -> SavedView:
    workspace_id = item.workspace_id or deps.workspaces.workspace_id(item.job_posting_id)
    status = deps.workspaces.get_status(user_id, workspace_id) or STATUS_BY_KIND[item.kind]
    return SavedView(job_posting_id=item.job_posting_id, kind=item.kind, status=WorkspaceStatus(status),
                     is_busan=item.is_busan, saved_at=item.saved_at, workspace_id=workspace_id,
                     title=posting.title if posting else None,
                     organization=posting.organization if posting else None,
                     closes_at=posting.closes_at if posting else None)


def _ask_leave_reason(deps: Deps, user_id: str, posting: PostingLatest, asked_at: str) -> bool:
    """수도권 공고를 처음 저장할 때만 이유를 묻는다. 이미 이유를 골랐으면 묻지 않는다 (T-09)."""
    if not posting.is_capital_area or deps.users.get_prefs(user_id).leave_reason is not None:
        return False
    if deps.config.leave_reason.ask_once_per_user:
        return deps.users.mark_leave_reason_asked(user_id, asked_at)
    return True


def add_target_posting(deps: Deps, user_id: str, request: SaveRequest, *, idempotency_key: str | None = None,
                       as_of: str | date | datetime | None = None) -> SaveResponse:
    """공고를 저장하거나 목표로 담는다. `OPP#SAVED#`와 워크스페이스를 한 트랜잭션으로 쓴다.

    TARGET이면 마감 D-7·D-3 일정을 만든다. 수도권 공고 첫 저장이면 askLeaveReason=true (사용자당 한 번, T-09).
    같은 Idempotency-Key로 다시 오면 한 번만 반영하고 (T-16), 본문이 다르면 409 PRECONDITION_NOT_MET.
    SAVED 이벤트를 남긴다.
    """
    job_posting_id = _check_id(request.job_posting_id)
    if request.from_alternative_of is not None:
        _check_id(request.from_alternative_of)
    # 없는 공고는 멱등 기록을 남기기 전에 걸러 낸다. 그래야 같은 키로 다시 시도할 수 있다
    if deps.catalog.get_latest(job_posting_id) is None:
        raise posting_not_found(job_posting_id)

    def run() -> SaveResponse:
        posting = deps.catalog.get_latest(job_posting_id)
        if posting is None:
            raise posting_not_found(job_posting_id)
        existing = deps.users.get_saved(user_id, job_posting_id)
        if existing is not None:
            return SaveResponse(saved=_view(deps, user_id, existing, posting), created=False)

        ctx = load_context(deps, user_id, as_of)
        status = STATUS_BY_KIND[request.kind]
        plans = (scheduler.upcoming_target_deadlines(deps, user_id, posting, as_of=ctx.as_of)
                 if request.kind == SavedKind.TARGET else [])
        item = SavedItem(job_posting_id=job_posting_id, kind=request.kind,
                         workspace_id=deps.workspaces.workspace_id(job_posting_id), snapshot_id=posting.snapshot_id,
                         is_busan=posting.is_busan, job_major=posting.job.major,
                         from_alternative_of=request.from_alternative_of, saved_at=clock.iso(ctx.as_of),
                         schedule_names=[p.name for p in plans])
        # 워크스페이스가 이미 있으면 None이 오고, 그 워크스페이스의 상태는 그대로 둔다
        workspace_tx = deps.workspaces.put_tx_item(user_id, job_posting_id, posting.snapshot_id, str(status))
        if not deps.users.put_saved(user_id, item, workspace_tx):
            current = deps.users.get_saved(user_id, job_posting_id) or item
            return SaveResponse(saved=_view(deps, user_id, current, posting), created=False)

        schedules = (scheduler.schedule_target_deadlines(deps, user_id, posting, as_of=ctx.as_of)
                     if request.kind == SavedKind.TARGET else [])
        ask = _ask_leave_reason(deps, user_id, posting, clock.iso(ctx.as_of))
        deps.events.emit(TrackEvent.SAVED, isBusan=posting.is_busan, kind=str(request.kind),
                         fromAlternative=request.from_alternative_of is not None)
        return SaveResponse(saved=_view(deps, user_id, item, posting), schedules=schedules,
                            ask_leave_reason=ask, created=True)

    return idempotent(deps, user_id, idempotency_key, "saved", request.to_api(), SaveResponse, run)


def list_saved(deps: Deps, user_id: str, *, as_of: str | date | datetime | None = None) -> SavedListResponse:
    """저장 목록. 지원 상태는 워크스페이스에서 읽는다. 최근에 저장한 것부터."""
    items = sorted(deps.users.list_saved(user_id), key=lambda s: (s.saved_at, s.job_posting_id), reverse=True)
    postings = deps.catalog.batch_get_latest([s.job_posting_id for s in items]) if items else {}
    return SavedListResponse(items=[_view(deps, user_id, s, postings.get(s.job_posting_id)) for s in items])


def remove_saved(deps: Deps, user_id: str, job_posting_id: str) -> UnsaveResponse:
    """저장을 푼다. 목표 공고의 마감 일정을 먼저 지우고 `OPP#SAVED#`를 지운다.

    일정을 먼저 지워야 중간에 실패해도 다시 부르면 남은 일정까지 지운다. 워크스페이스(분석·첨삭·면접 기록과
    지원 상태)는 공통 백엔드 소유라 지우지 않는다. 다시 저장하면 같은 워크스페이스에 이어 붙는다.
    저장돼 있지 않으면 아무것도 바꾸지 않고 deleted=false (같은 요청을 여러 번 보내도 결과가 같다).
    """
    job_posting_id = _check_id(job_posting_id)
    item = deps.users.get_saved(user_id, job_posting_id)
    if item is None:
        return UnsaveResponse(job_posting_id=job_posting_id, deleted=False)
    for name in item.schedule_names:
        deps.scheduler.delete(name)
    deps.users.delete_saved(user_id, job_posting_id)
    return UnsaveResponse(job_posting_id=job_posting_id, deleted=True)
