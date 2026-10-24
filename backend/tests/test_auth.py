from apps.accounts.models import Role, User
from apps.comms.models import AuditLog

from .helpers import PASSWORD, HCMTestCase


class FirstRunTests(HCMTestCase):
    def test_setup_only_once(self):
        r = self.client.post("/api/setup/", {"company_name": "X", "email": "x@x.test", "password": PASSWORD})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self.client.get("/api/setup/status/").json()["setup_completed"])

    def test_fresh_setup_creates_admin_and_leave_types(self):
        User.objects.all().delete()
        from apps.org.models import CompanySettings, LeaveType
        CompanySettings.objects.all().delete()
        LeaveType.objects.all().delete()
        self.assertFalse(self.client.get("/api/setup/status/").json()["setup_completed"])
        r = self.client.post("/api/setup/", {"company_name": "AR&MS", "email": "Boss@Arms.test", "password": PASSWORD})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["user"]["role"], "admin")
        self.assertEqual(set(LeaveType.objects.values_list("code", "yearly_quota")),
                         {("annual", 14), ("sick", 8), ("casual", 10), ("unpaid", None)})

    def test_weak_password_rejected(self):
        User.objects.all().delete()
        r = self.client.post("/api/setup/", {"company_name": "X", "email": "x@x.test", "password": "123"})
        self.assertEqual(r.status_code, 400)


class LoginTests(HCMTestCase):
    def test_login_and_password_is_hashed(self):
        r = self.client.post("/api/auth/login/", {"email": "admin@arms.test", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.json())
        self.assertTrue(User.objects.get(email="admin@arms.test").password.startswith(("bcrypt", "pbkdf2", "md5")))

    def test_wrong_password(self):
        r = self.client.post("/api/auth/login/", {"email": "admin@arms.test", "password": "nope-nope"})
        self.assertEqual(r.status_code, 401)

    def test_inactive_account_cannot_login_and_tokens_revoked(self):
        emp = self.employee()
        client = self.client_for(emp.user)
        self.assertEqual(client.get("/api/auth/me/").status_code, 200)
        r = self.client_for(self.admin).post(f"/api/users/{emp.user.pk}/deactivate/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        r = self.client.post("/api/auth/login/", {"email": emp.email, "password": PASSWORD})
        self.assertEqual(r.status_code, 401)


class TemporaryPasswordTests(HCMTestCase):
    def test_hr_creates_employee_with_temp_password_must_change(self):
        r = self.client_for(self.hr).post("/api/employees/", {
            "employee_code": "e010", "first_name": "Sara", "last_name": "Khan", "email": "sara@arms.test",
            "department": self.it.pk, "join_date": "2026-02-01", "basic_salary": "80000"})
        self.assertEqual(r.status_code, 201, r.content)
        temp = r.json()["temporary_password"]
        login = self.client.post("/api/auth/login/", {"email": "sara@arms.test", "password": temp}).json()
        self.assertTrue(login["user"]["must_change_password"])
        from rest_framework.test import APIClient
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
        self.assertEqual(c.get("/api/dashboard/employee/").status_code, 403)
        r = c.post("/api/auth/change-password/", {"current_password": temp, "new_password": "Brand-New-Pass9"})
        self.assertEqual(r.status_code, 200)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        self.assertEqual(c.get("/api/dashboard/employee/").status_code, 200)


class RoleTests(HCMTestCase):
    def test_hr_cannot_create_admin_or_hr_users(self):
        r = self.client_for(self.hr).post("/api/users/", {"email": "evil@arms.test", "first_name": "E"})
        self.assertEqual(r.status_code, 403)

    def test_admin_creates_hr_only(self):
        r = self.client_for(self.admin).post("/api/users/", {"email": "hr2@arms.test", "first_name": "H",
                                                             "role": "admin"})
        self.assertEqual(r.status_code, 400)
        r = self.client_for(self.admin).post("/api/users/", {"email": "hr2@arms.test", "first_name": "H"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(User.objects.get(email="hr2@arms.test").role, Role.HR)
        self.assertTrue(r.json()["temporary_password"].startswith("Tmp-"))

    def test_hr_cannot_change_settings_or_view_audit(self):
        hr = self.client_for(self.hr)
        self.assertEqual(hr.get("/api/settings/").status_code, 200)
        self.assertEqual(hr.patch("/api/settings/", {"grace_minutes": 60}).status_code, 403)
        self.assertEqual(hr.post("/api/departments/", {"name": "X", "code": "X"}).status_code, 403)
        self.assertEqual(hr.get("/api/audit-logs/").status_code, 403)

    def test_employee_blocked_from_admin_endpoints(self):
        c = self.client_for(self.employee().user)
        for url in ["/api/settings/", "/api/users/", "/api/audit-logs/", "/api/dashboard/hr/",
                    "/api/dashboard/admin/", "/api/payroll/runs/", "/api/attendance/board/"]:
            self.assertEqual(c.get(url).status_code, 403, url)

    def test_settings_change_is_audited(self):
        r = self.client_for(self.admin).patch("/api/settings/", {"grace_minutes": 10}, format="json")
        self.assertEqual(r.status_code, 200)
        entry = AuditLog.objects.filter(action="settings.updated").first()
        self.assertEqual(entry.before["grace_minutes"], 15)
        self.assertEqual(entry.after["grace_minutes"], 10)

    def test_audit_log_is_immutable(self):
        entry = AuditLog.objects.first()
        from django.core.exceptions import PermissionDenied
        entry.summary = "tampered"
        with self.assertRaises(PermissionDenied):
            entry.save()
        with self.assertRaises(PermissionDenied):
            entry.delete()
