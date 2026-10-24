# AR&MS HCM Lite

AI-assisted Human Capital Management for **AR&MS Management Company**, built for the Saylani Hackathon (HCM Lite brief).
Three roles (Admin, HR, Employee), 9 modules and 25 functionalities. Every number comes from records created in the app; there is no seeded or dummy data.

**Live app:** https://arms-hcm-lite.onrender.com (opens on the first-run setup screen; on Render's free plan the first visit can take up to a minute to wake up)

**Repository:** https://github.com/Muhammad-Hamza-bin-hashim/arms-hcm-lite

| | |
|---|---|
| **Backend** | Python 3.12+ · Django 6 · Django REST Framework · SimpleJWT · bcrypt · ReportLab (payslip PDF) |
| **Frontend** | React 19 · TypeScript · Vite · Tailwind CSS 4 · TanStack Query · Recharts · MediaPipe (camera check-in) |
| **Database** | SQLite locally, PostgreSQL in production (`DATABASE_URL`) |
| **AI** | Claude via the Anthropic SDK, or any OpenAI-compatible API with tool calling (Groq / Gemini free tiers work) |
| **Deploy** | One Docker service: Django serves the API at `/api/` and the built SPA at every other path |

---

## Run it locally (about 5 minutes)

Prerequisites: Python 3.12+, Node 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy ..\.env.example .env         # macOS/Linux: cp ../.env.example .env  -> then set SECRET_KEY
python manage.py migrate
python manage.py runserver        # http://127.0.0.1:8000

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173  (proxies /api to :8000)
```

Single-port alternative: run `npm run build` in `frontend/`, then open http://127.0.0.1:8000. Django serves the built app.

### Create the first Admin

- **In the browser (default):** a fresh install opens the **first-run setup** screen. Enter the company name and the Admin account. The screen is shown only once.
- **From env:** set `ADMIN_EMAIL`, `ADMIN_PASSWORD` (and optionally `COMPANY_NAME`), then run `python manage.py bootstrap_admin`. The Docker image runs this on start, and it does nothing if setup already happened.

After that, Admin creates **HR logins** (Users & logins). HR **registers employees**, which creates each employee's login with a **temporary password** they must change at first sign-in.

### Set the AI key

The key lives only in the backend environment. The browser never calls the AI provider.

```ini
# Claude
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-...
AI_MODEL=claude-opus-5-5
AI_EFFORT=low            # keeps answers inside the 15 s budget

# or any OpenAI-compatible provider with tool calling, e.g. Groq (free tier)
AI_PROVIDER=openai
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=openai/gpt-oss-120b
AI_API_KEY=gsk_...
```

Without a key the app still works. The assistant shows a friendly "not configured" message, and smart leave falls back to the normal form.

### Tests

```bash
cd backend && python manage.py test tests      # 73 tests: RBAC, attendance, leave, payroll, analytics, insights, AI
cd frontend && npm test                         # 19 tests: API client, UI states, role-based navigation
cd frontend && npx tsc -b && npm run build      # type check + production build
python backend/scripts/smoke_test.py            # the 5-minute demo over HTTP (needs a FRESH running server)
```

Step-by-step manual trial instructions: **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)**.

### Sample data for local trials only

`python manage.py seed_demo` fills an **empty** local database with 6 employees, ~10 weeks of attendance, leave and a finalized payroll (all passwords `Trial#2026`). It refuses to run on a database that is already set up and is never run automatically. Do not use it on the hosted instance, because judges must start from an empty install.

---

## Deploy (free hosting)

**Render (one click):** push the repo to GitHub, then in Render choose *New → Blueprint* and select the repo. `render.yaml` creates the Docker web service and a free Postgres database. Set `AI_API_KEY` in the service's *Environment* tab. The first visit opens the setup screen.

**Any Docker host** (Railway, Fly.io, Koyeb, …): build the root `Dockerfile` and set `DATABASE_URL`, `SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS=<your host>` and the `AI_*` variables. The container runs migrations on start.

