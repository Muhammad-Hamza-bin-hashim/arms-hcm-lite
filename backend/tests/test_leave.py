from datetime import date
from unittest import mock

from apps.leaves.models import LeaveRequest
from apps.org.models import Holiday

from .helpers import HCMTestCase, at

TODAY = date(2026, 10, 21)


class LeaveTests(HCMTestCase):
    def setUp(self):
        super().setUp()
        self.emp = self.employee()
        self.c = self.client_for(self.emp.user)
        self.hr_client = self.client_for(self.hr)
        patcher = mock.patch("django.utils.timezone.now", return_value=at(TODAY, 10))
        patcher.start()
        self.addCleanup(patcher.stop)

    def apply(self, start, end, leave_type="casual", reason="Family event"):
        return self.c.post("/api/leave/requests/", {"leave_type": leave_type, "start_date": start, "end_date": end,
                                                    "reason": reason}, format="json")

    def test_working_days_skip_weekend_and_holiday(self):
        Holiday.objects.create(date=date(2026, 10, 27), name="Holiday")
        r = self.apply("2026-10-23", "2026-10-28")  # Fri..Wed: Fri, Mon, (Tue holiday), Wed
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["days"], 3)

    def test_weekend_only_rejected(self):
        self.assertEqual(self.apply("2026-10-24", "2026-10-25").status_code, 422)

    def test_overlap_422(self):
        self.assertEqual(self.apply("2026-11-02", "2026-11-03").status_code, 201)
        r = self.apply("2026-11-03", "2026-11-04", "sick")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["code"], "overlap")

    def test_over_balance_422_counts_pending(self):
        self.assertEqual(self.apply("2026-11-02", "2026-11-06", "sick").status_code, 201)  # 5 of 8
        r = self.apply("2026-11-09", "2026-11-12", "sick")  # 4 more -> 9 > 8
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["code"], "insufficient_balance")
        self.assertEqual(self.apply("2026-11-09", "2026-11-11", "sick").status_code, 201)  # exactly 8

    def test_unpaid_unlimited(self):
        self.assertEqual(self.apply("2026-11-02", "2026-12-15", "unpaid").status_code, 201)

    def test_approve_reject_and_balance(self):
        lr = self.apply("2026-11-02", "2026-11-03", "sick").json()
        self.assertEqual(self.c.post(f"/api/leave/requests/{lr['id']}/approve/").status_code, 403)
        self.assertEqual(self.client_for(self.admin).post(f"/api/leave/requests/{lr['id']}/approve/").status_code, 403)
        r = self.hr_client.post(f"/api/leave/requests/{lr['id']}/approve/", {"comment": "Get well"})
        self.assertEqual(r.json()["status"], "approved")
        self.assertEqual(self.hr_client.post(f"/api/leave/requests/{lr['id']}/approve/").status_code, 409)
        bal = {b["code"]: b for b in self.c.get("/api/leave/balance/").json()["balances"]}
        self.assertEqual((bal["sick"]["used"], bal["sick"]["remaining"]), (2, 6))
        self.assertEqual(self.emp.user.notifications.filter(kind="leave").count(), 1)

        other = self.apply("2026-11-10", "2026-11-10").json()
        self.assertEqual(self.hr_client.post(f"/api/leave/requests/{other['id']}/reject/").status_code, 422)  # comment
        r = self.hr_client.post(f"/api/leave/requests/{other['id']}/reject/", {"comment": "Busy week"})
        self.assertEqual(r.json()["status"], "rejected")

    def test_cancel_rules(self):
        lr = self.apply("2026-11-02", "2026-11-03").json()
        self.assertEqual(self.c.post(f"/api/leave/requests/{lr['id']}/cancel/").json()["status"], "cancelled")
        past = LeaveRequest.objects.create(employee=self.emp, leave_type_id=lr["leave_type"], days=1, reason="x",
                                           start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
                                           status="approved")
        self.assertEqual(self.c.post(f"/api/leave/requests/{past.pk}/cancel/").status_code, 422)

    def test_cannot_cancel_or_see_others(self):
        other = self.employee("E002")
        lr = self.client_for(other.user).post("/api/leave/requests/", {
            "leave_type": "casual", "start_date": "2026-11-02", "end_date": "2026-11-02", "reason": "x"}).json()
        self.assertEqual(self.c.post(f"/api/leave/requests/{lr['id']}/cancel/").status_code, 404)
        self.assertEqual(self.c.get("/api/leave/requests/").json()["count"], 0)
        self.assertEqual(self.c.get(f"/api/leave/balance/?employee={other.pk}").json()["balances"][0]["used"], 0)

    def test_hr_cannot_approve_own_leave(self):
        hr_emp = self.employee("H001", email="hr@arms.test")  # links the HR login to an employee profile
        self.assertEqual(hr_emp.user, self.hr)
        lr = self.client_for(self.hr).post("/api/leave/requests/", {
            "leave_type": "casual", "start_date": "2026-11-02", "end_date": "2026-11-02", "reason": "x"}).json()
        r = self.client_for(self.hr).post(f"/api/leave/requests/{lr['id']}/approve/")
        self.assertEqual(r.status_code, 422)
