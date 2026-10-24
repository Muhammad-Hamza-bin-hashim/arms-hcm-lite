"""Leave rules: working days, balances, overlap, approval workflow."""
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.comms.services import notify, notify_many, record_audit
from apps.employees.models import Employee
from apps.org.models import LeaveType
from apps.org.services import WorkCalendar, local_today
from config.exceptions import BusinessRuleError, ConflictError

from .models import LeaveRequest

ACTIVE_STATUSES = (LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED)


def days_in_year(lr_start, lr_end, year, cal):
    return cal.count(max(lr_start, date(year, 1, 1)), min(lr_end, date(year, 12, 31)))


def used_days(employee, leave_type, year, *, statuses=(LeaveRequest.Status.APPROVED,), exclude_id=None, cal=None):
    cal = cal or WorkCalendar()
    qs = LeaveRequest.objects.filter(employee=employee, leave_type=leave_type, status__in=statuses,
                                     start_date__lte=date(year, 12, 31), end_date__gte=date(year, 1, 1))
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    total = 0
    for lr in qs:
        if lr.start_date.year == year and lr.end_date.year == year:
            total += lr.days
        else:
            total += days_in_year(lr.start_date, lr.end_date, year, cal)
    return total


def balances(employee, year=None):
    """Per leave type: quota, used (approved), pending, remaining. Unlimited types have quota/remaining = None."""
    year = year or local_today().year
    cal = WorkCalendar()
    result = []
    for lt in LeaveType.objects.filter(is_active=True):
        used = used_days(employee, lt, year, cal=cal)
        pending = used_days(employee, lt, year, statuses=(LeaveRequest.Status.PENDING,), cal=cal)
        result.append({
            "leave_type_id": lt.pk, "code": lt.code, "name": lt.name, "is_paid": lt.is_paid,
            "quota": lt.yearly_quota, "used": used, "pending": pending,
            "remaining": None if lt.yearly_quota is None else max(lt.yearly_quota - used, 0),
        })
    return {"year": year, "balances": result}


def validate_leave(employee, leave_type, start, end, *, exclude_id=None, cal=None, include_pending=True):
    """Returns the number of working days or raises 422 with a structured reason."""
    cal = cal or WorkCalendar()
    if not leave_type.is_active:
        raise BusinessRuleError("This leave type is not available.", code="inactive_type",
                                errors={"leave_type": ["Inactive leave type."]})
    if end < start:
        raise BusinessRuleError("End date must be on or after the start date.", code="invalid_range",
                                errors={"end_date": ["Before start date."]})
    if (end - start).days > 120:
        raise BusinessRuleError("A single request cannot exceed 120 calendar days.", code="too_long")
    if start < employee.join_date:
        raise BusinessRuleError("Leave cannot start before the joining date.", code="before_join",
                                errors={"start_date": ["Before joining date."]})
    days = cal.count(start, end)
    if days == 0:
        raise BusinessRuleError("The selected dates contain no working days (weekends/holidays only).",
                                code="no_working_days", errors={"start_date": ["No working days in range."]})
    overlap = LeaveRequest.objects.filter(employee=employee, status__in=ACTIVE_STATUSES,
                                          start_date__lte=end, end_date__gte=start)
    if exclude_id:
        overlap = overlap.exclude(pk=exclude_id)
    clash = overlap.select_related("leave_type").first()
    if clash:
        raise BusinessRuleError(
            f"Overlaps your {clash.status} {clash.leave_type.name.lower()} leave "
            f"({clash.start_date:%d %b} - {clash.end_date:%d %b}).",
            code="overlap", errors={"start_date": ["Overlaps an existing request."]})
    from apps.payroll.models import PayrollRun
    for y, m in {(d.year, d.month) for d in (start, end)}:
        if PayrollRun.objects.filter(year=y, month=m, status=PayrollRun.Status.FINALIZED).exists():
            raise BusinessRuleError(f"Payroll for {y}-{m:02d} is finalized; leave in that month is locked.",
                                    code="payroll_locked")
    if leave_type.yearly_quota is not None:
        statuses = ACTIVE_STATUSES if include_pending else (LeaveRequest.Status.APPROVED,)
        for year in range(start.year, end.year + 1):
            need = days_in_year(start, end, year, cal)
            taken = used_days(employee, leave_type, year, statuses=statuses, exclude_id=exclude_id, cal=cal)
            left = leave_type.yearly_quota - taken
            if need > left:
                raise BusinessRuleError(
                    f"Not enough {leave_type.name.lower()} leave: {need} day(s) requested, {max(left, 0)} available"
                    f" in {year}" + (" (including pending requests)." if include_pending else "."),
                    code="insufficient_balance", errors={"leave_type": ["Insufficient balance."]})
    return days


