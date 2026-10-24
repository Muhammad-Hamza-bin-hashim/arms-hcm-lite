"""Test-only fixtures. Synthetic records live here and never in the application."""
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from rest_framework.test import APIClient, APITestCase

from apps.accounts.authentication import issue_tokens
from apps.accounts.models import Role, User
from apps.accounts.services import run_first_setup
from apps.attendance.models import Attendance
from apps.employees.services import register_employee
from apps.org.models import Department, Designation

PKT = ZoneInfo("Asia/Karachi")
PASSWORD = "Str0ng-Passw0rd!"


def at(d: date, hh: int, mm: int = 0):
    return datetime.combine(d, time(hh, mm), tzinfo=PKT)


class HCMTestCase(APITestCase):
    def setUp(self):
        self.admin = run_first_setup(company_name="AR&MS Management Company", email="admin@arms.test",
                                     password=PASSWORD, first_name="Ada")
        self.hr = User.objects.create_user(email="hr@arms.test", password=PASSWORD, role=Role.HR, first_name="Hira")
        self.it = Department.objects.create(name="IT", code="IT")
        self.finance = Department.objects.create(name="Finance", code="FIN")
        self.dev = Designation.objects.create(name="Developer")

    def employee(self, code="E001", email=None, dept=None, join=date(2026, 1, 1), basic="100000", **extra):
        emp, _ = register_employee({
            "employee_code": code, "first_name": extra.pop("first_name", f"Emp{code}"), "last_name": "Test",
            "email": email or f"{code.lower()}@arms.test", "department": dept or self.it,
            "designation": self.dev, "join_date": join, "basic_salary": Decimal(basic),
            "employment_status": "active", **extra,
        }, actor=self.hr)
        user = emp.user
        user.set_password(PASSWORD)
        user.must_change_password = False
        user.save()
        return emp

    def client_for(self, user) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user)['access']}")
        return client

    def attendance(self, emp, d, check_in, check_out=None):
        from apps.attendance.services import _rule_snapshot, _status_for
        from apps.org.models import CompanySettings
        late_after, half = _rule_snapshot(CompanySettings.get())
        rec = Attendance(employee=emp, date=d, check_in=at(d, *check_in), late_after=late_after, half_day_minutes=half)
        rec.is_late = time(*check_in) > late_after
        if check_out:
            rec.check_out = at(d, *check_out)
            rec.worked_minutes = int((rec.check_out - rec.check_in).total_seconds() // 60)
        rec.status = _status_for(rec)
        rec.save()
        return rec
