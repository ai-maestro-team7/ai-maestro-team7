"""외부 서비스 없이 도는 가짜 포트와 실행기."""

from datetime import datetime, timedelta, timezone

from supervisor.deps import Deps
from supervisor.errors import OutputInvalid
from supervisor.models import ChatReply, DocumentInfo
from supervisor.store.memory import MemoryChatStore

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 20, 14, 30, 5, 123000, tzinfo=KST)

POSTING = {"jobPostingId": "demo-busan-data", "title": "데이터 분석 신입", "organization": "(주)가상데이터",
           "workRegion": "부산 해운대구", "isBusan": True, "isCapitalArea": False, "closesAt": "2026-12-05",
           "deadline": "마감 D-15", "salary": "연 3,400~3,800만 원", "career": "신입", "matchLevel": "잘 맞아요",
           "badges": [], "facts": ["직종 일치: 데이터 분석가"], "isSample": True}
FEED = {"items": [POSTING], "rankingBasis": "비슷하게 맞는 공고 중 부산 근무 공고를 먼저 보여드려요",
        "notice": "적합도는 실제 합격 확률이 아닙니다", "dataAsOf": "2026-11-20T05:00:00+09:00", "stale": False}
POLICY = {"policyId": "demo-busan-rent", "title": "[데모] 부산 청년 월세 지원", "bucket": "OPEN_NOW", "status": "ELIGIBLE",
          "reasons": ["나이 충족"], "manualChecks": [], "benefit": "월 20만 원", "source": "YOUTHCENTER",
          "asOf": "2026-11-20"}
POLICIES = {"items": [POLICY] * 7, "totals": {"guaranteedIfEligible": 240}, "dataAsOf": "2026-11-20T05:00:00+09:00"}


class FakeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


TEAM_POSTING = {**POSTING, "jobPostingId": "demo-team-1", "title": "[시연] 데이터 분석 인턴", "isSample": True}
COMPANY = {"name": "(주)가상데이터", "industry": "데이터 분석업", "source": "부산광역시 (데모)", "asOf": "2026-06-30"}


class FakeOpportunities:
    def __init__(self):
        self.calls = []
        self.search_error = None
        self.feeds = {"OFFICIAL": dict(FEED), "TEAM": {**FEED, "items": [TEAM_POSTING]}}
        self.companies = [COMPANY]

    def search_postings(self, user_id, **kwargs):
        self.calls.append(("search", user_id, kwargs))
        if self.search_error:
            raise self.search_error
        return dict(self.feeds[kwargs["scope"]])

    def find_companies(self, user_id, name):
        self.calls.append(("companies", user_id, {"name": name}))
        return [c for c in self.companies if name.replace(" ", "") in c["name"].replace(" ", "")]

    def match_policies(self, user_id, *, stage):
        self.calls.append(("policies", user_id, {"stage": stage}))
        return dict(POLICIES)

    def ask_policies(self, user_id, question):
        self.calls.append(("ask", user_id, {"question": question}))
        return {"question": question, "answered": True, "answer": "부산청년플랫폼에서 신청해요.", "sources": []}

    def profile_region_code(self, region):
        return {"부산": "26", "서울": "11", "전국": "ALL"}.get(region)


class FakeDocs:
    def __init__(self, documents=None, terms=None, summary=None):
        self.documents = list(documents or [])
        self.terms = list(terms or [])
        self.summary = dict(summary or {})

    def latest_documents(self, user_id):
        return [d for d in self.documents if d.document_id.startswith(user_id + ":") or ":" not in d.document_id]

    def resume_terms(self, user_id):
        return list(self.terms)

    def career_summary(self, user_id):
        return dict(self.summary)


class FakeProfiles:
    def __init__(self, profiles=None):
        self.profiles = dict(profiles or {})
        self.updates = []

    def get_basic_profile(self, user_id):
        return self.profiles.get(user_id)

    def update_basic_profile(self, user_id, patch):
        self.updates.append((user_id, dict(patch)))
        self.profiles[user_id] = {**self.profiles.get(user_id, {}), **patch}
        return self.profiles[user_id]


class FakeMentoring:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def start_job_fit(self, user_id, *, job_posting_id, target_ncs_code, idempotency_key):
        self.calls.append((user_id, job_posting_id, target_ncs_code, idempotency_key))
        if self.error:
            raise self.error
        return {"analysisId": "analysis-0001", "status": "PENDING", "profileId": "profile-1", "profileVersion": 2,
                "documentId": "doc-r1"}


class ScriptedRunner:
    """script(tools_by_name, call) → ChatReply. 실행할 때마다 다음 스크립트를 쓴다. 마지막 것을 되풀이한다."""

    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.runs = []

    def run(self, *, system_prompt, history, message, tools, max_turns):
        self.runs.append({"system_prompt": system_prompt, "history": history, "message": message,
                          "tool_names": [t.__name__ for t in tools], "max_turns": max_turns})
        script = self.scripts[min(len(self.runs) - 1, len(self.scripts) - 1)]
        by_name = {t.__name__: t for t in tools}
        result = script(by_name)
        if isinstance(result, Exception):
            raise result
        return result


class Dispatcher:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)


def cover_letter(doc_id="doc-cl", status="COMPLETED", has_text=True):
    return DocumentInfo(document_id=doc_id, document_type="COVER_LETTER", title="데이터 분석 자소서", status=status,
                        has_text=has_text, updated_at="2026-11-20T10:00:00+09:00")


def build_deps(runner, *, documents=None, terms=None, profiles=None, summary=None):
    clock = {"now": NOW}
    deps = Deps(store=MemoryChatStore(), opportunities=FakeOpportunities(), docs=FakeDocs(documents, terms, summary),
                profiles=FakeProfiles(profiles if profiles is not None else {"demo1": {
                    "desiredJobs": [{"name": "데이터 분석", "ncsCode": "20010105"}], "desiredRegion": "26"}}),
                runner=runner, dispatcher=Dispatcher(), model_id="test-model", now=lambda: clock["now"],
                mentoring=FakeMentoring())
    deps.clock = clock  # 테스트에서 시간을 옮긴다
    return deps


def reply(text="부산 데이터 분석 공고와 청년정책을 찾았어요.", follow_ups=None):
    return ChatReply(reply=text, follow_ups=follow_ups or [])


def invalid(reason="x"):
    return OutputInvalid(reason)
