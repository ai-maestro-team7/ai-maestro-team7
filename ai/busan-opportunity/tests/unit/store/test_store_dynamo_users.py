"""DynamoUsers: 조건부 쓰기, 트랜잭션, 멱등, 알림 페이지, TTL 값, Decimal 왕복."""

from unittest import mock

import pytest
from botocore.exceptions import ClientError

from opportunity.core import clock
from opportunity.models import (
    BasicProfile,
    Notification,
    NotificationType,
    OppError,
    OppPrefs,
    PolicyAlert,
    SavedItem,
    SavedKind,
    Sort,
)
from opportunity.models.user_state import ExplanationCache
from opportunity.seeds import demo_world as w
from opportunity.store.dynamo import DynamoUsers

TABLE = "team07-career-mentor"
AS_OF = w.DEMO_AS_OF


def epoch(iso: str) -> int:
    return int(clock.parse_as_of(iso).timestamp())


def noti(stamp: str, created_at: str = AS_OF) -> Notification:
    return Notification(notification_id=stamp, type=NotificationType.TARGET_DEADLINE, title="t", body="b",
                        created_at=created_at)


def saved(job_posting_id: str = w.SEOUL_DATA, *, busan: bool = False, major: str | None = "D") -> SavedItem:
    return SavedItem(job_posting_id=job_posting_id, kind=SavedKind.INTEREST, snapshot_id="20261121-abcd1234",
                     is_busan=busan, job_major=major, saved_at=AS_OF)


# ---------------------------------------------------------------- tests/unit/test_foundation.py와 같은 시나리오
def test_same_scenario_as_memory_repo(users):
    """`test_user_repo_conditional_writes`를 DynamoDB 구현으로 그대로 돌린다."""
    assert users.mark_leave_reason_asked("demo1", AS_OF) is True
    assert users.mark_leave_reason_asked("demo1", AS_OF) is False
    item = saved()
    tx = {"Put": {"TableName": TABLE, "Item": {"PK": "USER#demo1", "SK": "WORKSPACE#x"},
                  "ConditionExpression": "attribute_not_exists(SK)"}}
    assert users.put_saved("demo1", item, tx) is True
    assert users.put_saved("demo1", item) is False
    assert users.put_alert("demo1", PolicyAlert(policy_id=w.P_JOY_DOUBLE, scheduled_at=AS_OF, schedule_name="n"))
    assert not users.put_alert("demo1", PolicyAlert(policy_id=w.P_JOY_DOUBLE, scheduled_at=AS_OF, schedule_name="n"))
    for stamp in ("20261121T100000-aaaaaaaa", "20261122T100000-bbbbbbbb"):
        assert users.put_notification("demo1", noti(stamp)) is True
        assert users.put_notification("demo1", noti(stamp)) is False
    page, cursor = users.list_notifications("demo1", limit=1)
    assert page[0].notification_id.startswith("20261122") and cursor
    assert users.list_notifications("demo1", cursor=cursor)[0][0].notification_id.startswith("20261121")
    assert [users.incr_immediate_count("demo1", "2026-W47", 2) for _ in range(3)] == [True, True, False]
    assert users.idem_begin("demo1", "k", "h1").state == "NEW"
    users.idem_finish("demo1", "k", {"ok": True})
    assert users.idem_begin("demo1", "k", "h1").result == {"ok": True}
    assert users.idem_begin("demo1", "k", "h2").state == "CONFLICT"


def test_memory_and_dynamo_agree_on_notification_pages(users, deps):
    stamps = [f"2026112{d}T0{h}0000-{d}{h}aaaaaa" for d in range(1, 4) for h in range(1, 4)]
    for repo in (users, deps.users):
        for stamp in stamps:
            repo.put_notification("demo1", noti(stamp))

    def walk(repo, limit):
        out, cursor = [], None
        while True:
            page, cursor = repo.list_notifications("demo1", cursor=cursor, limit=limit)
            out.append([n.notification_id for n in page])
            if not cursor:
                return out

    for limit in (1, 2, 4, 9, 20):
        assert walk(users, limit) == walk(deps.users, limit)
    assert [n for page in walk(users, 4) for n in page] == sorted(stamps, reverse=True)


