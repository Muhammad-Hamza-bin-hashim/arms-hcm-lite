from datetime import time
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def default_weekend():
    return [5, 6]  # Python weekday(): Monday=0 ... Saturday=5, Sunday=6


class CompanySettings(models.Model):
    """Singleton (pk=1). Rules are read when a record is created, so changes apply to new records only."""

    company_name = models.CharField(max_length=200)
    timezone = models.CharField(max_length=64, default="Asia/Karachi")
    currency = models.CharField(max_length=8, default="PKR")
    office_start = models.TimeField(default=time(9, 0))
    office_end = models.TimeField(default=time(18, 0))
    grace_minutes = models.PositiveSmallIntegerField(default=15, validators=[MaxValueValidator(180)])
    half_day_hours = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("5.00"),
                                         validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("12"))])
    weekend_days = models.JSONField(default=default_weekend)
    office_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                     validators=[MinValueValidator(-90), MaxValueValidator(90)])
    office_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                     validators=[MinValueValidator(-180), MaxValueValidator(180)])
    office_radius_m = models.PositiveIntegerField(default=150, validators=[MinValueValidator(10), MaxValueValidator(5000)])
    late_penalty_enabled = models.BooleanField(default=False, help_text="Bonus rule: every 3 lates = 0.5 day deduction.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "company settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj = cls.objects.filter(pk=1).first()
        if obj is None:
            # Unsaved defaults: lets services run before first-run setup (e.g. in tests).
            obj = cls(company_name="")
        return obj


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Designation(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeaveType(models.Model):
    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    yearly_quota = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty = unlimited.")
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} {self.name}"


DEFAULT_LEAVE_TYPES = [
    {"code": "annual", "name": "Annual", "yearly_quota": 14, "is_paid": True},
    {"code": "sick", "name": "Sick", "yearly_quota": 8, "is_paid": True},
    {"code": "casual", "name": "Casual", "yearly_quota": 10, "is_paid": True},
    {"code": "unpaid", "name": "Unpaid", "yearly_quota": None, "is_paid": False},
]
