from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api import BranchMixin
from apps.common.schema import documented

from . import services
from .models import DeviceToken, Notification, NotificationPreference, StockAlert


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "branch", "type", "title", "body", "data", "is_read", "read_at", "created_at"]

    def get_is_read(self, obj) -> bool:
        return obj.read_at is not None


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The signed-in user's notification centre."""

    serializer_class = NotificationSerializer
    queryset = Notification.objects.none()  # for schema generation; see get_queryset
    filterset_fields = ["type", "branch"]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") in {"1", "true"}:
            qs = qs.filter(read_at__isnull=True)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread": Notification.objects.filter(user=request.user, read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        Notification.objects.filter(user=request.user, pk=pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceView(APIView):
    """Register (POST) or remove (DELETE) this device's FCM token."""

    @documented("Register this device's FCM token (token, platform)", body=True, empty=True)
    def post(self, request):
        token = str(request.data.get("token", "")).strip()
        if not token or len(token) > 512:
            raise serializers.ValidationError({"token": "A device token is required."})
        DeviceToken.objects.update_or_create(
            token=token, defaults={"user": request.user, "platform": str(request.data.get("platform", "android"))[:10]})
        return Response(status=status.HTTP_204_NO_CONTENT)

    @documented("Remove this device's FCM token (token)", body=True, empty=True)
    def delete(self, request):
        DeviceToken.objects.filter(user=request.user, token=str(request.data.get("token", ""))).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferenceView(APIView):
    @documented("Notification preferences per type")
    def get(self, request):
        saved = {p.type: p for p in request.user.notification_preferences.all()}
        return Response([
            {"type": type_, "label": label, "in_app": saved[type_].in_app if type_ in saved else True,
             "push": saved[type_].push if type_ in saved else True}
            for type_, label in services.NOTIFICATION_TYPES.items()
        ])

    @documented("Replace notification preferences: a list of {type, in_app, push}", body=True)
    def put(self, request):
        rows = request.data if isinstance(request.data, list) else []
        for row in rows:
            if row.get("type") in services.NOTIFICATION_TYPES:
                NotificationPreference.objects.update_or_create(
                    user=request.user, type=row["type"],
                    defaults={"in_app": bool(row.get("in_app", True)), "push": bool(row.get("push", True))})
        return self.get(request)


class StockAlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    base_unit_name = serializers.CharField(source="product.base_unit.name", read_only=True)
    reorder_level = serializers.IntegerField(source="product.reorder_level", read_only=True)
    acted_by_name = serializers.CharField(source="acted_by.username", read_only=True, default="")

    class Meta:
        model = StockAlert
        fields = ["id", "product", "product_name", "base_unit_name", "reorder_level", "kind", "status",
                  "triggered_quantity", "suggested_quantity", "requested_quantity", "acted_by_name", "acted_at",
                  "resolved_at", "created_at"]


class StockAlertViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = StockAlert.objects.select_related("product__base_unit", "acted_by")
    serializer_class = StockAlertSerializer
    read_perm = "inventory.view"
    perms = {"add_to_order": "alerts.act", "skip": "alerts.act"}
    filterset_fields = ["status", "kind", "product"]

    def _act(self, request, pk, action_name, quantity=None):
        alert = services.act_on_alert(alert_id=pk, branch=request.branch, user=request.user, action=action_name, quantity=quantity)
        return Response(self.get_serializer(alert).data)

    @action(detail=True, methods=["post"], url_path="add-to-order")
    def add_to_order(self, request, pk=None):
        quantity = request.data.get("quantity")
        if quantity not in (None, ""):
            quantity = serializers.IntegerField(min_value=1).run_validation(quantity)
        else:
            quantity = None
        return self._act(request, pk, "add", quantity)

    @action(detail=True, methods=["post"])
    def skip(self, request, pk=None):
        return self._act(request, pk, "skip")
