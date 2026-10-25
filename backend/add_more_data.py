from django.db import transaction
from decimal import Decimal
from datetime import datetime, time, timedelta
from random import Random

from apps.accounts.models import Role, User
from apps.attendance.models import Attendance, AttendanceCorrection
from apps.attendance.services import _rule_snapshot, _status_for
from apps.employees.models import Employee
from apps.employees.services import register_employee
from apps.leaves.models import LeaveRequest
from apps.leaves.services import validate_leave
from apps.org.models import CompanySettings, Department, Designation, LeaveType
from apps.org.services import WorkCalendar, company_tz, local_today
from apps.payroll.services import finalize, generate_draft, set_salary

rng = Random(424242)
s = CompanySettings.get()
cal = WorkCalendar(s)
tz = company_tz(s)
late_after, half_minutes = _rule_snapshot(s)
today = local_today()
hr = User.objects.filter(role=Role.HR).first()
admin = User.objects.filter(role=Role.ADMIN).first()
assert hr and admin

PASSWORD = "Trial#2026"
depts = {d.code: d for d in Department.objects.all()}
desigs = {d.name: d for d in Designation.objects.all()}

NEW_PEOPLE = [
    ("E007", "Nida", "Hussain", "CON", "Consultant", "female", 105000, 10, "steady"),
    ("E008", "Saad", "Iqbal", "FIN", "Junior Accountant", "male", 82000, 6, "late"),
    ("E009", "Mariam", "Shah", "OPS", "Team Lead", "female", 155000, 16, "steady"),
    ("E010", "Adnan", "Khalid", "OPS", "Operations Executive", "male", 72000, 4, "half_days"),
]

