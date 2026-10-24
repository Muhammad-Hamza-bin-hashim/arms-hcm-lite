from django.core.files.uploadedfile import SimpleUploadedFile

from apps.employees.models import Employee

from .helpers import HCMTestCase

CSV_HEADER = "employee_code,first_name,last_name,email,department,designation,join_date,basic_salary\n"


def csv_file(body):
    return SimpleUploadedFile("emp.csv", (CSV_HEADER + body).encode(), content_type="text/csv")


class EmployeeTests(HCMTestCase):
    def test_duplicate_code_and_email_rejected(self):
        self.employee("E001", email="a@arms.test")
        hr = self.client_for(self.hr)
        base = {"first_name": "X", "department": self.it.pk, "join_date": "2026-01-01", "basic_salary": "1000"}
        r = hr.post("/api/employees/", {**base, "employee_code": "e001", "email": "new@arms.test"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("employee_code", r.json()["errors"])
        r = hr.post("/api/employees/", {**base, "employee_code": "E002", "email": "A@arms.test"})
        self.assertEqual(r.status_code, 422)

    def test_salary_must_be_positive(self):
        r = self.client_for(self.hr).post("/api/employees/", {
            "employee_code": "E9", "first_name": "X", "email": "x9@arms.test", "department": self.it.pk,
            "join_date": "2026-01-01", "basic_salary": "0"})
        self.assertEqual(r.status_code, 400)

    def test_admin_views_but_cannot_register(self):
        r = self.client_for(self.admin).post("/api/employees/", {})
        self.assertEqual(r.status_code, 403)
        self.employee()
        self.assertEqual(self.client_for(self.admin).get("/api/employees/").json()["count"], 1)

    def test_search_filter_pagination(self):
        for i in range(25):
            self.employee(f"E{i:03d}", dept=self.it if i % 2 else self.finance)
        hr = self.client_for(self.hr)
        page = hr.get("/api/employees/").json()
        self.assertEqual(page["count"], 25)
        self.assertEqual(len(page["results"]), 20)
        self.assertEqual(hr.get("/api/employees/?page=2").json()["results"].__len__(), 5)
        self.assertEqual(hr.get(f"/api/employees/?department={self.finance.pk}").json()["count"], 13)
        self.assertEqual(hr.get("/api/employees/?search=E007").json()["count"], 1)

    def test_employee_isolation(self):
        a, b = self.employee("E001"), self.employee("E002")
        c = self.client_for(a.user)
        listing = c.get("/api/employees/").json()
        self.assertEqual([r["id"] for r in listing["results"]], [a.pk])
        self.assertEqual(c.get(f"/api/employees/{b.pk}/").status_code, 404)
        self.assertEqual(c.get(f"/api/employees/{b.pk}/360/").status_code, 404)
        self.assertEqual(c.get(f"/api/employees/{a.pk}/360/").status_code, 200)

    def test_employee_edits_only_phone_and_address(self):
        a = self.employee("E001")
        c = self.client_for(a.user)
        r = c.patch("/api/employees/me/", {"phone": "0300-1234567", "address": "Karachi"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["phone"], "0300-1234567")
        r = c.patch("/api/employees/me/", {"phone": "1", "department": self.finance.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.patch(f"/api/employees/{a.pk}/", {"first_name": "Hacker"}, format="json").status_code, 403)

    def test_exit_deactivates_login(self):
        a = self.employee("E001")
        r = self.client_for(self.hr).patch(f"/api/employees/{a.pk}/", {"employment_status": "exited",
                                                                       "exit_date": "2026-10-01"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        a.user.refresh_from_db()
        self.assertFalse(a.user.is_active)


class CsvTests(HCMTestCase):
    def test_dry_run_reports_row_field_reason(self):
        self.employee("E001", email="taken@arms.test")
        body = ("E100,Ali,Raza,ali@arms.test,IT,Developer,2026-03-01,90000\n"
                "E001,Dup,Code,dup@arms.test,IT,,2026-03-01,90000\n"
                "E101,Bad,Mail,not-an-email,IT,,2026-03-01,90000\n"
                "E102,No,Dept,nodept@arms.test,Marketing,,2026-03-01,90000\n"
                "E103,Bad,Date,bd@arms.test,FIN,,03/01/2026,90000\n"
                "E104,Neg,Sal,neg@arms.test,IT,,2026-03-01,-5\n"
                "E105,,Missing,taken@arms.test,IT,,2026-03-01,1000\n")
        r = self.client_for(self.hr).post("/api/employees/import/", {"file": csv_file(body), "dry_run": "true"},
                                          format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["total_rows"], 7)
        self.assertEqual(data["valid_rows"], 1)
        got = {(e["row"], e["field"]) for e in data["errors"]}
        self.assertTrue({(3, "employee_code"), (4, "email"), (5, "department"), (6, "join_date"),
                         (7, "basic_salary"), (8, "first_name"), (8, "email")} <= got, got)
        self.assertEqual(Employee.objects.count(), 1)  # dry run saved nothing

    def test_import_all_or_nothing_and_export(self):
        hr = self.client_for(self.hr)
        bad = "E100,Ali,Raza,ali@arms.test,IT,,2026-03-01,90000\nE101,X,Y,bad,IT,,2026-03-01,1\n"
        r = hr.post("/api/employees/import/", {"file": csv_file(bad), "dry_run": "false"}, format="multipart")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(Employee.objects.count(), 0)
        good = "E100,Ali,Raza,ali@arms.test,IT,Developer,2026-03-01,90000\nE101,Zara,Y,z@arms.test,FIN,,2026-03-01,1000\n"
        r = hr.post("/api/employees/import/", {"file": csv_file(good), "dry_run": "false"}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(len(r.json()["created"]), 2)
        export = hr.get("/api/employees/export/")
        self.assertEqual(export.status_code, 200)
        self.assertIn("ali@arms.test", export.content.decode())

    def test_export_neutralises_formulas(self):
        self.employee("E001", first_name="=HYPERLINK(1)")
        content = self.client_for(self.hr).get("/api/employees/export/").content.decode()
        self.assertIn("'=HYPERLINK(1)", content)
