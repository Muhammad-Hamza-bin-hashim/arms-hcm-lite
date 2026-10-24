# AR&MS HCM Lite: test and trial guide

Work through this guide in order. Part 1 runs the automated checks. Part 2 is the exact path the judges will take. Parts 3–6 cover the remaining features (sample data, AI, camera, security), Part 7 shows how to reset between trials, and Part 8 is the pre-submission checklist. Every step says what you should see; if you see something else, check **Troubleshooting** at the end.

Commands are for Windows PowerShell. On macOS/Linux use `source .venv/bin/activate` and `cp` instead of `copy`.

---

## 0. One-time setup (≈5 min)

```powershell
cd Desktop\arms-hcm\backend
python -m venv .venv                 # skip if .venv already exists
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env            # skip if backend\.env already exists
```

Open `backend\.env` and set `SECRET_KEY` to any long random string. Leave `DATABASE_URL` empty for local SQLite.

```powershell
cd ..\frontend
npm install
npm run build                        # Django serves this build on port 8000
```

---

## 1. Automated checks (≈2 min)

| Command (from the folder shown) | Expected result |
|---|---|
| `backend> python manage.py test tests` | `Ran 73 tests … OK` |
| `frontend> npm test` | `Test Files 4 passed`, `Tests 19 passed` |
| `frontend> npx tsc -b` | no output (no type errors) |
| `frontend> npm run build` | `✓ built in …` |

**API smoke test.** This replays the whole judges' demo over HTTP in about 5 seconds. It needs a running server with an empty database:

```powershell
cd backend
Remove-Item db.sqlite3 -ErrorAction SilentlyContinue
python manage.py migrate
python manage.py runserver           # leave running; open a second terminal for the next line
python scripts\smoke_test.py         # expected last line: ALL DEMO STEPS PASSED
```

The smoke test creates records. Reset afterwards (Part 7) before the manual trial.

---

## 2. Trial A: the judges' path on a fresh install (≈15 min)

Reset first (Part 7), start `python manage.py runserver`, and open **http://127.0.0.1:8000**.
Use a normal browser window for Admin, a private/incognito window for HR, and a second browser (or another profile) for the employee, so all three can stay signed in at once.

> **Judging day is a Saturday.** By default Saturday and Sunday are weekends. Check-ins still work and show as present today, but "Today is not a working day" appears and weekend days don't count in attendance rates. To demo a normal working day, Admin can untick **Sat** under Organization → Weekend days *before* anyone checks in. Settings apply to new records only.

### Admin

| # | Do this | You should see |
|---|---|---|
| A1 | Open the site | **Set up your company** screen (first run only) |
| A2 | First try a weak password like `12345678` | Inline error under the password field; nothing is created |
| A3 | Company `AR&MS Management Company`; your name; email `admin@arms.test`; password `Admin#2026x` twice → **Create company and Admin** | Organization page with a green "Company created" banner |
| A4 | **Company & rules**: office start 09:00, grace 15, half day 5. Click **Use my location** (allow it), radius 150 → **Save settings** | Toast "Settings saved. They apply to new records." |
| A5 | **Departments → Add department**: `Consulting` / `CON`. **Designations → Add**: `Consultant` | Rows appear in each table |
| A6 | **Leave types** tab | Annual 14, Casual 10, Sick 8, Unpaid (unlimited) are already there |
| A7 | **Users & logins → New HR login**: `hr@arms.test`, first name `Hamza` | A dialog shows a **temporary password** (`Tmp-…`). Copy it |

### HR

| # | Do this | You should see |
|---|---|---|
| H1 | Sign in as `hr@arms.test` with the temporary password | **Choose a new password**. No other page is reachable yet |
| H2 | Set `HrPass#2026` | HR dashboard (all zeros, with empty-state messages) |
| H3 | **Employees → Register employee**: code `E001`, `sana@arms.test`, Sana Khan, Consulting, join date the 1st of this month, basic `100000` | Hint shows "Gross = 1.5 × basic = PKR 150,000". After saving, a temporary password dialog appears. Copy it |
| H4 | Register two more (`E002` Bilal, basic `300000`; `E003` Zara, basic `80000`) | Directory lists 3 employees |
| H5 | Register `E001` again with a different email | Error "Employee code already exists." under the code field |
| H6 | Search `zara`, filter by department, open a row | Server-side search/filter works; the row opens **Employee 360** |

### Employee

| # | Do this | You should see |
|---|---|---|
| E1 | Sign in as `sana@arms.test` with the temporary password, set `Sana#2026pw` | Employee dashboard: "Hello, Sana", a check-in card, leave balances |
| E2 | **Check in** | Toast; the card shows the server time, and the status is *Present*, or *Late* after 09:15 |
| E3 | Look for the Check in button again | It is replaced by **Check out**. A second check-in through the API returns **409** (try it in Part 6) |
| E4 | **My leave → Smart leave**: type *Need next Monday and Tuesday off for my sister's wedding* → **Fill the form for me** | With an AI key: the form fills with Casual, next Monday → Tuesday, reason, and "Pre-filled 2 working day(s)". Without a key: a friendly message and the empty form (correct fallback) |
| E5 | Fill or keep the form → **Submit request** | Toast "Leave request sent to HR"; the request shows *Pending* (with an *AI* tag if pre-filled) |
| E6 | Apply again for overlapping dates | Amber message "Overlaps your pending casual leave…" (422) |
| E7 | Apply 9 days of sick leave | "Not enough sick leave: 9 day(s) requested, 8 available…" |

