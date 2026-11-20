"""채팅 한 턴 (개발계획서4 §7·§8).

start_turn: 요청 검사 → 대화 잡기 → 사용자 메시지·빈 답(PENDING) 저장 → 비동기 실행 보내기 → 202 본문
run_turn:   PENDING → PROCESSING → Strands Agent 실행 → 답 검사(1회 재시도) → 카드·행동 조립 → COMPLETED / FAILED
cancel_message: 만드는 중인 답 → CANCELLED, 대화 잠금 풀기. 늦게 끝난 실행의 결과는 저장하지 않는다
list_sessions·update_session·delete_session: 채팅 화면의 대화 목록, 고정, 삭제
"""

import logging
import time
from datetime import timedelta

from pydantic import ValidationError

from . import compose
from .checks import check_reply
from .context import build_user_context, context_block
from .deps import Deps
from .errors import (
    OutputInvalid,
    SupervisorError,
    document_not_found,
    invalid_input,
    message_not_found,
    session_full,
    session_not_found,
    turn_in_progress,
)
from .models import ActionType, ChatMessage, ChatReply, ChatRequest, ChatSession, ErrorInfo, MessageStatus, Role
from .prompts import system_prompt
from .tools import TurnTools

logger = logging.getLogger("supervisor")

EVENT_KEY = "agentTask"  # 백엔드가 채팅 턴 실행 이벤트를 알아보는 키
MAX_ATTEMPTS = 2  # 처음 1번 + 재시도 1번 (LLM 출력 규칙)


def _check_id(value: str | None, field: str, prefix: str | None = None) -> str:
    text = (value or "").strip()
    if not text or "#" in text or "%23" in text.lower() or len(text) > 100 or (prefix and not text.startswith(prefix)):
        raise invalid_input(f"{field} 형식이 올바르지 않아요.")
    return text


# ---------------------------------------------------------------- 시작 (202)
def start_turn(deps: Deps, user_id: str, body: dict) -> dict:
    cfg = deps.config
    try:
        request = ChatRequest.model_validate(body if isinstance(body, dict) else {})
    except ValidationError:
        raise invalid_input("요청 형식이 올바르지 않아요.") from None
    message = (request.message or "").strip()
    if not 1 <= len(message) <= cfg.message_max_chars:
        raise invalid_input(f"메시지는 1~{cfg.message_max_chars:,}자로 보내 주세요.")
    if len(request.attachments) > cfg.max_attachments:
        raise invalid_input(f"문서는 한 번에 {cfg.max_attachments}개까지 붙일 수 있어요.")
    attachment_ids = [_check_id(a.document_id, "documentId") for a in request.attachments]
    if attachment_ids:
        mine = {d.document_id for d in deps.docs.latest_documents(user_id)}
        if any(doc_id not in mine for doc_id in attachment_ids):
            raise document_not_found()  # 남의 문서도 없는 것과 같게 404

    now = deps.now()
    now_iso = deps.now_iso()
    if request.session_id:
        session_id = _check_id(request.session_id, "sessionId", "chat-")
        if deps.store.get_session(user_id, session_id) is None:
            raise session_not_found()
    else:
        session_id = deps.new_session_id()
        deps.store.create_session(ChatSession(session_id=session_id, owner_user_id=user_id,
                                              title=message[:cfg.title_max_chars], created_at=now_iso,
                                              last_message_at=now_iso))

    user_message_id = deps.new_message_id(now)
    reply_id = deps.new_message_id(now + timedelta(milliseconds=1))  # 사용자 메시지 바로 뒤로 정렬
    stale_before = (now - timedelta(seconds=cfg.stale_seconds)).isoformat(timespec="seconds")
    if not deps.store.begin_turn(user_id, session_id, reply_id, now=now_iso, stale_before=stale_before,
                                 max_messages=cfg.max_messages_per_session):
        session = deps.store.get_session(user_id, session_id)
        if session is not None and session.message_count + 2 > cfg.max_messages_per_session:
            raise session_full()
        raise turn_in_progress()

    common = {"session_id": session_id, "owner_user_id": user_id, "created_at": now_iso, "updated_at": now_iso}
    deps.store.put_message(ChatMessage(message_id=user_message_id, role=Role.USER, content=message,
                                       attachments=request.attachments, **common))
    deps.store.put_message(ChatMessage(message_id=reply_id, role=Role.ASSISTANT, status=MessageStatus.PENDING,
                                       **common))
    deps.dispatcher.dispatch({EVENT_KEY: {"userId": user_id, "sessionId": session_id, "messageId": reply_id}})
    return {"sessionId": session_id, "messageId": reply_id, "userMessageId": user_message_id,
            "status": MessageStatus.PENDING.value}


