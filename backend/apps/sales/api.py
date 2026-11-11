from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.services import log_action
from apps.catalog.models import Product, ProductPackaging
from apps.common.api import BranchMixin
from apps.common.exceptions import BusinessError
from apps.common.uploads import validate_upload
from apps.customers.models import Customer
from apps.inventory.models import Batch
from apps.inventory.selectors import sellable_quantity

from . import services
from .models import Sale, SaleItem, SaleItemBatch, SalePayment, SaleReturn, SaleReturnItem, Shift


# --- Input ----------------------------------------------------------------------------------

class SaleItemInput(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.select_related("base_unit"))
    packaging = serializers.PrimaryKeyRelatedField(
        queryset=ProductPackaging.objects.select_related("unit"), required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=0)
    batch = serializers.PrimaryKeyRelatedField(queryset=Batch.objects.all(), required=False, allow_null=True)


class PaymentInput(serializers.Serializer):
    method = serializers.ChoiceField(choices=SalePayment.Method.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)


class SaleInput(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.filter(is_active=True), required=False, allow_null=True)
    items = SaleItemInput(many=True)
    payments = PaymentInput(many=True, required=False)
    invoice_discount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=0)
    prescription_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    hold = serializers.BooleanField(required=False, default=False)


class CompleteInput(serializers.Serializer):
    payments = PaymentInput(many=True)
    prescription_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)


# --- Output ---------------------------------------------------------------------------------

class AllocationSerializer(serializers.ModelSerializer):
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    expiry_date = serializers.DateField(source="batch.expiry_date", read_only=True)

    class Meta:
        model = SaleItemBatch
        fields = ["batch", "batch_number", "expiry_date", "quantity", "returned_quantity"]


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    packaging_name = serializers.CharField(source="packaging.unit.name", read_only=True)
    allocations = AllocationSerializer(many=True, read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "packaging", "packaging_name", "quantity", "quantity_base",
                  "unit_price", "discount_amount", "tax_rate", "tax_amount", "line_total", "returned_base",
                  "refunded_amount", "allocations"]


