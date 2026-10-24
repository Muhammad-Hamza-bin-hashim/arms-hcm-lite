"""Company calendar: the single source for 'today', weekends and holidays."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import CompanySettings, Holiday


def company_tz(settings_obj=None) -> ZoneInfo:
    s = settings_obj or CompanySettings.get()
    try:
        return ZoneInfo(s.timezone or "Asia/Karachi")
    except Exception:  # invalid tz name stored
        return ZoneInfo("Asia/Karachi")


def local_now(settings_obj=None) -> datetime:
    return timezone.now().astimezone(company_tz(settings_obj))


def local_today(settings_obj=None) -> date:
    return local_now(settings_obj).date()


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


class WorkCalendar:
    """Working-day calculations using one settings + holiday snapshot."""

    def __init__(self, settings_obj=None, holidays=None):
        self.settings = settings_obj or CompanySettings.get()
        self.weekend = set(int(x) for x in (self.settings.weekend_days or []))
        self._holidays = holidays

    @property
    def holidays(self) -> set:
        if self._holidays is None:
            self._holidays = set(Holiday.objects.values_list("date", flat=True))
        return self._holidays

    def is_working_day(self, d: date) -> bool:
        return d.weekday() not in self.weekend and d not in self.holidays

    def working_days(self, start: date, end: date) -> list:
        if start is None or end is None or end < start:
            return []
        return [d for d in daterange(start, end) if self.is_working_day(d)]

    def count(self, start: date, end: date) -> int:
        return len(self.working_days(start, end))


def month_bounds(year: int, month: int):
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start, end
