"""Employee registration, updates and CSV import/export (single source for these rules)."""
import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.accounts.models import Role, User
from apps.accounts.services import generate_temp_password
from apps.comms.services import record_audit
from apps.org.models import Department, Designation
from config.exceptions import BusinessRuleError

from .models import Employee

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CSV_COLUMNS = ["employee_code", "first_name", "last_name", "email", "phone", "department", "designation",
               "join_date", "basic_salary", "gender", "employment_status", "address"]
CSV_REQUIRED = ["employee_code", "first_name", "email", "department", "join_date", "basic_salary"]


def employee_snapshot(emp: Employee) -> dict:
    return {
        "employee_code": emp.employee_code, "name": emp.full_name, "email": emp.email, "phone": emp.phone,
        "address": emp.address, "department": emp.department.name if emp.department_id else None,
        "designation": emp.designation.name if emp.designation_id else None, "join_date": emp.join_date,
        "exit_date": emp.exit_date, "employment_status": emp.employment_status, "gender": emp.gender,
    }


def _login_for(email, first_name, last_name):
    """Creates the employee's login, or links an existing HR login that has no employee profile yet."""
    existing = User.objects.filter(email__iexact=email).first()
    if existing:
        if existing.role == Role.HR and not hasattr(existing, "employee"):
            return existing, None
        raise BusinessRuleError("A login with this email already exists.", code="duplicate_email",
                                errors={"email": ["A login with this email already exists."]})
    temp = generate_temp_password()
    user = User.objects.create_user(email=email, password=temp, first_name=first_name, last_name=last_name,
                                    role=Role.EMPLOYEE, must_change_password=True)
    return user, temp


@transaction.atomic
def register_employee(data: dict, *, actor, request=None, audit=True):
    """HR registers an employee: creates the login (temporary password) and the first salary structure."""
    from apps.payroll.services import set_salary

    data = dict(data)
    basic = data.pop("basic_salary")
    email = data["email"].lower()
    if Employee.objects.filter(email__iexact=email).exists():
        raise BusinessRuleError("Email already used by another employee.", code="duplicate_email",
                                errors={"email": ["Email already used by another employee."]})
    if Employee.objects.filter(employee_code__iexact=data["employee_code"]).exists():
        raise BusinessRuleError("Employee code already exists.", code="duplicate_code",
                                errors={"employee_code": ["Employee code already exists."]})
    user, temp = _login_for(email, data["first_name"], data.get("last_name", ""))
    data["email"] = email
    employee = Employee.objects.create(user=user, created_by=actor, **data)
    set_salary(employee, basic, employee.join_date, actor=actor, request=request, audit=False)
    if audit:
        record_audit(actor, "employee.registered", "employee", employee.pk,
                     summary=f"Registered {employee.employee_code} {employee.full_name}",
                     after={**employee_snapshot(employee), "basic_salary": str(basic)}, request=request)
    return employee, temp


@transaction.atomic
def update_employee(employee: Employee, data: dict, *, actor, request=None):
    before = employee_snapshot(employee)
    if "email" in data:
        data["email"] = data["email"].lower()
        if Employee.objects.filter(email__iexact=data["email"]).exclude(pk=employee.pk).exists() or \
                User.objects.filter(email__iexact=data["email"]).exclude(pk=employee.user_id).exists():
            raise BusinessRuleError("Email already in use.", code="duplicate_email",
                                    errors={"email": ["Email already in use."]})
    if "employee_code" in data and Employee.objects.filter(
            employee_code__iexact=data["employee_code"]).exclude(pk=employee.pk).exists():
        raise BusinessRuleError("Employee code already exists.", code="duplicate_code",
                                errors={"employee_code": ["Employee code already exists."]})
    for field, value in data.items():
        setattr(employee, field, value)
    if employee.employment_status == Employee.Status.EXITED and not employee.exit_date:
        raise BusinessRuleError("Exit date is required when status is exited.", code="exit_date_required",
                                errors={"exit_date": ["Required when status is exited."]})
    if employee.exit_date and employee.exit_date < employee.join_date:
        raise BusinessRuleError("Exit date cannot be before the join date.", errors={"exit_date": ["Before join date."]})
    employee.save()

    user = employee.user
    user.email, user.first_name, user.last_name = employee.email, employee.first_name, employee.last_name
    fields = ["email", "first_name", "last_name"]
    if employee.employment_status == Employee.Status.EXITED and user.is_active and user.role == Role.EMPLOYEE:
        user.is_active = False
        user.token_version += 1
        fields += ["is_active", "token_version"]
    user.save(update_fields=fields)
    record_audit(actor, "employee.updated", "employee", employee.pk, summary=f"Updated {employee}",
                 before=before, after=employee_snapshot(employee), request=request)
    return employee


def update_own_contact(employee: Employee, *, phone=None, address=None, request=None):
    before = {"phone": employee.phone, "address": employee.address}
    if phone is not None:
        employee.phone = phone
    if address is not None:
        employee.address = address
    employee.save(update_fields=["phone", "address", "updated_at"])
    record_audit(employee.user, "employee.contact_updated", "employee", employee.pk,
                 summary="Updated own phone/address", before=before,
                 after={"phone": employee.phone, "address": employee.address}, request=request)
    return employee


