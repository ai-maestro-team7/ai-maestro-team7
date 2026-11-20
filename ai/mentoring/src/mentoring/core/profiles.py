"""역량 프로필 조회와 사용자 확인 (Requirement 7, 개발계획서1 F-01 처리 11단계).
확인은 이전 버전을 그대로 두고 다음 번호의 새 버전을 만든다. VERIFIED는 여기서만 생긴다.
"""
from ..errors import invalid_input, not_found, precondition_not_met
from ..models import (
    CareerProfile,
    ConfirmAction,
    ConfirmRequest,
    EvidenceLevel,
    FactStatus,
    Skill,
)
from ..ports import VersionConflict
from .logs import log_event, user_hash

PROFILE_MISSING = "역량 프로필이 아직 없어요. 이력서를 먼저 등록해 주세요."


def get_latest_profile(deps, user_id: str) -> CareerProfile:
    pointer = deps.users.get_profile_pointer(user_id)
    profile = (deps.users.get_profile_version(user_id, pointer.latest_profile_id, pointer.latest_version)
               if pointer else None)
    if profile is None or profile.owner_user_id != user_id:
        raise not_found(PROFILE_MISSING)
    return profile


def confirm_profile(deps, user_id: str, profile_id: str, request: ConfirmRequest) -> CareerProfile:
    if not profile_id or "#" in profile_id:
        raise invalid_input("ID 형식이 올바르지 않아요.", field="profileId")
    pointer = deps.users.get_profile_pointer(user_id)
    if pointer is None or pointer.latest_profile_id != profile_id:  # 남의 프로필과 없는 프로필을 구분하지 않는다
        raise not_found(PROFILE_MISSING)
    if request.base_version != pointer.latest_version:
        raise precondition_not_met("프로필이 그 사이에 바뀌었어요. 최신 프로필을 다시 불러와 주세요.",
                                   latestVersion=pointer.latest_version)
    current = deps.users.get_profile_version(user_id, profile_id, pointer.latest_version)
    if current is None:
        raise not_found(PROFILE_MISSING)

    limits = deps.config.confirmation
    skills = {s.skill_id: s.model_copy(deep=True) for s in current.skills}
    order = [s.skill_id for s in current.skills]
    decided_names: set[str] = set()
    seen: set[str] = set()
    for decision in request.decisions:
        if decision.skill_id in seen:
            raise invalid_input("같은 역량에 확인이 두 번 들어왔어요.", field="decisions", skillId=decision.skill_id)
        seen.add(decision.skill_id)
        skill = skills.get(decision.skill_id)
        if skill is None:
            raise invalid_input("프로필에 없는 역량이에요.", field="decisions", skillId=decision.skill_id)
        decided_names.add(skill.name)
        if decision.action == ConfirmAction.DELETE:
            del skills[decision.skill_id]
        elif decision.action == ConfirmAction.CONFIRM:
            skill.fact_status = FactStatus.VERIFIED
        elif decision.action == ConfirmAction.NOT_HELD:  # 사용자가 미보유를 확인 (UT-03)
            skill.evidence_level = EvidenceLevel.USER_CONFIRMED_GAP
            skill.fact_status = FactStatus.VERIFIED
            skill.evidence_ids = []
        elif decision.action == ConfirmAction.RENAME:
            skill.name = _name(decision.name, limits.name_max_chars)
            skill.fact_status = FactStatus.VERIFIED

    if len(request.additions) > limits.max_additions:
        raise invalid_input("한 번에 추가할 수 있는 역량 수를 넘었어요.", field="additions",
                            maxItems=limits.max_additions)
    existing = {s.name.lower() for s in skills.values()}
    added: list[Skill] = []
    next_number = _next_skill_number(current.skills)
    for addition in request.additions:
        name = _name(addition.name, limits.name_max_chars)
        if name.lower() in existing:
            raise invalid_input("이미 프로필에 있는 역량이에요.", field="additions")
        existing.add(name.lower())
        decided_names.add(name)
        # 서류에 없는 역량을 사용자가 적으면 근거 인용 없이 보유 선언으로 둔다 (Requirement 7 기준 6)
        added.append(Skill(skill_id=f"skill-{next_number}", name=name, evidence_level=EvidenceLevel.SELF_REPORTED,
                           fact_status=FactStatus.VERIFIED, evidence_ids=[]))
        next_number += 1

    kept = [skills[i] for i in order if i in skills] + added
    used = {e for s in kept for e in s.evidence_ids} | {
        e for group in (current.projects, current.experiences, current.certificates) for item in group
        for e in item.evidence_ids}
    profile = current.model_copy(deep=True, update={
        "profile_version": current.profile_version + 1, "based_on_version": current.profile_version,
        "created_by": "USER_CONFIRMATION", "skills": kept,
        "evidence": [e for e in current.evidence if e.evidence_id in used],
        "needs_confirmation": [n for n in current.needs_confirmation if n not in decided_names],
        "created_at": deps.now_iso()})
    try:
        deps.users.put_profile_version(profile, expected_version=current.profile_version)
    except VersionConflict:
        raise precondition_not_met("프로필이 그 사이에 바뀌었어요. 최신 프로필을 다시 불러와 주세요.") from None
    log_event("profile.confirmed", userHash=user_hash(deps, user_id), feature="profile", status="CREATED",
              counts={"decisions": len(request.decisions), "additions": len(added)})
    return profile


def _name(value: str | None, max_chars: int) -> str:
    name = (value or "").strip()
    if not name or len(name) > max_chars:
        raise invalid_input(f"역량 이름은 1자 이상 {max_chars}자 이하로 적어 주세요.", field="name", maxChars=max_chars)
    return name


def _next_skill_number(skills: list[Skill]) -> int:
    numbers = [int(s.skill_id.split("-")[-1]) for s in skills if s.skill_id.split("-")[-1].isdigit()]
    return max(numbers, default=0) + 1
