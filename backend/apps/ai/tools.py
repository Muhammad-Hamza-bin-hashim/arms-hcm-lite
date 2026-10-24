"""AI tools. Each one calls the same services as the REST API, with the caller's role and data scope.

The model never touches the database: it can only ask for these functions, and every function
re-checks the user's role before returning anything.
"""
from datetime import date, timedelta

from apps.accounts.models import Role
from apps.analytics import services as analytics
from apps.attendance.services import day_matrix, summarize
from apps.leaves.models import LeaveRequest
from apps.leaves.services import balances
from apps.org.models import Department
from apps.org.services import local_today, month_bounds
from apps.payroll.models import PayrollRun, Payslip

ALL = (Role.ADMIN, Role.HR, Role.EMPLOYEE)
STAFF = (Role.ADMIN, Role.HR)

PERIOD_SCHEMA = {
    "type": "string",
    "enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_year", "custom"],
    "description": "Reporting period. Use 'custom' with from_date/to_date.",
}
DATE_SCHEMA = {"type": "string", "description": "ISO date YYYY-MM-DD (only for period=custom)."}
DEPT_SCHEMA = {
    "type": ["string", "null"],
    "description": "Optional department name or code. Use null or omit this field to include all departments.",
}


class ToolDenied(Exception):
    pass


class ToolInputError(Exception):
    pass


def resolve_period(args):
    today = local_today()
    period = args.get("period") or "this_month"
    if period == "today":
        return today, today
    if period == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    if period == "this_week":
        return today - timedelta(days=today.weekday()), today
    if period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if period == "this_month":
        return today.replace(day=1), today
    if period == "last_month":
        prev = today.replace(day=1) - timedelta(days=1)
        return month_bounds(prev.year, prev.month)
    if period == "this_year":
        return today.replace(month=1, day=1), today
    if period == "custom":
        try:
            start, end = date.fromisoformat(args["from_date"]), date.fromisoformat(args["to_date"])
        except (KeyError, TypeError, ValueError):
            raise ToolInputError("For period=custom give from_date and to_date as YYYY-MM-DD.")
        if end < start or (end - start).days > 366:
            raise ToolInputError("Invalid custom range (max 366 days).")
        return start, end
    raise ToolInputError(f"Unknown period '{period}'.")


def resolve_department(value):
    if not value:
        return None
    value = str(value).strip()
    dept = (Department.objects.filter(name__iexact=value).first() or Department.objects.filter(code__iexact=value).first()
            or Department.objects.filter(name__icontains=value).first())
    if dept is None:
        known = ", ".join(Department.objects.values_list("name", flat=True)) or "none yet"
        raise ToolInputError(f"Unknown department '{value}'. Known departments: {known}.")
    return dept


def _filters(args):
    start, end = resolve_period(args)
    dept = resolve_department(args.get("department"))
    return analytics.Filters(start, end, dept.pk if dept else None), dept


def _period_out(f, dept):
    return {"from": f.start, "to": f.end, "department": dept.name if dept else "all departments"}


def _own_employee(user):
    employee = getattr(user, "employee", None)
    if employee is None:
        raise ToolDenied("This login has no employee profile, so personal data is not available.")
    return employee


# ---------- tool implementations ----------

def get_headcount(user, args):
    dept = resolve_department(args.get("department"))
    today = local_today()
    return {"as_of": today, "department": dept.name if dept else "all departments",
            "headcount": analytics.headcount(today, dept.pk if dept else None),
            "by_status": analytics.headcount_by_status(today, dept.pk if dept else None),
            "by_department": None if dept else analytics.headcount_by_department(today)}


def get_attendance_summary(user, args):
    if user.role == Role.EMPLOYEE:
        employee = _own_employee(user)
        start, end = resolve_period(args)
        end = min(end, local_today())
        start = max(start, employee.join_date)
        if end < start:
            return {"scope": "your own attendance", "summary": summarize([])}
        row = day_matrix([employee], start, end)[employee.pk]
        return {"scope": "your own attendance", "from": start, "to": end, "summary": summarize([row])}
    f, dept = _filters(args)
    data = analytics.attendance_overview(f, with_trend=False, with_departments=dept is None)
    return {**_period_out(f, dept), "summary": data["summary"], "by_department": data.get("by_department")}


def get_late_comers(user, args):
    f, dept = _filters(args)
    limit = min(max(int(args.get("limit") or 5), 1), 20)
    return {**_period_out(f, dept), "late_comers": analytics.late_comers(f, limit)}


def get_leave_summary(user, args):
    if user.role == Role.EMPLOYEE:
        employee = _own_employee(user)
        start, end = resolve_period(args)
        qs = LeaveRequest.objects.filter(employee=employee, start_date__lte=end, end_date__gte=start).select_related(
            "leave_type")
        return {"scope": "your own leave", "from": start, "to": end,
                "requests": [{"type": lr.leave_type.name, "start": lr.start_date, "end": lr.end_date, "days": lr.days,
                              "status": lr.status} for lr in qs]}
    f, dept = _filters(args)
    on_date = f.end if args.get("period") in ("today", "yesterday") else local_today()
    return {**_period_out(f, dept), **analytics.leave_summary(f),
            "on_leave_today" if on_date == local_today() else "on_leave_on_date":
                analytics.on_leave_on(on_date, dept.pk if dept else None)}


def get_my_leave_balance(user, args):
    employee = _own_employee(user)
    year = args.get("year")
    return {"employee": employee.full_name, **balances(employee, int(year) if year else None),
            "note": "remaining = quota - approved days; pending requests are listed separately"}


