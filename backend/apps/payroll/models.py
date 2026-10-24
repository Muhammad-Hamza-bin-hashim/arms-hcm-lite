from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.validators import MinValueValidator
from django.db import models

MONEY = {"max_digits": 14, "decimal_places": 2}
DAYS = {"max_digits": 6, "decimal_places": 2, "default": 0}


class SalaryStructure(models.Model):
    """Salary history; the row with the latest effective_from on or before a date applies."""

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="salary_structures")
    basic = models.DecimalField(validators=[MinValueValidator(0.01)], **MONEY)
    hra = models.DecimalField(**MONEY)
    medical = models.DecimalField(**MONEY)
    gross = models.DecimalField(**MONEY)
    effective_from = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-id"]
        constraints = [models.UniqueConstraint(fields=["employee", "effective_from"], name="uniq_salary_per_date")]


class PayrollRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINALIZED = "finalized", "Finalized"

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    working_days = models.PositiveSmallIntegerField(default=0)
    employee_count = models.PositiveIntegerField(default=0)
    total_gross = models.DecimalField(default=0, **MONEY)
    total_deductions = models.DecimalField(default=0, **MONEY)
    total_tax = models.DecimalField(default=0, **MONEY)
    total_net = models.DecimalField(default=0, **MONEY)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [models.UniqueConstraint(fields=["year", "month"], name="uniq_payroll_period")]

    @property
    def is_locked(self):
        return self.status == self.Status.FINALIZED

    @property
    def period_label(self):
        return f"{self.year}-{self.month:02d}"

    def save(self, *args, **kwargs):
        if self.pk:
            stored = PayrollRun.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if stored == self.Status.FINALIZED:
                raise PermissionDenied("Finalized payroll runs are locked.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_locked:
            raise PermissionDenied("Finalized payroll runs are locked.")
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Payroll {self.period_label}"


class Payslip(models.Model):
    """Immutable snapshot of every input and result, so a finalized payslip is always reproducible."""

    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payslips")
    employee_code = models.CharField(max_length=30)
    employee_name = models.CharField(max_length=200)
    department_name = models.CharField(max_length=120)
    designation_name = models.CharField(max_length=120, blank=True)
    basic = models.DecimalField(**MONEY)
    hra = models.DecimalField(**MONEY)
    medical = models.DecimalField(**MONEY)
    gross = models.DecimalField(**MONEY)
    working_days = models.PositiveSmallIntegerField()
    payable_days = models.PositiveSmallIntegerField(help_text="Working days employed in the month (proration).")
    absent_days = models.DecimalField(**DAYS)
    unpaid_leave_days = models.DecimalField(**DAYS)
    half_days = models.DecimalField(**DAYS)
    late_count = models.PositiveSmallIntegerField(default=0)
    late_penalty_days = models.DecimalField(**DAYS)
    per_day_rate = models.DecimalField(**MONEY)
    prorated_gross = models.DecimalField(**MONEY)
    deduction = models.DecimalField(**MONEY)
    earned_gross = models.DecimalField(**MONEY)
    annual_taxable = models.DecimalField(**MONEY)
    annual_tax = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    net = models.DecimalField(**MONEY)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_code"]
        constraints = [models.UniqueConstraint(fields=["run", "employee"], name="uniq_payslip_per_run")]

    def save(self, *args, **kwargs):
        if PayrollRun.objects.filter(pk=self.run_id, status=PayrollRun.Status.FINALIZED).exists():
            raise PermissionDenied("Payslips of a finalized payroll run are locked.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.run.is_locked:
            raise PermissionDenied("Payslips of a finalized payroll run are locked.")
        super().delete(*args, **kwargs)