# ---------------------------------------------------------------- 프로필·설정
def test_basic_profile_is_read_only(users, ddb):
    assert users.get_basic_profile("demo1") is None
    profile = w.build_profiles()["demo1"]
    ddb.Table(TABLE).put_item(Item={"PK": "USER#demo1", "SK": "PROFILE#BASIC", "entityType": "BasicProfile",
                                    **profile.to_api()})
    assert users.get_basic_profile("demo1") == profile
    assert isinstance(users.get_basic_profile("demo1"), BasicProfile)
    assert users.get_basic_profile("demo2") is None


def test_prefs_default_and_roundtrip(users, raw):
    assert users.get_prefs("demo1") == OppPrefs()
    prefs = OppPrefs(sort=Sort.DEADLINE, receiving_policies=["a", "b"],
                     demo_as_of="2026-12-01T09:00:00+09:00")
    users.put_prefs("demo1", prefs)
    assert users.get_prefs("demo1") == prefs
    item = raw(TABLE, "USER#demo1", "OPP#PREFS")
    assert item["ownerUserId"] == "demo1" and item["entityType"] == "OppPrefs" and "expiresAt" not in item
    users.put_prefs("demo1", prefs.model_copy(update={"demo_as_of": None}))  # 값이 사라지면 칸도 사라진다
    assert users.get_prefs("demo1").demo_as_of is None
    assert users.get_prefs("demo2") == OppPrefs()  # 사용자마다 따로


def test_leave_reason_asked_survives_put_prefs(users):
    """설정을 다시 저장해도 이유 질문을 이미 내려 줬다는 표시는 사라지지 않는다 (T-09)."""
    assert users.mark_leave_reason_asked("demo1", AS_OF) is True
    users.put_prefs("demo1", OppPrefs(receiving_policies=["x"]))
    prefs = users.get_prefs("demo1")
    assert prefs.leave_reason_asked_at == AS_OF and prefs.receiving_policies == ["x"]
    assert users.mark_leave_reason_asked("demo1", AS_OF) is False


def test_mark_leave_reason_asked_creates_prefs_item(users, raw):
    assert users.get_prefs("demo3").leave_reason_asked_at is None
    assert users.mark_leave_reason_asked("demo3", AS_OF)
    item = raw(TABLE, "USER#demo3", "OPP#PREFS")
    assert item["leaveReasonAskedAt"] == AS_OF and item["createdAt"] and item["entityType"] == "OppPrefs"
    assert users.get_prefs("demo3").sort == OppPrefs().sort


# ---------------------------------------------------------------- 저장 공고와 워크스페이스 트랜잭션
def workspace_tx(job_posting_id: str, user_id: str = "demo1") -> dict:
    """`backend/workspace.py`의 workspace_put이 주는 모양 그대로 (resource 형식, 실수는 Decimal)."""
    return {"Put": {"TableName": TABLE, "ConditionExpression": "attribute_not_exists(SK)",
                    "Item": {"PK": f"USER#{user_id}", "SK": f"WORKSPACE#ws-{job_posting_id}", "entityType": "Workspace",
                             "schemaVersion": "1.0", "ownerUserId": user_id, "workspaceId": f"ws-{job_posting_id}",
                             "jobPostingId": job_posting_id, "status": "INTEREST", "selectedDocuments": {},
                             "GSI1PK": f"USER#{user_id}#WSLIST", "GSI1SK": "INTEREST#2026-11-21T10:00:00+09:00"}}}


def test_saved_roundtrip_and_layout(users, raw):
    item = saved(w.SEOUL_DATA, busan=False, major="D")
    assert users.put_saved("demo1", item) is True
    assert users.get_saved("demo1", w.SEOUL_DATA) == item
    row = raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}")
    assert row["GSI1PK"] == "WATCH#D" and row["GSI1SK"] == "USER#demo1"  # 비부산 공고만 WATCH#
    assert row["ownerUserId"] == "demo1" and "expiresAt" not in row
    busan = saved(w.BUSAN_DATA, busan=True, major="D")
    users.put_saved("demo1", busan)
    assert "GSI1PK" not in raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.BUSAN_DATA}")
    no_major = saved(w.SEOUL_GAME, busan=False, major=None)
    users.put_saved("demo1", no_major)
    assert "GSI1PK" not in raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_GAME}")
    assert [s.job_posting_id for s in users.list_saved("demo1")] == sorted([w.SEOUL_DATA, w.BUSAN_DATA, w.SEOUL_GAME])
    assert users.get_saved("demo1", "wk24-none") is None and users.list_saved("demo2") == []