def get_payroll_summary(user, args):
    month = args.get("month")
    if month:
        try:
            y, m = (int(x) for x in str(month).split("-"))
            start, end = month_bounds(y, m)
        except (ValueError, TypeError):
            raise ToolInputError("month must be YYYY-MM.")
    else:
        start, end = None, None
    if user.role == Role.EMPLOYEE:
        employee = _own_employee(user)
        qs = Payslip.objects.filter(employee=employee, run__status=PayrollRun.Status.FINALIZED).select_related("run")
        if start:
            qs = qs.filter(run__year=start.year, run__month=start.month)
        slips = qs.order_by("-run__year", "-run__month")[:3]
        return {"scope": "your own finalized payslips",
                "payslips": [{"period": s.run.period_label, "gross": s.gross, "earned_gross": s.earned_gross,
                              "deduction": s.deduction, "tax": s.tax, "net": s.net, "absent_days": s.absent_days,
                              "unpaid_leave_days": s.unpaid_leave_days} for s in slips]}
    dept = resolve_department(args.get("department"))
    if start is None:
        latest = PayrollRun.objects.first()
        if latest is None:
            return {"message": "No payroll has been run yet."}
        start, end = month_bounds(latest.year, latest.month)
    f = analytics.Filters(start, end, dept.pk if dept else None)
    run = PayrollRun.objects.filter(year=start.year, month=start.month).first()
    return {"period": f"{start.year}-{start.month:02d}", "department": dept.name if dept else "all departments",
            "run_status": run.status if run else "not run",
            "finalized_totals": analytics.payroll_summary(f),
            "draft_or_final_totals": analytics.payroll_summary(f, include_drafts=True),
            "average_salary": analytics.salary_stats(local_today(), dept.pk if dept else None)}


def search_employees(user, args):
    dept = resolve_department(args.get("department"))
    results = analytics.search_employees(user, (args.get("query") or "").strip()[:100], dept.pk if dept else None)
    out = {"results": results, "count": len(results)}
    if user.role == Role.EMPLOYEE:
        out["note"] = "Employees can only look up their own record."
    return out


TOOLS = [
    {
        "name": "get_headcount", "roles": STAFF, "fn": get_headcount,
        "description": "Current headcount (employed active + probation), optionally for one department, with a "
                       "breakdown by status and by department.",
        "parameters": {"type": "object", "properties": {"department": DEPT_SCHEMA}, "additionalProperties": False},
    },
    {
        "name": "get_attendance_summary", "roles": ALL, "fn": get_attendance_summary,
        "description": "Attendance counts and rates (present, late, half day, missing checkout, on leave, absent, "
                       "attendance rate, late %, absenteeism %) for a period. Employees get only their own.",
        "parameters": {"type": "object", "properties": {"period": PERIOD_SCHEMA, "from_date": DATE_SCHEMA,
                                                        "to_date": DATE_SCHEMA, "department": DEPT_SCHEMA},
                       "additionalProperties": False},
    },
    {
        "name": "get_late_comers", "roles": STAFF, "fn": get_late_comers,
        "description": "Employees ranked by number of late arrivals in a period.",
        "parameters": {"type": "object", "properties": {"period": PERIOD_SCHEMA, "from_date": DATE_SCHEMA,
                                                        "to_date": DATE_SCHEMA, "department": DEPT_SCHEMA,
                                                        "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                       "additionalProperties": False},
    },
    {
        "name": "get_leave_summary", "roles": ALL, "fn": get_leave_summary,
        "description": "Leave usage by type and department for a period, plus who is on approved leave today. "
                       "Employees get only their own requests.",
        "parameters": {"type": "object", "properties": {"period": PERIOD_SCHEMA, "from_date": DATE_SCHEMA,
                                                        "to_date": DATE_SCHEMA, "department": DEPT_SCHEMA},
                       "additionalProperties": False},
    },
    {
        "name": "get_my_leave_balance", "roles": ALL, "fn": get_my_leave_balance,
        "description": "The signed-in user's own leave balance per type for a year (quota, used, pending, remaining).",
        "parameters": {"type": "object", "properties": {"year": {"type": "integer"}}, "additionalProperties": False},
    },
    {
        "name": "get_payroll_summary", "roles": ALL, "fn": get_payroll_summary,
        "description": "Payroll totals for a month (YYYY-MM; default latest run) and average salary. Employees get "
                       "only their own finalized payslips, never anyone else's.",
        "parameters": {"type": "object", "properties": {"month": {"type": "string"}, "department": DEPT_SCHEMA},
                       "additionalProperties": False},
    },
    {
        "name": "search_employees", "roles": ALL, "fn": search_employees,
        "description": "Find employees by name, code or email (no salary data). Employees can only find themselves.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "department": DEPT_SCHEMA},
                       "additionalProperties": False},
    },
]
TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def tools_for(role):
    return [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in TOOLS if role in t["roles"]]


def execute(user, name, args):
    """Runs a tool for `user`. Returns (result_dict, is_error)."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return {"error": f"Unknown tool '{name}'."}, True
    if user.role not in tool["roles"]:
        return {"error": "Permission denied: your role cannot access this data."}, True
    if not isinstance(args, dict) or "__invalid_json__" in args:
        return {"error": "Tool arguments must be a JSON object."}, True
    allowed = set(tool["parameters"]["properties"])
    unknown = set(args) - allowed
    if unknown:
        return {"error": f"Unknown argument(s): {', '.join(sorted(unknown))}."}, True
    try:
        return tool["fn"](user, args), False
    except ToolDenied as exc:
        return {"error": f"Permission denied: {exc}"}, True
    except ToolInputError as exc:
        return {"error": str(exc)}, True
