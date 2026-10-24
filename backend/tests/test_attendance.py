from datetime import date
from unittest import mock

from apps.attendance import services
from apps.attendance.models import Attendance, AttendanceCorrection
from apps.leaves.models import LeaveRequest
from apps.org.models import CompanySettings, Holiday, LeaveType

from .helpers import HCMTestCase, at

WED = date(2026, 10, 21)  # a Wednesday


def frozen(dt):
    return mock.patch("django.utils.timezone.now", return_value=dt)


class CheckInTests(HCMTestCase):
    def setUp(self):
        super().setUp()
        self.emp = self.employee()
        self.c = self.client_for(self.emp.user)

    def test_on_time_then_duplicate_409(self):
        with frozen(at(WED, 9, 15)):
            r = self.c.post("/api/attendance/check-in/", {"check_in": "2020-01-01T08:00:00Z"}, format="json")
            self.assertEqual(r.status_code, 201)
            rec = Attendance.objects.get()
            self.assertEqual(rec.status, "present")  # 09:15 is still within grace
            self.assertEqual(rec.check_in, at(WED, 9, 15))  # server time, client value ignored
            self.assertEqual(self.c.post("/api/attendance/check-in/").status_code, 409)

    def test_late_after_0915(self):
        with frozen(at(WED, 9, 16)):
            self.c.post("/api/attendance/check-in/")
        rec = Attendance.objects.get()
        self.assertEqual(rec.status, "late")
        self.assertTrue(rec.is_late)

    def test_half_day_under_five_hours(self):
        with frozen(at(WED, 9, 0)):
            self.c.post("/api/attendance/check-in/")
        with frozen(at(WED, 13, 59)):
            self.assertEqual(self.c.post("/api/attendance/check-out/").status_code, 200)
        self.assertEqual(Attendance.objects.get().status, "half_day")

    def test_full_day_and_double_checkout(self):
        with frozen(at(WED, 9, 0)):
            self.c.post("/api/attendance/check-in/")
        with frozen(at(WED, 17, 0)):
            self.c.post("/api/attendance/check-out/")
            self.assertEqual(self.c.post("/api/attendance/check-out/").status_code, 409)
        rec = Attendance.objects.get()
        self.assertEqual((rec.status, rec.worked_minutes), ("present", 480))

    def test_checkout_without_checkin(self):
        with frozen(at(WED, 17, 0)):
            self.assertEqual(self.c.post("/api/attendance/check-out/").status_code, 422)

    def test_missing_checkout_next_day(self):
        self.attendance(self.emp, date(2026, 10, 20), (9, 0))
        with frozen(at(WED, 10, 0)):
            services.close_stale_records()
        self.assertEqual(Attendance.objects.get().status, "missing_checkout")

    def test_settings_change_applies_to_new_records_only(self):
        with frozen(at(date(2026, 10, 20), 9, 20)):
            self.c.post("/api/attendance/check-in/")
        s = CompanySettings.get()
        s.grace_minutes = 30
        s.save()
        with frozen(at(WED, 9, 20)):
            self.c.post("/api/attendance/check-in/")
        statuses = dict(Attendance.objects.values_list("date", "status"))
        self.assertEqual(statuses[date(2026, 10, 20)], "late")
        self.assertEqual(statuses[WED], "present")

    def test_hr_without_profile_cannot_check_in(self):
        with frozen(at(WED, 9, 0)):
            self.assertEqual(self.client_for(self.hr).post("/api/attendance/check-in/").status_code, 422)


