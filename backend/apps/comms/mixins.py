from django.db.models import ProtectedError

from config.exceptions import BusinessRuleError

from .services import record_audit


class AuditedModelMixin:
    """Records create / update / delete on a ModelViewSet with before/after JSON."""

    audit_entity = ""

    def _entity(self):
        return self.audit_entity or self.get_queryset().model.__name__.lower()

    def perform_create(self, serializer):
        obj = serializer.save()
        record_audit(self.request.user, f"{self._entity()}.created", self._entity(), obj.pk,
                     summary=f"Created {self._entity()} {obj}", after=serializer.data, request=self.request)

    def perform_update(self, serializer):
        before = type(serializer)(serializer.instance).data
        obj = serializer.save()
        record_audit(self.request.user, f"{self._entity()}.updated", self._entity(), obj.pk,
                     summary=f"Updated {self._entity()} {obj}", before=before, after=serializer.data,
                     request=self.request)

    def perform_destroy(self, instance):
        before = self.get_serializer(instance).data
        pk, label = instance.pk, str(instance)
        try:
            instance.delete()
        except ProtectedError:
            raise BusinessRuleError(f"'{label}' is in use and cannot be deleted. Deactivate it instead.",
                                    code="in_use")
        record_audit(self.request.user, f"{self._entity()}.deleted", self._entity(), pk,
                     summary=f"Deleted {self._entity()} {label}", before=before, request=self.request)
