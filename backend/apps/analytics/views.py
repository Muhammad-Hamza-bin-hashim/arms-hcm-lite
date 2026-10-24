from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin, IsAdminOrHR, PasswordChanged

from . import services

AUTH = [IsAuthenticated, PasswordChanged]


class AdminDashboardView(APIView):
    permission_classes = AUTH + [IsAdmin]

    def get(self, request):
        return Response(services.admin_dashboard(services.Filters.from_params(request.query_params)))


class HRDashboardView(APIView):
    permission_classes = AUTH + [IsAdminOrHR]

    def get(self, request):
        return Response(services.hr_dashboard(services.Filters.from_params(request.query_params)))


class EmployeeDashboardView(APIView):
    permission_classes = AUTH

    def get(self, request):
        return Response(services.employee_dashboard(request.user))
