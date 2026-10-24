"""Salary structures, monthly payroll runs and finalization."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.attendance.services import day_matrix, summarize
from apps.comms.services import notify, record_audit
from apps.employees.models import Employee
from apps.org.models import CompanySettings
from apps.org.services import WorkCalendar, local_today, month_bounds
from config.exceptions import BusinessRuleError, ConflictError

from .calc import compute_pay, salary_components
from .models import PayrollRun, Payslip, SalaryStructure


def current_salary(employee, on_date=None):
    on_date = on_date or local_today()
    return (SalaryStructure.objects.filter(employee=employee, effective_from__lte=on_date)
            .order_by("-effective_from", "-id").first()
            or SalaryStructure.objects.filter(employee=employee).order_by("effective_from").first())


def set_salary(employee, basic, effective_from, *, actor, request=None, audit=True):
    if Decimal(basic) <= 0:
        raise BusinessRuleError("Basic salary must be greater than 0.", errors={"basic": ["Must be > 0."]})
    previous = current_salary(employee, effective_from)
    parts = salary_components(basic)
    structure, _ = SalaryStructure.objects.update_or_create(
        employee=employee, effective_from=effective_from, defaults={**parts, "created_by": actor})
    if audit:
        record_audit(actor, "salary.updated", "salary_structure", structure.pk,
                     summary=f"Set salary for {employee.employee_code} from {effective_from}",
                     before={"basic": previous.basic, "gross": previous.gross} if previous else None,
                     after={**parts, "effective_from": effective_from}, request=request)
    return structure


def _payroll_employees(start, end):
    return (Employee.objects.filter(join_date__lte=end).exclude(exit_date__lt=start)
            .select_related("department", "designation"))


def _payslip_values(employee, run, info_row, cal, settings_obj, start, end):
    salary = current_salary(employee, end)
    if salary is None:
        return None
    stats = summarize([info_row])
    payable = cal.count(max(start, employee.join_date), min(end, employee.exit_date or end))
    late_count = sum(1 for i in info_row.values() if i.working and i.is_late)
    penalty = Decimal(late_count // 3) * Decimal("0.5") if settings_obj.late_penalty_enabled else Decimal(0)
    pay = compute_pay(gross=salary.gross, working_days=run.working_days, payable_days=payable,
                      absent_days=stats["absent"], unpaid_leave_days=stats["unpaid_leave_days"],
                      half_days=stats["half_day"], late_penalty_days=penalty)
    return {
        "employee": employee, "employee_code": employee.employee_code, "employee_name": employee.full_name,
        "department_name": employee.department.name,
        "designation_name": employee.designation.name if employee.designation_id else "",
        "basic": salary.basic, "hra": salary.hra, "medical": salary.medical, "gross": salary.gross,
        "working_days": run.working_days, "payable_days": payable, "absent_days": stats["absent"],
        "unpaid_leave_days": stats["unpaid_leave_days"], "half_days": stats["half_day"],
        "late_count": late_count, "late_penalty_days": penalty, **pay,
    }


def _get_or_create_run(year, month, actor):
    try:
        with transaction.atomic():
            return PayrollRun.objects.get_or_create(year=year, month=month, defaults={"created_by": actor})
    except IntegrityError:  # concurrent creation of the same period
        return PayrollRun.objects.get(year=year, month=month), False


def generate_draft(year: int, month: int, *, actor, request=None):
    """Creates (or regenerates) the draft for a month. Finalized months are locked."""
    if not (1 <= month <= 12) or year < 2000:
        raise BusinessRuleError("Invalid payroll period.", code="invalid_period")
    today = local_today()
    start, end = month_bounds(year, month)
    if start > today:
        raise BusinessRuleError("Payroll cannot be run for a future month.", code="future_period")
    run, created = _get_or_create_run(year, month, actor)
    with transaction.atomic():
        run = PayrollRun.objects.select_for_update().get(pk=run.pk)
        if run.is_locked:
            raise ConflictError(f"Payroll for {run.period_label} is finalized and locked.")
        settings_obj = CompanySettings.get()
        cal = WorkCalendar(settings_obj)
        run.working_days = cal.count(start, end)
        run.payslips.all().delete()
        employees = list(_payroll_employees(start, end))
        matrix = day_matrix(employees, start, end, today=today, cal=cal)
        slips = []
        for emp in employees:
            values = _payslip_values(emp, run, matrix[emp.pk], cal, settings_obj, start, end)
            if values:
                slips.append(Payslip(run=run, **values))
        Payslip.objects.bulk_create(slips)
        run.employee_count = len(slips)
        run.total_gross = sum((s.earned_gross for s in slips), Decimal("0.00"))
        run.total_deductions = sum((s.deduction for s in slips), Decimal("0.00"))
        run.total_tax = sum((s.tax for s in slips), Decimal("0.00"))
        run.total_net = sum((s.net for s in slips), Decimal("0.00"))
        run.generated_at = timezone.now()
        run.save()
    record_audit(actor, "payroll.draft_generated" if created else "payroll.draft_regenerated", "payroll_run", run.pk,
                 summary=f"{'Generated' if created else 'Regenerated'} payroll draft {run.period_label}",
                 after={"employees": run.employee_count, "total_gross": run.total_gross, "total_net": run.total_net},
                 request=request)
    return run


def finalize(run_id, *, actor, request=None):
    """Admin only (enforced in the view). Atomic and safe against concurrent attempts."""
    with transaction.atomic():
        run = PayrollRun.objects.select_for_update().get(pk=run_id)
        if run.is_locked:
            raise ConflictError(f"Payroll for {run.period_label} is already finalized.")
        if run.employee_count == 0 or not run.payslips.exists():
            raise BusinessRuleError("This draft has no payslips. Generate the draft first.", code="empty_run")
        run.status = PayrollRun.Status.FINALIZED
        run.finalized_by = actor
        run.finalized_at = timezone.now()
        # Bypass the model's lock check for this single transition.
        PayrollRun.objects.filter(pk=run.pk).update(status=run.status, finalized_by=actor, finalized_at=run.finalized_at)
        slips = list(run.payslips.select_related("employee__user"))
    for slip in slips:
        notify(slip.employee.user, "payslip", f"Payslip for {run.period_label} is ready",
               f"Net pay: {slip.net:,.2f}", link="/payslips")
    record_audit(actor, "payroll.finalized", "payroll_run", run.pk, summary=f"Finalized payroll {run.period_label}",
                 before={"status": "draft"}, after={"status": "finalized", "total_net": run.total_net}, request=request)
    return run


def payslip_queryset_for(user):
    """Employees see only their own finalized payslips; HR/Admin see all."""
    qs = Payslip.objects.select_related("run", "employee")
    if user.role in ("admin", "hr"):
        return qs
    employee = getattr(user, "employee", None)
    if employee is None:
        return qs.none()
    return qs.filter(employee=employee, run__status=PayrollRun.Status.FINALIZED)
