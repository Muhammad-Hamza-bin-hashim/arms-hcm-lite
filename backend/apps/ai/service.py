"""AI assistant (M8): chat with tools, dashboard summary, smart leave, policy Q&A.

Guardrails: key on server only, tools reuse REST services with the caller's scope, the AI never
writes data, JSON output is validated (retry once, then fall back), 15 s deadline, ~20 calls per
user per hour, every call logged in ai_logs.
"""
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework.exceptions import Throttled

from apps.accounts.models import Role
from apps.org.models import CompanySettings, Holiday, LeaveType
from apps.org.services import local_today

from . import providers, tools
from .models import AILog

log = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 4
MAX_HISTORY = 10
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FALLBACK_CHAT = ("Sorry, the assistant is unavailable right now. Your data is safe - please try again in a minute, "
                 "or use the dashboards and forms directly.")


def _json(data):
    return json.dumps(data, cls=DjangoJSONEncoder, default=str)


def check_rate_limit(user):
    since = timezone.now() - timedelta(hours=1)
    used = AILog.objects.filter(user=user, created_at__gte=since).count()
    if used >= settings.AI_RATE_LIMIT_PER_HOUR:
        raise Throttled(detail=f"AI limit reached ({settings.AI_RATE_LIMIT_PER_HOUR} requests per hour). "
                               "Please try again later.")


def _log(user, feature, prompt, *, outcome, response="", tools_called=None, error="", started=None, provider=None):
    return AILog.objects.create(
        user=user, role=user.role, feature=feature, prompt=prompt[:4000], response=response[:8000],
        tools_called=tools_called or [], outcome=outcome, error=error[:2000],
        provider=getattr(provider, "name", settings.AI_PROVIDER), model=getattr(provider, "model", settings.AI_MODEL),
        latency_ms=int((time.monotonic() - started) * 1000) if started else 0,
    )


# ---------- policy (Section 3 rules, rendered from live settings) ----------

def policy_text():
    s = CompanySettings.get()
    weekend = ", ".join(WEEKDAYS[d] for d in sorted(s.weekend_days or [])) or "none"
    late_after = (datetime.combine(date.today(), s.office_start) + timedelta(minutes=s.grace_minutes)).time()
    quotas = "; ".join(f"{lt.name} ({lt.code}): {lt.yearly_quota if lt.yearly_quota is not None else 'unlimited'}"
                       f" days/year, {'paid' if lt.is_paid else 'unpaid'}" for lt in LeaveType.objects.filter(is_active=True))
    today = local_today()
    holidays = "; ".join(f"{h.date:%d %b %Y} {h.name}" for h in Holiday.objects.filter(
        date__gte=today, date__lte=today + timedelta(days=120))) or "none in the next 120 days"
    slabs = ("0% up to 600,000; 5% of income above 600,000 up to 1,200,000; 30,000 + 15% above 1,200,000 up to "
             "2,400,000; 210,000 + 25% above 2,400,000 up to 3,600,000; 510,000 + 35% above 3,600,000")
    return f"""COMPANY POLICY (the only rules you may use for policy questions):
- Office starts {s.office_start:%H:%M}, grace {s.grace_minutes} min: arriving after {late_after:%H:%M} is late.
- Working less than {Decimal(s.half_day_hours):g} hours is a half day. No check-out by end of day = missing_checkout.
- No attendance record and no approved leave on a working day = absent.
- Weekend: {weekend}. Upcoming public holidays: {holidays}.
- One attendance record per employee per day; the server sets the time. Mistakes are fixed by an attendance
  correction request that HR approves or rejects. Employees cannot edit attendance directly.
- Leave counts working days only (weekends and holidays skipped). Yearly quotas: {quotas}.
  Overlapping requests or requests above the remaining balance are rejected. HR approves or rejects with a comment.
  Pending leave can be cancelled; approved leave can be cancelled only before it starts.
- Payroll: gross = 1.5 x basic (basic + HRA 40% of basic + medical 10% of basic). Per-day rate = gross / working
  days in the month. Deduction = (absent days + unpaid leave days + 0.5 x half days) x per-day rate.
  Joiners and leavers are prorated by working days employed.{' Every 3 late arrivals deduct 0.5 day.' if s.late_penalty_enabled else ''}
  Illustrative annual tax on gross x 12: {slabs}; monthly tax = annual tax / 12.
  HR prepares the monthly draft; only Admin finalizes it, and finalized payroll is locked.
- Roles: Admin sets up the company and finalizes payroll; HR manages employees, approvals and payroll drafts;
  Employees see only their own data."""


