from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.accounts.permissions import IsAdmin, PasswordChanged

from .models import Announcement, AuditLog, Notification
from .services import notify_many, record_audit

AUTH = [IsAuthenticated, PasswordChanged]


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    created_by_role = serializers.CharField(source="created_by.role", read_only=True)

    class Meta:
        model = Announcement
        fields = ["id", "title", "body", "created_by_name", "created_by_role", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "is_read", "created_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "actor_email", "actor_role", "action", "entity_type", "entity_id", "summary", "before",
                  "after", "ip_address", "created_at"]


class AnnouncementListCreateView(ListAPIView):
    """All roles read; Admin and HR post."""

    permission_classes = AUTH
    serializer_class = AnnouncementSerializer
    queryset = Announcement.objects.select_related("created_by")

    def post(self, request):
        if request.user.role not in (Role.ADMIN, Role.HR):
            raise PermissionDenied("Only Admin and HR can post announcements.")
        ser = AnnouncementSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ann = ser.save(created_by=request.user)
        record_audit(request.user, "announcement.posted", "announcement", ann.pk, summary=f"Posted '{ann.title}'",
                     after={"title": ann.title}, request=request)
        notify_many(User.objects.filter(is_active=True).exclude(pk=request.user.pk), "announcement",
                    f"Announcement: {ann.title}", ann.body[:200], link="/announcements")
        return Response(AnnouncementSerializer(ann).data, status=status.HTTP_201_CREATED)


class AnnouncementDeleteView(APIView):
    permission_classes = AUTH

    def delete(self, request, pk):
        ann = get_object_or_404(Announcement, pk=pk)
        if not (request.user.role == Role.ADMIN or ann.created_by_id == request.user.pk):
            raise PermissionDenied("You can only remove your own announcements.")
        record_audit(request.user, "announcement.deleted", "announcement", ann.pk, summary=f"Deleted '{ann.title}'",
                     before={"title": ann.title, "body": ann.body}, request=request)
        ann.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationListView(ListAPIView):
    permission_classes = AUTH
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["unread_count"] = Notification.objects.filter(user=request.user, is_read=False).count()
        return response


class NotificationReadView(APIView):
    permission_classes = AUTH

    def post(self, request, pk=None):
        qs = Notification.objects.filter(user=request.user, is_read=False)
        if pk is not None:
            qs = qs.filter(pk=pk)
        updated = qs.update(is_read=True)
        return Response({"updated": updated})


class AuditLogView(ListAPIView):
    """Admin only, read only. There are no update/delete endpoints and the model refuses changes."""

    permission_classes = AUTH + [IsAdmin]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        qs = AuditLog.objects.all()
        p = self.request.query_params
        if p.get("entity_type"):
            qs = qs.filter(entity_type=p["entity_type"])
        if p.get("action"):
            qs = qs.filter(action__startswith=p["action"])
        if p.get("actor"):
            qs = qs.filter(actor_email__icontains=p["actor"])
        if p.get("search"):
            qs = qs.filter(Q(summary__icontains=p["search"]) | Q(action__icontains=p["search"]))
        if p.get("from"):
            qs = qs.filter(created_at__date__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(created_at__date__lte=p["to"])
        return qs
