from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from apps.leaves.models import LeaveRequest
from apps.org.models import LeaveType
from apps.org.services import WorkCalendar
from apps.payroll.calc import annual_tax, compute_pay, salary_components
from apps.payroll.models import PayrollRun, Payslip
from apps.payroll.services import set_salary

from .helpers import HCMTestCase, at

D = Decimal


class TaxSlabTests(SimpleTestCase):
    def test_boundaries(self):
        cases = {0: 0, 600000: 0, 600001: D("0.05"), 1200000: 30000, 1200001: D("30000.15"), 2400000: 210000,
                 3600000: 510000, 4000000: 650000}
        for income, tax in cases.items():
            self.assertEqual(annual_tax(income), D(tax).quantize(D("0.01")), income)

    def test_salary_components(self):
        self.assertEqual(salary_components("100000"),
                         {"basic": D("100000.00"), "hra": D("40000.00"), "medical": D("10000.00"),
                          "gross": D("150000.00")})

    def test_compute_pay_deductions(self):
        pay = compute_pay(gross=D("150000"), working_days=22, payable_days=22, absent_days=2, unpaid_leave_days=1,
                          half_days=1)
        self.assertEqual(pay["deduction"], D("23863.64"))
        self.assertEqual(pay["tax"], D("10000.00"))
        self.assertEqual(pay["net"], D("116136.36"))

    def test_deduction_never_exceeds_pay(self):
        pay = compute_pay(gross=D("10000"), working_days=22, payable_days=5, absent_days=10)
        self.assertEqual(pay["earned_gross"], D("0.00"))
        self.assertEqual(pay["net"], D("0.00"))


class PayrollRunTests(HCMTestCase):
    OCT = (2026, 10)

    def setUp(self):
        super().setUp()
        patcher = mock.patch("django.utils.timezone.now", return_value=at(date(2026, 11, 2), 10))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cal = WorkCalendar()

    def full_month(self, emp, skip=(), half=()):
        for d in self.cal.working_days(max(date(2026, 10, 1), emp.join_date), date(2026, 10, 31)):
            if d in skip:
                continue
            self.attendance(emp, d, (9, 0), (13, 0) if d in half else (17, 0))

    def run_payroll(self):
        r = self.client_for(self.hr).post("/api/payroll/runs/", {"year": 2026, "month": 10})
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def test_deductions_and_proration(self):
        a = self.employee("E001")
        unpaid = date(2026, 10, 7)
        LeaveRequest.objects.create(employee=a, leave_type=LeaveType.objects.get(code="unpaid"), start_date=unpaid,
                                    end_date=unpaid, days=1, reason="x", status="approved")
        self.full_month(a, skip={date(2026, 10, 5), date(2026, 10, 6), unpaid}, half={date(2026, 10, 8)})
        b = self.employee("E002", join=date(2026, 10, 15))
        self.full_month(b)
        run = self.run_payroll()
        self.assertEqual(run["working_days"], 22)
        slip_a = Payslip.objects.get(employee=a)
        self.assertEqual((slip_a.absent_days, slip_a.unpaid_leave_days, slip_a.half_days), (2, 1, 1))
        self.assertEqual(slip_a.net, D("116136.36"))
        slip_b = Payslip.objects.get(employee=b)
        self.assertEqual(slip_b.payable_days, 12)
        self.assertEqual(slip_b.prorated_gross, D("81818.18"))
        self.assertEqual(slip_b.tax, D("5454.55"))
        self.assertEqual(slip_b.net, D("76363.63"))

    def test_finalize_lock_and_permissions(self):
        a = self.employee("E001")
        self.full_month(a)
        run = self.run_payroll()
        self.assertEqual(self.client_for(self.hr).post(f"/api/payroll/runs/{run['id']}/finalize/").status_code, 403)
        emp_client = self.client_for(a.user)
        self.assertEqual(emp_client.get("/api/payroll/payslips/").json()["count"], 0)  # drafts hidden
        admin = self.client_for(self.admin)
        self.assertEqual(admin.post(f"/api/payroll/runs/{run['id']}/finalize/").status_code, 200)
        self.assertEqual(admin.post(f"/api/payroll/runs/{run['id']}/finalize/").status_code, 409)
        self.assertEqual(self.client_for(self.hr).post(f"/api/payroll/runs/{run['id']}/regenerate/").status_code, 409)
        self.assertEqual(self.client_for(self.hr).post("/api/payroll/runs/", {"year": 2026, "month": 10}).status_code,
                         409)
        slip = Payslip.objects.get()
        net = slip.net
        set_salary(a, D("500000"), date(2026, 10, 1), actor=self.hr)  # later salary change...
        slip.refresh_from_db()
        self.assertEqual(slip.net, net)  # ...does not touch the finalized snapshot
        slip.net = D("1")
        with self.assertRaises(PermissionDenied):
            slip.save()
        run_obj = PayrollRun.objects.get()
        with self.assertRaises(PermissionDenied):
            run_obj.delete()
        # employee now sees and downloads own payslip and got a notification
        listing = emp_client.get("/api/payroll/payslips/").json()
        self.assertEqual(listing["count"], 1)
        pdf = emp_client.get(f"/api/payroll/payslips/{slip.pk}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(a.user.notifications.filter(kind="payslip").count(), 1)
        # leave and corrections in a finalized month are locked
        r = emp_client.post("/api/attendance/corrections/", {"date": "2026-10-05", "check_in_time": "09:00",
                                                              "reason": "x"})
        self.assertEqual(r.json()["code"], "payroll_locked")

    def test_other_employee_payslip_hidden(self):
        a, b = self.employee("E001"), self.employee("E002")
        run = self.run_payroll()
        self.client_for(self.admin).post(f"/api/payroll/runs/{run['id']}/finalize/")
        other = Payslip.objects.get(employee=b)
        c = self.client_for(a.user)
        self.assertEqual(c.get(f"/api/payroll/payslips/{other.pk}/").status_code, 404)
        self.assertEqual(c.get(f"/api/payroll/payslips/{other.pk}/pdf/").status_code, 404)
        self.assertEqual(c.get(f"/api/payroll/payslips/?employee={b.pk}").json()["count"], 1)  # only own

    def test_future_month_rejected_and_hr_cannot_set_own_salary(self):
        r = self.client_for(self.hr).post("/api/payroll/runs/", {"year": 2026, "month": 12})
        self.assertEqual(r.status_code, 422)
        hr_emp = self.employee("H001", email="hr@arms.test")
        r = self.client_for(self.hr).post("/api/payroll/salaries/", {"employee": hr_emp.pk, "basic": "999999"})
        self.assertEqual(r.status_code, 403)

    def test_regenerate_draft_reflects_new_attendance(self):
        a = self.employee("E001")
        run = self.run_payroll()
        before = Payslip.objects.get().absent_days
        self.full_month(a)
        self.client_for(self.hr).post(f"/api/payroll/runs/{run['id']}/regenerate/")
        self.assertEqual(before, 22)
        self.assertEqual(Payslip.objects.get().absent_days, 0)
        self.assertEqual(PayrollRun.objects.count(), 1)