@transaction.atomic
def apply_leave(user, *, leave_type, start_date, end_date, reason, source=LeaveRequest.Source.FORM, request=None):
    employee = getattr(user, "employee", None)
    if employee is None:
        raise BusinessRuleError("Your login has no employee profile.", code="no_employee_profile")
    if employee.employment_status == Employee.Status.EXITED:
        raise BusinessRuleError("Exited employees cannot apply for leave.", code="exited")
    Employee.objects.select_for_update().get(pk=employee.pk)  # serialise concurrent applications
    days = validate_leave(employee, leave_type, start_date, end_date)
    lr = LeaveRequest.objects.create(employee=employee, leave_type=leave_type, start_date=start_date,
                                     end_date=end_date, days=days, reason=reason, source=source)
    record_audit(user, "leave.applied", "leave_request", lr.pk,
                 summary=f"Applied {days} day(s) {leave_type.name} leave",
                 after={"type": leave_type.code, "start": start_date, "end": end_date, "days": days, "source": source},
                 request=request)
    hr_users = User.objects.filter(role=Role.HR, is_active=True).exclude(pk=user.pk)
    notify_many(hr_users, "leave", "New leave request",
                f"{employee.full_name} applied for {days} day(s) of {leave_type.name.lower()} leave.", link="/leave/approvals")
    return lr


@transaction.atomic
def decide_leave(leave_id, *, approve: bool, comment="", actor, request=None):
    lr = LeaveRequest.objects.select_for_update().select_related("employee__user", "leave_type").get(pk=leave_id)
    if lr.status != LeaveRequest.Status.PENDING:
        raise ConflictError(f"This request is already {lr.status}.")
    if getattr(actor, "employee", None) and actor.employee.pk == lr.employee_id:
        raise BusinessRuleError("You cannot approve or reject your own leave.", code="own_request")
    if not approve and not comment.strip():
        raise BusinessRuleError("A comment is required when rejecting.", errors={"comment": ["Required."]})
    if approve:
        Employee.objects.select_for_update().get(pk=lr.employee_id)
        validate_leave(lr.employee, lr.leave_type, lr.start_date, lr.end_date, exclude_id=lr.pk,
                       include_pending=False)
    before = {"status": lr.status}
    lr.status = LeaveRequest.Status.APPROVED if approve else LeaveRequest.Status.REJECTED
    lr.decided_by, lr.decided_at, lr.decision_comment = actor, timezone.now(), comment
    lr.save()
    record_audit(actor, f"leave.{lr.status}", "leave_request", lr.pk,
                 summary=f"{lr.status.title()} {lr.days} day(s) {lr.leave_type.name} leave for {lr.employee.full_name}",
                 before=before, after={"status": lr.status, "comment": comment}, request=request)
    notify(lr.employee.user, "leave", f"Leave {lr.status}",
           f"Your {lr.leave_type.name.lower()} leave ({lr.start_date:%d %b} - {lr.end_date:%d %b}) was {lr.status}."
           + (f" Comment: {comment}" if comment else ""), link="/leave")
    return lr


@transaction.atomic
def cancel_leave(leave_id, *, user, request=None):
    lr = LeaveRequest.objects.select_for_update().select_related("employee", "leave_type").get(pk=leave_id)
    if getattr(user, "employee", None) is None or lr.employee_id != user.employee.pk:
        raise BusinessRuleError("You can only cancel your own leave.", code="not_owner")
    if lr.status == LeaveRequest.Status.PENDING:
        pass
    elif lr.status == LeaveRequest.Status.APPROVED:
        if lr.start_date <= local_today():
            raise BusinessRuleError("Approved leave that has already started cannot be cancelled. Contact HR.",
                                    code="already_started")
    else:
        raise ConflictError(f"This request is already {lr.status}.")
    before = {"status": lr.status}
    lr.status = LeaveRequest.Status.CANCELLED
    lr.cancelled_at = timezone.now()
    lr.save()
    record_audit(user, "leave.cancelled", "leave_request", lr.pk, summary=f"Cancelled {lr.leave_type.name} leave",
                 before=before, after={"status": lr.status}, request=request)
    return lr