# ---------- CSV ----------

def _parse_csv(raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BusinessRuleError("CSV must be UTF-8 encoded.", code="bad_csv")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BusinessRuleError("CSV file is empty.", code="bad_csv")
    headers = [h.strip().lower() for h in reader.fieldnames]
    missing = [c for c in CSV_REQUIRED if c not in headers]
    if missing:
        raise BusinessRuleError(f"Missing columns: {', '.join(missing)}", code="bad_csv",
                                errors={"columns": missing})
    rows = []
    for row in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
    if len(rows) > 1000:
        raise BusinessRuleError("CSV is limited to 1000 rows per import.", code="bad_csv")
    return rows


def validate_csv(raw: bytes):
    """Returns (clean_rows, errors). Each error = {row, field, reason}; row 2 is the first data line."""
    rows = _parse_csv(raw)
    departments = {}
    for d in Department.objects.all():
        departments[d.name.lower()] = d
        departments[d.code.lower()] = d
    designations = {d.name.lower(): d for d in Designation.objects.all()}
    existing_codes = {c.lower() for c in Employee.objects.values_list("employee_code", flat=True)}
    existing_emails = {e.lower() for e in User.objects.values_list("email", flat=True)}
    seen_codes, seen_emails = set(), set()
    clean, errors = [], []

    for idx, row in enumerate(rows, start=2):
        row_errors = []

        def err(field, reason):
            row_errors.append({"row": idx, "field": field, "reason": reason})

        for field in CSV_REQUIRED:
            if not row.get(field):
                err(field, "Required field is empty.")
        code = row.get("employee_code", "")
        email = row.get("email", "").lower()
        if code:
            if code.lower() in existing_codes:
                err("employee_code", "Employee code already exists.")
            elif code.lower() in seen_codes:
                err("employee_code", "Duplicate employee code in file.")
            seen_codes.add(code.lower())
        if email:
            if not EMAIL_RE.match(email):
                err("email", "Invalid email address.")
            elif email in existing_emails:
                err("email", "Email already exists.")
            elif email in seen_emails:
                err("email", "Duplicate email in file.")
            seen_emails.add(email)
        dept = departments.get(row.get("department", "").lower()) if row.get("department") else None
        if row.get("department") and dept is None:
            err("department", f"Unknown department '{row['department']}'.")
        desig = None
        if row.get("designation"):
            desig = designations.get(row["designation"].lower())
            if desig is None:
                err("designation", f"Unknown designation '{row['designation']}'.")
        join = None
        if row.get("join_date"):
            try:
                join = date.fromisoformat(row["join_date"])
            except ValueError:
                err("join_date", "Use ISO date format YYYY-MM-DD.")
        salary = None
        if row.get("basic_salary"):
            try:
                salary = Decimal(row["basic_salary"].replace(",", ""))
                if salary <= 0:
                    err("basic_salary", "Salary must be greater than 0.")
            except InvalidOperation:
                err("basic_salary", "Salary must be a number.")
        gender = (row.get("gender") or "unspecified").lower()
        if gender not in Employee.Gender.values:
            err("gender", f"Use one of: {', '.join(Employee.Gender.values)}.")
        status = (row.get("employment_status") or "probation").lower()
        if status not in (Employee.Status.PROBATION, Employee.Status.ACTIVE):
            err("employment_status", "Use 'probation' or 'active'.")

        if row_errors:
            errors.extend(row_errors)
        else:
            clean.append({
                "employee_code": code, "first_name": row["first_name"], "last_name": row.get("last_name", ""),
                "email": email, "phone": row.get("phone", ""), "address": row.get("address", ""),
                "department": dept, "designation": desig, "join_date": join, "basic_salary": salary,
                "gender": gender, "employment_status": status,
            })
    return clean, errors, len(rows)


@transaction.atomic
def import_csv(raw: bytes, *, actor, request=None):
    """All-or-nothing import. Returns created logins with their one-time temporary passwords."""
    clean, errors, total = validate_csv(raw)
    if errors:
        raise BusinessRuleError("CSV has errors; nothing was imported.", code="csv_invalid",
                                errors={"rows": errors})
    created = []
    for data in clean:
        emp, temp = register_employee(data, actor=actor, request=request, audit=False)
        created.append({"id": emp.pk, "employee_code": emp.employee_code, "email": emp.email,
                        "temporary_password": temp})
    record_audit(actor, "employee.csv_imported", "employee", "", summary=f"Imported {len(created)} employees via CSV",
                 after={"codes": [c["employee_code"] for c in created]}, request=request)
    return created


def _safe_cell(value):
    """Neutralise spreadsheet formula injection."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_csv(queryset) -> str:
    from apps.payroll.services import current_salary

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for e in queryset.select_related("department", "designation"):
        salary = current_salary(e)
        writer.writerow([_safe_cell(v) for v in [
            e.employee_code, e.first_name, e.last_name, e.email, e.phone, e.department.name,
            e.designation.name if e.designation_id else "", e.join_date.isoformat(),
            salary.basic if salary else "", e.gender, e.employment_status, e.address,
        ]])
    return out.getvalue()