def test_delete_saved_removes_only_saved_item(users, raw):
    users.put_saved("demo1", saved(), workspace_tx(w.SEOUL_DATA))
    users.delete_saved("demo1", w.SEOUL_DATA)
    assert raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}") is None and users.list_saved("demo1") == []
    assert raw(TABLE, "USER#demo1", f"WORKSPACE#ws-{w.SEOUL_DATA}")  # 워크스페이스는 남는다
    users.delete_saved("demo1", w.SEOUL_DATA)  # 없는 항목을 지워도 오류가 아니다


def test_update_saved_keeps_created_at_and_fixes_gsi(users, raw, fake_clock):
    item = saved(busan=False, major="D")
    users.put_saved("demo1", item)
    first = raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}")
    fake_clock.advance(minutes=5)
    users.update_saved("demo1", item.model_copy(update={"kind": SavedKind.TARGET, "workspace_id": "ws-x",
                                                        "schedule_names": ["n1", "n2"]}))
    row = raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}")
    assert row["createdAt"] == first["createdAt"] and row["updatedAt"] > first["updatedAt"]
    got = users.get_saved("demo1", w.SEOUL_DATA)
    assert got.kind == SavedKind.TARGET and got.workspace_id == "ws-x" and got.schedule_names == ["n1", "n2"]
    users.update_saved("demo1", got.model_copy(update={"is_busan": True}))
    assert "GSI1PK" not in raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}")


def test_put_saved_transaction_writes_both_items(users, raw):
    assert users.put_saved("demo1", saved(), workspace_tx(w.SEOUL_DATA)) is True
    assert raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}")
    workspace = raw(TABLE, "USER#demo1", f"WORKSPACE#ws-{w.SEOUL_DATA}")
    assert workspace["status"] == "INTEREST" and workspace["GSI1PK"] == "USER#demo1#WSLIST"


def test_put_saved_transaction_duplicate_is_false_and_changes_nothing(users, raw):
    users.put_saved("demo1", saved(), workspace_tx(w.SEOUL_DATA))
    before = raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}")
    again = saved().model_copy(update={"kind": SavedKind.TARGET})
    assert users.put_saved("demo1", again, workspace_tx(w.SEOUL_DATA)) is False
    assert raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}") == before
    assert users.get_saved("demo1", w.SEOUL_DATA).kind == SavedKind.INTEREST


def test_put_saved_transaction_is_all_or_nothing(users, raw, ddb):
    """워크스페이스가 이미 있으면(조건 실패) 저장 공고도 쓰지 않는다."""
    ddb.Table(TABLE).put_item(Item=workspace_tx(w.SEOUL_DATA)["Put"]["Item"])
    assert users.put_saved("demo1", saved(), workspace_tx(w.SEOUL_DATA)) is False
    assert raw(TABLE, "USER#demo1", f"OPP#SAVED#{w.SEOUL_DATA}") is None


def test_put_saved_transaction_other_failures_are_aws_errors(users):
    with mock.patch.object(users.resource.meta.client, "transact_write_items",
                           side_effect=ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"}},
                                                   "TransactWriteItems")):
        with pytest.raises(OppError) as caught:
            users.put_saved("demo1", saved(), workspace_tx(w.SEOUL_DATA))
    assert caught.value.code == "AWS_SERVICE_ERROR" and caught.value.details == {"service": "dynamodb"}


