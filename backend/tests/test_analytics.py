from datetime import date
from unittest import mock

from apps.ai import tools
from apps.leaves.models import LeaveRequest
from apps.org.models import LeaveType

from .helpers import HCMTestCase, at

TODAY = date(2026, 10, 21)


class AnalyticsTests(HCMTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("django.utils.timezone.now", return_value=at(TODAY, 12))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_dataset_no_errors(self):
        for url in ["/api/dashboard/hr/", "/api/dashboard/admin/"]:
            client = self.client_for(self.admin)
            r = client.get(url)
            self.assertEqual(r.status_code, 200, r.content)
        data = self.client_for(self.hr).get("/api/dashboard/hr/").json()
        self.assertEqual(data["headcount"], 0)
        self.assertIsNone(data["attendance"]["attendance_rate"])

    def test_dashboard_matches_records_and_filters(self):
        a = self.employee("E001", dept=self.it)
        b = self.employee("E002", dept=self.it)
        c = self.employee("E003", dept=self.finance)
        self.employee("E004", dept=self.finance, join=date(2026, 1, 1)).__class__.objects.filter(
            employee_code="E004").update(exit_date=date(2026, 10, 10), employment_status="exited")
        self.attendance(a, TODAY, (9, 30))           # late
        self.attendance(b, TODAY, (8, 55))           # present
        self.attendance(a, date(2026, 10, 20), (9, 40), (18, 0))  # late yesterday
        LeaveRequest.objects.create(employee=c, leave_type=LeaveType.objects.get(code="sick"), days=1,
                                    start_date=TODAY, end_date=TODAY, reason="x", status="approved")
        hr = self.client_for(self.hr)
        data = hr.get("/api/dashboard/hr/?from=2026-10-20&to=2026-10-21").json()
        self.assertEqual(data["headcount"], 3)
        self.assertEqual(data["today"]["present"], 2)
        self.assertEqual(data["today"]["late"], 1)
        self.assertEqual(data["today"]["on_leave"], 1)
        self.assertEqual(data["top_late_comers"][0]["code"], "E001")
        self.assertEqual(data["top_late_comers"][0]["late_count"], 2)
        it = hr.get(f"/api/dashboard/hr/?department={self.it.pk}").json()
        self.assertEqual(it["headcount"], 2)
        self.assertEqual(it["today"]["on_leave"], 0)
        admin = self.client_for(self.admin).get("/api/dashboard/admin/?from=2026-01-01&to=2026-10-21").json()
        self.assertEqual(admin["attrition_period"]["exits"], 1)
        # AI tools return the same numbers as the dashboard
        result, err = tools.execute(self.hr, "get_headcount", {"department": "IT"})
        self.assertFalse(err)
        self.assertEqual(result["headcount"], it["headcount"])
        result, _ = tools.execute(self.hr, "get_late_comers", {"period": "custom", "from_date": "2026-10-20",
                                                               "to_date": "2026-10-21"})
        self.assertEqual(result["late_comers"], data["top_late_comers"][:len(result["late_comers"])])
        result, _ = tools.execute(self.hr, "get_leave_summary", {"period": "today"})
        self.assertEqual([p["code"] for p in result["on_leave_today"]], ["E003"])

    def test_weekend_check_in_counts_as_present_today(self):
        a = self.employee("E001")
        saturday = date(2026, 10, 24)
        with mock.patch("django.utils.timezone.now", return_value=at(saturday, 11)):
            self.attendance(a, saturday, (10, 0))
            today = self.client_for(self.hr).get("/api/dashboard/hr/").json()["today"]
        self.assertEqual((today["present"], today["late"]), (1, 1))

    def test_bad_filters(self):
        r = self.client_for(self.hr).get("/api/dashboard/hr/?from=2026-10-21&to=2026-10-01")
        self.assertEqual(r.status_code, 400)

    def test_employee_dashboard(self):
        a = self.employee("E001")
        self.attendance(a, TODAY, (9, 30))
        data = self.client_for(a.user).get("/api/dashboard/employee/").json()
        self.assertEqual(data["late_count_month"], 1)
        self.assertEqual(data["hours_this_week"], 2.5)  # 09:30 -> 12:00 live
        self.assertIsNone(data["last_payslip"])
