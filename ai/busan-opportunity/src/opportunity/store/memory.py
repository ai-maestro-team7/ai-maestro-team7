"""메모리 구현. 테스트와 로컬 실행에 쓴다. AWS를 부르지 않는다.

DynamoDB 구현(`store/dynamo.py`)과 같은 규칙을 지킨다: 조건부 쓰기, 최신순 정렬, 멱등 처리.
"""

import math
from collections.abc import Sequence
from datetime import datetime

from ..models.policy import Policy
from ..models.posting import AltCandidates, CompanyRecord, PostingLatest, PostingSnapshot
from ..models.profile import BasicProfile, OppPrefs
from ..models.user_state import ExplanationCache, Notification, PolicyAlert, SavedItem
from ..ports import IdemResult, VectorHit


# ---------------------------------------------------------------- catalog
class MemoryCatalog:
    def __init__(self):
        self.snapshots: dict[tuple[str, str], PostingSnapshot] = {}
        self.latest: dict[str, PostingLatest] = {}
        self.alts: dict[str, AltCandidates] = {}
        self.policies: dict[str, Policy] = {}
        self.companies: dict[str, CompanyRecord] = {}
        self._data_as_of: str | None = None

    def get_latest(self, job_posting_id):
        return self.latest.get(job_posting_id)

    def batch_get_latest(self, job_posting_ids):
        return {i: self.latest[i] for i in job_posting_ids if i in self.latest}

    def get_snapshot(self, job_posting_id, snapshot_id):
        return self.snapshots.get((job_posting_id, snapshot_id))

    def get_alts(self, job_posting_id):
        return self.alts.get(job_posting_id)

    def query_postings_by_sido(self, sido, *, closes_from, limit=100):
        rows = [p for p in self.latest.values()
                if not p.work_region.unknown and p.work_region.sido == sido and p.closes_at >= closes_from]
        return sorted(rows, key=lambda p: (p.closes_at, p.job_posting_id))[:limit]

    def query_policies(self, region_key):
        rows = [p for p in self.policies.values() if p.region_key() == region_key]
        return sorted(rows, key=lambda p: (p.apply_end, p.policy_id))

    def get_policy(self, policy_id):
        return self.policies.get(policy_id)

    def get_company(self, company_id):
        return self.companies.get(company_id)

    def list_companies(self, sido):
        return sorted((c for c in self.companies.values() if c.sido == sido), key=lambda c: c.name)

    def data_as_of(self):
        return self._data_as_of

    def put_snapshot(self, snapshot):
        self.snapshots[(snapshot.job_posting_id, snapshot.snapshot_id)] = snapshot

    def put_latest(self, latest):
        self.latest[latest.job_posting_id] = latest

    def put_alts(self, alts):
        self.alts[alts.job_posting_id] = alts

    def put_policy(self, policy):
        self.policies[policy.policy_id] = policy

    def put_company(self, company):
        self.companies[company.company_id] = company

    def set_data_as_of(self, iso):
        self._data_as_of = iso


