from datetime import date, timedelta
from unittest import mock

from apps.analytics.insights import absence_anomalies, attrition_risk
from apps.org.services import WorkCalendar

from .helpers import HCMTestCase, at

TODAY = date(2026, 10, 30)  # Friday


class InsightTests(HCMTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("django.utils.timezone.now", return_value=at(TODAY, 18))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cal = WorkCalendar()

    def attend_all(self, emp, start, skip=(), late=()):
        for d in self.cal.working_days(start, TODAY):
            if d not in skip:
                self.attendance(emp, d, (9, 30) if d in late else (9, 0), (17, 30))

    def test_attrition_risk_ranks_and_explains(self):
        steady = self.employee("E001", join=date(2023, 1, 1))  # >1y, active, perfect attendance
        self.attend_all(steady, date(2026, 9, 1))
        risky = self.employee("E002", join=date(2026, 6, 1), employment_status="probation")
        self.attend_all(risky, date(2026, 9, 1), skip={date(2026, 10, d) for d in (5, 6, 7, 8, 9, 12, 13)},
                        late={date(2026, 10, d) for d in (19, 20, 21, 22, 23)})
        result = {r["code"]: r for r in attrition_risk(today=TODAY)}
        self.assertEqual(result["E001"]["score"], 0)
        self.assertEqual(result["E001"]["level"], "low")
        # absence 7/44 days -> 27.8 + late 5/37 days -> 6.8 + tenure 10 + probation 10 = 55
        self.assertEqual(result["E002"]["score"], 55)
        self.assertEqual(result["E002"]["level"], "medium")
        self.assertTrue(any("absent 7" in r for r in result["E002"]["reasons"]))
        self.assertIn("on probation", result["E002"]["reasons"])
        self.assertEqual(attrition_risk(today=TODAY)[0]["code"], "E002")

    def test_anomaly_flags(self):
        streak = self.employee("E001", join=date(2026, 1, 1))
        self.attend_all(streak, date(2026, 9, 1), skip={date(2026, 10, d) for d in (12, 13, 14, 15)})
        mondays = self.employee("E002", join=date(2026, 1, 1))
        edge = {date(2026, 10, d) for d in (2, 5, 9, 16)}  # Fri, Mon, Fri, Fri
        self.attend_all(mondays, date(2026, 9, 1), skip=edge)
        types = {(f["code"], f["type"]) for f in absence_anomalies(start=date(2026, 9, 1), end=TODAY, today=TODAY)}
        self.assertIn(("E001", "consecutive_absence"), types)
        self.assertIn(("E002", "weekend_adjacent_absence"), types)
        self.assertNotIn(("E002", "consecutive_absence"), types)

    def test_empty_and_dashboard_wiring(self):
        self.assertEqual(attrition_risk(today=TODAY), [])
        self.assertEqual(absence_anomalies(today=TODAY), [])
        emp = self.employee("E001", join=TODAY - timedelta(days=10))
        data = self.client_for(self.hr).get("/api/dashboard/hr/").json()
        self.assertIn("insights", data)
        self.assertEqual(data["insights"]["risk_levels"]["low"] + data["insights"]["risk_levels"]["medium"]
                         + data["insights"]["risk_levels"]["high"], 1)
        self.assertEqual(self.client_for(emp.user).get("/api/dashboard/hr/").status_code, 403)