# ---------------------------------------------------------------- 실행 (비동기)
def _history(messages: list[ChatMessage], current_id: str, keep: int) -> tuple[list[dict], ChatMessage | None]:
    """지난 대화(사용자 말과 완료된 답의 짝)와 이번 사용자 메시지. 모델에는 카드 없이 글만 넘긴다."""
    before = [m for m in messages if m.message_id < current_id]
    current_user = next((m for m in reversed(before) if m.role == Role.USER), None)
    pairs: list[dict] = []
    pending_user: ChatMessage | None = None
    for m in before:
        if current_user is not None and m.message_id == current_user.message_id:
            break
        if m.role == Role.USER:
            pending_user = m
        elif pending_user is not None and m.status == MessageStatus.COMPLETED and m.content:
            pairs += [{"role": "user", "text": pending_user.content}, {"role": "assistant", "text": m.content}]
            pending_user = None
    size = keep - keep % 2  # 짝 단위로 자른다 (user로 시작)
    return (pairs[-size:] if size > 0 else []), current_user


def _model_message(user_message: ChatMessage, context: str) -> str:
    """사용자 문맥(데이터)과 이번 사용자 말을 태그로 나눠 넘긴다."""
    text = user_message.content
    if user_message.attachments:
        text += f"\n\n(이번 메시지에 문서 {len(user_message.attachments)}개를 붙였어요.)"
    return f"{context}\n\n<user_message>\n{text}\n</user_message>"


def _pending_save(messages: list[ChatMessage], user_message: ChatMessage) -> dict | None:
    """바로 앞 Agent 답의 저장 묻기. 더 오래된 답의 것은 쓰지 않는다 (사용자가 무엇에 승낙했는지 분명하게)."""
    before = [m for m in messages if m.message_id < user_message.message_id and m.role == Role.ASSISTANT]
    if not before or before[-1].status != MessageStatus.COMPLETED:
        return None
    action = next((a for a in before[-1].actions if a.type == ActionType.SAVE_CONDITIONS), None)
    return {"conditions": action.conditions, "profilePatch": action.profile_patch} if action else None


def _recent_postings(messages: list[ChatMessage], user_message: ChatMessage) -> list[dict]:
    """바로 앞 Agent 답의 공고 카드. 사용자가 멈춘 답은 건너뛴다 (화면에 카드가 없었다)."""
    before = [m for m in messages if m.message_id < user_message.message_id and m.role == Role.ASSISTANT
              and m.status != MessageStatus.CANCELLED]
    if not before:
        return []
    return [c.posting for c in before[-1].cards if c.posting]


def _run_once(deps: Deps, user_id: str, history: list[dict], user_message: ChatMessage,
              pending_save: dict | None = None, recent: list[dict] | None = None,
              turn_key: str | None = None) -> tuple[ChatReply, TurnTools]:
    tools = TurnTools(deps, user_id, attachments=[a.document_id for a in user_message.attachments],
                      pending_save=pending_save, recent_postings=recent, turn_key=turn_key)
    context = context_block(build_user_context(tools))  # 이력서·경험 요약. 저장하지 않고 턴마다 새로 만든다
    reply = deps.runner.run(system_prompt=system_prompt(deps.config.prompt_version), history=history,
                            message=_model_message(user_message, context), tools=tools.functions(),
                            max_turns=deps.config.max_turns)
    sources = [*tools.record.texts, context, user_message.content, *(h["text"] for h in history)]
    return check_reply(deps.config, reply, sources), tools


