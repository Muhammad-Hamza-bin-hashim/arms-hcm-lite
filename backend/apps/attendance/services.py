"""Attendance rules and the per-employee day-status matrix.

The matrix is the single source used by the attendance calendar, daily board, payroll deductions,
dashboards and AI tools, so all of them agree.
"""
from collections import Counter, namedtuple
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.comms.services import notify, record_audit
from apps.employees.models import Employee
from apps.org.models import CompanySettings
from apps.org.services import WorkCalendar, company_tz, daterange, local_today
from config.exceptions import BusinessRuleError, ConflictError

from .models import Attendance, AttendanceCorrection

DayInfo = namedtuple("DayInfo", "status leave_code is_late working")

# Statuses that come from attendance rows.
RECORD_STATUSES = [s.value for s in Attendance.Status]
# Statuses synthesised for days without a row.
ON_LEAVE, ABSENT, NOT_MARKED, WEEKEND, HOLIDAY, FUTURE, NOT_EMPLOYED = (
    "on_leave", "absent", "not_marked", "weekend", "holiday", "future", "not_employed")


def _rule_snapshot(s: CompanySettings):
    late_after = (datetime.combine(datetime.min, s.office_start) + timedelta(minutes=s.grace_minutes)).time()
    return late_after, int(Decimal(s.half_day_hours) * 60)


def _status_for(record: Attendance) -> str:
    if record.check_out is None:
        return Attendance.Status.LATE if record.is_late else Attendance.Status.PRESENT
    if record.worked_minutes is not None and record.worked_minutes < record.half_day_minutes:
        return Attendance.Status.HALF_DAY
    return Attendance.Status.LATE if record.is_late else Attendance.Status.PRESENT


def close_stale_records(today=None):
    """Past days that never got a check-out become missing_checkout."""
    today = today or local_today()
    return (Attendance.objects.filter(date__lt=today, check_out__isnull=True)
            .exclude(status=Attendance.Status.MISSING_CHECKOUT)
            .update(status=Attendance.Status.MISSING_CHECKOUT))


def _require_profile(user):
    employee = getattr(user, "employee", None)
    if employee is None:
        raise BusinessRuleError("Your login has no employee profile, so attendance is not available.",
                                code="no_employee_profile")
    if employee.employment_status == Employee.Status.EXITED:
        raise BusinessRuleError("Exited employees cannot mark attendance.", code="exited")
    return employee


def check_in(user, *, source=Attendance.Source.WEB, latitude=None, longitude=None, distance_m=None, now=None,
             request=None):
    """Server stamps the time; one record per employee per day (second check-in -> 409)."""
    employee = _require_profile(user)
    s = CompanySettings.get()
    now = now or timezone.now()
    local = now.astimezone(company_tz(s))
    today = local.date()
    if today < employee.join_date:
        raise BusinessRuleError("You cannot check in before your joining date.", code="before_join")
    if Attendance.objects.filter(employee=employee, date=today).exists():
        raise ConflictError("You have already checked in today.")
    late_after, half_day_minutes = _rule_snapshot(s)
    is_late = local.replace(second=0, microsecond=0).time() > late_after
    try:
        with transaction.atomic():
            record = Attendance.objects.create(
                employee=employee, date=today, check_in=now, is_late=is_late,
                status=Attendance.Status.LATE if is_late else Attendance.Status.PRESENT,
                source=source, late_after=late_after, half_day_minutes=half_day_minutes,
                latitude=latitude, longitude=longitude, distance_m=distance_m,
            )
    except IntegrityError:
        raise ConflictError("You have already checked in today.")
    record_audit(user, "attendance.check_in", "attendance", record.pk,
                 summary=f"Checked in ({record.status}, {source})",
                 after={"date": today, "status": record.status, "source": source, "distance_m": distance_m},
                 request=request)
    return record


