"""Server-side KPIs. Dashboards and AI tools both call these functions, so their numbers always match.

Definitions (see README 'Metric definitions'):
- Employed on day d: join_date <= d and (exit_date is empty or exit_date >= d).
- Headcount: employed (active + probation) on the period end date.
- Attrition %: exits in period / average(headcount at start, headcount at end) x 100.
- Attendance rate: (present + late + missing_checkout + 0.5 x half_day) / (working-day records - on_leave).
- Late %: late / (present + late). Absenteeism: absent / expected working days.
- Leave utilization: approved days in the year / (quota x headcount) per leave type.
- Payroll cost: sum of earned gross and net from FINALIZED payslips in the period.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from rest_framework.exceptions import ValidationError

from apps.attendance.models import Attendance, AttendanceCorrection
from apps.attendance.services import day_matrix, employees_in_scope, summarize
from apps.employees.models import Employee
from apps.leaves.models import LeaveRequest
from apps.leaves.services import balances
from apps.org.models import Department, LeaveType
from apps.org.services import WorkCalendar, local_today
from apps.payroll.models import PayrollRun, Payslip, SalaryStructure

MAX_RANGE_DAYS = 366


class Filters:
    def __init__(self, start: date, end: date, department_id=None):
        if end < start:
            raise ValidationError({"to": ["'to' must be on or after 'from'."]})
        if (end - start).days > MAX_RANGE_DAYS:
            raise ValidationError({"from": [f"Range is limited to {MAX_RANGE_DAYS} days."]})
        self.start, self.end, self.department_id = start, end, department_id

    @classmethod
    def from_params(cls, params):
        today = local_today()

        def parse(key, default):
            value = params.get(key)
            if not value:
                return default
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise ValidationError({key: ["Use YYYY-MM-DD."]})

        start = parse("from", today.replace(day=1))
        end = parse("to", today)
        dept = params.get("department") or None
        if dept is not None and not str(dept).isdigit():
            raise ValidationError({"department": ["Invalid department."]})
        return cls(start, end, int(dept) if dept else None)

    def as_dict(self):
        dept_name = None
        if self.department_id:
            dept_name = Department.objects.filter(pk=self.department_id).values_list("name", flat=True).first()
        return {"from": self.start, "to": self.end, "department_id": self.department_id, "department": dept_name}


def _pct(num, den):
    return None if not den else float(round(Decimal(num) * 100 / Decimal(den), 1))


def _employed_on(qs, d):
    return qs.filter(join_date__lte=d).filter(Q(exit_date__isnull=True) | Q(exit_date__gte=d))


def _base(department_id=None):
    qs = Employee.objects.all()
    return qs.filter(department_id=department_id) if department_id else qs


# ---------- people ----------

def headcount(on_date=None, department_id=None) -> int:
    return _employed_on(_base(department_id), on_date or local_today()).count()


def headcount_by_department(on_date=None):
    on_date = on_date or local_today()
    rows = (_employed_on(Employee.objects.all(), on_date).values("department__id", "department__name")
            .annotate(count=Count("id")).order_by("-count"))
    return [{"department_id": r["department__id"], "department": r["department__name"], "count": r["count"]}
            for r in rows]


def headcount_by_status(on_date=None, department_id=None):
    rows = _employed_on(_base(department_id), on_date or local_today()).values("employment_status").annotate(
        count=Count("id"))
    return {r["employment_status"]: r["count"] for r in rows}


def attrition(f: Filters):
    exits = _base(f.department_id).filter(exit_date__range=(f.start, f.end)).count()
    hc_start = headcount(f.start, f.department_id)
    hc_end = headcount(f.end, f.department_id)
    avg = (hc_start + hc_end) / 2
    return {"exits": exits, "headcount_start": hc_start, "headcount_end": hc_end,
            "attrition_pct": _pct(exits, avg) if avg else None}


def gender_breakdown(on_date=None, department_id=None):
    rows = _employed_on(_base(department_id), on_date or local_today()).values("gender").annotate(count=Count("id"))
    return [{"gender": r["gender"], "count": r["count"]} for r in rows]


def tenure_breakdown(on_date=None, department_id=None):
    on_date = on_date or local_today()
    buckets = {"< 1 year": 0, "1-3 years": 0, "3-5 years": 0, "5+ years": 0}
    for join in _employed_on(_base(department_id), on_date).values_list("join_date", flat=True):
        years = (on_date - join).days / 365.25
        key = "< 1 year" if years < 1 else "1-3 years" if years < 3 else "3-5 years" if years < 5 else "5+ years"
        buckets[key] += 1
    return [{"bucket": k, "count": v} for k, v in buckets.items()]


def search_employees(user, query="", department_id=None, limit=10):
    """Same scope as the directory API: employees only ever see themselves."""
    qs = Employee.objects.select_related("department", "designation")
    if user.role == "employee":
        qs = qs.filter(user=user)
    if query:
        qs = qs.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query)
                       | Q(employee_code__icontains=query) | Q(email__icontains=query))
    if department_id:
        qs = qs.filter(department_id=department_id)
    return [{"id": e.pk, "code": e.employee_code, "name": e.full_name, "department": e.department.name,
             "designation": e.designation.name if e.designation_id else None, "status": e.employment_status,
             "join_date": e.join_date, "email": e.email} for e in qs[:limit]]


# ---------- attendance ----------

def attendance_overview(f: Filters, *, with_trend=True, with_departments=True):
    today = local_today()
    end = min(f.end, today)
    employees = list(employees_in_scope(f.department_id, f.start, end).select_related("department"))
    if end < f.start or not employees:
        empty = summarize([])
        return {"summary": empty, "by_department": [], "trend": []}
    cal = WorkCalendar()
    matrix = day_matrix(employees, f.start, end, today=today, cal=cal)
    result = {"summary": summarize(matrix.values())}
    if with_departments:
        groups = defaultdict(list)
        names = {}
        for e in employees:
            groups[e.department_id].append(matrix[e.pk])
            names[e.department_id] = e.department.name
        result["by_department"] = sorted(
            [{"department_id": k, "department": names[k], **summarize(v)} for k, v in groups.items()],
            key=lambda r: r["department"])
    if with_trend:
        trend = []
        d = f.start
        while d <= end:
            if cal.is_working_day(d):
                day_rows = [{d: matrix[e.pk][d]} for e in employees]
                s = summarize(day_rows)
                trend.append({"date": d, "attendance_rate": s["attendance_rate"], "present": s["present"] + s["late"]
                              + s["missing_checkout"] + s["half_day"], "late": s["late_arrivals"],
                              "absent": s["absent"], "on_leave": s["on_leave"]})
            d += timedelta(days=1)
        result["trend"] = trend
    return result


def late_comers(f: Filters, limit=5):
    qs = Attendance.objects.filter(date__range=(f.start, f.end), is_late=True)
    if f.department_id:
        qs = qs.filter(employee__department_id=f.department_id)
    rows = (qs.values("employee_id", "employee__employee_code", "employee__first_name", "employee__last_name",
                      "employee__department__name")
            .annotate(late_count=Count("id")).order_by("-late_count", "employee__employee_code")[:limit])
    return [{"employee_id": r["employee_id"], "code": r["employee__employee_code"],
             "name": f"{r['employee__first_name']} {r['employee__last_name']}".strip(),
             "department": r["employee__department__name"], "late_count": r["late_count"]} for r in rows]


def today_snapshot(department_id=None):
    today = local_today()
    f = Filters(today, today, department_id)
    s = attendance_overview(f, with_trend=False, with_departments=False)["summary"]
    # Records are counted directly so check-ins on a weekend/holiday still show as present today.
    records = Attendance.objects.filter(date=today)
    if department_id:
        records = records.filter(employee__department_id=department_id)
    counts = records.aggregate(present=Count("id"), late=Count("id", filter=Q(is_late=True)))
    on_leave = on_leave_on(today, department_id)
    pending_leave = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING)
    pending_corr = AttendanceCorrection.objects.filter(status=AttendanceCorrection.Status.PENDING)
    if department_id:
        pending_leave = pending_leave.filter(employee__department_id=department_id)
        pending_corr = pending_corr.filter(employee__department_id=department_id)
    return {
        "date": today, "headcount": headcount(today, department_id),
        "present": counts["present"], "late": counts["late"], "on_leave": s["on_leave"], "not_checked_in": s["not_marked"],
        "on_leave_list": on_leave,
        "pending_leave": pending_leave.count(), "pending_corrections": pending_corr.count(),
        "pending_approvals": pending_leave.count() + pending_corr.count(),
    }


def on_leave_on(d, department_id=None):
    if not WorkCalendar().is_working_day(d):
        return []
    qs = LeaveRequest.objects.filter(status=LeaveRequest.Status.APPROVED, start_date__lte=d, end_date__gte=d)
    qs = _employed_filter(qs, d)
    if department_id:
        qs = qs.filter(employee__department_id=department_id)
    return [{"employee_id": lr.employee_id, "name": lr.employee.full_name, "code": lr.employee.employee_code,
             "department": lr.employee.department.name, "leave_type": lr.leave_type.name,
             "start_date": lr.start_date, "end_date": lr.end_date}
            for lr in qs.select_related("employee__department", "leave_type")]


def _employed_filter(qs, d):
    return qs.filter(employee__join_date__lte=d).filter(Q(employee__exit_date__isnull=True)
                                                        | Q(employee__exit_date__gte=d))


# ---------- leave ----------

def leave_summary(f: Filters):
    """Approved working days per type within the range, plus yearly utilization against quota."""
    cal = WorkCalendar()
    qs = LeaveRequest.objects.filter(start_date__lte=f.end, end_date__gte=f.start).select_related("leave_type")
    if f.department_id:
        qs = qs.filter(employee__department_id=f.department_id)
    by_type = defaultdict(lambda: {"approved_days": 0, "requests": 0, "pending": 0})
    by_department = defaultdict(lambda: defaultdict(int))
    for lr in qs.select_related("employee__department"):
        bucket = by_type[lr.leave_type.code]
        bucket["name"] = lr.leave_type.name
        if lr.status == LeaveRequest.Status.APPROVED:
            days = cal.count(max(lr.start_date, f.start), min(lr.end_date, f.end))
            bucket["approved_days"] += days
            bucket["requests"] += 1
            by_department[lr.employee.department.name][lr.leave_type.code] += days
        elif lr.status == LeaveRequest.Status.PENDING:
            bucket["pending"] += 1

    year = f.end.year
    hc = headcount(f.end, f.department_id)
    year_qs = LeaveRequest.objects.filter(status=LeaveRequest.Status.APPROVED, start_date__year=year)
    if f.department_id:
        year_qs = year_qs.filter(employee__department_id=f.department_id)
    year_days = dict(year_qs.values_list("leave_type__code").annotate(total=Sum("days")))
    types = []
    for lt in LeaveType.objects.filter(is_active=True):
        b = by_type.get(lt.code, {"approved_days": 0, "requests": 0, "pending": 0})
        capacity = (lt.yearly_quota or 0) * hc
        types.append({"code": lt.code, "name": lt.name, "approved_days": b["approved_days"],
                      "approved_requests": b["requests"], "pending_requests": b["pending"],
                      "year_approved_days": year_days.get(lt.code, 0),
                      "utilization_pct": _pct(year_days.get(lt.code, 0), capacity) if lt.yearly_quota else None})
    return {"by_type": types,
            "by_department": [{"department": k, **v} for k, v in sorted(by_department.items())],
            "total_approved_days": sum(t["approved_days"] for t in types)}


# ---------- payroll ----------

def _period_key(d):
    return d.year * 100 + d.month


def payroll_summary(f: Filters, *, include_drafts=False):
    qs = Payslip.objects.annotate(period=F("run__year") * 100 + F("run__month")).filter(
        period__gte=_period_key(f.start), period__lte=_period_key(f.end))
    if not include_drafts:
        qs = qs.filter(run__status=PayrollRun.Status.FINALIZED)
    if f.department_id:
        qs = qs.filter(employee__department_id=f.department_id)
    totals = qs.aggregate(gross=Sum("earned_gross"), net=Sum("net"), tax=Sum("tax"), deductions=Sum("deduction"),
                          payslips=Count("id"))
    by_month = list(qs.values("run__year", "run__month").annotate(gross=Sum("earned_gross"), net=Sum("net"))
                    .order_by("run__year", "run__month"))
    by_dept = list(qs.values("department_name").annotate(gross=Sum("earned_gross"), net=Sum("net"), count=Count("id"))
                   .order_by("-gross"))
    return {
        "total_gross": totals["gross"] or Decimal("0"), "total_net": totals["net"] or Decimal("0"),
        "total_tax": totals["tax"] or Decimal("0"), "total_deductions": totals["deductions"] or Decimal("0"),
        "payslip_count": totals["payslips"],
        "by_month": [{"period": f"{r['run__year']}-{r['run__month']:02d}", "gross": r["gross"], "net": r["net"]}
                     for r in by_month],
        "by_department": [{"department": r["department_name"], "gross": r["gross"], "net": r["net"],
                           "payslips": r["count"]} for r in by_dept],
        "latest_runs": [{"period": r.period_label, "status": r.status, "total_net": r.total_net}
                        for r in PayrollRun.objects.all()[:3]],
    }


def salary_stats(on_date=None, department_id=None):
    """Mean contractual gross of currently employed staff by department and designation."""
    on_date = on_date or local_today()
    employees = _employed_on(_base(department_id), on_date).select_related("department", "designation")
    latest = {}
    for s in SalaryStructure.objects.filter(employee__in=employees, effective_from__lte=on_date).order_by(
            "employee_id", "effective_from", "id"):
        latest[s.employee_id] = s.gross
    by_dept, by_desig = defaultdict(list), defaultdict(list)
    for e in employees:
        if e.pk in latest:
            by_dept[e.department.name].append(latest[e.pk])
            by_desig[e.designation.name if e.designation_id else "Unassigned"].append(latest[e.pk])

    def mean(values):
        return (sum(values) / len(values)).quantize(Decimal("0.01")) if values else None

    all_values = list(latest.values())
    return {"average_gross": mean(all_values), "employees_with_salary": len(all_values),
            "by_department": [{"department": k, "average_gross": mean(v), "count": len(v)} for k, v in sorted(by_dept.items())],
            "by_designation": [{"designation": k, "average_gross": mean(v), "count": len(v)} for k, v in sorted(by_desig.items())]}


# ---------- dashboards ----------

def _insights(f: Filters):
    from .insights import absence_anomalies, attrition_risk
    risk = attrition_risk(f.department_id)
    levels = Counter(r["level"] for r in risk)
    return {
        "attrition_risk": [r for r in risk if r["level"] != "low"][:5],
        "risk_levels": {"high": levels["high"], "medium": levels["medium"], "low": levels["low"]},
        "anomalies": absence_anomalies(f.department_id, f.start, f.end),
    }

def hr_dashboard(f: Filters):
    att = attendance_overview(f)
    return {
        "filters": f.as_dict(),
        "today": today_snapshot(f.department_id),
        "headcount": headcount(f.end, f.department_id),
        "attendance": att["summary"],
        "attendance_trend": att["trend"],
        "absenteeism_by_department": [{"department": d["department"], "absenteeism_pct": d["absenteeism_pct"],
                                       "absent": d["absent"], "late_pct": d["late_pct"],
                                       "attendance_rate": d["attendance_rate"]} for d in att["by_department"]],
        "leave": leave_summary(f),
        "top_late_comers": late_comers(f, 5),
        "insights": _insights(f),
    }


def admin_dashboard(f: Filters):
    from apps.comms.models import AuditLog
    year_start = f.end.replace(month=1, day=1)
    return {
        "filters": f.as_dict(),
        "headcount": headcount(f.end, f.department_id),
        "headcount_by_status": headcount_by_status(f.end, f.department_id),
        "attrition_period": attrition(f),
        "attrition_ytd": attrition(Filters(year_start, f.end, f.department_id)),
        "payroll": payroll_summary(f),
        "salary": salary_stats(f.end, f.department_id),
        "headcount_by_department": headcount_by_department(f.end),
        "gender": gender_breakdown(f.end, f.department_id),
        "tenure": tenure_breakdown(f.end, f.department_id),
        "attendance": attendance_overview(f, with_trend=False, with_departments=False)["summary"],
        "today": today_snapshot(f.department_id),
        "insights": _insights(f),
        "audit_feed": [{"id": a.id, "summary": a.summary or a.action, "actor": a.actor_email, "action": a.action,
                        "created_at": a.created_at} for a in AuditLog.objects.all()[:8]],
    }


def employee_dashboard(user):
    from apps.attendance.services import worked_minutes_live
    from apps.payroll.services import payslip_queryset_for

    employee = getattr(user, "employee", None)
    if employee is None:
        return {"has_profile": False}
    today = local_today()
    week_start = today - timedelta(days=today.weekday())
    week_minutes = sum(worked_minutes_live(a) for a in Attendance.objects.filter(employee=employee,
                                                                                  date__range=(week_start, today)))
    month_start = today.replace(day=1)
    own_rows = day_matrix([employee], max(month_start, employee.join_date), today) if employee.join_date <= today else {}
    own = summarize(own_rows.values()) if own_rows else summarize([])
    last = (payslip_queryset_for(user).filter(employee=employee, run__status=PayrollRun.Status.FINALIZED)
            .order_by("-run__year", "-run__month").first())
    return {
        "has_profile": True,
        "employee": {"id": employee.pk, "name": employee.full_name, "code": employee.employee_code,
                     "department": employee.department.name},
        "hours_this_week": round(week_minutes / 60, 1), "target_hours": 40,
        "late_count_month": own["late_arrivals"], "month_attendance": own,
        "leave_balance": balances(employee, today.year),
        "last_payslip": {"id": last.id, "period": last.run.period_label, "net": last.net,
                         "earned_gross": last.earned_gross} if last else None,
    }
