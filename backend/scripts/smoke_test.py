"""Smoke test: walks the brief's 5-minute demo over HTTP against a running FRESH install.

    python scripts/smoke_test.py                      # local server on :8000
    python scripts/smoke_test.py https://your-app.onrender.com

It creates real records (company, users, attendance, leave, payroll), so run it only on a
throwaway database - never on the instance the judges will use.
"""
import datetime
import sys
import time

import requests

ROOT = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
B = f"{ROOT}/api"
for _ in range(30):
    try:
        requests.get(f"{B}/health/", timeout=1)
        break
    except requests.RequestException:
        time.sleep(0.5)


def call(method, path, token=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.request(method, f"{B}{path}", headers=h, timeout=30, **kw)
    return r


def ok(r, code=200):
    if r.status_code != code:
        print("FAIL", r.request.method, r.url, r.status_code, r.text[:400])
        sys.exit(1)
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r


print("1. first-run setup")
if ok(call("GET", "/setup/status/"))["setup_completed"]:
    sys.exit("This instance is already set up. The smoke test needs a fresh, empty database.")
admin = ok(call("POST", "/setup/", json={"company_name": "AR&MS Management Company", "email": "admin@arms.pk",
                                        "password": "Admin#2026x", "first_name": "Ayesha", "last_name": "Rauf"}), 201)
A = admin["access"]
ok(call("PATCH", "/settings/", A, json={"office_lat": "24.860700", "office_lng": "67.001100", "office_radius_m": 150}))
it = ok(call("POST", "/departments/", A, json={"name": "Consulting", "code": "CON"}), 201)
ok(call("POST", "/designations/", A, json={"name": "Consultant"}), 201)
hr = ok(call("POST", "/users/", A, json={"email": "hr@arms.pk", "first_name": "Hamza", "last_name": "Ali"}), 201)

print("2. HR first login + registers employees")
H = ok(call("POST", "/auth/login/", json={"email": "hr@arms.pk", "password": hr["temporary_password"]}))
assert H["user"]["must_change_password"]
assert call("GET", "/employees/", H["access"]).status_code == 403
H = ok(call("POST", "/auth/change-password/", H["access"], json={"current_password": hr["temporary_password"], "new_password": "HrPass#2026"}))["access"]
emps = []
for code, name, basic in [("E001", "Sana", "100000"), ("E002", "Bilal", "300000"), ("E003", "Zara", "80000")]:
    r = ok(call("POST", "/employees/", H, json={"employee_code": code, "first_name": name, "last_name": "Khan",
                                                "email": f"{name.lower()}@arms.pk", "department": it["id"],
                                                "join_date": str(datetime.date.today().replace(day=1)), "basic_salary": basic, "gender": "female"}), 201)
    emps.append(r)

print("3. employee signs in, changes password, checks in (409 on second)")
e = emps[0]
E = ok(call("POST", "/auth/login/", json={"email": "sana@arms.pk", "password": e["temporary_password"]}))["access"]
E = ok(call("POST", "/auth/change-password/", E, json={"current_password": e["temporary_password"], "new_password": "Sana#2026pw"}))["access"]
ok(call("POST", "/attendance/check-in/", E), 201)
assert call("POST", "/attendance/check-in/", E).status_code == 409

print("4. leave: apply, HR approves")
today = datetime.date.today()
monday = today + datetime.timedelta(days=7 - today.weekday())  # next Monday
lr = ok(call("POST", "/leave/requests/", E, json={"leave_type": "casual", "start_date": str(monday),
                                                   "end_date": str(monday + datetime.timedelta(days=1)),
                                                   "reason": "Sister's wedding", "source": "ai"}), 201)
assert lr["days"] == 2, lr
ok(call("POST", f"/leave/requests/{lr['id']}/approve/", H, json={"comment": "Congrats"}))
bal = {b["code"]: b for b in ok(call("GET", "/leave/balance/", E))["balances"]}
assert bal["casual"]["remaining"] == 8, bal["casual"]

print("5. dashboards, AI fallback without key")
hd = ok(call("GET", "/dashboard/hr/", H))
assert hd["headcount"] == 3 and hd["today"]["present"] == 1, hd["today"]
assert "insights" in hd
ai = ok(call("POST", "/ai/chat/", H, json={"message": "Who is on leave today?"}))
print("   ai:", ai["ok"], ai["answer"][:80])

print("6. payroll: HR drafts, HR cannot finalize, Admin finalizes")
run = ok(call("POST", "/payroll/runs/", H, json={"year": today.year, "month": today.month}), 201)
assert call("POST", f"/payroll/runs/{run['id']}/finalize/", H).status_code == 403
ok(call("POST", f"/payroll/runs/{run['id']}/finalize/", A))
assert call("POST", f"/payroll/runs/{run['id']}/regenerate/", H).status_code == 409

print("7. employee payslip PDF; colleague salary blocked; admin audit log")
slips = ok(call("GET", "/payroll/payslips/", E))
assert slips["count"] == 1
pdf = call("GET", f"/payroll/payslips/{slips['results'][0]['id']}/pdf/", E)
assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
other = ok(call("GET", "/payroll/payslips/", H))["results"]
bilal = [p for p in other if p["employee_code"] == "E002"][0]
assert call("GET", f"/payroll/payslips/{bilal['id']}/", E).status_code == 404
assert call("GET", f"/employees/{emps[1]['employee']['id']}/", E).status_code == 404
audit = ok(call("GET", "/audit-logs/", A))
print("   audit entries:", audit["count"])
assert call("GET", "/audit-logs/", H).status_code == 403
spa = requests.get(f"{ROOT}/dashboard", timeout=10)
assert spa.status_code == 200 and "<div id=\"root\">" in spa.text, spa.text[:200]
print("ALL DEMO STEPS PASSED")
