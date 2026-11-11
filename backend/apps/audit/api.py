from rest_framework import serializers, viewsets

from apps.common.api import PermMixin

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", default="", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "user", "user_name", "branch", "action", "object_type", "object_id", "summary",
                  "changes", "ip_address", "created_at"]


class AuditLogViewSet(PermMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.none()  # for schema generation; see get_queryset
    read_perm = "audit.view"
    filterset_fields = ["action", "object_type", "object_id", "user", "branch"]
    search_fields = ["summary", "action"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user")
        user = self.request.user
        if not user.is_owner:
            qs = qs.filter(branch__in=user.accessible_branches())
        return qs
