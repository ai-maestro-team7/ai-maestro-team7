"""카드와 행동 만들기 (개발계획서4 §6). 모델 답이 아니라 이번 턴 도구 기록으로만 만든다."""

from .deps import Deps
from .models import ActionType, CardType, ChatAction, ChatCard
from .tools import CAREER_WORDS, TurnRecord, won_label


def _norm(text: str | None) -> str:
    return "".join((text or "").lower().replace("·", "").split())


def cards(record: TurnRecord) -> list[ChatCard]:
    out: list[ChatCard] = []
    if record.search and "error" not in record.search.feed:
        out += [ChatCard(type=CardType.POSTING, posting=item) for item in record.search.feed.get("items") or []]
    if record.policies and "error" not in record.policies:
        out += [ChatCard(type=CardType.POLICY, policy=item) for item in record.policies.get("items") or []]
    return out


def profile_patch(deps: Deps, chat: dict, saved: dict) -> tuple[dict, list[str]]:
    """대화 조건 가운데 저장된 기본 프로필과 다른 것만 `PUT /api/v1/me/profile` 본문으로 (D-40).

    직무는 이름만으로 맨 앞에 넣고 이름이 같은 기존 항목은 빼며 최대 3개. 지역은 시·도 코드나 ALL로 적을 수 있을 때만.
    기업명은 한 번 쓰는 조건이라 넣지 않는다.
    """
    patch: dict = {}
    labels: list[str] = []
    job = chat.get("jobName")
    saved_jobs = [j for j in saved.get("desiredJobs") or [] if isinstance(j, dict) and j.get("name")]
    if job and (not saved_jobs or _norm(saved_jobs[0]["name"]) != _norm(job)):
        rest = [{k: v for k, v in j.items() if k in ("work24Code", "ncsCode", "name") and v is not None}
                for j in saved_jobs if _norm(j["name"]) != _norm(job)]
        patch["desiredJobs"] = [{"name": job}, *rest][:3]
        labels.append(f"직무 {job}")
    region = chat.get("region")
    if region:
        code = deps.opportunities.profile_region_code(region)
        if code and code != saved.get("desiredRegion"):
            patch["desiredRegion"] = code
            labels.append(f"지역 {region}")
    salary = chat.get("minSalary")
    if salary is not None and salary != saved.get("desiredSalaryMin"):
        patch["desiredSalaryMin"] = salary
        labels.append(won_label(salary))
    career = chat.get("careerType")
    if career and career != saved.get("desiredCareerType"):
        patch["desiredCareerType"] = career
        labels.append(CAREER_WORDS[career])
    return patch, labels


def actions(deps: Deps, record: TurnRecord) -> list[ChatAction]:
    out: list[ChatAction] = []
    search = record.search
    found = bool(search and "error" not in search.feed and search.feed.get("items"))
    if record.saved_conditions is not None:
        out.append(ChatAction(type=ActionType.CONDITIONS_SAVED, conditions=record.saved_conditions))
    elif search and "error" not in search.feed and search.chat_conditions:
        patch, labels = profile_patch(deps, search.chat_conditions, record.saved_profile or {})
        if patch:
            out.append(ChatAction(type=ActionType.SAVE_CONDITIONS, conditions=labels, profile_patch=patch))

    interview = record.interview
    if interview is not None:
        if interview.cover_letter is not None:
            out.append(ChatAction(type=ActionType.START_INTERVIEW, job=interview.job,
                                  document_id=interview.cover_letter.document_id,
                                  title=interview.cover_letter.title or "저장된 자기소개서"))
        else:
            limits = deps.config.cover_letter
            out.append(ChatAction(type=ActionType.REQUEST_COVER_LETTER, job=interview.job,
                                  min_chars=limits.min_chars, max_chars=limits.max_chars))
    elif found:
        job = search.job_name or (search.feed["items"][0].get("title") or "")[:deps.config.interview_job_max_chars]
        if job:
            out.append(ChatAction(type=ActionType.SUGGEST_INTERVIEW, job=job))
    return out


def notice_and_as_of(record: TurnRecord) -> tuple[str | None, str | None]:
    feed = record.search.feed if record.search and "error" not in record.search.feed else {}
    policies = record.policies if record.policies and "error" not in record.policies else {}
    return feed.get("notice"), feed.get("dataAsOf") or policies.get("dataAsOf")
