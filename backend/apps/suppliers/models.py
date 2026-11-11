from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel

MONEY = {"max_digits": 14, "decimal_places": 2}


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)
    contact_person = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    tax_number = models.CharField(max_length=60, blank=True)
    opening_balance = models.DecimalField(**MONEY, default=Decimal("0"), help_text="Amount owed to the supplier at go-live.")
    payment_terms_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupplierProduct(TimeStampedModel):
    """Supplier-wise product pricing, used for price comparison and PO defaults."""

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="products")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="supplier_prices")
    packaging = models.ForeignKey("catalog.ProductPackaging", null=True, blank=True, on_delete=models.SET_NULL)
    price = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    supplier_sku = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["supplier", "product"], name="uniq_supplier_product")]


class SupplierPayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        CARD = "card", "Card"
        WALLET = "wallet", "Mobile wallet"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=255, blank=True)
    grn = models.ForeignKey("purchases.GoodsReceivedNote", null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    idempotency_key = models.CharField(max_length=80, null=True, blank=True, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=~Q(amount=0), name="supplier_payment_nonzero")]