Only `.env.example` is committed. Real keys and database passwords belong in the host's environment settings.

---

## 5-minute demo script

1. **Fresh install → setup:** company *AR&MS Management Company* plus the Admin account.
2. **Admin → Organization:** check office hours (09:00, 15 min grace) and set the office location ("Use my location", radius 150 m). Add a department (Consulting / CON) and a designation. The default leave types (annual 14, sick 8, casual 10, unpaid) are already there.
3. **Admin → Users & logins → New HR login:** copy the temporary password.
4. **HR** signs in, sets a new password, then **Employees → Register employee** (two or three people). Copy each temporary password.
5. **Employee** signs in, changes the password, and clicks **Check in** on the dashboard (or **Camera** on a phone). A second check-in returns 409.
6. **Employee → My leave → Smart leave:** "Need next Monday and Tuesday off for my sister's wedding". The form is pre-filled as casual leave with the correct dates; review it and submit.
7. **HR → Leave requests:** approve with a comment. The employee gets a notification.
8. **HR → Dashboard → Summarize**, then ask the assistant *"Who is on leave today?"* and *"What is this month's attendance rate?"* The answers match the dashboard numbers.
9. **HR → Payroll runs → Run payroll** for the month. **Admin → Finalize** (the month is now locked).
10. **Employee → Payslips → PDF.** Ask the assistant *"What is Bilal's salary?"* and it politely refuses. **Admin → Audit log** shows every step with before/after JSON.

---

## Business rules and assumptions

All rules live in backend services (`apps/*/services.py`). The dashboards and AI tools call those same functions, so the numbers always agree.

**Settings** (`CompanySettings`, editable by Admin): office start 09:00, grace 15 min, half day under 5 h, weekend Sat–Sun, office lat/lng and a 150 m radius, timezone Asia/Karachi. Each attendance record **snapshots** the late-after time and half-day threshold when it is created, so settings changes apply to new records only.

**Attendance**
- The server stamps the time. There is one record per employee per day; a second check-in returns **409**.
- **Late** = check-in after office start + grace (minute precision: 09:15 is on time, 09:16 is late). **Half day** = worked time under 5 h once checked out.
- **missing_checkout:** a past day with no check-out (applied automatically before any report runs).
- **Absent** is derived, not stored: a past working day with no record and no approved leave, while the person was employed. Today is "not checked in", not absent.
- Weekends and holidays don't count in rates, but a check-in on those days still shows as present that day.
- Employees fix mistakes through **correction requests**; HR approves or rejects them and approval writes a `source=correction` record.

**Leave**
- Counts working days only (weekends and holidays skipped). The day count is fixed when the request is created.
- Quotas: annual 14, sick 8, casual 10; unpaid is unlimited. Balance = quota − approved days in that calendar year (requests spanning two years are split by year).
- Rejected with **422**: overlap with a pending or approved request; over balance (pending requests count, to prevent over-booking); no working days in range; before the join date; any day in a month whose payroll is finalized.
- States: pending → approved / rejected (a rejection needs a comment) / cancelled. Approved leave can be cancelled only before it starts. HR cannot decide their own leave. The balance is computed from approved rows, so nothing is ever deducted twice.

**Payroll** (`apps/payroll/calc.py`, Decimal arithmetic only, rounded half-up to 0.01)
- Gross = 1.5 × basic = basic + HRA 40% + medical 10%. The salary structure effective at month end is used.
- W = working days in the month; payable days = working days employed (proration for joiners and leavers).
- Per day = gross ÷ W. Prorated gross = gross × payable ÷ W.
- Deduction = (absent + unpaid leave + 0.5 × half days [+ 0.5 per 3 lates if the bonus late-penalty rule is on]) × per day, capped at prorated gross.
- Tax: the illustrative brief slabs applied to **gross × 12**; monthly tax = annual ÷ 12, prorated by payable ÷ W and capped at earned gross. Net = earned gross − tax.
- HR generates or regenerates the **draft**; only Admin can **finalize**, which is atomic and uses a row lock (a second attempt returns 409). Finalized runs and payslips refuse every write at the model level. Each payslip stores a full snapshot (names, salary, days, rates), so later salary or attendance changes never alter it.
- Running the current month counts absences up to today; regenerate the draft before finalizing.
- The tax slabs are the challenge's illustrative values, not current Pakistani tax law.

