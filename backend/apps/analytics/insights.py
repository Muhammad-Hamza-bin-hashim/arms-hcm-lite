"""Bonus insights: attrition-risk score and absence anomaly flags.

Both are transparent rules on attendance and leave records (not a trained model). Every score
lists the reasons that produced it so HR can judge it, and nothing here changes any record.
"""
from collections import Counter
from datetime import timedelta

from apps.attendance.services import ABSENT, day_matrix, employees_in_scope, summarize
from apps.leaves.models import LeaveRequest
from apps.org.services import WorkCalendar, local_today

RISK_WINDOW_DAYS = 60

# (points cap, description) for each factor; total is capped at 100.
RISK_WEIGHTS = {
    "absenteeism": 35,   # absent ÷ expected working days in the window (35 pts at >= 20%)
    "lateness": 20,      # late % (20 pts at >= 40%)
    "unpaid_leave": 15,  # unpaid leave days (15 pts at >= 5 days)
    "rejected_leave": 10,  # rejected leave requests in the window (10 pts at >= 2)
    "tenure": 10,        # under one year of service
    "probation": 10,     # still on probation
}


def _level(score):
    return "high" if score >= 60 else "medium" if score >= 30 else "low"


def attrition_risk(department_id=None, *, today=None, limit=None):
    """Per-employee risk score 0-100 over the last 60 days, highest first."""
    today = today or local_today()
    start = today - timedelta(days=RISK_WINDOW_DAYS - 1)
    employees = list(employees_in_scope(department_id, today, today).filter(exit_date__isnull=True)
                     .select_related("department"))
    if not employees:
        return []
    cal = WorkCalendar()
    matrix = day_matrix(employees, start, today, today=today, cal=cal)
    rejected = Counter(LeaveRequest.objects.filter(employee__in=employees, status=LeaveRequest.Status.REJECTED,
                                                   decided_at__date__gte=start)
                       .values_list("employee_id", flat=True))
    results = []
    for e in employees:
        s = summarize([matrix[e.pk]])
        reasons, score = [], 0.0
        absent_rate = (s["absent"] / s["expected_working_days"]) if s["expected_working_days"] else 0
        if absent_rate:
            pts = min(1.0, absent_rate / 0.20) * RISK_WEIGHTS["absenteeism"]
            score += pts
            reasons.append(f"absent {s['absent']} of {s['expected_working_days']} working days")
        late_pct = (s["late_pct"] or 0) / 100
        if late_pct:
            score += min(1.0, late_pct / 0.40) * RISK_WEIGHTS["lateness"]
            reasons.append(f"late on {s['late_pct']}% of attended days")
        if s["unpaid_leave_days"]:
            score += min(1.0, s["unpaid_leave_days"] / 5) * RISK_WEIGHTS["unpaid_leave"]
            reasons.append(f"{s['unpaid_leave_days']} unpaid leave day(s)")
        if rejected[e.pk]:
            score += min(1.0, rejected[e.pk] / 2) * RISK_WEIGHTS["rejected_leave"]
            reasons.append(f"{rejected[e.pk]} leave request(s) rejected")
        if (today - e.join_date).days < 365:
            score += RISK_WEIGHTS["tenure"]
            reasons.append("less than 1 year of service")
        if e.employment_status == "probation":
            score += RISK_WEIGHTS["probation"]
            reasons.append("on probation")
        score = round(min(score, 100))
        results.append({"employee_id": e.pk, "code": e.employee_code, "name": e.full_name,
                        "department": e.department.name, "score": score, "level": _level(score),
                        "reasons": reasons})
    results.sort(key=lambda r: (-r["score"], r["code"]))
    return results[:limit] if limit else results


def absence_anomalies(department_id=None, start=None, end=None, *, today=None):
    """Flags unusual absence patterns in the range (defaults to the last 60 days)."""
    today = today or local_today()
    end = min(end or today, today)
    start = start or end - timedelta(days=RISK_WINDOW_DAYS - 1)
    employees = list(employees_in_scope(department_id, start, end).select_related("department"))
    if not employees or end < start:
        return []
    cal = WorkCalendar()
    matrix = day_matrix(employees, start, end, today=today, cal=cal)
    flags = []
    dept_rows = {}
    for e in employees:
        row = matrix[e.pk]
        dept_rows.setdefault(e.department.name, []).append(row)
        working = [(d, i) for d, i in sorted(row.items()) if i.working]

        # 1. Three or more consecutive absent working days.
        streak, best, best_end = 0, 0, None
        for d, info in working:
            streak = streak + 1 if info.status == ABSENT else 0
            if streak > best:
                best, best_end = streak, d
        if best >= 3:
            flags.append(_flag(e, "consecutive_absence", "high" if best >= 5 else "medium",
                               f"{best} consecutive working days absent (until {best_end:%d %b})"))

        # 2. Absences clustered next to the weekend (Mondays / Fridays).
        absences = [d for d, i in working if i.status == ABSENT]
        edge = [d for d in absences if d.weekday() in (0, 4)]
        if len(edge) >= 3 and len(edge) / len(absences) >= 0.6:
            flags.append(_flag(e, "weekend_adjacent_absence", "medium",
                               f"{len(edge)} of {len(absences)} absences fall on Mondays or Fridays"))

        # 3. Repeated missing check-outs.
        missing = sum(1 for _, i in working if i.status == "missing_checkout")
        if missing >= 3:
            flags.append(_flag(e, "missing_checkouts", "low", f"{missing} days without a check-out"))

    # 4. Department absenteeism far above the company rate.
    company = summarize(matrix.values())["absenteeism_pct"]
    if company:
        for dept, rows in dept_rows.items():
            rate = summarize(rows)["absenteeism_pct"]
            if rate is not None and len(rows) >= 2 and rate >= 2 * company and rate - company >= 5:
                flags.append({"type": "department_absenteeism", "severity": "medium", "employee_id": None,
                              "name": dept, "department": dept,
                              "detail": f"absenteeism {rate}% vs company {company}%"})
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f["severity"]], f["name"]))
    return flags


def _flag(e, kind, severity, detail):
    return {"type": kind, "severity": severity, "employee_id": e.pk, "name": e.full_name,
            "code": e.employee_code, "department": e.department.name, "detail": detail}