### HR approves, payroll runs

| # | Do this | You should see |
|---|---|---|
| H7 | HR → **Leave requests** (Pending tab) → ✓ Approve, comment "Congrats" | Toast; Sana gets a bell notification |
| H8 | HR → **Dashboard** | Headcount 3, Present today 1, pending approvals updated |
| H9 | **Summarize** in the AI summary card | 3–5 bullets with an *AI-generated* badge (or a friendly note without a key) |
| H10 | Click **Ask the assistant** → *Who is on leave today?* | Answer from records (needs a key, see Part 4) |
| H11 | **Payroll runs → Run payroll** → this month → **Generate draft** | Draft page: employees, gross, deductions, tax, net; banner "Draft… Admin must finalize" |
| H12 | Look for a Finalize button as HR | There isn't one (and the API refuses with 403) |

### Admin finalizes, employee downloads

| # | Do this | You should see |
|---|---|---|
| A8 | Admin → **Payroll runs** → open the month → **Finalize** → confirm | Banner "Finalized … locked"; the Recalculate button is gone for HR |
| E8 | Employee → **Payslips** → **PDF** | A PDF with the AR&MS header, earnings, deductions, tax and net pay |
| E9 | Ask the assistant *What is Bilal's salary?* | Polite refusal; only own data is available |
| E10 | Type `/employees/2` or `/audit` in the address bar | "Not found" / "Not available for your role" |
| A9 | Admin → **Audit log** → click any row | Actor, action, time, and before/after JSON for each step you did |

**Check the numbers by hand.** Sana, basic 100,000 → gross 150,000 → annual 1,800,000 → tax 30,000 + 15% × 600,000 = 120,000 a year = **10,000 a month** (when she worked every working day). Each absent day deducts 150,000 ÷ working days in the month.

---

## 3. Trial B: explore with sample data (local only, ≈10 min)

This fills dashboards, charts, insights and history without manual typing.

```powershell
cd backend
Remove-Item db.sqlite3 -ErrorAction SilentlyContinue
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Every password is `Trial#2026`: `admin@arms.test`, `hr@arms.test`, and employees `sana@`, `bilal@`, `zara@`, `omar@`, `hira@`, `usman@arms.test`.

Things worth checking:
- **HR dashboard:** attendance trend, absenteeism by department, leave by type, top late-comers (Bilal first), and at the bottom **Attrition risk** (Hira high: 5-day absence streak, unpaid leave, probation) and **Absence anomaly flags** (Zara: absences on Mondays/Fridays).
- **Change the filters** (Last 7 days, a department): every card and chart updates, and the numbers match **Attendance board** for the same days.
- **Payroll runs:** last month is already finalized. Open it, click a payslip to see the breakdown, and confirm there is no Recalculate button.
- **Leave requests:** 2 pending (Zara, Usman) to approve or reject. Rejecting needs a comment.
- **Employee view (e.g. hira@):** calendar with absent, late and leave days. Click an absent day → **Request correction** → HR approves it under **Corrections** → the day turns present on the calendar.
- **Dark mode:** the moon icon in the top bar.
- **Phone layout:** open the browser dev tools (F12) → device toolbar → 375 px wide.

Never run `seed_demo` on the hosted site; judges must start empty.

---

## 4. AI assistant trial (needs a key)

1. Put a key in `backend\.env`, then restart `runserver`:
   ```ini
   AI_PROVIDER=anthropic
   AI_API_KEY=sk-ant-...
   AI_MODEL=claude-opus-5-5
   AI_EFFORT=low
   ```
   No paid key? Use a free OpenAI-compatible provider instead (e.g. Groq: `AI_PROVIDER=openai`, `AI_BASE_URL=https://api.groq.com/openai/v1`, `AI_MODEL=openai/gpt-oss-120b`, `AI_API_KEY=gsk_...`).
2. Admin → **AI logs** should say the provider is configured.
3. Ask the brief's live questions and compare each answer with the screen it should match:

| Signed in as | Ask | Good answer matches |
|---|---|---|
| HR | How many active employees are in Consulting? | Dashboard filtered to Consulting → Headcount |
| HR | Who came late most often this month? | *Top 5 late-comers* card |
| HR | What is this month's attendance rate? | *Attendance rate* tile (This month) |
| HR | Who is on leave today? | *On leave today* card |
| Employee | How many sick leaves do I have left this year? | Sick tile on **My leave** |
| Employee | What is {colleague}'s salary? | A polite refusal |
| Employee | Smart leave: "Need next Monday and Tuesday off for my sister's wedding" | Casual, the correct next Monday → Tuesday |
| Any | When am I counted late? / Kitni sick leaves milti hain? (Roman Urdu) | Policy answer from the rules: after 09:15 / 8 per year, in Roman Urdu |