class DayStatusTests(HCMTestCase):
    def test_absent_vs_leave_vs_weekend_vs_holiday(self):
        emp = self.employee()
        Holiday.objects.create(date=date(2026, 10, 14), name="Test holiday")
        LeaveRequest.objects.create(employee=emp, leave_type=LeaveType.objects.get(code="sick"), days=1,
                                    start_date=date(2026, 10, 13), end_date=date(2026, 10, 13), reason="flu",
                                    status="approved")
        self.attendance(emp, date(2026, 10, 12), (9, 0), (17, 0))
        with frozen(at(date(2026, 10, 19), 8, 0)):
            row = services.day_matrix([emp], date(2026, 10, 10), date(2026, 10, 20))[emp.pk]
        self.assertEqual(row[date(2026, 10, 10)].status, "weekend")
        self.assertEqual(row[date(2026, 10, 12)].status, "present")
        self.assertEqual(row[date(2026, 10, 13)].status, "on_leave")
        self.assertEqual(row[date(2026, 10, 14)].status, "holiday")
        self.assertEqual(row[date(2026, 10, 15)].status, "absent")
        self.assertEqual(row[date(2026, 10, 19)].status, "not_marked")
        self.assertEqual(row[date(2026, 10, 20)].status, "future")
        s = services.summarize([row])
        # 12 present, 13 leave, 15 + 16 absent -> rate = 1 / (4 - 1)
        self.assertEqual((s["present"], s["on_leave"], s["absent"]), (1, 1, 2))
        self.assertEqual(s["attendance_rate"], 33.3)

    def test_not_employed_before_join(self):
        emp = self.employee(join=date(2026, 10, 15))
        with frozen(at(WED, 8, 0)):
            row = services.day_matrix([emp], date(2026, 10, 12), date(2026, 10, 16))[emp.pk]
        self.assertEqual(row[date(2026, 10, 12)].status, "not_employed")
        self.assertEqual(services.summarize([row])["absent"], 2)


class CorrectionTests(HCMTestCase):
    def test_request_and_approve_creates_record(self):
        emp = self.employee()
        with frozen(at(WED, 10, 0)):
            r = self.client_for(emp.user).post("/api/attendance/corrections/", {
                "date": "2026-10-20", "check_in_time": "09:05", "check_out_time": "17:30", "reason": "Forgot"})
            self.assertEqual(r.status_code, 201, r.content)
            cid = r.json()["id"]
            # employees cannot approve
            self.assertEqual(self.client_for(emp.user).post(f"/api/attendance/corrections/{cid}/approve/").status_code,
                             403)
            r = self.client_for(self.hr).post(f"/api/attendance/corrections/{cid}/approve/", {"comment": "ok"})
            self.assertEqual(r.status_code, 200)
        rec = Attendance.objects.get(employee=emp, date=date(2026, 10, 20))
        self.assertEqual((rec.status, rec.source), ("present", "correction"))
        self.assertEqual(AttendanceCorrection.objects.get().status, "approved")
        self.assertEqual(emp.user.notifications.filter(kind="attendance").count(), 1)

    def test_no_future_corrections(self):
        emp = self.employee()
        with frozen(at(WED, 10, 0)):
            r = self.client_for(emp.user).post("/api/attendance/corrections/", {
                "date": "2026-10-25", "check_in_time": "09:00", "reason": "x"})
        self.assertEqual(r.status_code, 422)


class CameraTests(HCMTestCase):
    def setUp(self):
        super().setUp()
        s = CompanySettings.get()
        s.office_lat, s.office_lng, s.office_radius_m = 24.8607, 67.0011, 150
        s.save()
        self.c = self.client_for(self.employee().user)

    def post(self, **kw):
        body = {"latitude": 24.8607, "longitude": 67.0011, "accuracy": 20, "face_count": 1, **kw}
        with frozen(at(WED, 9, 0)):
            return self.c.post("/api/attendance/camera-check-in/", body, format="json")

    def test_rejections(self):
        self.assertEqual(self.post(face_count=0).json()["code"], "no_face")
        self.assertEqual(self.post(face_count=2).json()["code"], "multiple_faces")
        self.assertEqual(self.post(accuracy=150).json()["code"], "poor_accuracy")
        self.assertEqual(self.post(latitude=24.8707).json()["code"], "outside_geofence")  # ~1.1 km away

    def test_accepted_inside_radius(self):
        r = self.post(latitude=24.8613)  # ~67 m north
        self.assertEqual(r.status_code, 201, r.content)
        rec = Attendance.objects.get()
        self.assertEqual(rec.source, "camera")
        self.assertLess(rec.distance_m, 150)
