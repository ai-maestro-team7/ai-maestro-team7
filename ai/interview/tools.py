"""에이전트 툴 공통 부분 (follow-up design §3).

피드백 에이전트(C-2, feedback.py)와 꼬리질문 판단 에이전트(follow_up.py, #109)가 같이 쓴다.
- search_resume: 자소서에서 키워드가 든 문장 찾기. LLM·AWS를 부르지 않는 문자열 검색이다
- ToolUsage: 툴 호출 횟수와 상한. 상한은 에이전트 실행(시도)마다 새로 센다
툴 결과와 인자는 로그에 남기지 않는다. ToolUsage.summary()는 툴 이름과 횟수만 돌려준다.
"""

import re
from collections import Counter

RESUME_PASSAGE_LIMIT = 3
PASSAGE_MAX_CHARS = 200
KEYWORD_MAX_CHARS = 30

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def search_resume(resume_text: str, keyword: str) -> dict:
    """자소서에서 키워드가 든 문장을 최대 3개 찾는다 (공백 정규화 후 대소문자 무시 부분 문자열, 문장당 200자).

    잘못된 인자는 예외 대신 오류 사실을 돌려준다. 에이전트가 인자를 고쳐 다시 부를 수 있게 하려는 것이다.
    """
    word = _normalize(keyword or "")
    if not word:
        return {"error": "EMPTY_KEYWORD"}
    if len(word) > KEYWORD_MAX_CHARS:
        return {"error": "KEYWORD_TOO_LONG", "maxChars": KEYWORD_MAX_CHARS}
    sentences = [_normalize(s) for s in _SENTENCE_SPLIT.split(resume_text) if s.strip()]
    hits = [s[:PASSAGE_MAX_CHARS] for s in sentences if word.lower() in s.lower()]
    return {"keyword": word, "passages": hits[:RESUME_PASSAGE_LIMIT], "found": len(hits)}


class ToolUsage:
    """툴 호출 횟수. 상한은 에이전트 실행(시도)마다 새로 센다. 넘으면 툴이 '지금까지 정보로 답하라'를 돌려준다.

    3차 수동 확인에서 상한을 두 시도가 같이 써서 재시도가 시작하자마자 TOOL_LIMIT을 받았다 (#92). start_attempt로 나눈다.
    """

    def __init__(self, limit: int):
        self.limit = limit
        self.calls: Counter[str] = Counter()      # 이번 시도
        self.all_calls: Counter[str] = Counter()  # 모든 시도 합 (로그용)
        self.attempts = 0

    def start_attempt(self) -> None:
        self.calls = Counter()
        self.attempts += 1

    @property
    def total(self) -> int:
        return sum(self.calls.values())

    def take(self, name: str) -> dict | None:
        self.calls[name] += 1
        self.all_calls[name] += 1
        if self.total > self.limit:
            return {"error": "TOOL_LIMIT", "message": "도구 호출 한도에 닿았습니다. 지금까지 받은 정보로 답을 쓰세요."}
        return None

    def summary(self) -> str:
        return ",".join(f"{name}:{n}" for name, n in sorted(self.all_calls.items())) or "none"
