from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response

from apps.common.api import BranchMixin, MasterDataViewSet

from . import services
from .models import Customer, CustomerPayment


class CustomerSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email", "address", "price_tier", "credit_limit", "loyalty_points",
                  "is_active", "balance"]
        read_only_fields = ["loyalty_points"]

    def get_balance(self, obj) -> str:
        return str(services.customer_balance(obj))


class CustomerViewSet(MasterDataViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    read_perm = "customers.view"
    write_perm = "customers.manage"
    search_fields = ["name", "phone"]
    filterset_fields = ["is_active", "price_tier"]
    http_method_names = ["get", "post", "patch", "head", "options"]


class CustomerPaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = CustomerPayment
        fields = ["id", "customer", "customer_name", "amount", "method", "reference", "created_by", "created_at"]
        read_only_fields = ["created_by"]


class CustomerPaymentViewSet(BranchMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = CustomerPayment.objects.select_related("customer")
    serializer_class = CustomerPaymentSerializer
    read_perm = "customers.view"
    write_perm = "customers.manage"
    filterset_fields = ["customer"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.receive_customer_payment(
            branch=request.branch, user=request.user, idempotency_key=request.headers.get("Idempotency-Key"),
            **serializer.validated_data)
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)
