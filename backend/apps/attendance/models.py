from django.conf import settings
from django.db import models


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        HALF_DAY = "half_day", "Half day"
        MISSING_CHECKOUT = "missing_checkout", "Missing checkout"

    class Source(models.TextChoices):
        WEB = "web", "Web"
        CAMERA = "camera", "Camera"
        CORRECTION = "correction", "HR correction"

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(db_index=True)
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    is_late = models.BooleanField(default=False)
    worked_minutes = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.WEB)
    # Rule snapshot taken when the record is created (settings changes apply to new records only).
    late_after = models.TimeField()
    half_day_minutes = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "employee_id"]
        constraints = [models.UniqueConstraint(fields=["employee", "date"], name="uniq_attendance_per_day")]


class AttendanceCorrection(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="attendance_corrections")
    date = models.DateField()
    check_in_time = models.TimeField()
    check_out_time = models.TimeField(null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
