from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import diff_instance, log_action
from apps.common.api import AuditedMixin, PermMixin
from apps.common.schema import documented

from .models import Branch, BusinessProfile


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "code", "kind", "address", "phone", "is_active"]


class BranchViewSet(AuditedMixin, PermMixin, viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    queryset = Branch.objects.none()  # for schema generation; see get_queryset
    write_perm = "system.manage"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        return Branch.objects.all() if user.is_owner else user.accessible_branches()


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        exclude = ["id", "created_at", "updated_at"]

    def validate_near_expiry_days(self, value):
        if not isinstance(value, list) or not all(isinstance(v, int) and v > 0 for v in value):
            raise serializers.ValidationError("Provide a list of positive day counts, e.g. [30, 60, 90].")
        return sorted(set(value))


class BusinessProfileView(PermMixin, APIView):
    perms = {"patch": "system.manage"}

    @documented("Business profile and configuration")
    def get(self, request):
        return Response(BusinessProfileSerializer(BusinessProfile.get()).data)

    @documented("Update the business profile", body=True)
    def patch(self, request):
        profile = BusinessProfile.get()
        serializer = BusinessProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = diff_instance(profile, serializer.validated_data)
        serializer.save()
        log_action(user=request.user, action="update", obj=profile, request=request, changes=changes)
        return Response(serializer.data)
