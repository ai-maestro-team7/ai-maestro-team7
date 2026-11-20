"""Hypothesis 전략 (테스트 전용, 파트 테스트도 재사용할 수 있다). 실행 코드는 import하지 않는다."""
from __future__ import annotations

from hypothesis import strategies as st

from ..errors import ERROR_CODES

_text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=40)
_json_scalar = st.none() | st.booleans() | st.integers(-1000, 1000) | st.text(max_size=20)


def schema_versions(major: int | None = None) -> st.SearchStrategy[str]:
    """ "주.부" 형식 문자열. major를 주면 주 버전을 고정한다."""
    majors = st.just(major) if major is not None else st.integers(0, 20)
    return st.builds(lambda a, b: f"{a}.{b}", majors, st.integers(0, 20))


@st.composite
def error_envelopes(draw) -> dict:
    """유효한 Error_Envelope JSON 데이터 (별칭 코드, details 유무 포함)."""
    body = {
        "code": draw(st.sampled_from(sorted(ERROR_CODES))),
        "message": draw(_text),
        "requestId": draw(_text),
        "retryable": draw(st.booleans()),
    }
    if draw(st.booleans()):
        body["details"] = draw(st.dictionaries(st.text(min_size=1, max_size=10), _json_scalar, max_size=3))
    return {"error": body}