## Metric definitions (Section 7)

| Metric | Implementation |
|---|---|
| Headcount | employed on the end date (join ≤ d and no exit before d) |
| Attrition % | exits in period ÷ average(headcount at start, at end) × 100; YTD = 1 Jan → end date |
| Attendance rate | (present + late + missing_checkout + 0.5 × half_day) ÷ (working-day records − on_leave) |
| Late % / absenteeism | late ÷ (present + late) / absent ÷ expected working days, per department |
| Leave utilization | approved days in the year ÷ (quota × headcount), per type |
| Payroll cost / avg salary | Σ earned gross and net of **finalized** payslips by month and department / mean current gross by department and designation |

Every dashboard accepts `from`, `to` and `department`. Empty data returns `null` rates (shown as "—"), never a division error.

---

## AI assistant (M8)

- `POST /api/ai/chat`: the model chooses from the 7 tools (`get_headcount`, `get_attendance_summary`, `get_late_comers`, `get_leave_summary`, `get_my_leave_balance`, `get_payroll_summary`, `search_employees`). Each tool calls the same analytics, leave and payroll services as the REST API, **with the caller's role and scope**:
  - Employees are offered only self-scoped tools.
  - Every tool re-checks the role on execution.
  - Unknown arguments are rejected.
- **Dashboard summary:** the server recomputes the KPI JSON for the current filters (it never trusts numbers from the browser) and asks for 3–5 bullets. The JSON reply is validated; on failure it retries once, then shows a friendly fallback.
- **Smart leave:** a sentence becomes a validated `{leave_type, start_date, end_date, reason}`. The prompt includes a 3-week dated calendar so "next Monday" resolves correctly. The backend runs the real leave checks as a dry run. **Nothing is saved** until the employee presses Submit.
- **Policy Q&A:** the Section 3 rules are rendered from live settings into the system prompt. The model is told to answer only from them and to say it doesn't know otherwise. Roman Urdu is supported.
- **Guardrails:**
  - The key is server-only, and the model never touches the database.
  - 15 s overall deadline.
  - 20 requests per user per hour (429 after that).
  - Every call is logged in `ai_logs` (Admin → AI logs) with tools, outcome and latency.
  - Answers carry an "AI-generated" label.

## Security

- JWT auth with versioned tokens: logout, password change or reset, and deactivation revoke every issued token.
- Passwords are hashed with bcrypt (Django `BCryptSHA256PasswordHasher`).
- Login and setup are throttled. Temporary passwords force a change on first sign-in, and every other endpoint is blocked until then.
- Role and **object-level** checks on every endpoint (not just hidden buttons). Employee querysets are filtered by their own `employee_id`, so changing IDs in URLs, query strings or bodies returns 404/403. Tests cover this with direct API calls.
- HR cannot change settings, create Admin users, view the audit log, finalize payroll, or set their own salary.
- The audit log is append-only: the model refuses update and delete, and there are no write endpoints. Sensitive keys (passwords, tokens) are masked in before/after JSON.
- CSV export neutralises spreadsheet formulas. CSV import is limited to 2 MB / 1000 rows and is all-or-nothing.
- Camera attendance sends only the face count and GPS. The server computes the Haversine distance and stores the result, never a photo.

---

## The 25 functionalities