# ---------------------------------------------------------------- 정책 알림 신청
def test_alerts_crud(users, raw):
    alert = PolicyAlert(policy_id=w.P_JOY_DOUBLE, scheduled_at="2026-12-01T09:00:00+09:00", schedule_name="alert-1")
    assert users.get_alert("demo1", w.P_JOY_DOUBLE) is None
    assert users.put_alert("demo1", alert) is True and users.put_alert("demo1", alert) is False
    assert users.get_alert("demo1", w.P_JOY_DOUBLE) == alert
    other = PolicyAlert(policy_id=w.P_DIDIMDOL, scheduled_at=AS_OF, schedule_name="alert-2")
    users.put_alert("demo1", other)
    assert [a.policy_id for a in users.list_alerts("demo1")] == sorted([w.P_JOY_DOUBLE, w.P_DIDIMDOL])
    created = raw(TABLE, "USER#demo1", f"OPP#ALERT#{w.P_JOY_DOUBLE}")["createdAt"]
    users.update_alert("demo1", alert.model_copy(update={"checks": 2}))
    assert users.get_alert("demo1", w.P_JOY_DOUBLE).checks == 2
    assert raw(TABLE, "USER#demo1", f"OPP#ALERT#{w.P_JOY_DOUBLE}")["createdAt"] == created
    users.delete_alert("demo1", w.P_JOY_DOUBLE)
    users.delete_alert("demo1", w.P_JOY_DOUBLE)  # 없어도 오류 없이
    assert users.get_alert("demo1", w.P_JOY_DOUBLE) is None and len(users.list_alerts("demo1")) == 1


# ---------------------------------------------------------------- 알림함
def test_notification_expires_after_retention_days(users, raw, config):
    created = "2026-11-21T10:12:00+09:00"
    users.put_notification("demo1", noti("20261121T101200-a1b2c3d4", created))
    row = raw(TABLE, "USER#demo1", "OPP#NOTI#20261121T101200-a1b2c3d4")
    expected = epoch(created) + config.notifications.retention_days * 86400
    assert int(row["expiresAt"]) == expected and row["ownerUserId"] == "demo1"
    assert row["createdAt"] == created and row["entityType"] == "Notification"


def test_notifications_newest_first_with_cursor(users):
    stamps = [f"202611{d:02d}T090000-{d:08x}" for d in range(10, 17)]
    for stamp in stamps:
        users.put_notification("demo1", noti(stamp))
    users.put_notification("demo2", noti("20261201T090000-ffffffff"))  # 다른 사용자 것은 섞이지 않는다
    page, cursor = users.list_notifications("demo1", limit=3)
    assert [n.notification_id for n in page] == sorted(stamps, reverse=True)[:3] and cursor == page[-1].notification_id
    ids = []
    cursor = None
    while True:
        page, cursor = users.list_notifications("demo1", cursor=cursor, limit=3)
        ids += [n.notification_id for n in page]
        if not cursor:
            break
    assert ids == sorted(stamps, reverse=True)
    last, none_left = users.list_notifications("demo1", limit=7)
    assert len(last) == 7 and none_left is None  # 딱 맞게 끝나면 cursor가 없다
    assert users.list_notifications("demo3") == ([], None)


def test_expired_notifications_are_skipped(users, fake_clock, config):
    users.put_notification("demo1", noti("20260101T090000-aaaaaaaa", "2026-01-01T09:00:00+09:00"))  # 90일 지남
    users.put_notification("demo1", noti("20261120T090000-bbbbbbbb", "2026-11-20T09:00:00+09:00"))
    assert [n.notification_id for n in users.list_notifications("demo1")[0]] == ["20261120T090000-bbbbbbbb"]
    fake_clock.advance(days=config.notifications.retention_days + 1)
    assert users.list_notifications("demo1") == ([], None)


def test_mark_notification_read(users):
    users.put_notification("demo1", noti("20261121T100000-aaaaaaaa"))
    assert users.mark_notification_read("demo1", "20261121T100000-aaaaaaaa") is True
    assert users.list_notifications("demo1")[0][0].read is True
    assert users.mark_notification_read("demo1", "20261121T100000-none0000") is False  # 없는 알림은 만들지 않는다
    assert users.mark_notification_read("demo2", "20261121T100000-aaaaaaaa") is False  # 남의 알림도 못 건드린다
    assert users.list_notifications("demo2") == ([], None)


# ---------------------------------------------------------------- 즉시 알림 한도
def test_immediate_count_cap_per_week(users, raw):
    assert [users.incr_immediate_count("demo1", "2026-W47", 2) for _ in range(4)] == [True, True, False, False]
    assert int(raw(TABLE, "USER#demo1", "OPP#CAP#2026-W47")["immediateCount"]) == 2  # 거부된 시도는 세지 않는다
    assert users.incr_immediate_count("demo1", "2026-W48", 2) is True  # 다음 주는 새로 센다
    assert users.incr_immediate_count("demo2", "2026-W47", 2) is True  # 사용자마다 따로
    assert users.incr_immediate_count("demo1", "2026-W49", 0) is False
    assert raw(TABLE, "USER#demo1", "OPP#CAP#2026-W49") is None