def system_prompt(user):
    s = CompanySettings.get()
    today = local_today()
    scope = {
        Role.ADMIN: "an Admin: you may discuss all company data.",
        Role.HR: "HR: you may discuss HR data for all employees.",
        Role.EMPLOYEE: ("an Employee: you may ONLY discuss this person's own data and company policy. Politely refuse "
                        "any request about another employee's salary, pay, attendance, leave or personal details."),
    }[user.role]
    return f"""You are the HR assistant inside AR&MS HCM Lite for {s.company_name or 'AR&MS Management Company'}.
Today is {WEEKDAYS[today.weekday()]} {today.isoformat()} ({s.timezone}). The user is {user.full_name}, {scope}

Rules:
- The database is the only source of truth. For any number or fact about people, attendance, leave or payroll,
  call a tool and answer only from its result. Never invent, estimate or extrapolate numbers.
- If a tool returns an error or permission denied, explain that briefly. If you cannot answer, say you don't know.
- For policy questions answer only from the COMPANY POLICY below; if it isn't covered, say you don't know.
- You cannot create, change, approve or delete anything. Point users to the right screen instead.
- Be concise: short sentences or bullets, include the period and department you used.
- If the user writes in Roman Urdu, reply in Roman Urdu.

{policy_text()}"""


# ---------- chat ----------

