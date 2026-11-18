"""Business-day helpers (weekends only; no holiday calendar in v1)."""
from datetime import date, timedelta


def add_bdays(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if d.weekday() < 5:
            remaining -= 1
    return d


def bdiff(a: date, b: date) -> int:
    """Absolute number of business days between two dates."""
    lo, hi = (a, b) if a <= b else (b, a)
    n, d = 0, lo
    while d < hi:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def business_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out
