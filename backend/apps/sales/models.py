from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel

MONEY = {"max_digits": 14, "decimal_places": 2}
COST = {"max_digits": 16, "decimal_places": 6}
ZERO = Decimal("0")


class Shift(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="shifts")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    opening_cash = models.DecimalField(**MONEY, default=ZERO)
    opened_at = models.DateTimeField(auto_now_add=True)
    expected_cash = models.DecimalField(**MONEY, null=True, blank=True)
    closing_cash = models.DecimalField(**MONEY, null=True, blank=True, help_text="Cash counted at close.")
    closed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "cashier"], condition=Q(status="open"), name="one_open_shift_per_cashier"),
        ]


class Sale(TimeStampedModel):
    class Status(models.TextChoices):
        HELD = "held", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="sales")
    number = models.CharField(max_length=40, unique=True, null=True, blank=True,
                              help_text="Assigned when the invoice is completed, so numbering has no gaps.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HELD, db_index=True)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.PROTECT, related_name="sales")

    subtotal = models.DecimalField(**MONEY, default=ZERO)
    discount_total = models.DecimalField(**MONEY, default=ZERO)
    invoice_discount = models.DecimalField(**MONEY, default=ZERO)
    tax_total = models.DecimalField(**MONEY, default=ZERO)
    total = models.DecimalField(**MONEY, default=ZERO)
    paid_total = models.DecimalField(**MONEY, default=ZERO)
    change_due = models.DecimalField(**MONEY, default=ZERO)
    cost_total = models.DecimalField(**COST, default=ZERO, help_text="Actual batch cost of everything sold.")

    prescription_reference = models.CharField(max_length=120, blank=True)
    prescription_file = models.FileField(upload_to="prescriptions/%Y/%m/", null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=80, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "idempotency_key"], condition=Q(idempotency_key__isnull=False),
                                    name="uniq_sale_idempotency_key"),
        ]
        indexes = [models.Index(fields=["branch", "status", "completed_at"])]


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="sale_items")
    packaging = models.ForeignKey("catalog.ProductPackaging", on_delete=models.PROTECT, related_name="+")
    requested_batch = models.ForeignKey("inventory.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(help_text="Quantity in the chosen packaging.")
    quantity_base = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4, help_text="Price per pack.")
    discount_amount = models.DecimalField(**MONEY, default=ZERO, help_text="Line discount plus this line's share of the invoice discount.")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    tax_amount = models.DecimalField(**MONEY, default=ZERO)
    line_total = models.DecimalField(**MONEY, default=ZERO, help_text="What the customer pays for this line.")
    cost_total = models.DecimalField(**COST, default=ZERO)
    returned_base = models.PositiveIntegerField(default=0)
    refunded_amount = models.DecimalField(**MONEY, default=ZERO)
    refunded_tax = models.DecimalField(**MONEY, default=ZERO)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(returned_base__lte=models.F("quantity_base")), name="sale_item_return_within_sold")]


class SaleItemBatch(models.Model):
    """Which batches a line was served from, at their actual cost."""

    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, related_name="allocations")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="sale_allocations")
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(**COST)
    returned_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]


class SalePayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        BANK = "bank", "Bank transfer"
        WALLET = "wallet", "Mobile wallet"
        CREDIT = "credit", "Customer credit"

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(**MONEY)
    reference = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="sale_payment_positive")]


class SaleReturn(TimeStampedModel):
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="sale_returns")
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="returns")
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.PROTECT, related_name="returns")
    number = models.CharField(max_length=40, unique=True)
    reason = models.CharField(max_length=255)
    refund_method = models.CharField(max_length=10, choices=SalePayment.Method.choices, default=SalePayment.Method.CASH)
    total = models.DecimalField(**MONEY, default=ZERO)
    tax_total = models.DecimalField(**MONEY, default=ZERO)
    idempotency_key = models.CharField(max_length=80, null=True, blank=True, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name="items")
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name="return_items")
    quantity_base = models.PositiveIntegerField()
    restock = models.BooleanField(default=True, help_text="False when the goods are damaged and must not go back on the shelf.")
    amount = models.DecimalField(**MONEY)
