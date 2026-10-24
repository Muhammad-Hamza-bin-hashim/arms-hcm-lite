from django.conf import settings
from django.db import models


class Employee(models.Model):
    class Status(models.TextChoices):
        PROBATION = "probation", "Probation"
        ACTIVE = "active", "Active"
        EXITED = "exited", "Exited"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        UNSPECIFIED = "unspecified", "Prefer not to say"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee")
    employee_code = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True)
    gender = models.CharField(max_length=12, choices=Gender.choices, default=Gender.UNSPECIFIED)
    date_of_birth = models.DateField(null=True, blank=True)
    department = models.ForeignKey("org.Department", on_delete=models.PROTECT, related_name="employees")
    designation = models.ForeignKey("org.Designation", on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="employees")
    join_date = models.DateField()
    exit_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROBATION,
                                         db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_code"]
        indexes = [models.Index(fields=["department", "employment_status"])]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def is_employed_on(self, d):
        return self.join_date <= d and (self.exit_date is None or d <= self.exit_date)

    def __str__(self):
        return f"{self.employee_code} {self.full_name}"