def check_out(user, *, now=None, request=None):
    employee = _require_profile(user)
    s = CompanySettings.get()
    now = now or timezone.now()
    today = now.astimezone(company_tz(s)).date()
    with transaction.atomic():
        record = Attendance.objects.select_for_update().filter(employee=employee, date=today).first()
        if record is None:
            raise BusinessRuleError("Check in first.", code="not_checked_in")
        if record.check_out is not None:
            raise ConflictError("You have already checked out today.")
        record.check_out = now
        record.worked_minutes = max(0, int((now - record.check_in).total_seconds() // 60))
        record.status = _status_for(record)
        record.save(update_fields=["check_out", "worked_minutes", "status", "updated_at"])
    record_audit(user, "attendance.check_out", "attendance", record.pk, summary=f"Checked out ({record.status})",
                 after={"date": today, "status": record.status, "worked_minutes": record.worked_minutes},
                 request=request)
    return record


# ---------- corrections ----------

def request_correction(user, *, date, check_in_time, check_out_time=None, reason, request=None):
    employee = _require_profile(user)
    today = local_today()
    if date > today:
        raise BusinessRuleError("You cannot request a correction for a future date.", code="future_date")
    if date < employee.join_date:
        raise BusinessRuleError("Date is before your joining date.", code="before_join")
    if check_out_time and check_out_time <= check_in_time:
        raise BusinessRuleError("Check-out must be after check-in.", errors={"check_out_time": ["After check-in."]})
    _ensure_payroll_open(date)
    if AttendanceCorrection.objects.filter(employee=employee, date=date,
                                           status=AttendanceCorrection.Status.PENDING).exists():
        raise ConflictError("A correction for this date is already pending.")
    corr = AttendanceCorrection.objects.create(employee=employee, date=date, check_in_time=check_in_time,
                                               check_out_time=check_out_time, reason=reason)
    record_audit(user, "attendance_correction.requested", "attendance_correction", corr.pk,
                 summary=f"Requested correction for {date}",
                 after={"date": date, "check_in": check_in_time, "check_out": check_out_time, "reason": reason},
                 request=request)
    return corr


def _ensure_payroll_open(d):
    from apps.payroll.models import PayrollRun
    if PayrollRun.objects.filter(year=d.year, month=d.month, status=PayrollRun.Status.FINALIZED).exists():
        raise BusinessRuleError("Payroll for that month is finalized, so its attendance is locked.",
                                code="payroll_locked")


@transaction.atomic
def decide_correction(corr_id, *, approve: bool, comment="", actor, request=None):
    corr = AttendanceCorrection.objects.select_for_update().select_related("employee__user").get(pk=corr_id)
    if corr.status != AttendanceCorrection.Status.PENDING:
        raise ConflictError("This correction has already been decided.")
    if getattr(actor, "employee", None) and actor.employee.pk == corr.employee_id:
        raise BusinessRuleError("You cannot decide your own correction.", code="own_request")
    before_record = None
    if approve:
        _ensure_payroll_open(corr.date)
        s = CompanySettings.get()
        tz = company_tz(s)
        check_in_dt = datetime.combine(corr.date, corr.check_in_time, tzinfo=tz)
        check_out_dt = datetime.combine(corr.date, corr.check_out_time, tzinfo=tz) if corr.check_out_time else None
        record = Attendance.objects.select_for_update().filter(employee=corr.employee, date=corr.date).first()
        if record:
            before_record = {"check_in": record.check_in, "check_out": record.check_out, "status": record.status}
        else:
            late_after, half_day_minutes = _rule_snapshot(s)
            record = Attendance(employee=corr.employee, date=corr.date, late_after=late_after,
                                half_day_minutes=half_day_minutes)
        record.check_in = check_in_dt
        record.check_out = check_out_dt
        record.is_late = corr.check_in_time.replace(second=0, microsecond=0) > record.late_after
        record.worked_minutes = int((check_out_dt - check_in_dt).total_seconds() // 60) if check_out_dt else None
        record.source = Attendance.Source.CORRECTION
        record.status = _status_for(record)
        if check_out_dt is None and corr.date < local_today(s):
            record.status = Attendance.Status.MISSING_CHECKOUT
        record.save()
    corr.status = AttendanceCorrection.Status.APPROVED if approve else AttendanceCorrection.Status.REJECTED
    corr.reviewed_by = actor
    corr.reviewed_at = timezone.now()
    corr.review_comment = comment
    corr.save()
    record_audit(actor, f"attendance_correction.{corr.status}", "attendance_correction", corr.pk,
                 summary=f"{corr.status.title()} correction for {corr.employee} on {corr.date}",
                 before=before_record, after={"status": corr.status, "comment": comment}, request=request)
    notify(corr.employee.user, "attendance", f"Attendance correction {corr.status}",
           f"Your correction for {corr.date:%d %b %Y} was {corr.status}." + (f" Comment: {comment}" if comment else ""),
           link="/attendance")
    return corr


# ---------- day-status matrix ----------

def employees_in_scope(department_id=None, start=None, end=None):
    qs = Employee.objects.all()
    if department_id:
        qs = qs.filter(department_id=department_id)
    if end:
        qs = qs.filter(join_date__lte=end)
    if start:
        qs = qs.exclude(exit_date__lt=start)
    return qs


def day_matrix(employees, start, end, *, today=None, cal=None):
    """{employee_id: {date: DayInfo}} for every day in [start, end]."""
    from apps.leaves.models import LeaveRequest

    today = today or local_today()
    close_stale_records(today)
    cal = cal or WorkCalendar()
    employees = list(employees)
    ids = [e.pk for e in employees]
    records = {}
    for r in Attendance.objects.filter(employee_id__in=ids, date__range=(start, end)).values(
            "employee_id", "date", "status", "is_late"):
        records[(r["employee_id"], r["date"])] = r
    leave_days = {}
    for lr in LeaveRequest.objects.filter(employee_id__in=ids, status=LeaveRequest.Status.APPROVED,
                                          start_date__lte=end, end_date__gte=start).values(
            "employee_id", "start_date", "end_date", "leave_type__code"):
        for d in daterange(max(lr["start_date"], start), min(lr["end_date"], end)):
            leave_days[(lr["employee_id"], d)] = lr["leave_type__code"]

    matrix = {}
    for emp in employees:
        row = {}
        for d in daterange(start, end):
            working = cal.is_working_day(d)
            key = (emp.pk, d)
            if not emp.is_employed_on(d):
                row[d] = DayInfo(NOT_EMPLOYED, None, False, False)
            elif key in records:
                rec = records[key]
                row[d] = DayInfo(rec["status"], None, rec["is_late"], working)
            elif not working:
                row[d] = DayInfo(HOLIDAY if d in cal.holidays else WEEKEND, None, False, False)
            elif key in leave_days:
                row[d] = DayInfo(ON_LEAVE, leave_days[key], False, True)
            elif d > today:
                row[d] = DayInfo(FUTURE, None, False, True)
            elif d == today:
                row[d] = DayInfo(NOT_MARKED, None, False, True)
            else:
                row[d] = DayInfo(ABSENT, None, False, True)
        matrix[emp.pk] = row
    return matrix


def summarize(rows) -> dict:
    """Counts over working days only. `rows` is an iterable of {date: DayInfo} dicts."""
    c = Counter()
    late_flags = 0
    for row in rows:
        for info in row.values():
            if not info.working:
                continue
            c[info.status] += 1
            if info.leave_code:
                c[f"leave:{info.leave_code}"] += 1
            late_flags += int(info.is_late)
    present, late, half, missing = (c[Attendance.Status.PRESENT], c[Attendance.Status.LATE],
                                    c[Attendance.Status.HALF_DAY], c[Attendance.Status.MISSING_CHECKOUT])
    on_leave, absent = c[ON_LEAVE], c[ABSENT]
    # "working-day records": every employee-working-day that has been decided (excludes today unmarked / future).
    working_records = present + late + half + missing + on_leave + absent
    denominator = working_records - on_leave
    attended = Decimal(present + late + missing) + Decimal("0.5") * half
    return {
        "present": present, "late": late, "half_day": half, "missing_checkout": missing,
        "on_leave": on_leave, "absent": absent, "not_marked": c[NOT_MARKED],
        "late_arrivals": late_flags,
        "working_day_records": working_records,
        "expected_working_days": working_records - on_leave,
        "attendance_rate": _pct(attended, denominator),
        "late_pct": _pct(late, present + late),
        "absenteeism_pct": _pct(absent, denominator),
        "unpaid_leave_days": c["leave:unpaid"],
    }


def _pct(num, den):
    if not den:
        return None
    return float(round(Decimal(num) * 100 / Decimal(den), 1))


def worked_minutes_live(record: Attendance, now=None) -> int:
    if record.worked_minutes is not None:
        return record.worked_minutes
    if record.check_out is None and record.date == local_today():
        now = now or timezone.now()
        return max(0, int((now - record.check_in).total_seconds() // 60))
    return 0