# ---------------------------------------------------------------- career-mentor
class MemoryUsers:
    def __init__(self):
        self.profiles: dict[str, BasicProfile] = {}
        self.prefs: dict[str, OppPrefs] = {}
        self.saved: dict[tuple[str, str], SavedItem] = {}
        self.alerts: dict[tuple[str, str], PolicyAlert] = {}
        self.notifications: dict[tuple[str, str], Notification] = {}
        self.caps: dict[tuple[str, str], int] = {}
        self.explanations: dict[tuple[str, str], ExplanationCache] = {}
        self.idem: dict[tuple[str, str], dict] = {}
        self.workspace_txs: list[dict] = []  # put_saved와 함께 쓴 워크스페이스 항목 (테스트 확인용)

    def get_basic_profile(self, user_id):
        return self.profiles.get(user_id)

    def get_prefs(self, user_id):
        return self.prefs.get(user_id) or OppPrefs()

    def put_prefs(self, user_id, prefs):
        self.prefs[user_id] = prefs

    def mark_leave_reason_asked(self, user_id, asked_at):
        prefs = self.get_prefs(user_id)
        if prefs.leave_reason_asked_at:
            return False
        self.prefs[user_id] = prefs.model_copy(update={"leave_reason_asked_at": asked_at})
        return True

    def get_saved(self, user_id, job_posting_id):
        return self.saved.get((user_id, job_posting_id))

    def list_saved(self, user_id):
        rows = [v for (u, _), v in self.saved.items() if u == user_id]
        return sorted(rows, key=lambda s: s.job_posting_id)

    def put_saved(self, user_id, item, workspace_tx=None):
        if (user_id, item.job_posting_id) in self.saved:
            return False
        self.saved[(user_id, item.job_posting_id)] = item
        if workspace_tx is not None:
            self.workspace_txs.append(workspace_tx)
        return True

    def update_saved(self, user_id, item):
        self.saved[(user_id, item.job_posting_id)] = item

    def delete_saved(self, user_id, job_posting_id):
        self.saved.pop((user_id, job_posting_id), None)

    def get_alert(self, user_id, policy_id):
        return self.alerts.get((user_id, policy_id))

    def list_alerts(self, user_id):
        rows = [v for (u, _), v in self.alerts.items() if u == user_id]
        return sorted(rows, key=lambda a: a.policy_id)

    def put_alert(self, user_id, alert):
        if (user_id, alert.policy_id) in self.alerts:
            return False
        self.alerts[(user_id, alert.policy_id)] = alert
        return True

    def update_alert(self, user_id, alert):
        self.alerts[(user_id, alert.policy_id)] = alert

    def delete_alert(self, user_id, policy_id):
        self.alerts.pop((user_id, policy_id), None)

    def put_notification(self, user_id, notification):
        if (user_id, notification.notification_id) in self.notifications:
            return False
        self.notifications[(user_id, notification.notification_id)] = notification
        return True

    def list_notifications(self, user_id, *, cursor=None, limit=20):
        rows = sorted((v for (u, _), v in self.notifications.items() if u == user_id),
                      key=lambda n: n.notification_id, reverse=True)  # ID가 시각으로 시작해 최신순이 된다
        if cursor:
            rows = [n for n in rows if n.notification_id < cursor]
        page = rows[:limit]
        next_cursor = page[-1].notification_id if len(rows) > limit else None
        return page, next_cursor

    def mark_notification_read(self, user_id, notification_id):
        item = self.notifications.get((user_id, notification_id))
        if item is None:
            return False
        self.notifications[(user_id, notification_id)] = item.model_copy(update={"read": True})
        return True

    def incr_immediate_count(self, user_id, week_key, limit):
        count = self.caps.get((user_id, week_key), 0)
        if count >= limit:
            return False
        self.caps[(user_id, week_key)] = count + 1
        return True

    def get_explanation(self, user_id, job_posting_id):
        return self.explanations.get((user_id, job_posting_id))

    def put_explanation(self, user_id, cache, ttl_hours):
        self.explanations[(user_id, cache.job_posting_id)] = cache

    def idem_begin(self, user_id, key, request_hash):
        row = self.idem.get((user_id, key))
        if row is None:
            self.idem[(user_id, key)] = {"requestHash": request_hash, "result": None}
            return IdemResult("NEW")
        if row["requestHash"] != request_hash:
            return IdemResult("CONFLICT")
        return IdemResult("REPLAY", row["result"])

    def idem_finish(self, user_id, key, result):
        self.idem[(user_id, key)]["result"] = result


# ---------------------------------------------------------------- 벡터
def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _match(metadata: dict, condition: dict) -> bool:
    """S3 Vectors 필터의 일부만 지원한다: 같음, $eq, $ne, $gte, $lte, $in, $and."""
    for key, expected in condition.items():
        if key == "$and":
            if not all(_match(metadata, c) for c in expected):
                return False
            continue
        actual = metadata.get(key)
        if isinstance(expected, dict):
            for op, value in expected.items():
                if op == "$eq" and actual != value:
                    return False
                if op == "$ne" and actual == value:
                    return False
                if op == "$gte" and not (actual is not None and actual >= value):
                    return False
                if op == "$lte" and not (actual is not None and actual <= value):
                    return False
                if op == "$in" and actual not in value:
                    return False
        elif actual != expected:
            return False
    return True


class MemoryVectors:
    def __init__(self):
        self.rows: dict[str, tuple[list[float], dict]] = {}

    def query(self, vector, *, top_k, filter=None):
        hits = [VectorHit(key, cosine(vector, v), dict(meta)) for key, (v, meta) in self.rows.items()
                if not filter or _match(meta, filter)]
        return sorted(hits, key=lambda h: (-h.similarity, h.key))[:top_k]

    def put(self, key, vector, metadata):
        self.rows[key] = (list(vector), dict(metadata))

    def get(self, key):
        row = self.rows.get(key)
        return list(row[0]) if row else None

    def delete(self, key):
        self.rows.pop(key, None)


