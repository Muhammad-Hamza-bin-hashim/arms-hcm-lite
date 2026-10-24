from django.db.models import Q
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import PasswordChanged
from apps.org.services import local_today

from . import services
from .models import Employee
from .serializers import EmployeeCreateSerializer, EmployeeSerializer, EmployeeWriteSerializer, SelfContactSerializer

ORDERING = {"code": "employee_code", "name": "first_name", "join_date": "join_date", "department": "department__name"}


class EmployeeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Admin/HR: directory of all employees. Employee: only their own row. HR registers and edits."""

    permission_classes = [IsAuthenticated, PasswordChanged]
    serializer_class = EmployeeSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        qs = Employee.objects.select_related("department", "designation", "user")
        if user.role == Role.EMPLOYEE:
            return qs.filter(user=user)
        p = self.request.query_params
        if p.get("search"):
            q = p["search"].strip()
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(employee_code__icontains=q)
                           | Q(email__icontains=q) | Q(phone__icontains=q))
        if p.get("department"):
            qs = qs.filter(department_id=p["department"])
        if p.get("designation"):
            qs = qs.filter(designation_id=p["designation"])
        if p.get("status"):
            qs = qs.filter(employment_status=p["status"])
        order = p.get("ordering", "code")
        field = ORDERING.get(order.lstrip("-"), "employee_code")
        return qs.order_by(("-" if order.startswith("-") else "") + field, "id")

    def _require_hr(self):
        if self.request.user.role != Role.HR:
            raise PermissionDenied("Only HR can register or edit employees.")

    def create(self, request, *args, **kwargs):
        self._require_hr()
        ser = EmployeeCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        employee, temp = services.register_employee(ser.validated_data, actor=request.user, request=request)
        return Response({"employee": EmployeeSerializer(employee).data, "temporary_password": temp},
                        status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        self._require_hr()
        employee = self.get_object()
        ser = EmployeeWriteSerializer(employee, data=request.data, partial=kwargs.get("partial", False))
        ser.is_valid(raise_exception=True)
        services.update_employee(employee, dict(ser.validated_data), actor=request.user, request=request)
        employee.refresh_from_db()
        return Response(EmployeeSerializer(employee).data)

    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        employee = getattr(request.user, "employee", None)
        if employee is None:
            return Response({"detail": "No employee profile linked to this login.", "code": "no_employee_profile"},
                            status=status.HTTP_404_NOT_FOUND)
        if request.method == "PATCH":
            ser = SelfContactSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            extra = set(request.data.keys()) - {"phone", "address"}
            if extra:
                raise PermissionDenied(f"You can only edit phone and address (not: {', '.join(sorted(extra))}).")
            services.update_own_contact(employee, request=request, **ser.validated_data)
        return Response(EmployeeSerializer(employee).data)

    @action(detail=True, methods=["get"], url_path="360")
    def profile_360(self, request, pk=None):
        employee = self.get_object()  # scoped queryset: employees can only reach their own row
        return Response(build_360(employee, request.user))

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        self._require_hr()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Attach a CSV file."]})
        if upload.size > 2 * 1024 * 1024:
            raise ValidationError({"file": ["File is larger than 2 MB."]})
        raw = upload.read()
        dry_run = str(request.data.get("dry_run", request.query_params.get("dry_run", "true"))).lower() != "false"
        if dry_run:
            clean, errors, total = services.validate_csv(raw)
            return Response({"dry_run": True, "total_rows": total, "valid_rows": len(clean), "errors": errors})
        created = services.import_csv(raw, actor=request.user, request=request)
        return Response({"dry_run": False, "created": created}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        self._require_hr()
        response = HttpResponse(services.export_csv(self.get_queryset()), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="employees-{local_today()}.csv"'
        return response

    @action(detail=False, methods=["get"], url_path="csv-template")
    def csv_template(self, request):
        self._require_hr()
        response = HttpResponse(",".join(services.CSV_COLUMNS) + "\n", content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="employee-import-template.csv"'
        return response


def build_360(employee, viewer):
    """Profile + attendance + leave + payroll history, filtered by what the viewer may see."""
    from datetime import timedelta

    from apps.attendance.models import Attendance
    from apps.attendance.services import day_matrix, summarize
    from apps.leaves.models import LeaveRequest
    from apps.leaves.services import balances
    from apps.payroll.services import current_salary, payslip_queryset_for

    today = local_today()
    start = max(employee.join_date, today - timedelta(days=29))
    matrix = day_matrix([employee], start, today, today=today) if start <= today else {employee.pk: {}}
    recent = Attendance.objects.filter(employee=employee).order_by("-date")[:10]
    leaves = LeaveRequest.objects.filter(employee=employee).select_related("leave_type").order_by("-created_at")[:10]
    payslips = payslip_queryset_for(viewer).filter(employee=employee).order_by("-run__year", "-run__month")[:12]
    data = {
        "employee": EmployeeSerializer(employee).data,
        "attendance_30d": summarize([matrix[employee.pk]]),
        "recent_attendance": [{"date": a.date, "status": a.status, "check_in": a.check_in, "check_out": a.check_out,
                               "worked_minutes": a.worked_minutes, "source": a.source} for a in recent],
        "leave_balance": balances(employee, today.year),
        "recent_leaves": [{"id": lr.id, "type": lr.leave_type.name, "start_date": lr.start_date,
                           "end_date": lr.end_date, "days": lr.days, "status": lr.status} for lr in leaves],
        "payslips": [{"id": p.id, "period": p.run.period_label, "status": p.run.status, "net": p.net,
                      "earned_gross": p.earned_gross} for p in payslips],
    }
    if viewer.role in (Role.ADMIN, Role.HR) or getattr(viewer, "employee", None) == employee:
        salary = current_salary(employee)
        data["salary"] = ({"basic": salary.basic, "hra": salary.hra, "medical": salary.medical,
                           "gross": salary.gross, "effective_from": salary.effective_from} if salary else None)
    return data
