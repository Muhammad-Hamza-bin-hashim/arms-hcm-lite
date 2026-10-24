from decimal import Decimal

from rest_framework import serializers

from apps.org.models import Department, Designation

from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    designation_name = serializers.CharField(source="designation.name", read_only=True, default=None)
    user_id = serializers.IntegerField(read_only=True)
    is_login_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = Employee
        fields = ["id", "employee_code", "first_name", "last_name", "full_name", "email", "phone", "address",
                  "gender", "date_of_birth", "department", "department_name", "designation", "designation_name",
                  "join_date", "exit_date", "employment_status", "user_id", "is_login_active", "created_at"]
        read_only_fields = ["created_at"]


class EmployeeWriteSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.filter(is_active=True))
    designation = serializers.PrimaryKeyRelatedField(queryset=Designation.objects.all(), required=False,
                                                     allow_null=True)

    class Meta:
        model = Employee
        fields = ["employee_code", "first_name", "last_name", "email", "phone", "address", "gender",
                  "date_of_birth", "department", "designation", "join_date", "exit_date", "employment_status"]

    def validate_employee_code(self, value):
        return value.strip().upper()


class EmployeeCreateSerializer(EmployeeWriteSerializer):
    basic_salary = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    class Meta(EmployeeWriteSerializer.Meta):
        fields = EmployeeWriteSerializer.Meta.fields + ["basic_salary"]

    def validate(self, attrs):
        if attrs.get("employment_status") == Employee.Status.EXITED:
            raise serializers.ValidationError({"employment_status": "A new employee cannot be registered as exited."})
        attrs.pop("exit_date", None)
        return attrs


class SelfContactSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True)
