from django.conf import settings
from django.db import models


class AILog(models.Model):
    class Feature(models.TextChoices):
        CHAT = "chat", "Chat"
        SUMMARY = "summary", "Dashboard summary"
        SMART_LEAVE = "smart_leave", "Smart leave"

    class Outcome(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"
        TIMEOUT = "timeout", "Timeout"
        INVALID = "invalid_output", "Invalid output"
        UNCONFIGURED = "unconfigured", "Not configured"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_logs")
    role = models.CharField(max_length=20)
    feature = models.CharField(max_length=20, choices=Feature.choices)
    prompt = models.TextField()
    tools_called = models.JSONField(default=list)
    response = models.TextField(blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    error = models.TextField(blank=True)
    provider = models.CharField(max_length=30, blank=True)
    model = models.CharField(max_length=80, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "ai_logs"
        ordering = ["-created_at"]