with transaction.atomic():
    new_emps = []
    for code, first, last, dept_code, dname, gender, basic, months, pattern in NEW_PEOPLE:
        if Employee.objects.filter(employee_code=code).exists():
            continue
        dept = depts[dept_code]
        if dname not in desigs:
            desigs[dname] = Designation.objects.create(name=dname)
        join = today - timedelta(days=months * 30)
        emp, temp = register_employee({
            "employee_code": code,
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}@arms.test",
            "department": dept,
            "designation": desigs[dname],
            "join_date": join,
            "basic_salary": Decimal(basic),
            "gender": gender,
            "employment_status": "probation" if months < 6 else "active",
            "phone": f"0300-66{code[-3:]}00",
        }, actor=hr)
        emp.user.set_password(PASSWORD)
        emp.user.must_change_password = False
        emp.user.save()
        new_emps.append((emp, pattern))
        # add a salary revision for some
        if months >= 12:
            set_salary(emp, Decimal(int(basic * 1.08)), join + timedelta(days=180), actor=hr)

    all_emps = list(Employee.objects.all())

    # More attendance over last ~90 days
    start = today - timedelta(days=90)
    for emp in all_emps:
        for d in cal.working_days(max(start, emp.join_date), today):
            if Attendance.objects.filter(employee=emp, date=d).exists():
                continue
            # some randomness
            if rng.random() < 0.05 and d < today:
                continue  # absence
            if d == today and rng.random() < 0.25:
                continue  # not in yet
            late = rng.random() < 0.12
            minute_in = rng.randint(18, 52) if late else rng.randint(-12, 10)
            check_in = datetime.combine(d, time(9, 0), tzinfo=tz) + timedelta(minutes=minute_in)
            rec = Attendance(employee=emp, date=d, check_in=check_in, late_after=late_after,
                             half_day_minutes=half_minutes, is_late=check_in.time() > late_after)
            if d != today:
                if rng.random() < 0.25 and (emp.employment_status == 'probation' or rng.random() < 0.15):
                    # sometimes half day
                    hours = 4.0
                    rec.check_out = check_in + timedelta(hours=hours)
                    rec.worked_minutes = 240
                elif rng.random() < 0.02:
                    rec.status = "missing_checkout"
                else:
                    hours = rng.uniform(8.1, 9.4)
                    rec.check_out = check_in + timedelta(hours=hours)
                    rec.worked_minutes = int(hours * 60)
            if not getattr(rec, "status", None):
                rec.status = _status_for(rec)
            rec.save()

    # Attendance corrections (some pending/approved)
    types_leave = {lt.code: lt for lt in LeaveType.objects.all()}
    by_code = {e.employee_code: e for e in all_emps}
    # create a couple of corrections
    corr_plan = [
        ("E007", today - timedelta(days=7), time(9, 5), time(17, 10), "Forgot to check out properly", "pending"),
        ("E008", today - timedelta(days=14), time(8, 55), time(17, 5), "System was slow", "approved"),
        ("E010", today - timedelta(days=5), time(9, 12), time(17, 0), "Traffic delay at entry", "pending"),
    ]
    for code, cdate, cin, cout, reason, status in corr_plan:
        emp = by_code.get(code)
        if not emp:
            continue
        ac = AttendanceCorrection.objects.create(employee=emp, date=cdate, check_in_time=cin,
                                                check_out_time=cout, reason=reason, status=status)
        if status == "approved":
            ac.reviewed_by = hr
            ac.reviewed_at = timezone.now()
            ac.review_comment = "Approved as per records"
            ac.save()
            # apply correction to attendance
            att = Attendance.objects.filter(employee=emp, date=cdate).first()
            if att:
                tzinfo = tz
                att.check_in = datetime.combine(cdate, cin, tzinfo=tzinfo)
                att.check_out = datetime.combine(cdate, cout, tzinfo=tzinfo)
                att.worked_minutes = int((att.check_out - att.check_in).total_seconds() // 60)
                att.source = "correction"
                att.status = _status_for(att)
                att.save()

    # More leave requests
    leave_plan = [
        ("E007", "annual", 3, 4, "pending", "Short vacation"),
        ("E008", "sick", -2, -2, "approved", "Flu"),
        ("E009", "casual", 15, 16, "pending", "Family event"),
        ("E010", "unpaid", 20, 21, "rejected", "Not eligible at this time"),
        ("E001", "casual", 25, 25, "pending", "Appointment"),
    ]
    for code, ltcode, a, b, status, reason in leave_plan:
        emp = by_code.get(code)
        if not emp or ltcode not in types_leave:
            continue
        startd = today + timedelta(days=a)
        endd = today + timedelta(days=b)
        while startd <= endd and not cal.is_working_day(startd):
            startd += timedelta(days=1)
        if startd > endd or startd < emp.join_date:
            continue
        try:
            n = validate_leave(emp, types_leave[ltcode], startd, endd)
            lr = LeaveRequest.objects.create(employee=emp, leave_type=types_leave[ltcode],
                                             start_date=startd, end_date=endd, days=n,
                                             reason=reason, status=status,
                                             decided_by=hr if status in ("approved", "rejected") else None)
            if status == "approved":
                lr.decided_at = timezone.now()
                lr.save()
            elif status == "rejected":
                lr.decided_at = timezone.now()
                lr.decision_comment = "Rejected per policy"
                lr.save()
        except Exception:
            continue

    # Ensure salary structures exist for all
    for emp in all_emps:
        if not SalaryStructure.objects.filter(employee=emp).exists():
            set_salary(emp, Decimal(50000), emp.join_date, actor=hr)

    # Add one more finalized payroll run for month before last? we already have previous month finalized; add older one if missing
    # generate for two months back if possible
    for months_back in [2, 3]:
        try:
            d = today.replace(day=1) - timedelta(days=months_back * 31)
            y, m = d.year, d.month
            if PayrollRun.objects.filter(year=y, month=m).exists():
                continue
            run = generate_draft(y, m, actor=hr)
            finalize(run.pk, actor=admin)
        except Exception:
            continue

print("done")