def _clean_history(history):
    out = []
    if not isinstance(history, list):
        return out
    for item in history[-MAX_HISTORY:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
            out.append({"role": item["role"], "content": item["content"][:2000]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def chat(user, message, history=None):
    check_rate_limit(user)
    started = time.monotonic()
    deadline = started + settings.AI_TIMEOUT_SECONDS
    called = []
    provider = None
    try:
        provider = providers.get_provider()
        messages = [provider.user_message(m["content"]) if m["role"] == "user" else provider.assistant_text(m["content"])
                    for m in _clean_history(history)]
        messages.append(provider.user_message(message))
        role_tools = tools.tools_for(user.role)
        system = system_prompt(user)
        for _ in range(MAX_TOOL_ROUNDS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                raise providers.ProviderTimeout("deadline")
            turn = provider.complete(system=system, messages=messages, tools=role_tools, timeout=remaining)
            if turn.refused:
                answer = "I can't help with that request."
                break
            if not turn.tool_calls:
                answer = turn.text.strip() or "I don't know."
                break
            messages.append(turn.assistant_message)
            results = []
            for call in turn.tool_calls:
                result, is_error = tools.execute(user, call.name, call.arguments)
                called.append({"name": call.name, "arguments": call.arguments, "error": is_error})
                results.append((call, _json(result), is_error))
            messages.extend(provider.tool_results(results))
        else:
            answer = "That question needed too many steps. Please ask something more specific."
        _log(user, AILog.Feature.CHAT, message, outcome=AILog.Outcome.OK, response=answer, tools_called=called,
             started=started, provider=provider)
        return {"ok": True, "answer": answer, "tools_used": [c["name"] for c in called], "ai_generated": True}
    except providers.ProviderUnconfigured as exc:
        _log(user, AILog.Feature.CHAT, message, outcome=AILog.Outcome.UNCONFIGURED, error=str(exc), started=started)
        return {"ok": False, "answer": "The AI assistant is not configured on this server yet (missing AI_API_KEY).",
                "tools_used": [], "ai_generated": False}
    except providers.ProviderTimeout as exc:
        _log(user, AILog.Feature.CHAT, message, outcome=AILog.Outcome.TIMEOUT, tools_called=called, error=str(exc),
             started=started, provider=provider)
        return {"ok": False, "answer": "The assistant took too long to answer (15 s limit). Please try again.",
                "tools_used": [c["name"] for c in called], "ai_generated": False}
    except providers.ProviderError as exc:
        log.warning("AI provider error: %s", exc)
        _log(user, AILog.Feature.CHAT, message, outcome=AILog.Outcome.ERROR, tools_called=called, error=str(exc),
             started=started, provider=provider)
        return {"ok": False, "answer": FALLBACK_CHAT, "tools_used": [], "ai_generated": False}


# ---------- structured JSON helper ----------

def _extract_json(text):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found.")
    return json.loads(text[start:end + 1])


def _structured(user, feature, prompt_for_log, system, user_text, validate):
    """Ask for JSON, validate, retry once with the validation error, else report failure."""
    check_rate_limit(user)
    started = time.monotonic()
    deadline = started + settings.AI_TIMEOUT_SECONDS
    provider = None
    try:
        provider = providers.get_provider()
        messages = [provider.user_message(user_text)]
        last_error = ""
        for attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                raise providers.ProviderTimeout("deadline")
            turn = provider.complete(system=system, messages=messages, timeout=remaining, max_tokens=1024)
            try:
                value = validate(_extract_json(turn.text))
                _log(user, feature, prompt_for_log, outcome=AILog.Outcome.OK, response=turn.text, started=started,
                     provider=provider)
                return value, None
            except (ValueError, KeyError, TypeError) as exc:
                last_error = str(exc)
                messages += [provider.assistant_text(turn.text or "(empty)"),
                             provider.user_message(f"That output was invalid: {last_error}. Reply again with ONLY the "
                                                   "corrected JSON object.")]
        _log(user, feature, prompt_for_log, outcome=AILog.Outcome.INVALID, error=last_error, started=started,
             provider=provider)
        return None, "The AI reply could not be validated."
    except providers.ProviderUnconfigured as exc:
        _log(user, feature, prompt_for_log, outcome=AILog.Outcome.UNCONFIGURED, error=str(exc), started=started)
        return None, "The AI assistant is not configured on this server yet."
    except providers.ProviderTimeout as exc:
        _log(user, feature, prompt_for_log, outcome=AILog.Outcome.TIMEOUT, error=str(exc), started=started,
             provider=provider)
        return None, "The AI took too long to respond."
    except providers.ProviderError as exc:
        _log(user, feature, prompt_for_log, outcome=AILog.Outcome.ERROR, error=str(exc), started=started,
             provider=provider)
        return None, "The AI service is unavailable right now."


# ---------- dashboard summary ----------

def compact_kpis(dashboard: dict, role) -> dict:
    """KPI JSON for the summary: the same numbers the dashboard shows, without long lists."""
    d = dashboard
    insights = {"attrition_risk_levels": d["insights"]["risk_levels"],
                "absence_anomaly_flags": [{k: a[k] for k in ("type", "severity", "name", "detail")}
                                          for a in d["insights"]["anomalies"][:5]]}
    if role == Role.ADMIN:
        return {
            "insights": insights,
            "filters": d["filters"], "headcount": d["headcount"], "headcount_by_status": d["headcount_by_status"],
            "attrition_period": d["attrition_period"], "attrition_ytd": d["attrition_ytd"],
            "payroll_finalized": {k: d["payroll"][k] for k in ("total_gross", "total_net", "total_tax",
                                                                 "total_deductions", "payslip_count", "by_department")},
            "average_gross_salary": d["salary"]["average_gross"],
            "average_salary_by_department": d["salary"]["by_department"],
            "headcount_by_department": d["headcount_by_department"], "gender": d["gender"], "tenure": d["tenure"],
            "attendance": d["attendance"],
            "today": {k: v for k, v in d["today"].items() if k != "on_leave_list"},
        }
    return {
        "insights": insights,
        "filters": d["filters"], "headcount": d["headcount"],
        "today": {k: v for k, v in d["today"].items() if k != "on_leave_list"},
        "attendance": d["attendance"], "absenteeism_by_department": d["absenteeism_by_department"],
        "leave_by_type": d["leave"]["by_type"], "top_late_comers": d["top_late_comers"],
    }


def summarize_dashboard(user, kpis: dict):
    kpi_json = _json(kpis)
    system = ("You write dashboard insights for an HR system. Use ONLY the numbers in the KPI JSON. Do not invent "
              "trends, causes, percentages or comparisons that are not directly supported. If data is empty, say so. "
              "Null means 'not enough data'. Reply with ONLY a JSON object: {\"bullets\": [3 to 5 short strings]}.")

    def validate(obj):
        bullets = obj["bullets"]
        if not isinstance(bullets, list) or not 3 <= len(bullets) <= 5:
            raise ValueError("'bullets' must be a list of 3 to 5 strings")
        cleaned = [str(b).strip()[:300] for b in bullets if str(b).strip()]
        if len(cleaned) < 3:
            raise ValueError("bullets must be non-empty strings")
        return cleaned

    bullets, error = _structured(user, AILog.Feature.SUMMARY, "dashboard summary", system,
                                 f"KPI JSON for the current filters:\n{kpi_json}", validate)
    return {"ok": bullets is not None, "bullets": bullets or [], "error": error, "ai_generated": bullets is not None}


# ---------- smart leave ----------

def smart_leave(user, text):
    today = local_today()
    types = list(LeaveType.objects.filter(is_active=True))
    codes = {lt.code for lt in types}
    upcoming = "\n".join(f"{(today + timedelta(days=i)).isoformat()} {WEEKDAYS[(today + timedelta(days=i)).weekday()]}"
                         for i in range(0, 21))
    system = f"""You turn a leave request written in plain words (English or Roman Urdu) into JSON for a leave form.
Today is {WEEKDAYS[today.weekday()]} {today.isoformat()}. Calendar of the next 3 weeks:
{upcoming}
Date rules: "next <weekday>" means the first such weekday after today; "tomorrow" is today + 1 day.
A single day means start_date = end_date. Never pick dates in the past unless the text clearly says so.
Leave type codes: {", ".join(f"{lt.code} ({lt.name})" for lt in types)}.
Choose: illness/doctor -> sick; vacation/travel/long planned holiday -> annual; personal or family events
(wedding, function, errand, emergency) -> casual; explicitly unpaid -> unpaid.
Reply with ONLY a JSON object: {{"leave_type": code, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
"reason": short reason in English}}."""

    def validate(obj):
        lt = str(obj["leave_type"]).lower().strip()
        if lt not in codes:
            raise ValueError(f"leave_type must be one of {sorted(codes)}")
        start, end = date.fromisoformat(str(obj["start_date"])), date.fromisoformat(str(obj["end_date"]))
        if end < start:
            raise ValueError("end_date is before start_date")
        if start < today - timedelta(days=60) or end > today + timedelta(days=365):
            raise ValueError("dates are outside the allowed window")
        reason = str(obj.get("reason") or "").strip()[:500] or "Leave"
        return {"leave_type": lt, "start_date": start, "end_date": end, "reason": reason}

    draft, error = _structured(user, AILog.Feature.SMART_LEAVE, text, system, text[:1000], validate)
    if draft is None:
        return {"ok": False, "fallback": True, "error": error}
    result = {"ok": True, "draft": draft, "ai_generated": True, "days": None, "validation_error": None}
    # Same backend checks the real submission will run (nothing is saved here).
    from apps.leaves.services import validate_leave
    from config.exceptions import BusinessRuleError
    employee = getattr(user, "employee", None)
    if employee is not None:
        try:
            result["days"] = validate_leave(employee, LeaveType.objects.get(code=draft["leave_type"]),
                                            draft["start_date"], draft["end_date"])
        except BusinessRuleError as exc:
            result["validation_error"] = str(exc.detail)
    return result
