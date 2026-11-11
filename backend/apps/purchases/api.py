from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.models import Product
from apps.common.api import BranchMixin
from apps.common.exceptions import BusinessError
from apps.suppliers.models import Supplier

from . import services
from .models import (GoodsReceivedNote, GRNItem, PurchaseOrder, PurchaseOrderItem, PurchaseRequisition,
                     PurchaseReturn, PurchaseReturnItem, RequisitionItem)


class DocumentViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """List/retrieve plus explicit service-backed actions. No generic update or delete."""

    read_perm = "purchases.view"

    def respond(self, instance, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=instance.pk)).data, status=code)


# --- Requisitions / order list ----------------------------------------------------------------

class RequisitionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")
    requested_by_name = serializers.CharField(source="requested_by.username", read_only=True)

    class Meta:
        model = RequisitionItem
        fields = ["id", "product", "product_name", "quantity", "supplier", "supplier_name", "requested_by_name",
                  "po_item", "note"]
        read_only_fields = ["po_item"]


class RequisitionSerializer(serializers.ModelSerializer):
    items = RequisitionItemSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = ["id", "number", "status", "note", "created_by", "decided_by", "decided_at", "created_at", "items"]


class RequisitionViewSet(DocumentViewSet):
    queryset = PurchaseRequisition.objects.prefetch_related("items__product", "items__supplier", "items__requested_by")
    serializer_class = RequisitionSerializer
    perms = {
        "add_item": "requisitions.manage", "update_item": "requisitions.manage", "remove_item": "requisitions.manage",
        "submit": "requisitions.manage", "approve": "purchases.approve", "reject": "purchases.approve",
        "convert": "purchases.approve",
    }
    filterset_fields = ["status"]

    @action(detail=False, methods=["get"])
    def current(self, request):
        """The branch's open order list (may be empty)."""
        requisition = self.get_queryset().filter(status="draft").first()
        return Response(self.get_serializer(requisition).data if requisition else {"id": None, "status": "draft", "items": []})

    @action(detail=False, methods=["post"], url_path="items")
    def add_item(self, request):
        serializer = RequisitionItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        item = services.add_to_order_list(branch=request.branch, product=d["product"], quantity=d["quantity"],
                                          user=request.user, supplier=d.get("supplier"), note=d.get("note", ""))
        return Response(RequisitionItemSerializer(item).data, status=status.HTTP_201_CREATED)

    def _editable_item(self, request, item_id) -> RequisitionItem:
        item = RequisitionItem.objects.select_related("requisition").filter(
            pk=item_id, requisition__branch=request.branch).first()
        if item is None:
            raise serializers.ValidationError("Order list line not found.")
        if item.requisition.status not in ("draft", "pending"):
            raise BusinessError("This requisition can no longer be edited.", code="bad_status")
        return item

    @action(detail=False, methods=["patch"], url_path=r"items/(?P<item_id>\d+)")
    def update_item(self, request, item_id=None):
        item = self._editable_item(request, item_id)
        serializer = RequisitionItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("product", None)
        serializer.save()
        return Response(serializer.data)

    @update_item.mapping.delete
    def remove_item(self, request, item_id=None):
        self._editable_item(request, item_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self.respond(services.submit_requisition(requisition_id=pk, branch=request.branch, user=request.user))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.respond(services.decide_requisition(requisition_id=pk, branch=request.branch, user=request.user, approve=True))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.respond(services.decide_requisition(requisition_id=pk, branch=request.branch, user=request.user, approve=False))

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        orders = services.convert_requisition(requisition_id=pk, branch=request.branch, user=request.user)
        return Response({"purchase_orders": [{"id": o.pk, "number": o.number, "supplier": o.supplier.name} for o in orders]})


# --- Purchase orders ------------------------------------------------------------------------

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    packaging_name = serializers.CharField(source="packaging.unit.name", read_only=True)
    packaging_factor = serializers.IntegerField(source="packaging.factor", read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "product", "product_name", "packaging", "packaging_name", "packaging_factor", "quantity",
                  "unit_price", "received_base"]
        read_only_fields = ["received_base"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "number", "supplier", "supplier_name", "status", "expected_date", "note", "total",
                  "created_by", "approved_by", "approved_at", "created_at", "items"]
        read_only_fields = ["number", "status", "created_by", "approved_by", "approved_at"]


class PurchaseOrderViewSet(DocumentViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items__product", "items__packaging__unit")
    serializer_class = PurchaseOrderSerializer
    write_perm = "purchases.manage"
    perms = {"approve": "purchases.approve"}
    filterset_fields = ["status", "supplier"]
    search_fields = ["number", "supplier__name"]

    def _save(self, request, order=None):
        serializer = self.get_serializer(order, data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        return services.save_purchase_order(
            branch=request.branch, user=request.user, supplier=d["supplier"], items=d["items"],
            expected_date=d.get("expected_date"), note=d.get("note", ""), order=order)

    def create(self, request):
        return self.respond(self._save(request), status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        return self.respond(self._save(request, self.get_object()))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.respond(services.transition_purchase_order(order_id=pk, branch=request.branch, user=request.user, action="approve"))

    @action(detail=True, methods=["post"], url_path="mark-ordered")
    def mark_ordered(self, request, pk=None):
        return self.respond(services.transition_purchase_order(order_id=pk, branch=request.branch, user=request.user, action="mark_ordered"))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self.respond(services.transition_purchase_order(order_id=pk, branch=request.branch, user=request.user, action="cancel"))


# --- Goods received notes -------------------------------------------------------------------

class GRNItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    packaging_name = serializers.CharField(source="packaging.unit.name", read_only=True)

    class Meta:
        model = GRNItem
        fields = ["id", "po_item", "product", "product_name", "packaging", "packaging_name", "quantity",
                  "damaged_quantity", "unit_cost", "batch_number", "expiry_date", "manufacturing_date",
                  "selling_price", "batch"]
        read_only_fields = ["batch"]


class GRNSerializer(serializers.ModelSerializer):
    items = GRNItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = GoodsReceivedNote
        fields = ["id", "number", "supplier", "supplier_name", "purchase_order", "status", "supplier_invoice_number",
                  "supplier_invoice_date", "note", "total", "created_by", "confirmed_by", "confirmed_at", "created_at", "items"]
        read_only_fields = ["number", "status", "total", "created_by", "confirmed_by", "confirmed_at"]


class GRNViewSet(DocumentViewSet):
    queryset = GoodsReceivedNote.objects.select_related("supplier").prefetch_related("items__product", "items__packaging__unit")
    serializer_class = GRNSerializer
    write_perm = "purchases.receive"
    filterset_fields = ["status", "supplier", "purchase_order"]
    search_fields = ["number", "supplier_invoice_number", "supplier__name"]

    def _save(self, request, grn=None):
        serializer = self.get_serializer(grn, data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        return services.save_grn(
            branch=request.branch, user=request.user, supplier=d["supplier"], items=d["items"],
            purchase_order=d.get("purchase_order"), supplier_invoice_number=d.get("supplier_invoice_number", ""),
            supplier_invoice_date=d.get("supplier_invoice_date"), note=d.get("note", ""), grn=grn)

    def create(self, request):
        return self.respond(self._save(request), status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        return self.respond(self._save(request, self.get_object()))

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self.respond(services.confirm_grn(grn_id=pk, branch=request.branch, user=request.user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self.respond(services.cancel_grn(grn_id=pk, branch=request.branch, user=request.user))


# --- Supplier returns -----------------------------------------------------------------------

class PurchaseReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="batch.product.__str__", read_only=True)

    class Meta:
        model = PurchaseReturnItem
        fields = ["id", "batch", "product_name", "quantity", "unit_cost"]
        read_only_fields = ["unit_cost"]


class PurchaseReturnSerializer(serializers.ModelSerializer):
    items = PurchaseReturnItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = ["id", "number", "supplier", "supplier_name", "grn", "reason", "total", "created_by", "created_at", "items"]
        read_only_fields = ["number", "total", "created_by"]


class PurchaseReturnViewSet(DocumentViewSet):
    queryset = PurchaseReturn.objects.select_related("supplier").prefetch_related("items__batch__product")
    serializer_class = PurchaseReturnSerializer
    write_perm = "purchases.manage"
    filterset_fields = ["supplier"]

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        purchase_return = services.create_purchase_return(
            branch=request.branch, user=request.user, supplier=d["supplier"], reason=d["reason"], items=d["items"],
            grn=d.get("grn"))
        return self.respond(purchase_return, status.HTTP_201_CREATED)
