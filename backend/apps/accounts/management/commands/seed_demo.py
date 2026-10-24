"""LOCAL TRIAL ONLY: fills an EMPTY database with sample people and ~10 weeks of activity.

Never run automatically and never on the judging/hosted instance (the brief requires a fresh,
empty install there). It refuses to run if setup has already happened.

    python manage.py seed_demo
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.accounts.services import run_first_setup, setup_completed
from apps.attendance.models import Attendance
from apps.attendance.services import _rule_snapshot, _status_for
from apps.comms.models import Announcement
from apps.employees.services import register_employee
from apps.leaves.models import LeaveRequest
from apps.leaves.services import validate_leave
from apps.org.models import CompanySettings, Department, Designation, Holiday, LeaveType
from apps.org.services import WorkCalendar, company_tz, local_today
from apps.payroll.services import finalize, generate_draft

PASSWORD = "Trial#2026"
PEOPLE = [
    # code, first, last, dept, designation, gender, basic, months employed, pattern
    ("E001", "Sana", "Khan", "CON", "Senior Consultant", "female", 180000, 30, "steady"),
    ("E002", "Bilal", "Ahmed", "CON", "Consultant", "male", 120000, 14, "late"),
    ("E003", "Zara", "Malik", "FIN", "Accountant", "female", 95000, 8, "weekend_edges"),
    ("E004", "Omar", "Farooq", "FIN", "Finance Manager", "male", 260000, 40, "steady"),
    ("E005", "Hira", "Siddiqui", "OPS", "Operations Executive", "female", 70000, 3, "streak"),
    ("E006", "Usman", "Raza", "OPS", "Operations Executive", "male", 68000, 1, "half_days"),
]


class Command(BaseCommand):
    help = "LOCAL TRIAL ONLY: seed an empty database with sample employees and activity."

    def handle(self, *args, **options):
        if setup_completed() or User.objects.exists():
            raise CommandError("Database is not empty. seed_demo only runs on a fresh database "
                               "(delete backend/db.sqlite3 and run `python manage.py migrate` first).")
        rng = random.Random(2026)
        with transaction.atomic():
            admin = run_first_setup(company_name="AR&MS Management Company", email="admin@arms.test",
                                    password=PASSWORD, first_name="Ayesha", last_name="Rauf")
            s = CompanySettings.get()
            s.office_lat, s.office_lng, s.office_radius_m = Decimal("24.860700"), Decimal("67.001100"), 150
            s.save()
            hr = User.objects.create_user(email="hr@arms.test", password=PASSWORD, role=Role.HR,
                                          first_name="Hamza", last_name="Ali")
            depts = {code: Department.objects.create(name=name, code=code) for code, name in
                     [("CON", "Consulting"), ("FIN", "Finance"), ("OPS", "Operations")]}
            desigs = {}
            today = local_today()
            Holiday.objects.get_or_create(date=today - timedelta(days=20), defaults={"name": "Sample public holiday"})
            employees = []
            for code, first, last, dept, desig, gender, basic, months, pattern in PEOPLE:
                if desig not in desigs:
                    desigs[desig] = Designation.objects.create(name=desig)
                join = today - timedelta(days=months * 30)
                emp, _ = register_employee({
                    "employee_code": code, "first_name": first, "last_name": last,
                    "email": f"{first.lower()}@arms.test", "department": depts[dept], "designation": desigs[desig],
                    "join_date": join, "basic_salary": Decimal(basic), "gender": gender,
                    "employment_status": "probation" if months < 6 else "active", "phone": f"0300-55{code[-3:]}00",
                }, actor=hr)
                emp.user.set_password(PASSWORD)
                emp.user.must_change_password = False
                emp.user.save()
                employees.append((emp, pattern))

            cal = WorkCalendar(s)
            tz = company_tz(s)
            late_after, half_minutes = _rule_snapshot(s)
            start = today - timedelta(days=75)  # covers last month (payroll) and the 60-day insight window
            leave_days = self._leave(employees, today, hr, cal)
            for emp, pattern in employees:
                streak_start = today - timedelta(days=12)
                for d in cal.working_days(max(start, emp.join_date), today):
                    if (emp.pk, d) in leave_days:
                        continue
                    if pattern == "weekend_edges" and d.weekday() in (0, 4) and rng.random() < 0.55 and d != today:
                        continue
                    if pattern == "streak" and streak_start <= d < streak_start + timedelta(days=5):
                        continue
                    if rng.random() < 0.04 and d != today:
                        continue  # occasional absence
                    if d == today and rng.random() < 0.3:
                        continue  # not in yet today
                    late = rng.random() < (0.45 if pattern == "late" else 0.08)
                    minute_in = rng.randint(17, 55) if late else rng.randint(-15, 12)
                    check_in = datetime.combine(d, time(9, 0), tzinfo=tz) + timedelta(minutes=minute_in)
                    rec = Attendance(employee=emp, date=d, check_in=check_in, late_after=late_after,
                                     half_day_minutes=half_minutes, is_late=check_in.time() > late_after)
                    if d != today:
                        hours = 4 if (pattern == "half_days" and rng.random() < 0.3) else rng.uniform(8.2, 9.3)
                        if rng.random() < 0.03:
                            rec.status = "missing_checkout"
                        else:
                            rec.check_out = check_in + timedelta(hours=hours)
                            rec.worked_minutes = int(hours * 60)
                    if not getattr(rec, "status", None):
                        rec.status = _status_for(rec)
                    rec.save()

            prev = today.replace(day=1) - timedelta(days=1)
            run = generate_draft(prev.year, prev.month, actor=hr)
            finalize(run.pk, actor=admin)
            Announcement.objects.create(created_by=hr, title="Welcome to AR&MS HCM Lite",
                                        body="Check in from your dashboard each morning and apply for leave under My leave. "
                                             "Ask the assistant if you have questions about policy.")

        self.stdout.write(self.style.SUCCESS("Sample data created (LOCAL TRIAL ONLY)."))
        self.stdout.write(f"All passwords: {PASSWORD}")
        self.stdout.write("  Admin     admin@arms.test")
        self.stdout.write("  HR        hr@arms.test")
        for code, first, *_ in PEOPLE:
            self.stdout.write(f"  Employee  {first.lower()}@arms.test ({code})")

    def _leave(self, employees, today, hr, cal):
        """A few approved / pending / unpaid requests, validated by the real leave rules."""
        types = {lt.code: lt for lt in LeaveType.objects.all()}
        by_code = {e.employee_code: e for e, _ in employees}
        plan = [
            ("E001", "annual", -18, -16, "approved", "Family trip"),
            ("E002", "sick", -9, -9, "approved", "Fever"),
            ("E004", "casual", 0, 0, "approved", "Personal errand"),
            ("E005", "unpaid", -30, -29, "approved", "Personal reasons"),
            ("E003", "casual", 5, 6, "pending", "Cousin's wedding"),
            ("E006", "annual", 10, 12, "pending", "Visiting home town"),
        ]
        days = set()
        for code, lt, a, b, status, reason in plan:
            emp = by_code[code]
            start, end = today + timedelta(days=a), today + timedelta(days=b)
            while not cal.is_working_day(start) and start < end:
                start += timedelta(days=1)
            if not cal.is_working_day(start) or start < emp.join_date:
                continue
            n = validate_leave(emp, types[lt], start, end)
            lr = LeaveRequest.objects.create(employee=emp, leave_type=types[lt], start_date=start, end_date=end,
                                             days=n, reason=reason, status=status,
                                             decided_by=hr if status == "approved" else None)
            if status == "approved":
                days.update((emp.pk, d) for d in cal.working_days(lr.start_date, lr.end_date))
        return days
