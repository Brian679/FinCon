"""Charter service-level helpers (working days, due dates)."""
from datetime import date, datetime, timedelta

from django.utils import timezone

# Fixed-date Zimbabwean public holidays (month, day). Moveable feasts (Easter)
# are added per year in ``holidays_for``.
FIXED_HOLIDAYS = [(1, 1), (2, 21), (4, 18), (5, 1), (5, 25), (8, 12), (8, 13), (12, 22), (12, 25), (12, 26)]


def _easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def holidays_for(year):
    days = {date(year, m, d) for m, d in FIXED_HOLIDAYS}
    easter = _easter(year)
    days |= {easter - timedelta(days=2), easter - timedelta(days=1), easter + timedelta(days=1)}
    return days


def is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays_for(d.year)


def add_working_days(start, days: int):
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_working_day(current.date() if isinstance(current, datetime) else current):
            added += 1
    return current


def due_from_standard(code: str, start=None):
    """Due datetime for a charter standard code, e.g. ``acknowledge-complaints``."""
    from .models import ServiceStandard

    start = start or timezone.now()
    std = ServiceStandard.objects.filter(code=code).first()
    if std is None:
        return None
    if std.unit == ServiceStandard.Unit.MINUTES:
        return start + timedelta(minutes=std.value)
    if std.unit == ServiceStandard.Unit.HOURS:
        return start + timedelta(hours=std.value)
    if std.unit == ServiceStandard.Unit.WORKING_DAYS:
        return add_working_days(start, std.value)
    return start
