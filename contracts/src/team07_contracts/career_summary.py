"""Career_Profile_Summary (R9, D-12·D-40). 소유 A, 소비 C·BACKEND. A → C 단방향.

이력서 원문 필드는 없다 (A §12.2 allowRawResume: false). C의 면접 결과를 A로 되돌리는 필드·함수도 없다.
"""
from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field, StrictInt

from .base import ContractModel, SafeId, non_blank

# [D-40 PROPOSED] 목록 한도: (최대 항목 수, 항목 최대 글자 수)
CAREER_SUMMARY_LIMITS: dict[str, tuple[int, int]] = {
    "projects": (10, 200),
    "skills": (30, 50),
    "needsConfirmation": (10, 200),
}


def _items(key: str):
    max_items, max_len = CAREER_SUMMARY_LIMITS[key]
    return Annotated[list[Annotated[str, non_blank(max_len)]], Field(max_length=max_items)]


class CareerProfileSummary(ContractModel):
    projects: _items("projects")
    skills: _items("skills")  # 원천: 역량 프로필 skills[] 중 factStatus == VERIFIED (A §4.2)
    needs_confirmation: _items("needsConfirmation")  # 확인이 필요한 역량. 부족이 확정된 역량이 아니다
    profile_id: Optional[SafeId] = None
    profile_version: Optional[Annotated[StrictInt, Field(ge=1)]] = None
