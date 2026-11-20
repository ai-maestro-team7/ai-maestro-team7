"""지역 조건 읽기 (B-02). 공고문에서 지역과 관련된 우대·제한 조건을 찾아 `RegionalCondition` 목록으로 만든다.

판정이 아니라 "대상일 수 있어요"를 보여 줄 근거만 만든다. 사용자에게 맞는지는 `core.facts.regional_talent_view`가
학교 소재지·거주지와 견줘 본다. LLM은 쓰지 않는다.

읽는 조건
- 비수도권 지역인재 ("비수도권 지역인재", "비수도권인재", "비수도권(서울·인천·경기 제외) 지역학교") → NON_CAPITAL
- 이전지역인재·권역 인재 ("이전지역(대구.경북)인재", "충청권 지역 학부까지의 졸업자", "광주·전남 지역인재") → SCHOOL
  지역을 적지 않은 "이전지역인재"·"지역인재"는 부산 이전기관이면 부산, 아니면 UNKNOWN
- 지방공공기관 지역 제한 ("지역 제한: 경상남도 김해시 (지역인재 우선채용)") → 시·도면 SCHOOL_OR_RESIDENCE, 시·군·구면 RESIDENCE
- 거주자 우대·제한 ("주민등록상 주소지가 울산, 양산, 부산 거주자", "서울시 강동구 거주자") → RESIDENCE
"""

import re

from ..config import OpportunityConfig
from ..ingest.field_maps import KLID_SIDO_ALIASES, SIDO_ALIASES
from ..models.enums import RegionalBenefitKind, RegionalTalentStatus
from ..models.posting import PostingSnapshot, RegionalCondition, RegionalTalent

Kind = RegionalBenefitKind

KEYWORDS = ("지역인재", "채용목표제")  # 예전 판정 근거 찾기 (find_basis)
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n+")

# 여러 시·도를 묶어 부르는 이름. 공고문에 이 이름이 나오면 묶인 시·도 전부로 본다
REGION_GROUPS = {
    "충청권": ("30", "36", "43", "44"), "대전충청권": ("30", "36", "43", "44"),
    "호남권": ("29", "46", "52"), "영남권": ("26", "27", "31", "47", "48"),
    "동남권": ("26", "31", "48"), "부울경": ("26", "31", "48"), "대경권": ("27", "47"),
    "강원권": ("51",), "제주권": ("50",),
    # 띄어 쓰지 않고 붙여 적은 이름 ("광주전남지역인재")
    "광주전남": ("29", "46"), "대구경북": ("27", "47"), "부산울산경남": ("26", "31", "48"), "울산경남": ("31", "48"),
    "대전충남": ("30", "44"), "대전세종충남": ("30", "36", "44"),
}
_PARTICLE = r"(?:에서|에|의|와|과|및|이|가|은|는|인|을|를|로|으로)?"
_NAMES = sorted({*SIDO_ALIASES, *KLID_SIDO_ALIASES}, key=len, reverse=True)
_SIDO_RE = re.compile(r"(?<![가-힣])(" + "|".join(map(re.escape, _NAMES)) + r")" + _PARTICLE + r"(?![가-힣])")
_GROUP_RE = re.compile(r"(?<![가-힣])(" + "|".join(sorted(REGION_GROUPS, key=len, reverse=True)) + r")")
_EXCEPT = re.compile(r"\([^()]*제외[^()]*\)")  # "비수도권(서울, 인천, 경기 제외)"의 괄호는 지역 목록이 아니다
_SIGUNGU_AFTER_SIDO = re.compile(r"(?<![가-힣])(" + "|".join(map(re.escape, _NAMES)) + r")\s+([가-힣]{1,5}(?:시|군|구))"
                                 + _PARTICLE + r"(?![가-힣])")
_SIGUNGU_TOKEN = re.compile(r"^[가-힣]{1,5}(?:시|군|구)$")
_KLID_LIMIT = re.compile(r"^지역 제한:\s*([^(]+)")  # 괄호 뒤는 사유("지역인재 채용")라 지역이 아니다
_ENTRY_SPLIT = re.compile(r"\s*[,，、/]\s*")

