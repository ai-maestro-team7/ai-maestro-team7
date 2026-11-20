"""텍스트 도구 묶음: 정규화(#41), 개인정보 가리기(#42), 근거 검증(#43).
세 모듈은 따로 만들어지므로 core는 이 묶음을 Deps로 받는다. 운영에서는 `load_text_tools()`가 실제 모듈을 붙이고,
테스트는 같은 모양의 가짜를 넣는다.

모양 (각 이슈의 공개 이름과 같다):
- normalize(raw) -> str
- mask_pii(text) -> 결과.masked_text(길이 보존), 결과.spans[start, end, kind]
- overlaps_mask(start, end, spans) -> bool
- check_evidence(source, quote, start, end) -> 결과.status("EXACT"|"RELOCATED"|"NOT_FOUND"), .start, .end
- find_unsupported_facts(source, generated) -> list (비어 있으면 원문에 없는 수치·날짜·기간이 없다)
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TextTools:
    normalize: Callable[[str], str]
    mask_pii: Callable[[str], Any]
    overlaps_mask: Callable[[int, int, list], bool]
    check_evidence: Callable[[str, str, int | None, int | None], Any]
    find_unsupported_facts: Callable[[str, str], list]


def load_text_tools() -> TextTools:
    """실제 모듈을 붙인다. 아직 들어오지 않은 모듈이 있으면 ImportError를 그대로 올린다."""
    from mentoring.extract import normalize_text
    from mentoring.privacy import mask_pii, overlaps_mask
    from mentoring.verify import check_evidence, find_unsupported_facts

    return TextTools(normalize=normalize_text, mask_pii=mask_pii, overlaps_mask=overlaps_mask,
                     check_evidence=check_evidence, find_unsupported_facts=find_unsupported_facts)
