"""Audit logging and notifications used by every module."""
import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder

from .models import AuditLog, Notification

SENSITIVE_KEYS = {"password", "token", "access", "refresh", "temporary_password", "ai_api_key"}


def _clean(data):
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: ("***" if k.lower() in SENSITIVE_KEYS else _clean(v)) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_clean(v) for v in data]
    # Round-trip through Django's encoder so dates/decimals become JSON-safe.
    if isinstance(data, Decimal):
        return str(data)
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def _client_ip(request):
    if request is None:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", ""))[:64]


def record_audit(actor, action, entity_type, entity_id="", *, summary="", before=None, after=None, request=None):
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_email=getattr(actor, "email", "") or "",
        actor_role=getattr(actor, "role", "") or "",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        summary=summary[:300],
        before=_clean(before),
        after=_clean(after),
        ip_address=_client_ip(request),
    )


def notify(user, kind, title, body="", link=""):
    if user is None:
        return None
    return Notification.objects.create(user=user, kind=kind, title=title[:200], body=body, link=link)


def notify_many(users, kind, title, body="", link=""):
    Notification.objects.bulk_create(
        [Notification(user=u, kind=kind, title=title[:200], body=body, link=link) for u in users]
    )