4. **Graceful failure:** set a wrong key → ask anything → a friendly message, not a crash; AI logs shows outcome *error*. Rate limit: the 21st request in an hour returns "AI limit reached". To see that quickly, set `AI_RATE_LIMIT_PER_HOUR=3` temporarily.
5. Every answer shows an **AI-generated** badge and the names of the tools it used.

---

## 5. Camera check-in trial (bonus)

Browsers only allow the camera and GPS on **https** or **localhost**.
- **Laptop:** Admin sets the office location with **Use my location**. As an employee, the check-in card shows a **Camera** button. Look at the camera: "Face detected" turns green; then **Check in**.
- **Phone:** use the hosted https URL (Part 8). On localhost from a phone it will not work.
- **Negative checks:** cover the camera (no face), two people in frame (rejected), or set the office location far away (rejected with "You are N m from the office…"). Location accuracy worse than 100 m is also rejected.
- No photo is stored: only the face count and coordinates are sent, and the server computes the distance.

---

## 6. Security spot checks (direct API, ≈5 min)

Judges may test the API directly, not just the buttons. Sign in as an employee, open dev tools → **Application → Local Storage → `hcm.access`**, and copy the token. Then in PowerShell:

```powershell
$T = "<paste employee token>"
$H = @{ Authorization = "Bearer $T" }
Invoke-RestMethod http://127.0.0.1:8000/api/employees/ -Headers $H          # only the employee's own row
Invoke-RestMethod http://127.0.0.1:8000/api/employees/2/ -Headers $H        # 404 (another employee's id)
Invoke-RestMethod http://127.0.0.1:8000/api/audit-logs/ -Headers $H         # 403
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/hr/ -Headers $H       # 403
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/attendance/check-in/ -Headers $H   # 409 if already checked in
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/payroll/runs/1/finalize/ -Headers $H  # 403
```

Also:
- **Sign out** in one window and refresh the other: the session ends, because logout revokes all tokens.
- Admin **deactivates** a user → that user is signed out on the next request and cannot sign in.
- View the page source or the network tab: the AI key never appears in the browser.

---

## 7. Reset between trials

```powershell
cd backend
# stop runserver first (Ctrl+C)
Remove-Item db.sqlite3
python manage.py migrate
python manage.py runserver
```

Then sign out of every browser window or clear Local Storage. The next visit shows the setup screen again.

---

## 8. Deploy and final pre-submission check

1. Create a GitHub repo and push. (`.env` and `db.sqlite3` are git-ignored; only `.env.example` is committed.)
2. Render → **New → Blueprint** → pick the repo. It reads `render.yaml` and creates the web service plus a Postgres database.
3. In the service's **Environment** tab set `AI_API_KEY`. Optionally change `AI_PROVIDER` / `AI_MODEL`.
4. Wait for the deploy, then open `https://<name>.onrender.com/api/health/` → `{"status": "ok"}`.
5. **Optional dress rehearsal:** run `python backend\scripts\smoke_test.py https://<name>.onrender.com` → ALL DEMO STEPS PASSED. This fills the hosted database, so afterwards **reset it**: in Render, delete and recreate the database (or create a new one and point `DATABASE_URL` at it), then redeploy. Judges must see the setup screen.
6. Open the hosted URL in a private window: you should see **Set up your company**. That is the state to submit.
7. Submit both links on the LMS: the GitHub repo and the hosted URL.

The free Render tier sleeps after inactivity, and the first request can take ~1 minute. Open the site a few minutes before your demo slot.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `SECRET_KEY environment variable is required` | Set `SECRET_KEY` in `backend\.env` (or `DEBUG=true` locally) |
| Port 8000 shows "Frontend not built" | Run `npm run build` in `frontend`, or use `npm run dev` and open :5173 |
| Login page loops back / "session ended" | Clear Local Storage for the site; you probably reset the database while still signed in |
| Setup screen won't appear | The database already has an Admin. Reset it (Part 7) |
| Assistant says "not configured" | `AI_API_KEY` is missing or the server wasn't restarted after editing `.env` |
| Assistant times out | Use `AI_EFFORT=low` or a faster model; the limit is 15 s by design |
| Camera button missing | Admin hasn't set the office latitude/longitude |
| Camera/GPS blocked | Use https (hosted) or localhost; allow permissions in the browser |
| Check-in shows "Late" at night | Expected: any check-in after 09:15 local time is late |
| Leave request rejected with "no working days" | The dates fall only on weekends/holidays |
| "Payroll for that month is finalized" | Leave and corrections are locked for finalized months, by design |
| `seed_demo` refuses to run | It only runs on an empty database. Reset first |