def run_turn(deps: Deps, task: dict) -> dict:
    """예외를 밖으로 던지지 않는다 (비동기 호출이라 받을 쪽이 없다). 결과는 메시지 상태로 남긴다."""
    started = time.perf_counter()
    try:
        user_id, session_id, message_id = task["userId"], task["sessionId"], task["messageId"]
    except (KeyError, TypeError):
        return {"status": "SKIPPED", "reason": "INVALID_TASK"}
    user_hash = deps.hash_user_id(user_id)
    if not deps.store.claim_message(user_id, session_id, message_id, now=deps.now_iso()):
        logger.info("stage=chat.skipped userHash=%s messageId=%s", user_hash, message_id)
        return {"messageId": message_id, "status": "SKIPPED", "reason": "NOT_PENDING"}

    message = deps.store.get_message(user_id, session_id, message_id)  # 강한 일관 읽기 (store/dynamo.py)
    if message is None:
        # 잡은 턴을 풀어 다음 메시지가 막히지 않게 한다
        deps.store.end_turn(user_id, session_id, message_id, now=deps.now_iso())
        logger.warning("stage=chat.missing userHash=%s messageId=%s", user_hash, message_id)
        return {"messageId": message_id, "status": "SKIPPED", "reason": "NOT_FOUND"}
    error: ErrorInfo | None = None
    reply: ChatReply | None = None
    tools: TurnTools | None = None
    try:
        messages = deps.store.list_messages(user_id, session_id, deps.config.max_messages_per_session)
        history, user_message = _history(messages, message_id, deps.config.history_messages)
        if user_message is None:
            raise SupervisorError(500, "INTERNAL_ERROR", "대화를 읽지 못했어요.", True)
        pending = _pending_save(messages, user_message)
        recent = _recent_postings(messages, user_message)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                reply, tools = _run_once(deps, user_id, history, user_message, pending, recent, message_id)
                break
            except OutputInvalid as invalid:
                logger.warning("stage=chat.check attempt=%d userHash=%s reason=%s", attempt, user_hash, invalid.reason)
        if reply is None:
            error = ErrorInfo(code="AI_OUTPUT_INVALID", message="답을 만들지 못했어요. 다시 보내 주세요.", retryable=True)
    except SupervisorError as e:
        error = ErrorInfo(code=e.code, message=e.message, retryable=e.retryable)
    except Exception as e:  # noqa: BLE001 - Bedrock 권한·한도·네트워크·SDK 오류
        logger.warning("stage=chat.error userHash=%s errorType=%s", user_hash, type(e).__name__)
        error = ErrorInfo(code="AWS_SERVICE_ERROR", message="AI 서비스에 연결하지 못했어요. 잠시 후 다시 보내 주세요.",
                          retryable=True)

    now_iso = deps.now_iso()
    base = message.model_copy(update={"updated_at": now_iso, "model_id": deps.model_id,
                                      "prompt_version": deps.config.prompt_version,
                                      "config_version": deps.config.config_version})
    if error is None and reply is not None and tools is not None:
        notice, data_as_of = compose.notice_and_as_of(tools.record)
        resume_document = tools.attached_resume()
        final = base.model_copy(update={
            "status": MessageStatus.COMPLETED, "content": reply.reply, "follow_ups": reply.follow_ups,
            "cards": compose.cards(tools.record),
            "actions": compose.actions(deps, tools.record,
                                       resume_document_id=resume_document.document_id if resume_document else None),
            "tool_calls": tools.record.calls, "notice": notice, "data_as_of": data_as_of})
    else:
        final = base.model_copy(update={"status": MessageStatus.FAILED, "error": error,
                                        "tool_calls": tools.record.calls if tools else []})
    if not deps.store.finish_message(final):
        # 그사이 사용자가 멈췄거나 대화를 지웠다. 늦게 나온 결과는 버린다 (cancel_message가 잠금도 이미 풀었다)
        deps.store.end_turn(user_id, session_id, message_id, now=now_iso)
        logger.info("stage=chat.dropped userHash=%s messageId=%s durationMs=%d", user_hash, message_id,
                    round((time.perf_counter() - started) * 1000))
        return {"messageId": message_id, "status": "SKIPPED", "reason": "CANCELLED"}
    deps.store.end_turn(user_id, session_id, message_id, now=now_iso)
    logger.info("stage=chat.finished userHash=%s messageId=%s status=%s tools=%s errorCode=%s durationMs=%d",
                user_hash, message_id, final.status.value, ",".join(c.name for c in final.tool_calls),
                error.code if error else None, round((time.perf_counter() - started) * 1000))
    return {"messageId": message_id, "status": final.status.value, "errorCode": error.code if error else None}