| # | Functionality | Status | Where |
|---|---|---|---|
| 01 | First-run setup | ✅ | `/api/setup/`, setup screen, `bootstrap_admin` |
| 02 | Login, logout, change password, role menus/dashboards | ✅ | `apps/accounts`, Layout |
| 03 | Company settings incl. location & radius | ✅ | Organization → Company & rules |
| 04 | Departments, designations, leave types, holidays | ✅ | Organization tabs |
| 05 | Create HR logins; deactivate / reset any login | ✅ | Users & logins |
| 06 | Register employee (creates login) / edit; own phone & address | ✅ | Employees, Profile |
| 07 | Directory with server-side search, filters, paging; Employee 360 | ✅ | Employees, `/employees/:id` |
| 08 | CSV import with dry-run report (row/field/reason); CSV export | ✅ | Employees → Import / Export |
| 09 | Web check-in / check-out | ✅ | Dashboard widget, My attendance |
| 10 | Attendance calendar and daily board | ✅ | My attendance, Attendance board |
| 11 | Attendance correction request / approve | ✅ | My attendance, Corrections |
| 12 | Apply / cancel leave, balance, history | ✅ | My leave |
| 13 | Approve / reject leave with comment | ✅ | Leave requests |
| 14 | Salary structure per employee | ✅ | Salary structures |
| 15 | Monthly payroll draft | ✅ | Payroll runs |
| 16 | Finalize payroll (locks month) | ✅ | Payroll run → Finalize (Admin) |
| 17 | Payslips with PDF | ✅ | Payslips |
| 18 | Dashboards, KPIs, trends, insights with filters | ✅ | Dashboard (per role) |
| 19 | AI chat on real data, role-scoped | ✅ | Assistant button (all pages) |
| 20 | AI dashboard summary | ✅ | Dashboard → Summarize |
| 21 | Smart leave | ✅ | My leave → Smart leave |
| 22 | Policy Q&A | ✅ | Assistant |
| 23 | Announcements | ✅ | Announcements, dashboards |
| 24 | In-app notifications | ✅ | Bell icon |
| 25 | Audit log | ✅ | Audit log (Admin) |

**Bonus implemented:**
- Camera check-in with face detection (MediaPipe, exactly one face) plus server-side geofence and GPS-accuracy checks.
- **Attrition-risk score** (0–100, last 60 days) from absences, lateness, unpaid and rejected leave, tenure and probation. Every score lists its reasons (`apps/analytics/insights.py`).
- **Absence anomaly flags:** 3+ consecutive absences, Monday/Friday clustering, repeated missing check-outs, and departments at 2× the company absenteeism rate.
- Late-penalty rule (3 lates = 0.5 day; toggle in settings).
- Roman Urdu in the AI.
- Dark mode and an installable PWA manifest.

### Not done / known limits

- No native mobile app. Camera check-in works in mobile and desktop browsers instead.
- No face *matching* against an enrolled face and no liveness check. Detection only, by design, so no biometric data is stored.
- No password-reset email. Admin resets passwords and shares the temporary one.
- Front-end tests cover the API client, UI states and role-based navigation. Full click-through flows are covered by `scripts/smoke_test.py` (API) and the manual guide, not by a browser test runner.

## Project layout

```
backend/
  config/            settings, urls (API + SPA), error envelope, pagination
  apps/accounts      users, roles, JWT, first-run setup, user admin           (M1)
  apps/org           company settings, departments, designations, leave types, holidays, calendar (M2)
  apps/employees     employees, registration, CSV import/export, Employee 360 (M3)
  apps/attendance    check-in/out, camera + geofence, corrections, day-status matrix (M4)
  apps/leaves        leave rules, balances, approvals                         (M5)
  apps/payroll       salary structures, payroll runs, calc, PDF payslips      (M6)
  apps/analytics     KPI services + dashboards                                (M7)
  apps/ai            providers, tools, chat / summary / smart leave, ai_logs  (M8)
  apps/comms         announcements, notifications, audit log                  (M9)
  scripts/           smoke_test.py (demo over HTTP)
  tests/             73 API & service tests
frontend/src/
  lib/               API client, auth, types, formatting
  components/        design system (ui), layout, charts, AI chat, check-in, camera
  pages/             one folder per area
```