class KeywordEmbedder:
    """낱말 묶음마다 축 하나를 주는 가짜 임베딩. 같은 직무군이면 유사도가 높게 나온다."""

    AXES = (
        ("데이터", "분석", "통계", "data", "analyst", "sql", "빅데이터"),
        ("회계", "사무", "경영", "총무", "세무", "재무"),
        ("금융", "행정", "공공", "공사", "공단", "기금"),
        ("게임", "클라이언트", "그래픽스"),
        ("개발", "엔지니어", "백엔드", "서버", "python"),
        ("마케팅", "홍보", "콘텐츠"),
        ("영업", "판매", "고객"),
        ("디자인", "ux", "ui"),
    )

    def embed(self, text, *, kind="document"):
        lowered = text.lower()
        vector = [float(sum(lowered.count(word) for word in words)) for words in self.AXES]
        vector.append(0.05)  # 낱말이 하나도 없어도 0 벡터가 되지 않게
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector]


# ---------------------------------------------------------------- 일정·메일·지표·워크스페이스
class MemoryScheduler:
    def __init__(self):
        self.schedules: dict[str, tuple[datetime, dict]] = {}

    def create_once(self, name, at, payload):
        if name in self.schedules:
            return False
        self.schedules[name] = (at, payload)
        return True

    def delete(self, name):
        self.schedules.pop(name, None)

    def due(self, as_of: datetime) -> list[tuple[str, datetime, dict]]:
        """as_of까지 울릴 일정 (이른 순). 데모 시간 앞당기기와 테스트에서 쓴다."""
        rows = [(name, at, payload) for name, (at, payload) in self.schedules.items() if at <= as_of]
        return sorted(rows, key=lambda r: (r[1], r[0]))


class MemoryMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, user_id, subject, body):
        self.sent.append((user_id, subject, body))
        return True


class MemoryEvents:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def emit(self, event, **dimensions):
        self.events.append((str(event), dimensions))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]


class MemoryWorkspaces:
    def __init__(self):
        self.status: dict[tuple[str, str], str] = {}

    def workspace_id(self, job_posting_id):
        return f"ws-{job_posting_id}"

    def put_tx_item(self, user_id, job_posting_id, snapshot_id, status):
        ws_id = self.workspace_id(job_posting_id)
        if (user_id, ws_id) in self.status:
            return None
        self.status[(user_id, ws_id)] = status
        return {"Put": {"workspaceId": ws_id, "snapshotId": snapshot_id, "status": status}}

    def get_status(self, user_id, workspace_id):
        return self.status.get((user_id, workspace_id))

    def set_status(self, user_id, workspace_id, status):
        self.status[(user_id, workspace_id)] = status


class MemoryRawStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get(self, key):
        return self.objects.get(key)

    def list(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))


class MemorySecrets:
    def __init__(self, values: dict[str, str] | None = None):
        self.values = values or {}

    def get(self, name):
        return self.values[name]


class ScriptedLlm:
    """정해 둔 답을 차례로 돌려주는 가짜 LLM. 받은 프롬프트는 calls에 남는다."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def invoke(self, system, user, *, max_tokens=1024):
        self.calls.append((system, user))
        return self.replies.pop(0) if self.replies else ""


class MemoryRetriever:
    """낱말이 겹치는 만큼 점수를 주는 가짜 검색. `docs`는 {doc_id: (text, metadata)}다."""

    def __init__(self, docs: dict[str, tuple[str, dict]] | None = None):
        self.docs = docs or {}
        self.calls: list[tuple[str, int, dict | None]] = []

    def retrieve(self, query, *, top_k, filter=None):
        from ..ports import RetrievedDoc

        self.calls.append((query, top_k, filter))
        words = [w for w in query.replace("?", " ").split() if len(w) > 1]
        rows = []
        for doc_id, (text, metadata) in self.docs.items():
            score = sum(text.count(w) for w in words)
            if score:
                rows.append(RetrievedDoc(doc_id, text, float(score), dict(metadata)))
        return sorted(rows, key=lambda r: (-r.score, r.doc_id))[:top_k]
