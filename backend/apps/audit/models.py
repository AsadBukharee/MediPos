from django.conf import settings
from django.db import models

from apps.common.models import ImmutableModel


class AuditLog(ImmutableModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=80, blank=True, db_index=True)
    object_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["object_type", "object_id"])]
