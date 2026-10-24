from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdmin, IsAdminOrHR, PasswordChanged
from apps.employees.models import Employee
from apps.org.services import local_today

from . import services
from .models import PayrollRun, Payslip, SalaryStructure
from .pdf import render_payslip

AUTH = [IsAuthenticated, PasswordChanged]


class SalarySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)

    class Meta:
        model = SalaryStructure
        fields = ["id", "employee", "employee_name", "employee_code", "basic", "hra", "medical", "gross",
                  "effective_from", "created_at"]


class PayslipSerializer(serializers.ModelSerializer):
    period = serializers.CharField(source="run.period_label", read_only=True)
    run_status = serializers.CharField(source="run.status", read_only=True)

    class Meta:
        model = Payslip
        exclude = ["created_at"]


class RunSerializer(serializers.ModelSerializer):
    period = serializers.CharField(source="period_label", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    finalized_by_name = serializers.CharField(source="finalized_by.full_name", read_only=True, default=None)

    class Meta:
        model = PayrollRun
        fields = ["id", "year", "month", "period", "status", "working_days", "employee_count", "total_gross",
                  "total_deductions", "total_tax", "total_net", "created_by_name", "created_at", "generated_at",
                  "finalized_by_name", "finalized_at"]


class SalaryView(ListAPIView):
    """Admin views, HR manages salary structures."""

    permission_classes = AUTH + [IsAdminOrHR]
    serializer_class = SalarySerializer

    class Input(serializers.Serializer):
        employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
        basic = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
        effective_from = serializers.DateField(required=False)

    def get_queryset(self):
        qs = SalaryStructure.objects.select_related("employee")
        if self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=self.request.query_params["employee"])
        return qs

    def post(self, request):
        if request.user.role != Role.HR:
            raise PermissionDenied("Only HR can set salary structures.")
        ser = self.Input(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if getattr(request.user, "employee", None) == d["employee"]:
            raise PermissionDenied("You cannot change your own salary.")
        structure = services.set_salary(d["employee"], d["basic"], d.get("effective_from") or local_today(),
                                        actor=request.user, request=request)
        return Response(SalarySerializer(structure).data, status=status.HTTP_201_CREATED)


class RunListCreateView(ListAPIView):
    permission_classes = AUTH + [IsAdminOrHR]
    serializer_class = RunSerializer
    queryset = PayrollRun.objects.select_related("created_by", "finalized_by")

    class Input(serializers.Serializer):
        year = serializers.IntegerField(min_value=2000, max_value=2100)
        month = serializers.IntegerField(min_value=1, max_value=12)

    def post(self, request):
        if request.user.role != Role.HR:
            raise PermissionDenied("Only HR prepares the payroll draft.")
        ser = self.Input(data=request.data)
        ser.is_valid(raise_exception=True)
        run = services.generate_draft(ser.validated_data["year"], ser.validated_data["month"], actor=request.user,
                                      request=request)
        return Response(RunSerializer(run).data, status=status.HTTP_201_CREATED)


class RunDetailView(RetrieveAPIView):
    permission_classes = AUTH + [IsAdminOrHR]
    serializer_class = RunSerializer
    queryset = PayrollRun.objects.all()

    def retrieve(self, request, *args, **kwargs):
        run = self.get_object()
        return Response({**RunSerializer(run).data,
                         "payslips": PayslipSerializer(run.payslips.select_related("run"), many=True).data})


class RunRegenerateView(APIView):
    permission_classes = AUTH + [IsAdminOrHR]

    def post(self, request, pk):
        if request.user.role != Role.HR:
            raise PermissionDenied("Only HR prepares the payroll draft.")
        run = get_object_or_404(PayrollRun, pk=pk)
        run = services.generate_draft(run.year, run.month, actor=request.user, request=request)
        return Response(RunSerializer(run).data)


class RunFinalizeView(APIView):
    permission_classes = AUTH + [IsAdmin]

    def post(self, request, pk):
        get_object_or_404(PayrollRun, pk=pk)
        run = services.finalize(pk, actor=request.user, request=request)
        return Response(RunSerializer(run).data)


class PayslipListView(ListAPIView):
    permission_classes = AUTH
    serializer_class = PayslipSerializer

    def get_queryset(self):
        qs = services.payslip_queryset_for(self.request.user)
        p = self.request.query_params
        if p.get("mine") == "true":
            qs = qs.filter(employee__user=self.request.user, run__status=PayrollRun.Status.FINALIZED)
        if p.get("employee") and self.request.user.role != Role.EMPLOYEE:
            qs = qs.filter(employee_id=p["employee"])
        if p.get("run"):
            qs = qs.filter(run_id=p["run"])
        return qs.order_by("-run__year", "-run__month", "employee_code")


class PayslipDetailView(RetrieveAPIView):
    permission_classes = AUTH
    serializer_class = PayslipSerializer

    def get_queryset(self):
        return services.payslip_queryset_for(self.request.user)


class PayslipPdfView(APIView):
    permission_classes = AUTH

    def get(self, request, pk):
        slip = get_object_or_404(services.payslip_queryset_for(request.user), pk=pk)
        response = HttpResponse(render_payslip(slip), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="payslip-{slip.employee_code}-{slip.run.period_label}.pdf"'
        return response
