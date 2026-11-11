from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel

MONEY = {"max_digits": 14, "decimal_places": 2}
PRICE = {"max_digits": 14, "decimal_places": 4}
non_negative = [MinValueValidator(Decimal("0"))]


class PurchaseRequisition(TimeStampedModel):
    """The branch "order list". Low-stock alerts and staff add lines; a manager approves and converts it to POs."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Open order list"
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ORDERED = "ordered", "Ordered"
        PARTIALLY_RECEIVED = "partially_received", "Partially received"
        FULFILLED = "fulfilled", "Fulfilled"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="requisitions")
    number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["branch"], condition=Q(status="draft"), name="one_open_order_list_per_branch"),
        ]


class RequisitionItem(TimeStampedModel):
    requisition = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(help_text="Requested quantity in base units.")
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    po_item = models.ForeignKey("PurchaseOrderItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="requisition_items")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["requisition", "product"], name="uniq_requisition_product"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="requisition_quantity_positive"),
        ]


class PurchaseOrder(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        ORDERED = "ordered", "Sent to supplier"
        PARTIALLY_RECEIVED = "partially_received", "Partially received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    OPEN_STATUSES = (Status.APPROVED, Status.ORDERED, Status.PARTIALLY_RECEIVED)

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="purchase_orders")
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="purchase_orders")
    number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    expected_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total(self) -> Decimal:
        return sum((item.quantity * item.unit_price for item in self.items.all()), Decimal("0"))


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    packaging = models.ForeignKey("catalog.ProductPackaging", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(help_text="Ordered quantity in the chosen packaging.")
    unit_price = models.DecimalField(**PRICE, validators=non_negative, help_text="Price per pack.")
    received_base = models.PositiveBigIntegerField(default=0, help_text="Base units received so far.")

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="po_item_quantity_positive")]

    @property
    def ordered_base(self) -> int:
        return self.quantity * self.packaging.factor

    @property
    def outstanding_base(self) -> int:
        return max(self.ordered_base - self.received_base, 0)


class GoodsReceivedNote(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="grns")
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="grns")
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="grns")
    number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    supplier_invoice_number = models.CharField(max_length=60, blank=True)
    supplier_invoice_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "goods received note"


class GRNItem(models.Model):
    grn = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name="items")
    po_item = models.ForeignKey(PurchaseOrderItem, null=True, blank=True, on_delete=models.PROTECT, related_name="grn_items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    packaging = models.ForeignKey("catalog.ProductPackaging", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(help_text="Good packs received (added to stock).")
    damaged_quantity = models.PositiveIntegerField(default=0, help_text="Packs delivered damaged (not added to stock, not billed).")
    unit_cost = models.DecimalField(**PRICE, validators=non_negative, help_text="Cost per pack.")
    batch_number = models.CharField(max_length=60)
    expiry_date = models.DateField()
    manufacturing_date = models.DateField(null=True, blank=True)
    selling_price = models.DecimalField(**PRICE, null=True, blank=True, validators=non_negative,
                                        help_text="Optional batch selling price per base unit.")
    batch = models.ForeignKey("inventory.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="grn_items")

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="grn_item_quantity_positive")]


class PurchaseReturn(TimeStampedModel):
    """Stock sent back to a supplier (acts as a debit note)."""

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="purchase_returns")
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="purchase_returns")
    grn = models.ForeignKey(GoodsReceivedNote, null=True, blank=True, on_delete=models.PROTECT, related_name="returns")
    number = models.CharField(max_length=40, unique=True)
    reason = models.CharField(max_length=255)
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class PurchaseReturnItem(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="items")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(help_text="Base units returned.")
    unit_cost = models.DecimalField(max_digits=16, decimal_places=6)
