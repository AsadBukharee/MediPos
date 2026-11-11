from django.db.models import F, Q
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.models import Barcode, Product
from apps.common.api import BranchMixin, BranchReadOnlyViewSet

from . import selectors, services
from .models import Batch, StockAdjustment, StockAdjustmentItem, StockMovement


class BatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = ["id", "product", "product_name", "batch_number", "expiry_date", "manufacturing_date",
                  "purchase_cost", "selling_price", "supplier", "grn", "quantity_on_hand", "status",
                  "status_reason", "received_at", "is_expired"]

    def get_is_expired(self, obj) -> bool:
        return obj.is_expired()


class BatchViewSet(BranchReadOnlyViewSet):
    queryset = Batch.objects.select_related("product")
    serializer_class = BatchSerializer
    read_perm = "inventory.view"
    perms = {"set_status": "inventory.adjust"}
    filterset_fields = ["product", "status"]
    search_fields = ["batch_number", "product__name"]
    ordering_fields = ["expiry_date", "received_at", "quantity_on_hand"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("in_stock") in {"1", "true"}:
            qs = qs.filter(quantity_on_hand__gt=0)
        return qs

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        batch = services.set_batch_status(
            batch_id=int(pk), branch=request.branch, status=request.data.get("status", ""),
            reason=str(request.data.get("reason", "")), user=request.user)
        return Response(BatchSerializer(batch).data)


class StockRowSerializer(serializers.ModelSerializer):
    base_unit_name = serializers.CharField(source="base_unit.name", read_only=True)
    on_hand = serializers.IntegerField(read_only=True)
    sellable = serializers.IntegerField(read_only=True)
    nearest_expiry = serializers.DateField(read_only=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "generic_name", "strength", "sku", "base_unit_name", "retail_price",
                  "reorder_level", "min_stock", "max_stock", "on_hand", "sellable", "nearest_expiry", "state"]

    def get_state(self, obj) -> str:
        if obj.sellable == 0:
            return "out"
        if obj.reorder_level and obj.sellable <= obj.reorder_level:
            return "low"
        return "ok"


class StockViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Current stock per medicine in the selected branch."""

    serializer_class = StockRowSerializer
    queryset = Product.objects.none()  # for schema generation; see get_queryset
    read_perm = "inventory.view"
    filterset_fields = ["category", "is_active"]
    ordering_fields = ["name", "sellable", "on_hand", "nearest_expiry"]
    ordering = ["name"]

    def get_queryset(self):
        qs = selectors.products_with_stock(self.request.branch).select_related("base_unit")
        params = self.request.query_params
        term = params.get("search", "").strip()
        if term:
            by_barcode = Barcode.objects.filter(code=term).values("product_id")
            qs = qs.filter(Q(name__icontains=term) | Q(generic_name__icontains=term) | Q(sku__iexact=term)
                           | Q(pk__in=by_barcode))
        state = params.get("state")
        if state == "low":
            qs = qs.filter(reorder_level__gt=0, sellable__lte=F("reorder_level"), sellable__gt=0)
        elif state == "out":
            qs = qs.filter(sellable=0)
        elif state == "in":
            qs = qs.filter(sellable__gt=0)
        return qs

    @action(detail=True, methods=["get"])
    def batches(self, request, pk=None):
        batches = Batch.objects.filter(branch=request.branch, product_id=pk, quantity_on_hand__gt=0).select_related("product")
        return Response(BatchSerializer(batches, many=True).data)


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_name", "batch", "batch_number", "movement_type", "quantity",
                  "balance_after", "unit_cost", "source_type", "source_id", "source_number", "note",
                  "user", "user_name", "created_at"]


class StockMovementViewSet(BranchReadOnlyViewSet):
    """The stock ledger (read-only by design)."""

    queryset = StockMovement.objects.select_related("product", "batch", "user")
    serializer_class = StockMovementSerializer
    read_perm = "inventory.view"
    filterset_fields = {"product": ["exact"], "batch": ["exact"], "movement_type": ["exact"],
                        "created_at": ["date__gte", "date__lte"]}


class AdjustmentItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False)

    class Meta:
        model = StockAdjustmentItem
        fields = ["id", "product", "product_name", "batch", "batch_number", "expiry_date", "unit_cost", "quantity_delta"]


class AdjustmentSerializer(serializers.ModelSerializer):
    items = AdjustmentItemSerializer(many=True)
    requested_by_name = serializers.CharField(source="requested_by.username", read_only=True)

    class Meta:
        model = StockAdjustment
        fields = ["id", "number", "reason", "note", "status", "requested_by", "requested_by_name",
                  "decided_by", "decided_at", "created_at", "items"]
        read_only_fields = ["number", "status", "requested_by", "decided_by", "decided_at"]


class AdjustmentViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                        viewsets.GenericViewSet):
    queryset = StockAdjustment.objects.prefetch_related("items__product").select_related("requested_by")
    serializer_class = AdjustmentSerializer
    read_perm = "inventory.view"
    write_perm = "inventory.adjust"
    perms = {"approve": "inventory.adjust.approve", "reject": "inventory.adjust.approve"}
    filterset_fields = ["status", "reason"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        adjustment = services.request_adjustment(
            branch=request.branch, user=request.user, reason=data["reason"], note=data.get("note", ""), items=data["items"])
        return Response(self.get_serializer(adjustment).data, status=status.HTTP_201_CREATED)

    def _decide(self, request, pk, approve):
        adjustment = services.decide_adjustment(adjustment_id=int(pk), branch=request.branch, user=request.user, approve=approve)
        return Response(self.get_serializer(self.get_queryset().get(pk=adjustment.pk)).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, pk, True)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, pk, False)
