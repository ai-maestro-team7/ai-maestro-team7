"""역량 표준 분류 후보 (#104, 개발계획서1 §4.3 `name` + `ncsUnitCode`, 제안서 4.1 "NCS 기반 역량 표준화").

역량 이름(`name`)은 이력서 표현 그대로 자유롭게 두고, 표준 분류는 공식 목록에서만 고른다.
- 직무 능력: 희망 직무(`PROFILE#BASIC.desiredJobs[].ncsCode`)의 NCS 능력단위
- 공통 능력: NCS 직업기초능력 34개 (하위영역)
목록은 `team07-reference`(Deps.ncs)에서 정확히 읽는다. 의미 검색은 쓰지 않는다 (tech.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .logs import log_event, user_hash

_NCS_CODE = re.compile(r"^\d{8}$")


@dataclass(frozen=True)
class UnitOption:
    code: str
    name: str
    job: str


@dataclass(frozen=True)
class BasicOption:
    id: str
    name: str  # "의사소통능력 > 경청능력"


@dataclass
class Taxonomy:
    ncs_codes: list[str] = field(default_factory=list)
    units: list[UnitOption] = field(default_factory=list)
    basic: list[BasicOption] = field(default_factory=list)

    @property
    def unit_codes(self) -> set[str]:
        return {u.code for u in self.units}

    @property
    def basic_ids(self) -> set[str]:
        return {b.id for b in self.basic}


def desired_ncs_codes(basic_profile: dict | None, limit: int) -> list[str]:
    jobs = (basic_profile or {}).get("desiredJobs") or []
    codes = [str(j.get("ncsCode")) for j in jobs if isinstance(j, dict) and j.get("ncsCode")]
    return [c for c in dict.fromkeys(codes) if _NCS_CODE.match(c)][:limit]


def load_taxonomy(deps, user_id: str) -> Taxonomy:
    """후보 목록을 만든다. 기준 데이터를 못 읽으면 빈 목록(코드 없이 추출)으로 둔다."""
    ncs = getattr(deps, "ncs", None)
    if ncs is None:
        return Taxonomy()
    cfg = deps.config.extraction
    store = getattr(deps, "analyses", None)
    try:
        basic_profile = store.get_basic_profile(user_id) if store is not None else None
        codes = desired_ncs_codes(basic_profile, cfg.max_desired_jobs)
        units: list[UnitOption] = []
        for code in codes:
            profile = ncs.get_job_profile(code)
            job = profile.name if profile else code
            units.extend(UnitOption(code=u.unit_code, name=u.name, job=job) for u in ncs.list_units(code))
        basic = [BasicOption(id=s.skill_id, name=f"{s.name} > {s.sub_area_name}")
                 for s in ncs.list_basic_skills()]
    except Exception as error:  # noqa: BLE001 - 분류 후보가 없어도 역량 추출은 계속한다
        log_event("taxonomy.unavailable", userHash=user_hash(deps, user_id), errorCode=type(error).__name__)
        return Taxonomy()
    return Taxonomy(ncs_codes=codes, units=units[:cfg.max_candidate_units], basic=basic)


def taxonomy_for_prompt(taxonomy: Taxonomy) -> dict:
    return {
        "ncsUnits": [{"code": u.code, "name": u.name, "job": u.job} for u in taxonomy.units],
        "basicSkills": [{"id": b.id, "name": b.name} for b in taxonomy.basic],
    }
