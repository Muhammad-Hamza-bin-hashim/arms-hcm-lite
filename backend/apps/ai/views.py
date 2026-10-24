from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdmin, IsAdminOrHR, PasswordChanged
from apps.analytics import services as analytics

from . import service
from .models import AILog

AUTH = [IsAuthenticated, PasswordChanged]


class StatusView(APIView):
    permission_classes = AUTH

    def get(self, request):
        return Response({"configured": bool(settings.AI_API_KEY), "provider": settings.AI_PROVIDER,
                         "rate_limit_per_hour": settings.AI_RATE_LIMIT_PER_HOUR})


class ChatView(APIView):
    permission_classes = AUTH

    class Input(serializers.Serializer):
        message = serializers.CharField(max_length=1000)
        history = serializers.ListField(child=serializers.DictField(), required=False, max_length=20)

    def post(self, request):
        ser = self.Input(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(service.chat(request.user, ser.validated_data["message"].strip(),
                                     ser.validated_data.get("history")))


class SummaryView(APIView):
    """Summarizes the KPI JSON for the current filters (recomputed on the server, never trusted from the browser)."""

    permission_classes = AUTH + [IsAdminOrHR]

    def post(self, request):
        board = request.data.get("dashboard") or ("admin" if request.user.role == Role.ADMIN else "hr")
        if board == "admin" and request.user.role != Role.ADMIN:
            raise PermissionDenied("Only Admin can summarize the company dashboard.")
        f = analytics.Filters.from_params(request.data)
        data = analytics.admin_dashboard(f) if board == "admin" else analytics.hr_dashboard(f)
        kpis = service.compact_kpis(data, Role.ADMIN if board == "admin" else Role.HR)
        return Response(service.summarize_dashboard(request.user, kpis))


class SmartLeaveView(APIView):
    permission_classes = AUTH

    class Input(serializers.Serializer):
        text = serializers.CharField(max_length=500)

    def post(self, request):
        if request.user.role == Role.ADMIN:
            raise PermissionDenied("Smart leave is for employees and HR applying for their own leave.")
        ser = self.Input(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(service.smart_leave(request.user, ser.validated_data["text"].strip()))


class AILogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = AILog
        fields = ["id", "user_email", "role", "feature", "prompt", "tools_called", "response", "outcome", "error",
                  "provider", "model", "latency_ms", "created_at"]


class AILogListView(ListAPIView):
    permission_classes = AUTH + [IsAdmin]
    serializer_class = AILogSerializer
    queryset = AILog.objects.select_related("user")
