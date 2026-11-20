"""DynamoDB 대화 저장소 (moto). 조건부 쓰기 규칙이 메모리 구현과 같은지 본다."""

import boto3
import pytest
from moto import mock_aws

from supervisor.models import ChatMessage, ChatSession, MessageStatus, Role
from supervisor.store.dynamo import DynamoChatStore

NOW = "2026-11-20T14:30:05+09:00"


@pytest.fixture
def store():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
        table = dynamodb.create_table(
            TableName="test-cm", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                  {"AttributeName": "SK", "AttributeType": "S"}])
        yield DynamoChatStore(table)


def message(mid, role=Role.USER, status=MessageStatus.COMPLETED, content="안녕"):
    return ChatMessage(session_id="chat-1", message_id=mid, owner_user_id="u-1", role=role, status=status,
                       content=content, created_at=NOW, updated_at=NOW)


def test_session_turn_and_messages(store):
    store.create_session(ChatSession(session_id="chat-1", owner_user_id="u-1", title="안녕", created_at=NOW,
                                     last_message_at=NOW))
    with pytest.raises(Exception):
        store.create_session(ChatSession(session_id="chat-1", owner_user_id="u-1", title="x", created_at=NOW,
                                         last_message_at=NOW))
    assert store.get_session("u-2", "chat-1") is None

    assert store.begin_turn("u-1", "chat-1", "m-2", now=NOW, stale_before="2026-11-20T14:27:05+09:00", max_messages=4)
    assert not store.begin_turn("u-1", "chat-1", "m-4", now=NOW, stale_before="2026-11-20T14:27:05+09:00",
                                max_messages=4)  # 진행 중
    assert store.begin_turn("u-1", "chat-1", "m-4", now=NOW, stale_before="2026-11-20T14:40:00+09:00",
                            max_messages=4)  # 멈춘 턴 이어받기
    store.end_turn("u-1", "chat-1", "m-2", now=NOW)  # 남의 턴은 풀지 않는다
    assert store.get_session("u-1", "chat-1").pending_message_id == "m-4"
    store.end_turn("u-1", "chat-1", "m-4", now=NOW)
    session = store.get_session("u-1", "chat-1")
    assert session.pending_message_id is None and session.message_count == 4
    assert not store.begin_turn("u-1", "chat-1", "m-6", now=NOW, stale_before=NOW, max_messages=4)  # 한도

    store.put_message(message("m-1"))
    store.put_message(message("m-2", Role.ASSISTANT, MessageStatus.PENDING, ""))
    assert store.claim_message("u-1", "chat-1", "m-2", now=NOW)
    assert not store.claim_message("u-1", "chat-1", "m-2", now=NOW)
    assert not store.claim_message("u-1", "chat-1", "m-9", now=NOW)
    assert store.get_message("u-1", "chat-1", "m-2").status == MessageStatus.PROCESSING
    assert [m.message_id for m in store.list_messages("u-1", "chat-1", 10)] == ["m-1", "m-2"]
    assert [m.message_id for m in store.list_messages("u-1", "chat-1", 1)] == ["m-2"]
    assert store.list_messages("u-2", "chat-1", 10) == []


def test_cancel_finish_list_pin_delete(store):
    """멈추기·끝내기 조건, 대화 목록·고정·삭제. Scan 없이 GetItem·Query·쓰기만 쓴다."""
    from unittest import mock

    from botocore.client import BaseClient

    seen = []
    original = BaseClient._make_api_call

    def spy(self, operation_name, api_params):
        seen.append(operation_name)
        return original(self, operation_name, api_params)

    with mock.patch.object(BaseClient, "_make_api_call", spy):
        for sid, user in (("chat-1", "u-1"), ("chat-10", "u-1"), ("chat-1", "u-2")):
            store.create_session(ChatSession(session_id=sid, owner_user_id=user, title=sid, created_at=NOW,
                                             last_message_at=NOW))
        store.put_message(message("m-1"))
        store.put_message(message("m-2", Role.ASSISTANT, MessageStatus.PENDING, ""))

        # 멈추기: 만드는 중일 때만
        assert store.cancel_message("u-1", "chat-1", "m-2", now=NOW)
        assert not store.cancel_message("u-1", "chat-1", "m-2", now=NOW)  # 이미 멈춤
        assert not store.cancel_message("u-1", "chat-1", "m-1", now=NOW)  # 끝난 메시지
        assert not store.cancel_message("u-1", "chat-1", "m-9", now=NOW)  # 없는 메시지
        assert not store.claim_message("u-1", "chat-1", "m-2", now=NOW)  # 멈춘 답은 실행하지 않는다
        assert not store.finish_message(message("m-2", Role.ASSISTANT, MessageStatus.COMPLETED, "늦은 답"))
        assert store.get_message("u-1", "chat-1", "m-2").status == MessageStatus.CANCELLED

        # 실행이 잡은(PROCESSING) 답만 끝낼 수 있다
        store.put_message(message("m-4", Role.ASSISTANT, MessageStatus.PENDING, ""))
        assert not store.finish_message(message("m-4", Role.ASSISTANT, MessageStatus.COMPLETED, "답"))
        assert store.claim_message("u-1", "chat-1", "m-4", now=NOW)
        assert store.finish_message(message("m-4", Role.ASSISTANT, MessageStatus.COMPLETED, "답"))
        assert store.get_message("u-1", "chat-1", "m-4").content == "답"
        assert not store.finish_message(message("m-5", Role.ASSISTANT, MessageStatus.COMPLETED, "답"))

        # 목록·고정
        assert sorted(s.session_id for s in store.list_sessions("u-1")) == ["chat-1", "chat-10"]
        assert store.set_pinned("u-1", "chat-10", True) and store.get_session("u-1", "chat-10").pinned
        assert not store.set_pinned("u-1", "chat-9", True)

        # 삭제: 그 대화의 메시지만 지운다 (CHAT#chat-1#은 CHAT#chat-10#과 겹치지 않는다)
        store.put_message(ChatMessage(session_id="chat-10", message_id="m-1", owner_user_id="u-1", role=Role.USER,
                                      content="x", created_at=NOW, updated_at=NOW))
        assert store.delete_session("u-1", "chat-1")
        assert store.get_session("u-1", "chat-1") is None and store.list_messages("u-1", "chat-1", 10) == []
        assert [m.message_id for m in store.list_messages("u-1", "chat-10", 10)] == ["m-1"]
        assert store.get_session("u-2", "chat-1") is not None  # 남의 같은 ID 대화는 그대로
        assert not store.delete_session("u-1", "chat-1")
    assert seen and "Scan" not in seen