# ---------------------------------------------------------------- 조회
def get_message(deps: Deps, user_id: str, session_id: str, message_id: str) -> dict:
    session_id = _check_id(session_id, "sessionId", "chat-")
    message_id = _check_id(message_id, "messageId")
    message = deps.store.get_message(user_id, session_id, message_id)
    if message is None or message.owner_user_id != user_id:
        raise message_not_found()
    return message.view()


def get_session(deps: Deps, user_id: str, session_id: str) -> dict:
    session_id = _check_id(session_id, "sessionId", "chat-")
    session = deps.store.get_session(user_id, session_id)
    if session is None or session.owner_user_id != user_id:
        raise session_not_found()
    messages = deps.store.list_messages(user_id, session_id, deps.config.max_messages_per_session)
    return {**session.view(), "messages": [m.view() for m in messages if m.owner_user_id == user_id]}


# ---------------------------------------------------------------- 멈추기
def cancel_message(deps: Deps, user_id: str, session_id: str, message_id: str) -> dict:
    """만드는 중인 답을 멈춘다. 이미 돌고 있는 모델은 끝까지 갈 수 있지만 그 결과는 저장하지 않는다 (finish_message 조건).

    멈추면 대화 잠금을 바로 풀어 다음 말을 보낼 수 있다. 그사이 답이 끝났으면 끝난 답을 그대로 돌려준다.
    """
    session_id = _check_id(session_id, "sessionId", "chat-")
    message_id = _check_id(message_id, "messageId")
    message = deps.store.get_message(user_id, session_id, message_id)
    if message is None or message.owner_user_id != user_id or message.role != Role.ASSISTANT:
        raise message_not_found()
    now_iso = deps.now_iso()
    if deps.store.cancel_message(user_id, session_id, message_id, now=now_iso):
        deps.store.end_turn(user_id, session_id, message_id, now=now_iso)
        logger.info("stage=chat.cancelled userHash=%s messageId=%s", deps.hash_user_id(user_id), message_id)
        message = deps.store.get_message(user_id, session_id, message_id) or message
    return message.view()


# ---------------------------------------------------------------- 대화 목록·고정·삭제
def list_sessions(deps: Deps, user_id: str) -> dict:
    """내 대화 목록. 고정한 대화가 먼저, 그 안과 밖은 최근에 말한 순서. 메시지는 넣지 않는다."""
    sessions = [s for s in deps.store.list_sessions(user_id) if s.owner_user_id == user_id]
    sessions.sort(key=lambda s: s.last_message_at, reverse=True)
    sessions.sort(key=lambda s: not s.pinned)  # 안정 정렬이라 고정한 대화 안에서도 최근 순서가 남는다
    return {"sessions": [s.view() for s in sessions[:deps.config.max_sessions_listed]]}


def update_session(deps: Deps, user_id: str, session_id: str, body: dict) -> dict:
    """대화 고정·고정 해제. 지금은 `pinned`만 바꿀 수 있다."""
    session_id = _check_id(session_id, "sessionId", "chat-")
    if not isinstance(body, dict) or set(body) != {"pinned"} or not isinstance(body["pinned"], bool):
        raise invalid_input("pinned(true 또는 false)만 바꿀 수 있어요.")
    session = deps.store.get_session(user_id, session_id)
    if session is None or session.owner_user_id != user_id or not deps.store.set_pinned(user_id, session_id,
                                                                                         body["pinned"]):
        raise session_not_found()
    return session.model_copy(update={"pinned": body["pinned"]}).view()


def delete_session(deps: Deps, user_id: str, session_id: str) -> dict:
    """대화와 메시지를 모두 지운다. 답을 만드는 중이어도 지운다 (늦게 끝난 결과는 finish_message가 버린다)."""
    session_id = _check_id(session_id, "sessionId", "chat-")
    session = deps.store.get_session(user_id, session_id)
    if session is None or session.owner_user_id != user_id or not deps.store.delete_session(user_id, session_id):
        raise session_not_found()
    logger.info("stage=chat.deleted userHash=%s", deps.hash_user_id(user_id))
    return {"sessionId": session_id, "deleted": True}