def test_immediate_count_expires_two_weeks_after_the_week_starts(users, raw):
    users.incr_immediate_count("demo1", "2026-W47", 2)
    row = raw(TABLE, "USER#demo1", "OPP#CAP#2026-W47")
    assert int(row["expiresAt"]) == epoch("2026-11-30T00:00:00+09:00")  # W47은 11-16(월)에 시작, 2주 뒤


# ---------------------------------------------------------------- 설명 문장 캐시
def test_explanation_cache_roundtrip_and_ttl(users, raw, fake_clock, config):
    cache = ExplanationCache(job_posting_id=w.BUSAN_DATA, sentences=["하나", "둘"], facts_hash="abc", created_at=AS_OF)
    assert users.get_explanation("demo1", w.BUSAN_DATA) is None
    users.put_explanation("demo1", cache, config.explanation.cache_hours)
    assert users.get_explanation("demo1", w.BUSAN_DATA) == cache
    row = raw(TABLE, "USER#demo1", f"OPP#EXPL#{w.BUSAN_DATA}")
    assert int(row["expiresAt"]) == epoch(AS_OF) + config.explanation.cache_hours * 3600
    assert users.get_explanation("demo2", w.BUSAN_DATA) is None
    fake_clock.advance(hours=config.explanation.cache_hours, seconds=1)
    assert users.get_explanation("demo1", w.BUSAN_DATA) is None  # TTL 삭제가 늦어도 만료된 문장은 안 쓴다
    newer = cache.model_copy(update={"created_at": clock.iso(fake_clock()), "facts_hash": "new"})
    users.put_explanation("demo1", newer, 24)
    assert users.get_explanation("demo1", w.BUSAN_DATA).facts_hash == "new"


# ---------------------------------------------------------------- 멱등 (D-31)
def test_idempotency_three_states(users, raw, fake_clock):
    assert users.idem_begin("demo1", "key-1", "hash-a").state == "NEW"
    in_flight = users.idem_begin("demo1", "key-1", "hash-a")  # 아직 끝나지 않은 같은 요청
    assert in_flight.state == "REPLAY" and in_flight.result is None
    users.idem_finish("demo1", "key-1", {"saved": True, "score": 0.5, "nested": {"ids": ["a", "b"]}})
    replay = users.idem_begin("demo1", "key-1", "hash-a")
    assert replay.state == "REPLAY" and replay.result == {"saved": True, "score": 0.5, "nested": {"ids": ["a", "b"]}}
    assert isinstance(replay.result["score"], float)
    assert users.idem_begin("demo1", "key-1", "hash-b").state == "CONFLICT"
    assert users.idem_begin("demo2", "key-1", "hash-b").state == "NEW"  # 키는 사용자마다
    row = raw(TABLE, "USER#demo1", "IDEM#key-1")
    assert row["requestHash"] == "hash-a" and row["ownerUserId"] == "demo1"
    assert int(row["expiresAt"]) == epoch(AS_OF) + 24 * 3600


def test_idempotency_key_is_reusable_after_24_hours(users, fake_clock):
    users.idem_begin("demo1", "key-1", "hash-a")
    users.idem_finish("demo1", "key-1", {"old": True})
    fake_clock.advance(hours=24, seconds=1)  # TTL 삭제 전이어도 보관 시간이 지났으면 새 요청
    assert users.idem_begin("demo1", "key-1", "hash-b").state == "NEW"
    assert users.idem_begin("demo1", "key-1", "hash-b").result is None


def test_idem_finish_does_not_create_missing_row(users, raw):
    users.idem_finish("demo1", "never-begun", {"x": 1})
    assert raw(TABLE, "USER#demo1", "IDEM#never-begun") is None


