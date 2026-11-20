"""모델 답 검사 (개발계획서4 §5). 통과하지 못하면 OutputInvalid → 한 번 다시 돌린다."""

import re

from .config import SupervisorConfig
from .errors import OutputInvalid
from .models import ChatReply

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm_number(text: str) -> str:
    value = text.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {_norm_number(m) for m in _NUMBER.findall(text or "")}


def banned_in(config: SupervisorConfig, text: str) -> list[str]:
    """금지 문구. "적합도는 실제 합격 확률이 아닙니다" 같은 허용 문장은 먼저 지우고 본다."""
    cleaned = text or ""
    for phrase in config.allowed_phrases:
        cleaned = cleaned.replace(phrase, "")
    return [p for p in config.banned_phrases if p in cleaned]


def check_reply(config: SupervisorConfig, reply: ChatReply, sources: list[str]) -> ChatReply:
    """형식·숫자·금지 문구를 검사하고 앞뒤 공백을 정리한 답을 돌려준다.

    sources는 이번 턴 도구 결과, 사용자 메시지, 지난 대화다. 답의 숫자는 그 안에 있어야 한다.
    개수를 말하는 작은 수(freeNumberMax 이하 정수)는 대조하지 않는다.
    """
    limits = config.reply
    text = (reply.reply or "").strip()
    if not text:
        raise OutputInvalid("EMPTY_REPLY")
    if len(text) > limits.max_chars:
        raise OutputInvalid("REPLY_TOO_LONG")
    follow_ups = [" ".join(f.split()) for f in reply.follow_ups if f and f.strip()]
    if len(follow_ups) > limits.max_follow_ups or any(len(f) > limits.follow_up_max_chars for f in follow_ups):
        follow_ups = [f for f in follow_ups if len(f) <= limits.follow_up_max_chars][:limits.max_follow_ups]
    for part in [text, *follow_ups]:
        if banned_in(config, part):
            raise OutputInvalid("BANNED_PHRASE")
    allowed = set().union(*(numbers_in(s) for s in sources)) if sources else set()
    for number in numbers_in(" ".join([text, *follow_ups])):
        if number in allowed:
            continue
        if number.isdigit() and int(number) <= limits.free_number_max:
            continue
        raise OutputInvalid("NUMBER_NOT_GROUNDED")
    return ChatReply(reply=text, follow_ups=follow_ups)
