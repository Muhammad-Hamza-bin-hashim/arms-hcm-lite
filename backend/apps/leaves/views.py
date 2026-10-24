from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsHR, PasswordChanged
from apps.employees.models import Employee
from apps.org.models import LeaveType
from apps.org.services import local_today
from config.exceptions import BusinessRuleError

from . import services
from .models import LeaveRequest

AUTH = [IsAuthenticated, PasswordChanged]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)
    department = serializers.CharField(source="employee.department.name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)

    class Meta:
        model = LeaveRequest
        fields = ["id", "employee", "employee_name", "employee_code", "department", "leave_type", "leave_type_name",
                  "leave_type_code", "start_date", "end_date", "days", "reason", "status", "source",
                  "decided_by_name", "decided_at", "decision_comment", "cancelled_at", "created_at"]


class LeaveInput(serializers.Serializer):
    leave_type = serializers.CharField(help_text="Leave type id or code")
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    source = serializers.ChoiceField(choices=LeaveRequest.Source.choices, default=LeaveRequest.Source.FORM)

    def validate_leave_type(self, value):
        lt = (LeaveType.objects.filter(pk=value).first() if str(value).isdigit()
              else LeaveType.objects.filter(code__iexact=value).first())
        if lt is None:
            raise serializers.ValidationError("Unknown leave type.")
        return lt


def _own_employee(user):
    if user.role == Role.ADMIN:
        raise PermissionDenied("Admins do not apply for leave in HCM Lite.")
    employee = getattr(user, "employee", None)
    if employee is None:
        raise BusinessRuleError("Your login has no employee profile.", code="no_employee_profile")
    return employee


class LeaveRequestListCreateView(ListAPIView):
    permission_classes = AUTH
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        user, p = self.request.user, self.request.query_params
        qs = LeaveRequest.objects.select_related("employee__department", "leave_type", "decided_by")
        if user.role == Role.EMPLOYEE or p.get("mine") == "true":
            qs = qs.filter(employee__user=user)
        else:
            if p.get("employee"):
                qs = qs.filter(employee_id=p["employee"])
            if p.get("department"):
                qs = qs.filter(employee__department_id=p["department"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("leave_type"):
            qs = qs.filter(leave_type__code=p["leave_type"])
        return qs

    def post(self, request):
        _own_employee(request.user)
        ser = LeaveInput(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if not d["reason"].strip():
            raise ValidationError({"reason": ["Please give a reason."]})
        lr = services.apply_leave(request.user, leave_type=d["leave_type"], start_date=d["start_date"],
                                  end_date=d["end_date"], reason=d["reason"], source=d["source"], request=request)
        return Response(LeaveRequestSerializer(lr).data, status=status.HTTP_201_CREATED)


class LeavePreviewView(APIView):
    """Validates a request without saving it (used by the form and by smart leave)."""

    permission_classes = AUTH

    def post(self, request):
        employee = _own_employee(request.user)
        ser = LeaveInput(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        days = services.validate_leave(employee, d["leave_type"], d["start_date"], d["end_date"])
        return Response({"valid": True, "days": days})


class LeaveDecisionView(APIView):
    permission_classes = AUTH + [IsHR]
    approve = True

    def post(self, request, pk):
        if not LeaveRequest.objects.filter(pk=pk).exists():
            return Response({"detail": "Not found.", "code": "not_found"}, status=404)
        lr = services.decide_leave(pk, approve=self.approve, comment=str(request.data.get("comment", ""))[:500],
                                   actor=request.user, request=request)
        return Response(LeaveRequestSerializer(lr).data)


class LeaveCancelView(APIView):
    permission_classes = AUTH

    def post(self, request, pk):
        if not LeaveRequest.objects.filter(pk=pk, employee__user=request.user).exists():
            return Response({"detail": "Not found.", "code": "not_found"}, status=404)
        lr = services.cancel_leave(pk, user=request.user, request=request)
        return Response(LeaveRequestSerializer(lr).data)


class LeaveBalanceView(APIView):
    permission_classes = AUTH

    def get(self, request):
        p = request.query_params
        year = int(p["year"]) if p.get("year", "").isdigit() else local_today().year
        if p.get("employee") and request.user.role in (Role.ADMIN, Role.HR):
            employee = Employee.objects.filter(pk=p["employee"]).first()
            if employee is None:
                raise ValidationError({"employee": ["Unknown employee."]})
        else:
            employee = getattr(request.user, "employee", None)
            if employee is None:
                raise BusinessRuleError("Your login has no employee profile.", code="no_employee_profile")
        return Response(services.balances(employee, year))


class LeaveTypeOptionsView(APIView):
    """Active leave types for the leave form (all roles)."""

    permission_classes = AUTH

    def get(self, request):
        return Response([{"id": lt.pk, "code": lt.code, "name": lt.name, "yearly_quota": lt.yearly_quota,
                          "is_paid": lt.is_paid} for lt in LeaveType.objects.filter(is_active=True)])
