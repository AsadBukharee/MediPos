from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.api import BranchMixin, MasterDataViewSet

from . import services
from .models import Supplier, SupplierPayment, SupplierProduct


class SupplierSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_person", "phone", "email", "address", "tax_number", "opening_balance",
                  "payment_terms_days", "is_active", "balance"]

    def get_balance(self, obj) -> str:
        return str(services.supplier_balance(obj, self.context["request"].user.accessible_branches()))


class SupplierViewSet(MasterDataViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    read_perm = "suppliers.view"
    write_perm = "suppliers.manage"
    search_fields = ["name", "contact_person", "phone"]
    filterset_fields = ["is_active"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        return Response(services.supplier_ledger(self.get_object(), request.user.accessible_branches()))


class SupplierProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = SupplierProduct
        fields = ["id", "supplier", "supplier_name", "product", "product_name", "packaging", "price", "supplier_sku"]

    def validate(self, attrs):
        packaging, product = attrs.get("packaging"), attrs.get("product")
        if packaging and product and packaging.product_id != product.pk:
            raise serializers.ValidationError({"packaging": "Packaging belongs to another product."})
        return attrs


class SupplierProductViewSet(MasterDataViewSet):
    """Supplier-wise prices; filter by product to compare suppliers."""

    queryset = SupplierProduct.objects.select_related("supplier", "product").order_by("supplier__name", "id")
    serializer_class = SupplierProductSerializer
    read_perm = "suppliers.view"
    write_perm = "suppliers.manage"
    filterset_fields = ["supplier", "product"]


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = SupplierPayment
        fields = ["id", "supplier", "supplier_name", "amount", "method", "reference", "note", "grn", "created_by", "created_at"]
        read_only_fields = ["created_by"]


class SupplierPaymentViewSet(BranchMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = SupplierPayment.objects.select_related("supplier")
    serializer_class = SupplierPaymentSerializer
    read_perm = "suppliers.view"
    write_perm = "suppliers.pay"
    filterset_fields = ["supplier", "method"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.pay_supplier(
            branch=request.branch, user=request.user, idempotency_key=request.headers.get("Idempotency-Key"),
            **serializer.validated_data)
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)
