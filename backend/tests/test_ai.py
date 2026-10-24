import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import override_settings

from apps.ai import providers, tools
from apps.ai.models import AILog
from apps.payroll.services import generate_draft

from .helpers import HCMTestCase, at

TODAY = date(2026, 10, 24)  # Saturday -> "next Monday" = 26 Oct


class FakeProvider:
    """Scripted provider: each item is a str (final text) or a list of (tool_name, args) calls."""

    name, model = "fake", "fake-1"

    def __init__(self, script, exc=None):
        self.script, self.exc, self.seen_tools = list(script), exc, []

    def user_message(self, text):
        return {"role": "user", "content": text}

    assistant_text = user_message

    def tool_results(self, results):
        self.results = [(c.name, json.loads(content), err) for c, content, err in results]
        return [{"role": "tool", "content": content} for _, content, _ in results]

    def complete(self, *, system, messages, tools=None, timeout=15.0, max_tokens=2048):
        if self.exc:
            raise self.exc
        self.seen_tools = [t["name"] for t in (tools or [])]
        self.system = system
        step = self.script.pop(0)
        if isinstance(step, str):
            return providers.LLMTurn(text=step)
        calls = [providers.ToolCall(f"c{i}", name, args) for i, (name, args) in enumerate(step)]
        return providers.LLMTurn(text="", tool_calls=calls, assistant_message={"role": "assistant", "content": ""})


@override_settings(AI_API_KEY="test-key")
class AITests(HCMTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("django.utils.timezone.now", return_value=at(TODAY, 11))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.emp = self.employee("E001", first_name="Ali")
        self.other = self.employee("E002", first_name="Bilal", basic="300000")

    def fake(self, script, exc=None):
        fake = FakeProvider(script, exc)
        patcher = mock.patch.object(providers, "get_provider", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_chat_runs_tool_with_user_scope_and_logs(self):
        fake = self.fake([[("get_my_leave_balance", {})], "You have 8 sick days left."])
        r = self.client_for(self.emp.user).post("/api/ai/chat/", {"message": "How many sick leaves do I have left?"},
                                                format="json").json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["tools_used"], ["get_my_leave_balance"])
        self.assertTrue(r["ai_generated"])
        sick = [b for b in fake.results[0][1]["balances"] if b["code"] == "sick"][0]
        self.assertEqual(sick["remaining"], 8)
        log = AILog.objects.get()
        self.assertEqual((log.feature, log.outcome, log.tools_called[0]["name"]), ("chat", "ok", "get_my_leave_balance"))
        # employees are not offered company-wide tools
        self.assertNotIn("get_headcount", fake.seen_tools)
        self.assertNotIn("get_late_comers", fake.seen_tools)

    def test_employee_cannot_get_colleague_salary_via_tools(self):
        generate_draft(2026, 10, actor=self.hr)
        from apps.payroll.services import finalize
        from apps.payroll.models import PayrollRun
        finalize(PayrollRun.objects.get().pk, actor=self.admin)
        result, err = tools.execute(self.emp.user, "get_payroll_summary", {"month": "2026-10"})
        self.assertFalse(err)
        self.assertEqual(len(result["payslips"]), 1)
        self.assertEqual(result["payslips"][0]["gross"], Decimal("150000.00"))  # own, not Bilal's 450k
        found, _ = tools.execute(self.emp.user, "search_employees", {"query": "Bilal"})
        self.assertEqual(found["count"], 0)
        denied, err = tools.execute(self.emp.user, "get_headcount", {})
        self.assertTrue(err)
        self.assertIn("Permission denied", denied["error"])
        denied, err = tools.execute(self.emp.user, "get_late_comers", {"period": "this_month"})
        self.assertTrue(err)

    def test_unknown_args_and_department(self):
        res, err = tools.execute(self.hr, "get_headcount", {"department": "Marketing"})
        self.assertTrue(err)
        self.assertIn("Known departments", res["error"])
        res, err = tools.execute(self.hr, "get_headcount", {"sql": "drop table"})
        self.assertTrue(err)

    def test_policy_in_system_prompt(self):
        fake = self.fake(["Late after 09:15."])
        self.client_for(self.emp.user).post("/api/ai/chat/", {"message": "When am I late?"}, format="json")
        self.assertIn("after 09:15 is late", fake.system)
        self.assertIn("Politely refuse", fake.system)

    def test_timeout_and_provider_error_are_graceful(self):
        self.fake([], exc=providers.ProviderTimeout("slow"))
        r = self.client_for(self.emp.user).post("/api/ai/chat/", {"message": "hi"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertEqual(AILog.objects.get().outcome, "timeout")

    @override_settings(AI_API_KEY="")
    def test_unconfigured(self):
        r = self.client_for(self.emp.user).post("/api/ai/chat/", {"message": "hi"}, format="json").json()
        self.assertFalse(r["ok"])
        self.assertIn("not configured", r["answer"])

    @override_settings(AI_RATE_LIMIT_PER_HOUR=2)
    def test_rate_limit(self):
        self.fake(["a", "b", "c"])
        c = self.client_for(self.emp.user)
        for _ in range(2):
            self.assertEqual(c.post("/api/ai/chat/", {"message": "hi"}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/ai/chat/", {"message": "hi"}, format="json").status_code, 429)

    def test_smart_leave_retry_then_valid(self):
        fake = self.fake(["not json at all",
                          '{"leave_type": "casual", "start_date": "2026-10-26", "end_date": "2026-10-27", '
                          '"reason": "Sister\'s wedding"}'])
        r = self.client_for(self.emp.user).post("/api/ai/smart-leave/", {
            "text": "I need next Monday and Tuesday off for my sister's wedding"}, format="json").json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["draft"]["leave_type"], "casual")
        self.assertEqual((r["draft"]["start_date"], r["draft"]["end_date"]), ("2026-10-26", "2026-10-27"))
        self.assertEqual(r["days"], 2)
        self.assertIn("2026-10-26 Monday", fake.system)
        from apps.leaves.models import LeaveRequest
        self.assertEqual(LeaveRequest.objects.count(), 0)  # AI never saves

    def test_smart_leave_falls_back_after_two_invalid(self):
        self.fake(['{"leave_type": "vacation"}', "still wrong"])
        r = self.client_for(self.emp.user).post("/api/ai/smart-leave/", {"text": "off tomorrow"}, format="json").json()
        self.assertFalse(r["ok"])
        self.assertTrue(r["fallback"])
        self.assertEqual(AILog.objects.get().outcome, "invalid_output")

    def test_summary_validates_bullets_and_is_staff_only(self):
        self.fake(['{"bullets": ["Headcount is 2.", "No late arrivals.", "No leave today."]}'])
        r = self.client_for(self.hr).post("/api/ai/summary/", {}, format="json").json()
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["bullets"]), 3)
        self.assertEqual(self.client_for(self.emp.user).post("/api/ai/summary/", {}).status_code, 403)
        self.assertEqual(self.client_for(self.hr).post("/api/ai/summary/", {"dashboard": "admin"}).status_code, 403)