_NON_CAPITAL_TALENT = re.compile(r"비수도권(?:지역)?(?:인재|지역학교|소재학교|학교|대학|출신)")
_NON_CAPITAL_PHRASES = re.compile(r"비수도권(?:지역)?인재")
_RESIDENCE_HINT = re.compile(r"거주자|거주지가|주민등록")
_RESIDENCE_EXCLUDE = re.compile(r"제한\s*없|제한없|F-\d|출신지|블라인드|^근무지")
# 양성평등 채용목표제처럼 지역과 상관없는 채용목표제는 빼고, "지역"이나 "이전"이 같이 나올 때만 센다
_REGIONAL_TARGET = re.compile(r"(?:지역|이전).*채용목표제|채용목표제.*(?:지역|이전)")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _lines(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


def find_basis(text: str) -> str | None:
    """지역인재 언급이 있는 첫 문장. 없으면 None."""
    for sentence in _lines(text):
        if any(word in sentence for word in KEYWORDS):
            return sentence
    return None


def _sido_code(name: str) -> str | None:
    key = (name or "").strip()
    return SIDO_ALIASES.get(key) or KLID_SIDO_ALIASES.get(key)


def find_sidos(text: str) -> list[str]:
    """글에 나온 시·도 코드 (나온 차례, 중복 없음). 권역 이름("충청권")은 묶인 시·도로 푼다."""
    found: list[str] = []
    for m in _GROUP_RE.finditer(text or ""):
        found += REGION_GROUPS[m.group(1)]
    for m in _SIDO_RE.finditer(text or ""):
        code = _sido_code(m.group(1))
        if code:
            found.append(code)
    return list(dict.fromkeys(found))


def _klid_entry(entry: str, home_sido: str | None) -> RegionalCondition:
    """지역 제한 칸의 지역 하나. "경상남도 김해시", "인천광역시", "양산시"(시·도 없음 → 기관 시·도)."""
    tokens = entry.split()
    label = entry.strip()
    if not tokens:
        return RegionalCondition(kind=Kind.UNKNOWN, label=label or None)
    sido = _sido_code(tokens[0])
    rest = tokens[1:] if sido else tokens
    if sido and not rest:
        return RegionalCondition(kind=Kind.SCHOOL_OR_RESIDENCE, sido=sido, label=label)
    if len(rest) == 1 and (sido or _SIGUNGU_TOKEN.match(rest[0])):
        return RegionalCondition(kind=Kind.RESIDENCE, sido=sido or home_sido, sigungu=rest[0], label=label)
    return RegionalCondition(kind=Kind.UNKNOWN, label=label)


def _klid_conditions(line: str, home_sido: str | None) -> list[RegionalCondition] | None:
    """"지역 제한: …" 줄이면 지역마다 조건 하나. 그런 줄이 아니면 None."""
    m = _KLID_LIMIT.match(line)
    if not m:
        return None
    entries = [e for e in _ENTRY_SPLIT.split(m.group(1).strip()) if e.strip()]
    return [_klid_entry(entry, home_sido) for entry in entries] or [RegionalCondition(kind=Kind.UNKNOWN)]


def _talent_conditions(line: str, relocated_sido: str | None) -> list[RegionalCondition]:
    """지역인재·비수도권·이전지역 언급이 있는 줄의 조건."""
    compact = _compact(_EXCEPT.sub("", line))
    non_capital = bool(_NON_CAPITAL_TALENT.search(compact))
    rest = _NON_CAPITAL_PHRASES.sub("", compact)
    other = "지역인재" in rest or "이전지역" in rest or bool(_REGIONAL_TARGET.search(rest))
    if not (non_capital or other):
        return []
    out = [RegionalCondition(kind=Kind.NON_CAPITAL, label="비수도권 지역인재")] if non_capital else []
    if other:
        label = "이전지역인재" if "이전지역" in compact else "지역인재"
        sidos = find_sidos(_EXCEPT.sub("", line))
        if sidos:
            out += [RegionalCondition(kind=Kind.SCHOOL, sido=s, label=label) for s in sidos]
        elif relocated_sido:
            out.append(RegionalCondition(kind=Kind.SCHOOL, sido=relocated_sido, label=label))
        else:
            out.append(RegionalCondition(kind=Kind.UNKNOWN, label=label))
    return out


def _residence_conditions(line: str) -> list[RegionalCondition]:
    """거주자 우대·제한 줄. 지역 이름이 없으면("근무지 인근지역 거주자") 조건을 만들지 않는다."""
    if not _RESIDENCE_HINT.search(line) or _RESIDENCE_EXCLUDE.search(line):
        return []
    out: list[RegionalCondition] = []
    covered: set[str] = set()
    for m in _SIGUNGU_AFTER_SIDO.finditer(line):
        sido = _sido_code(m.group(1))
        if sido:
            out.append(RegionalCondition(kind=Kind.RESIDENCE, sido=sido, sigungu=m.group(2),
                                         label=f"{m.group(1)} {m.group(2)} 거주"))
            covered.add(sido)
    for sido in find_sidos(line):
        if sido not in covered:
            out.append(RegionalCondition(kind=Kind.RESIDENCE, sido=sido, label="거주자"))
    return out


def find_conditions(text: str, *, home_sido: str | None = None,
                    relocated_sido: str | None = None) -> tuple[list[RegionalCondition], str | None]:
    """공고문의 지역 조건과 첫 근거 줄.

    home_sido는 기관(근무지) 시·도로, 지역 제한 칸에 시·도 없이 "양산시"만 적혔을 때 쓴다.
    relocated_sido는 부산 이전기관이면 부산 코드다. 지역을 적지 않은 "이전지역인재"를 그 시·도로 본다.
    지역을 콕 집은 조건이 하나라도 있으면 "어느 지역인지 모름"(UNKNOWN)은 뺀다.
    """
    conditions: list[RegionalCondition] = []
    basis = None
    for line in _lines(text):
        found = _klid_conditions(line, home_sido)
        if found is None:
            found = _talent_conditions(line, relocated_sido) + _residence_conditions(line)
        if found and basis is None:
            basis = line
        conditions += found
    unique = list({(c.kind, c.sido, c.sigungu): c for c in conditions}.values())
    if any(c.kind in (Kind.SCHOOL, Kind.RESIDENCE, Kind.SCHOOL_OR_RESIDENCE) for c in unique):
        unique = [c for c in unique if c.kind != Kind.UNKNOWN]
    return unique, basis


def judge_regional_talent(text: str, *, home_sido: str | None = None,
                          relocated_sido: str | None = None) -> RegionalTalent:
    """지역 조건이 있으면 LIKELY(조건 목록과 근거), 부산 이전기관인데 공고문에서 못 찾으면 CHECK_NEEDED, 아니면
    NOT_APPLICABLE. LIKELY는 "이 공고에 지역 조건이 있다"는 뜻이고 사용자에게 맞는지는 아직 모른다."""
    conditions, basis = find_conditions(text, home_sido=home_sido, relocated_sido=relocated_sido)
    if conditions:
        return RegionalTalent(status=RegionalTalentStatus.LIKELY, basis=basis, conditions=conditions)
    if relocated_sido:
        return RegionalTalent(status=RegionalTalentStatus.CHECK_NEEDED)
    return RegionalTalent(status=RegionalTalentStatus.NOT_APPLICABLE)


def judge_posting_regional_talent(config: OpportunityConfig, snapshot: PostingSnapshot, text: str, *,
                                  relocated: bool, relocated_sido: str | None = None) -> RegionalTalent:
    """공고 하나의 지역 조건. 수집(`ingest.pipeline`)과 보강(`enrich.pipeline`)이 같은 규칙을 쓴다.

    relocated는 부산 이전기관 배지나 기업 시드로 안다. 시드에 시·도가 없으면 부산으로 본다(배지가 부산 이전기관이다).
    """
    region = snapshot.work_region
    home = None if region.unknown or region.overseas else region.sido
    where = (relocated_sido or config.data.busan_sido) if relocated else None
    return judge_regional_talent(text, home_sido=home, relocated_sido=where)