class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment
        fields = ["method", "amount", "reference"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    cashier_name = serializers.CharField(source="cashier.username", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Sale
        fields = ["id", "number", "status", "branch", "branch_name", "customer", "customer_name", "cashier",
                  "cashier_name", "shift", "subtotal", "discount_total", "invoice_discount", "tax_total", "total",
                  "paid_total", "change_due", "prescription_reference", "prescription_file", "note",
                  "created_at", "completed_at", "cancelled_at", "cancel_reason", "items", "payments"]


class SaleListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    cashier_name = serializers.CharField(source="cashier.username", read_only=True)

    class Meta:
        model = Sale
        fields = ["id", "number", "status", "customer_name", "cashier_name", "total", "paid_total", "created_at", "completed_at"]


class SaleViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Sale.objects.select_related("customer", "cashier", "branch")
    read_perm = "sales.view"
    write_perm = "sales.create"
    perms = {"cancel": "sales.cancel"}
    filterset_fields = {"status": ["exact"], "customer": ["exact"], "cashier": ["exact"],
                        "completed_at": ["date__gte", "date__lte"]}
    search_fields = ["number", "customer__name", "customer__phone"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        return SaleListSerializer if self.action == "list" else SaleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action != "list":
            qs = qs.prefetch_related("items__product", "items__packaging__unit", "items__allocations__batch", "payments")
        return qs

    def respond(self, sale, code=status.HTTP_200_OK):
        self.action = "retrieve"
        return Response(SaleSerializer(self.get_queryset().get(pk=sale.pk), context=self.get_serializer_context()).data, status=code)

    def create(self, request):
        """Complete a sale (or hold it with hold=true). Send an Idempotency-Key header so retries are safe."""
        serializer = SaleInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        sale = services.create_sale(
            branch=request.branch, user=request.user, items=d["items"], payments=d.get("payments", []),
            customer=d.get("customer"), invoice_discount=d.get("invoice_discount", 0),
            prescription_reference=d.get("prescription_reference", ""), note=d.get("note", ""),
            hold=d.get("hold", False), idempotency_key=request.headers.get("Idempotency-Key"))
        return self.respond(sale, status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def quote(self, request):
        """Price a cart without saving anything. The POS shows these numbers, never its own maths."""
        serializer = SaleInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        lines, totals = services.price_lines(branch=request.branch, user=request.user, customer=d.get("customer"),
                                             items=d["items"], invoice_discount=d.get("invoice_discount", 0))
        return Response({
            **{k: str(v) for k, v in totals.items()},
            "requires_prescription": any(l.product.requires_prescription for l in lines),
            "items": [{
                "product": l.product.pk, "product_name": str(l.product), "packaging": l.packaging.pk,
                "packaging_name": l.packaging.unit.name, "quantity": l.quantity, "quantity_base": l.quantity_base,
                "unit_price": str(l.unit_price), "discount_amount": str(l.discount), "tax_amount": str(l.tax_amount),
                "line_total": str(l.line_total), "available_base": sellable_quantity(request.branch, l.product),
            } for l in lines],
        })

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        serializer = CompleteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        return self.respond(services.complete_held_sale(
            sale_id=pk, branch=request.branch, user=request.user, payments=d["payments"],
            prescription_reference=d.get("prescription_reference", "")))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Reverse a completed invoice (stock and accounts). Needs the sales.cancel permission."""
        return self.respond(services.cancel_sale(sale_id=pk, branch=request.branch, user=request.user,
                                                 reason=str(request.data.get("reason", ""))))

    @action(detail=True, methods=["post"], url_path="discard")
    def discard(self, request, pk=None):
        """Drop a held invoice (no stock or accounts were touched)."""
        sale = Sale.objects.filter(pk=pk, branch=request.branch).first()
        if sale is None or sale.status != Sale.Status.HELD:
            raise BusinessError("Only held invoices can be discarded.", code="bad_status")
        return self.respond(services.cancel_sale(sale_id=pk, branch=request.branch, user=request.user, reason="Held invoice discarded"))

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def prescription(self, request, pk=None):
        sale = self.get_object()
        upload = validate_upload(request.FILES.get("file"))
        if upload is None:
            raise serializers.ValidationError({"file": "Attach the prescription image or PDF."})
        sale.prescription_file = upload
        sale.save(update_fields=["prescription_file", "updated_at"])
        log_action(user=request.user, action="sale.prescription", obj=sale, request=request)
        return self.respond(sale)


# --- Returns --------------------------------------------------------------------------------

class SaleReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="sale_item.product.__str__", read_only=True)

    class Meta:
        model = SaleReturnItem
        fields = ["id", "sale_item", "product_name", "quantity_base", "restock", "amount"]
        read_only_fields = ["amount"]


class SaleReturnSerializer(serializers.ModelSerializer):
    items = SaleReturnItemSerializer(many=True)
    sale_number = serializers.CharField(source="sale.number", read_only=True)

    class Meta:
        model = SaleReturn
        fields = ["id", "number", "sale", "sale_number", "reason", "refund_method", "total", "tax_total",
                  "created_by", "created_at", "items"]
        read_only_fields = ["number", "total", "tax_total", "created_by"]


class SaleReturnViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = SaleReturn.objects.select_related("sale").prefetch_related("items__sale_item__product")
    serializer_class = SaleReturnSerializer
    read_perm = "sales.view"
    write_perm = "sales.return"
    filterset_fields = ["sale"]

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        sale_return = services.create_sale_return(
            branch=request.branch, user=request.user, sale_id=d["sale"].pk, items=d["items"], reason=d["reason"],
            refund_method=d.get("refund_method", "cash"), idempotency_key=request.headers.get("Idempotency-Key"))
        return Response(self.get_serializer(self.get_queryset().get(pk=sale_return.pk)).data, status=status.HTTP_201_CREATED)


# --- Shifts ---------------------------------------------------------------------------------

CASH_FIELD = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class ShiftSerializer(serializers.ModelSerializer):
    cashier_name = serializers.CharField(source="cashier.username", read_only=True)
    running_cash = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = ["id", "cashier", "cashier_name", "status", "opening_cash", "opened_at", "expected_cash",
                  "closing_cash", "closed_at", "note", "running_cash"]

    def get_running_cash(self, obj) -> str:
        return str(services.shift_expected_cash(obj))


class ShiftViewSet(BranchMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Shift.objects.select_related("cashier")
    serializer_class = ShiftSerializer
    read_perm = "sales.view"
    write_perm = "sales.create"
    filterset_fields = ["status", "cashier"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.has_perm_code("sales.cancel"):  # cashiers only see their own shifts
            qs = qs.filter(cashier=self.request.user)
        return qs

    @action(detail=False, methods=["get"])
    def current(self, request):
        shift = services.current_shift(request.branch, request.user)
        return Response(self.get_serializer(shift).data if shift else None)

    @action(detail=False, methods=["post"])
    def open(self, request):
        shift = services.open_shift(branch=request.branch, user=request.user,
                                    opening_cash=CASH_FIELD.run_validation(request.data.get("opening_cash", 0)))
        return Response(self.get_serializer(shift).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        if request.data.get("closing_cash") in (None, ""):
            raise serializers.ValidationError({"closing_cash": "Enter the cash you counted."})
        shift = services.close_shift(shift_id=pk, branch=request.branch, user=request.user,
                                     closing_cash=CASH_FIELD.run_validation(request.data["closing_cash"]),
                                     note=str(request.data.get("note", "")))
        return Response(self.get_serializer(shift).data)
