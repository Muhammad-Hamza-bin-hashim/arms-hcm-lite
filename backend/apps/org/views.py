from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import PasswordChanged, RoleAccess
from apps.comms.mixins import AuditedModelMixin
from apps.comms.services import record_audit

from .models import CompanySettings, Department, Designation, Holiday, LeaveType
from .serializers import (CompanySettingsSerializer, DepartmentSerializer, DesignationSerializer, HolidaySerializer,
                          LeaveTypeSerializer)

ADMIN_MANAGES = {"read_roles": (Role.ADMIN, Role.HR), "write_roles": (Role.ADMIN,)}


class CompanySettingsView(APIView):
    permission_classes = [IsAuthenticated, PasswordChanged, RoleAccess]
    read_roles = ADMIN_MANAGES["read_roles"]
    write_roles = ADMIN_MANAGES["write_roles"]

    def get(self, request):
        obj, _ = CompanySettings.objects.get_or_create(pk=1, defaults={"company_name": ""})
        return Response(CompanySettingsSerializer(obj).data)

    def patch(self, request):
        obj, _ = CompanySettings.objects.get_or_create(pk=1, defaults={"company_name": ""})
        before = CompanySettingsSerializer(obj).data
        ser = CompanySettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        record_audit(request.user, "settings.updated", "company_settings", 1, summary="Updated company settings",
                     before=before, after=ser.data, request=request)
        return Response(ser.data)

    put = patch


class _AdminManagedViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, PasswordChanged, RoleAccess]
    read_roles = ADMIN_MANAGES["read_roles"]
    write_roles = ADMIN_MANAGES["write_roles"]
    pagination_class = None


class DepartmentViewSet(_AdminManagedViewSet):
    serializer_class = DepartmentSerializer
    audit_entity = "department"

    def get_queryset(self):
        return Department.objects.annotate(
            employee_count=Count("employees", filter=~Q(employees__employment_status="exited"))
        )


class DesignationViewSet(_AdminManagedViewSet):
    serializer_class = DesignationSerializer
    queryset = Designation.objects.all()
    audit_entity = "designation"


class LeaveTypeViewSet(_AdminManagedViewSet):
    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.all()
    audit_entity = "leave_type"


class HolidayViewSet(_AdminManagedViewSet):
    serializer_class = HolidaySerializer
    audit_entity = "holiday"

    def get_queryset(self):
        qs = Holiday.objects.all()
        year = self.request.query_params.get("year")
        if year and year.isdigit():
            qs = qs.filter(date__year=int(year))
        return qs
