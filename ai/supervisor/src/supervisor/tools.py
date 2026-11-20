"""한 턴의 Agent 도구 (개발계획서4 §4).

공고는 공식 데이터(공공 API로 모은 공고)에서 먼저 찾고, 없으면 그렇다고 알린 뒤 팀이 넣어 둔 데이터에서 찾는다 (§9.1).
조건 저장 도구는 인자가 없다. 저장할 값은 코드가 만든 것(이번 검색 또는 바로 앞 답의 저장 묻기)만 쓴다 (D-40).

도구는 턴마다 새로 만든다. 사용자 ID는 도구 인자가 아니라 백엔드가 확인한 값을 클로저로 넣는다 (B T-20과 같은 규칙).
도구 결과는 사실 목록(dict)이고, 카드·행동은 `compose.py`가 여기 남은 기록으로 만든다. 모델이 만든 숫자는 쓰지 않는다.
도구 오류는 예외 대신 `{"error": {code, message}}`로 돌려준다. 메시지는 오류 객체가 가진 사용자용 문장만 쓴다.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .deps import Deps
from .models import DocumentInfo, ToolCall

logger = logging.getLogger("supervisor")

CAREER_TYPES = ("NEW", "EXPERIENCED", "ANY")
CAREER_WORDS = {"NEW": "신입", "EXPERIENCED": "경력", "ANY": "경력 무관"}
TEXT_STATUSES = {"EXTRACTED", "ANALYZING", "REQUIRES_USER_REVIEW", "COMPLETED"}  # 정규화 텍스트가 있는 A 문서 상태
GENERIC_ERROR = "지금은 이 정보를 가져오지 못했어요."
OFFICIAL, TEAM = "OFFICIAL", "TEAM"


@dataclass
class SearchRecord:
    """마지막 공고 검색. chat_conditions는 모델이 이번 대화에서 직접 넘긴 조건만 담는다 (저장 묻기용)."""

    feed: dict
    chat_conditions: dict[str, Any]
    job_name: str | None


@dataclass
class InterviewRecord:
    job: str
    cover_letter: DocumentInfo | None


@dataclass
class DiagnosisRecord:
    """이번 턴에 시작한 A 직무 적합도 분석. 화면이 진단 흐름으로 저장한다."""

    analysis_id: str
    profile_id: str
    profile_version: int
    document_id: str
    target_role: str
    target_ncs_code: str | None
    job_posting_id: str | None


@dataclass
class TurnRecord:
    calls: list[ToolCall] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)  # 숫자 대조에 쓰는 도구 결과 글
    search: SearchRecord | None = None
    policies: dict | None = None
    interview: InterviewRecord | None = None
    saved_profile: dict | None = None
    profile_loaded: bool = False
    saved_conditions: list[str] | None = None  # 이번 턴에 저장 도구가 저장한 조건 (보여 줄 말)
    diagnosis: DiagnosisRecord | None = None


def _clean(value: str | None, max_chars: int = 50) -> str | None:
    text = " ".join((value or "").split())
    return text[:max_chars] if text else None


def _error(error: Exception) -> dict:
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    if isinstance(code, str) and isinstance(message, str):
        return {"error": {"code": code, "message": message}}
    return {"error": {"code": "TOOL_FAILED", "message": GENERIC_ERROR}}


def won_label(manwon: int) -> str:
    return f"연봉 {manwon:,}만 원 이상"


class TurnTools:
    def __init__(self, deps: Deps, user_id: str, *, attachments: list[str] | None = None,
                 pending_save: dict | None = None, recent_postings: list[dict] | None = None,
                 turn_key: str | None = None):
        """pending_save: 바로 앞 답의 저장 묻기 {conditions, profilePatch}. 사용자가 이번 말로 승낙하면 이것을 저장한다.
        recent_postings: 바로 앞 답의 공고 카드 [{jobPostingId, title, …}]. "이 공고"를 가리킬 수 있는 범위다.
        turn_key: 이번 턴의 메시지 ID. 진단 같은 생성 요청의 멱등 키로 쓴다 (다시 돌려도 한 번만 만든다).
        """
        self.deps, self.user_id = deps, user_id
        self.attachments = list(attachments or [])
        self.pending_save = pending_save
        self.recent_postings = list(recent_postings or [])
        self.turn_key = turn_key
        self.record = TurnRecord()

    # ------------------------------------------------------------ 공통
    def saved_profile(self) -> dict:
        if not self.record.profile_loaded:
            self.record.saved_profile = self.deps.profiles.get_basic_profile(self.user_id) or {}
            self.record.profile_loaded = True
        return self.record.saved_profile or {}

    def _call(self, name: str, fn: Callable[[], dict]) -> dict:
        """호출 상한, 처리 시간, 오류 변환. 원문·인자는 로그에 남기지 않는다."""
        if len(self.record.calls) >= self.deps.config.max_tool_calls:
            return {"error": {"code": "TOOL_LIMIT", "message": "이번 답에서 더 찾아볼 수 없어요. 지금까지 찾은 것으로 답해 주세요."}}
        started = time.perf_counter()
        ok = True
        try:
            result = fn()
        except Exception as error:  # noqa: BLE001 - 도구 오류는 모델에게 사실로 돌려준다
            ok = False
            result = _error(error)
            logger.warning("stage=tool tool=%s errorCode=%s", name, result["error"]["code"])
        duration = round((time.perf_counter() - started) * 1000)
        self.record.calls.append(ToolCall(name=name, ok=ok and "error" not in result, duration_ms=duration))
        self.record.texts.append(_flatten(result))
        return result

    def documents(self) -> list[DocumentInfo]:
        return self.deps.docs.latest_documents(self.user_id)

    def cover_letter(self) -> DocumentInfo | None:
        letters = [d for d in self.documents()
                   if d.document_type == "COVER_LETTER" and d.has_text and d.status in TEXT_STATUSES]
        return max(letters, key=lambda d: d.updated_at or "", default=None)

    # ------------------------------------------------------------ 도구 함수
    def functions(self) -> list[Callable[..., dict]]:
        tools = self

        def get_my_status() -> dict:
            """사용자의 저장된 검색 조건, 이력서·자소서 유무, 이력서에서 찾은 역량 이름(확인 전)을 돌려준다.
            이력서로 찾기 전, 면접 준비 전, 사용자 상황을 알아야 할 때 쓴다. 입력은 없다."""
            return tools._call("get_my_status", tools._status)

        def search_job_postings(job_name: str | None = None, keyword: str | None = None,
                                organization: str | None = None, region: str | None = None,
                                min_salary: int | None = None, career_type: str | None = None,
                                use_resume: bool = False) -> dict:
            """채용공고를 최대 5개 찾는다. 사용자가 일자리·채용공고를 찾을 때 쓴다. 사용자가 말한 조건만 넘긴다.

            Args:
                job_name: 찾을 직무 이름 (예: 데이터 분석). 이번 검색에만 쓰고 저장하지 않는다
                keyword: 공고 제목·직무에 들어갈 낱말
                organization: 회사·기관 이름
                region: 부산, 서울, 경남, 수도권, 전국 같은 지역 말
                min_salary: 최소 연봉 (만 원/년. 3천만 원이면 3000)
                career_type: NEW(신입), EXPERIENCED(경력), ANY(무관)
                use_resume: 이력서에서 찾은 역량을 검색에 함께 쓸지
            """
            return tools._call("search_job_postings", lambda: tools._search(
                job_name=job_name, keyword=keyword, organization=organization, region=region,
                min_salary=min_salary, career_type=career_type, use_resume=use_resume))

        def find_youth_policies(stage: str | None = None) -> dict:
            """사용자가 받을 수 있는 청년정책과 판정 이유를 돌려준다. 공고를 찾을 때 함께, 또는 정책을 물을 때 쓴다.

            Args:
                stage: PREPARE(취업 준비), EMPLOYED(취업 후), SETTLE(정착). 모르면 비운다
            """
            return tools._call("find_youth_policies", lambda: tools._policies(stage))

        def ask_youth_policy(question: str) -> dict:
            """청년정책의 내용·자격·신청 방법 질문에 원문 근거와 함께 답한다. answered=false면 답을 만들지 않는다.

            Args:
                question: 정책에 관한 사용자 질문 (예: 부산 청년 월세 지원 신청 방법)
            """
            return tools._call("ask_youth_policy", lambda: tools._ask(question))

        def save_search_conditions() -> dict:
            """검색 조건을 사용자 기본 프로필에 저장한다. 사용자가 이번 말에서 저장하겠다고 분명히 답했을 때만 쓴다
            (예: "응 저장해 줘", "저장할래"). 입력은 없다. 저장할 값은 바로 앞 검색에서 정해진 조건이다."""
            return tools._call("save_search_conditions", tools._save)

        def start_resume_diagnosis(job_posting_id: str | None = None, job_name: str | None = None) -> dict:
            """내 이력서(역량 프로필)를 공고나 희망 직무와 비교하는 이력서·직무 진단을 시작한다. 사용자가 "이 공고와 내
            이력서 비교", "진단해 줘", "자소서 다듬기"처럼 진단·첨삭을 원할 때 쓴다. 결과는 1분쯤 뒤 진단 화면에서 본다.

            Args:
                job_posting_id: 비교할 공고 ID. 이번 검색 결과나 <user_context>의 recentPostings에 있는 것만
                job_name: 공고 없이 희망 직무로 진단할 때 직무 이름 (저장된 희망 직무 가운데 하나)
            """
            return tools._call("start_resume_diagnosis", lambda: tools._diagnose(job_posting_id, job_name))

        def prepare_mock_interview(job: str) -> dict:
            """모의면접 체험을 준비한다. 저장된 자소서가 있는지 확인한다. 사용자가 면접 연습을 원할 때 쓴다.

            Args:
                job: 면접 볼 직무 이름 (1~50자, 예: 데이터 분석)
            """
            return tools._call("prepare_mock_interview", lambda: tools._prepare_interview(job))

        return [get_my_status, search_job_postings, find_youth_policies, ask_youth_policy, save_search_conditions,
                start_resume_diagnosis, prepare_mock_interview]

    # ------------------------------------------------------------ 구현
    def _status(self) -> dict:
        saved = self.saved_profile()
        docs = self.documents()
        terms = self.deps.docs.resume_terms(self.user_id)
        resume = [d for d in docs if d.document_type == "RESUME"]
        return {
            "savedConditions": {
                "desiredJobs": [j.get("name") for j in saved.get("desiredJobs") or [] if j.get("name")],
                "desiredRegion": saved.get("desiredRegion"),
                "desiredSalaryMin": saved.get("desiredSalaryMin"),
                "desiredCareerType": saved.get("desiredCareerType"),
            },
            "documents": [{"documentType": d.document_type, "title": d.title, "status": d.status} for d in docs],
            "attachedThisMessage": [d.document_type for d in docs if d.document_id in self.attachments],
            "resumeReady": bool(terms),
            "resumeProcessing": bool(resume) and not terms and any(d.status not in {"COMPLETED", "FAILED"} for d in resume),
            "resumeSkills": terms,
            "resumeSkillsNote": "이력서에서 찾은 역량이고 사용자가 아직 확인하지 않았어요" if terms else None,
            "hasCoverLetter": self.cover_letter() is not None,
        }

    def _search(self, *, job_name, keyword, organization, region, min_salary, career_type, use_resume) -> dict:
        saved = self.saved_profile()
        chat: dict[str, Any] = {}
        job = _clean(job_name)
        if job:
            chat["jobName"] = job
        place = _clean(region, 20)
        if place:
            chat["region"] = place
        if min_salary is not None:
            if isinstance(min_salary, bool) or not isinstance(min_salary, int) or min_salary < 0:
                return {"error": {"code": "INVALID_INPUT", "message": "최소 연봉은 0 이상의 만 원 단위 숫자로 주세요."}}
            chat["minSalary"] = min_salary
        career = (career_type or "").strip().upper() or None
        if career is not None:
            if career not in CAREER_TYPES:
                return {"error": {"code": "INVALID_INPUT", "message": "career_type은 NEW, EXPERIENCED, ANY 중 하나예요."}}
            chat["careerType"] = career

        # 말하지 않은 조건은 저장된 기본 프로필 값을 쓴다 (개발계획서4 §4)
        use_region = place or saved.get("desiredRegion") or "ALL"
        use_salary = chat.get("minSalary", saved.get("desiredSalaryMin"))
        use_career = chat.get("careerType", saved.get("desiredCareerType"))
        terms = self.deps.docs.resume_terms(self.user_id) if use_resume else []
        org = _clean(organization)

        def find(scope: str) -> dict:
            return self.deps.opportunities.search_postings(
                self.user_id, job_name=job, keyword=_clean(keyword), organization=org, region=use_region,
                min_salary=use_salary, career_type=use_career, query_terms=terms or None, scope=scope)

        # 1. 공식 데이터 → 2. 없으면 팀 데이터 (§9.1). 공식 데이터에 없다는 사실은 모델에 그대로 준다
        team = self.deps.config.team_data
        feed, source = find(OFFICIAL), OFFICIAL
        official_found = bool(feed.get("items"))
        if not official_found and team.fallback:
            feed, source = find(TEAM), TEAM

        applied = [f"직무 {job}" if job else "직무 저장된 희망 직무"]
        applied.append(f"지역 {place}" if place else ("지역 저장된 희망 지역" if saved.get("desiredRegion") else "지역 전국"))
        if use_salary is not None:
            applied.append(won_label(use_salary))
        if use_career:
            applied.append(CAREER_WORDS.get(use_career, use_career))
        if _clean(organization):
            applied.append(f"기업 {_clean(organization)}")
        if use_resume:
            applied.append("이력서 역량 함께 사용" if terms else "이력서 역량 없음 (분석 전이거나 이력서가 없어요)")
        saved_job = next((j.get("name") for j in saved.get("desiredJobs") or [] if j.get("name")), None)
        self.record.search = SearchRecord(feed=feed, chat_conditions=chat, job_name=job or saved_job)
        result = {**feed, "appliedConditions": applied, "officialFound": official_found,
                  "dataSource": "공식 데이터 (공공 API로 모은 공고)" if source == OFFICIAL else team.label}
        if not official_found:
            result["officialNote"] = "공식 데이터(공공 API로 모은 공고)에는 조건에 맞는 공고가 없어요"
            if source == TEAM:
                result["teamDataNote"] = f"아래 공고는 {team.label}예요. 실제 채용 여부는 회사에 확인해야 해요"
        if org and self.deps.config.max_companies:
            companies = self.deps.opportunities.find_companies(self.user_id, org)[:self.deps.config.max_companies]
            result["companies"] = companies or []
            if not companies:
                result["companiesNote"] = f"우리 기업 데이터(부산 청끌·강소·이전기관)에 '{org}'이 없어요"
        from .compose import profile_patch  # 순환 import 방지

        patch, labels = profile_patch(self.deps, chat, saved) if chat else ({}, [])
        if patch:
            result["canSaveConditions"] = labels  # 화면에 [저장하기]가 뜬다. 모델은 한 번 묻기만 한다
        return result

    def _policies(self, stage: str | None) -> dict:
        stage = (stage or "").strip().upper() or None
        result = self.deps.opportunities.match_policies(self.user_id, stage=stage)
        cap = self.deps.config.max_policies
        result = {**result, "items": list(result.get("items") or [])[:cap]}
        self.record.policies = result
        return result

    def _ask(self, question: str) -> dict:
        text = _clean(question, 300)
        if not text:
            return {"error": {"code": "INVALID_INPUT", "message": "질문을 알려 주세요."}}
        return self.deps.opportunities.ask_policies(self.user_id, text)

    def _save(self) -> dict:
        """이번 턴 검색의 저장 대상, 없으면 바로 앞 답의 저장 묻기를 저장한다. 값은 코드가 만든 것만 쓴다."""
        from .compose import profile_patch  # 순환 import 방지

        patch, labels = {}, []
        if self.record.search and "error" not in self.record.search.feed and self.record.search.chat_conditions:
            patch, labels = profile_patch(self.deps, self.record.search.chat_conditions, self.saved_profile())
        if not patch and self.pending_save:
            patch = dict(self.pending_save.get("profilePatch") or {})
            labels = list(self.pending_save.get("conditions") or [])
        allowed = set(self.deps.config.savable_profile_fields)
        patch = {k: v for k, v in patch.items() if k in allowed}
        if not patch:
            return {"error": {"code": "NOTHING_TO_SAVE", "message": "저장할 검색 조건이 없어요. 먼저 조건을 말해 주세요."}}
        self.deps.profiles.update_basic_profile(self.user_id, patch)
        self.record.saved_conditions = labels
        self.record.profile_loaded = False  # 다음에 읽을 때 저장된 값을 다시 읽는다
        return {"saved": True, "conditions": labels, "next": "다음 검색부터 이 조건을 써요"}

    def known_postings(self) -> dict[str, dict]:
        """모델이 가리킬 수 있는 공고: 이번 턴 검색 결과와 바로 앞 답의 공고 카드. 모델이 지어낸 ID는 받지 않는다."""
        rows = list(self.recent_postings)
        if self.record.search and "error" not in self.record.search.feed:
            rows += list(self.record.search.feed.get("items") or [])
        return {r["jobPostingId"]: r for r in rows if isinstance(r, dict) and r.get("jobPostingId")}

    def _diagnose(self, job_posting_id: str | None, job_name: str | None) -> dict:
        if self.deps.mentoring is None:
            return {"error": {"code": "NOT_IMPLEMENTED", "message": "이력서 진단이 아직 연결되지 않았어요."}}
        saved = self.saved_profile()
        posting = None
        target_ncs = None
        pid = (job_posting_id or "").strip() or None
        if pid:
            posting = self.known_postings().get(pid)
            if posting is None:
                return {"error": {"code": "UNKNOWN_POSTING",
                                  "message": "방금 보여 드린 공고 가운데서 골라 주세요. 어떤 공고인지 다시 알려 주세요."}}
            role = posting.get("title") or "선택한 공고"
        else:
            jobs = [j for j in saved.get("desiredJobs") or [] if isinstance(j, dict) and j.get("ncsCode")]
            wanted = _clean(job_name)
            match = next((j for j in jobs if wanted and _norm(j.get("name")) == _norm(wanted)), None) or (jobs[0] if jobs else None)
            if match is None:
                return {"error": {"code": "NEED_TARGET",
                                  "message": "비교할 공고를 먼저 찾아 주세요. 희망 직무를 저장하면 직무 기준으로도 진단할 수 있어요."}}
            target_ncs, role = match["ncsCode"], match.get("name") or "희망 직무"
        key = f"chat-diagnosis-{self.turn_key or 'none'}-{pid or target_ncs}"
        started = self.deps.mentoring.start_job_fit(self.user_id, job_posting_id=pid, target_ncs_code=target_ncs,
                                                    idempotency_key=key[:200])
        self.record.diagnosis = DiagnosisRecord(
            analysis_id=started["analysisId"], profile_id=started["profileId"],
            profile_version=int(started["profileVersion"]), document_id=started.get("documentId") or "",
            target_role=role[:self.deps.config.interview_job_max_chars], target_ncs_code=target_ncs,
            job_posting_id=pid)
        return {"started": True, "status": started.get("status", "PENDING"), "target": role,
                "next": "진단은 1분쯤 걸려요. 화면의 [진단 결과 보기]에서 강점·보완할 역량을 보고, 이어서 자소서 첨삭과 학습 로드맵으로 갈 수 있어요"}

    def _prepare_interview(self, job: str) -> dict:
        name = _clean(job, 200)
        if not name or len(name) > self.deps.config.interview_job_max_chars:
            return {"error": {"code": "INVALID_INPUT",
                              "message": f"직무 이름은 1~{self.deps.config.interview_job_max_chars}자로 주세요."}}
        letter = self.cover_letter()
        self.record.interview = InterviewRecord(job=name, cover_letter=letter)
        limits = self.deps.config.cover_letter
        if letter:
            return {"ready": True, "job": name, "coverLetter": {"title": letter.title or "저장된 자기소개서"},
                    "next": "화면에 [모의면접 시작하기] 버튼이 떠요. 체험용 면접이에요"}
        return {"ready": False, "job": name, "needsCoverLetter": True,
                "next": f"화면에 자소서 입력 칸이 떠요. {limits.min_chars:,}~{limits.max_chars:,}자로 붙여 넣으면 면접 화면으로 넘어가요"}


def _norm(text: str | None) -> str:
    return "".join((text or "").lower().replace("·", "").split())


def _flatten(value: Any) -> str:
    """숫자 대조용으로 결과 값을 한 줄 글로 편다."""
    if isinstance(value, dict):
        return " ".join(f"{k} {_flatten(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(v) for v in value)
    return "" if value is None else str(value)