# ---------------------------------------------------------------- 공통 규칙
def test_every_item_has_meta_fields(users, raw):
    users.put_prefs("demo1", OppPrefs())
    users.put_saved("demo1", saved())
    users.put_alert("demo1", PolicyAlert(policy_id=w.P_JOY_DOUBLE, scheduled_at=AS_OF, schedule_name="n"))
    users.put_notification("demo1", noti("20261121T100000-aaaaaaaa"))
    users.incr_immediate_count("demo1", "2026-W47", 2)
    users.put_explanation("demo1", ExplanationCache(job_posting_id=w.BUSAN_DATA, sentences=[], facts_hash="h",
                                                    created_at=AS_OF), 24)
    users.idem_begin("demo1", "k", "h")
    for sk in ("OPP#PREFS", f"OPP#SAVED#{w.SEOUL_DATA}", f"OPP#ALERT#{w.P_JOY_DOUBLE}",
               "OPP#NOTI#20261121T100000-aaaaaaaa", "OPP#CAP#2026-W47", f"OPP#EXPL#{w.BUSAN_DATA}", "IDEM#k"):
        row = raw(TABLE, "USER#demo1", sk)
        assert row, sk
        assert row["entityType"] and row["schemaVersion"] and row["createdAt"] and row["updatedAt"], sk
        assert row["ownerUserId"] == "demo1", sk
    for sk in ("OPP#NOTI#20261121T100000-aaaaaaaa", "OPP#CAP#2026-W47", f"OPP#EXPL#{w.BUSAN_DATA}", "IDEM#k"):
        assert "expiresAt" in raw(TABLE, "USER#demo1", sk), sk  # TTL은 임시 데이터에만
    for sk in ("OPP#PREFS", f"OPP#SAVED#{w.SEOUL_DATA}", f"OPP#ALERT#{w.P_JOY_DOUBLE}"):
        assert "expiresAt" not in raw(TABLE, "USER#demo1", sk), sk


def test_users_never_scan_and_stay_in_own_partition(users, ddb):
    from botocore.client import BaseClient
    original = BaseClient._make_api_call
    seen = []

    def spy(self, operation_name, api_params):
        seen.append(operation_name)
        return original(self, operation_name, api_params)

    with mock.patch.object(BaseClient, "_make_api_call", spy):
        users.put_saved("demo1", saved())
        users.list_saved("demo1")
        users.list_alerts("demo1")
        users.list_notifications("demo1")
        users.get_prefs("demo1")
        users.idem_begin("demo1", "k", "h")
    assert "Scan" not in seen and seen
    users.put_saved("demo2", saved(w.BUSAN_DATA, busan=True))
    assert [s.job_posting_id for s in users.list_saved("demo1")] == [w.SEOUL_DATA]


def test_float_decimal_roundtrip(users):
    users.idem_begin("demo1", "k", "h")
    payload = {"a": 0.1, "b": [1.5, {"c": 0.25}], "d": 2, "e": 1.0, "f": "x"}
    users.idem_finish("demo1", "k", payload)
    got = users.idem_begin("demo1", "k", "h").result
    assert got == {"a": 0.1, "b": [1.5, {"c": 0.25}], "d": 2, "e": 1, "f": "x"}
    assert isinstance(got["a"], float) and isinstance(got["d"], int)


def test_invalid_week_key_is_rejected(users):
    with pytest.raises(OppError) as caught:
        users.incr_immediate_count("demo1", "2026-47", 2)
    assert caught.value.code == "INVALID_INPUT"


def test_boto_errors_become_aws_service_error(users):
    boom = ClientError({"Error": {"Code": "InternalServerError", "Message": "USER#demo1 boom"}}, "Query")
    with mock.patch.object(users.t.table, "query", side_effect=boom):
        with pytest.raises(OppError) as caught:
            users.list_saved("demo1")
    assert caught.value.code == "AWS_SERVICE_ERROR" and caught.value.retryable
    assert "demo1" not in caught.value.message


def test_table_name_comes_from_env_when_not_given(ddb, monkeypatch):
    monkeypatch.setenv("TABLE_CAREER_MENTOR", TABLE)
    assert DynamoUsers(ddb, retention_days=90).t.name == TABLE
    monkeypatch.delenv("TABLE_CAREER_MENTOR")
    with pytest.raises(Exception, match="TABLE_CAREER_MENTOR"):
        DynamoUsers(ddb, retention_days=90)
