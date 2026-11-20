"""테스트용 메모리 저장소. DynamoDB 구현과 같은 조건 규칙을 따른다."""

from ..models import ChatMessage, ChatSession, MessageStatus


class MemoryChatStore:
    def __init__(self):
        self.sessions: dict[tuple[str, str], ChatSession] = {}
        self.messages: dict[tuple[str, str, str], ChatMessage] = {}

    def get_session(self, user_id, session_id):
        return self.sessions.get((user_id, session_id))

    def create_session(self, session):
        key = (session.owner_user_id, session.session_id)
        if key in self.sessions:
            raise ValueError("session exists")
        self.sessions[key] = session

    def begin_turn(self, user_id, session_id, message_id, *, now, stale_before, max_messages):
        session = self.sessions.get((user_id, session_id))
        if session is None or session.message_count + 2 > max_messages:
            return False
        if session.pending_message_id and (session.pending_since or "") >= stale_before:
            return False
        self.sessions[(user_id, session_id)] = session.model_copy(update={
            "pending_message_id": message_id, "pending_since": now, "message_count": session.message_count + 2,
            "last_message_at": now})
        return True

    def end_turn(self, user_id, session_id, message_id, *, now):
        session = self.sessions.get((user_id, session_id))
        if session is not None and session.pending_message_id == message_id:
            self.sessions[(user_id, session_id)] = session.model_copy(update={
                "pending_message_id": None, "pending_since": None, "last_message_at": now})

    def put_message(self, message):
        self.messages[(message.owner_user_id, message.session_id, message.message_id)] = message

    def get_message(self, user_id, session_id, message_id):
        return self.messages.get((user_id, session_id, message_id))

    def list_messages(self, user_id, session_id, limit):
        rows = [m for (u, s, _), m in self.messages.items() if u == user_id and s == session_id]
        return sorted(rows, key=lambda m: m.message_id)[-limit:]

    def claim_message(self, user_id, session_id, message_id, *, now):
        message = self.messages.get((user_id, session_id, message_id))
        if message is None or message.status != MessageStatus.PENDING:
            return False
        self.messages[(user_id, session_id, message_id)] = message.model_copy(update={
            "status": MessageStatus.PROCESSING, "updated_at": now})
        return True

    def finish_message(self, message):
        key = (message.owner_user_id, message.session_id, message.message_id)
        current = self.messages.get(key)
        if current is None or current.status != MessageStatus.PROCESSING:
            return False
        self.messages[key] = message
        return True

    def cancel_message(self, user_id, session_id, message_id, *, now):
        message = self.messages.get((user_id, session_id, message_id))
        if message is None or message.status not in (MessageStatus.PENDING, MessageStatus.PROCESSING):
            return False
        self.messages[(user_id, session_id, message_id)] = message.model_copy(update={
            "status": MessageStatus.CANCELLED, "updated_at": now})
        return True

    def list_sessions(self, user_id):
        return [s for (u, _), s in self.sessions.items() if u == user_id]

    def set_pinned(self, user_id, session_id, pinned):
        session = self.sessions.get((user_id, session_id))
        if session is None:
            return False
        self.sessions[(user_id, session_id)] = session.model_copy(update={"pinned": pinned})
        return True

    def delete_session(self, user_id, session_id):
        if self.sessions.pop((user_id, session_id), None) is None:
            return False
        for key in [k for k in self.messages if k[0] == user_id and k[1] == session_id]:
            del self.messages[key]
        return True
