"""날짜·시각 계산. B의 모든 날짜 계산은 여기의 as_of로만 한다.

as_of는 요청 인자 → 사용자 설정의 demoAsOf(데모 시간 앞당기기) → 지금 순서로 정한다.
시각은 KST(+09:00)로 쓴다 (D-29).
"""

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROLLING = "9999-12-31"


def now_kst() -> datetime:
    return datetime.now(KST).replace(microsecond=0)


def parse_as_of(value: str | date | datetime | None) -> datetime:
    """as_of 값을 KST datetime으로 바꾼다. None이면 지금. 날짜만 오면 그날 09:00."""
    if value is None:
        return now_kst()
    if isinstance(value, datetime):
        return value.astimezone(KST) if value.tzinfo else value.replace(tzinfo=KST)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 9, tzinfo=KST)
    text = value.strip()
    if len(text) == 10:
        return parse_as_of(date.fromisoformat(text))
    return parse_as_of(datetime.fromisoformat(text))


def resolve_as_of(as_of: str | date | datetime | None = None, demo_as_of: str | None = None) -> datetime:
    return parse_as_of(as_of if as_of is not None else demo_as_of)


def iso(value: datetime) -> str:
    """ISO 8601 +09:00, 초 단위."""
    return parse_as_of(value).isoformat(timespec="seconds")


def day(value: str | date | datetime | None) -> str:
    """YYYY-MM-DD."""
    return parse_as_of(value).date().isoformat()


def is_rolling(closes_at: str | None) -> bool:
    return not closes_at or closes_at == ROLLING


def is_expired(closes_at: str | None, as_of: str | date | datetime | None) -> bool:
    """마감일이 as_of 날짜보다 앞이면 마감. 마감 당일은 진행 중이다."""
    if is_rolling(closes_at):
        return False
    return closes_at < day(as_of)


def d_day(closes_at: str | None, as_of: str | date | datetime | None) -> int | None:
    """마감까지 남은 날. 상시 채용은 None."""
    if is_rolling(closes_at):
        return None
    return (date.fromisoformat(closes_at) - parse_as_of(as_of).date()).days


def deadline_number(closes_at: str | None) -> int:
    """S3 Vectors 필터용 YYYYMMDD 숫자."""
    return int((closes_at or ROLLING).replace("-", ""))


def age_range(birth_year: int, as_of: str | date | datetime | None) -> tuple[int, int]:
    """생년만 알 때의 만 나이 범위 (생일 전, 생일 후)."""
    year = parse_as_of(as_of).year
    return year - birth_year - 1, year - birth_year


def week_key(as_of: str | date | datetime | None) -> str:
    """`OPP#CAP#{yyyy-Www}`에 쓰는 ISO 주."""
    year, week, _ = parse_as_of(as_of).isocalendar()
    return f"{year}-W{week:02d}"


def at_hour(day_value: str | date, hour: int) -> datetime:
    """그날 hour시 KST."""
    d = date.fromisoformat(day_value) if isinstance(day_value, str) else day_value
    return datetime(d.year, d.month, d.day, hour, tzinfo=KST)


def hours_between(earlier: str | datetime, later: str | datetime) -> float:
    return (parse_as_of(later) - parse_as_of(earlier)).total_seconds() / 3600
