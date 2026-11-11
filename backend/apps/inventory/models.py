from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common.models import ImmutableModel, TimeStampedModel

COST = {"max_digits": 16, "decimal_places": 6}


class Batch(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        BLOCKED = "blocked", "Blocked"
        QUARANTINED = "quarantined", "Quarantined"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="batches")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=60)
    expiry_date = models.DateField()
    manufacturing_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(**COST, help_text="Actual cost per base unit.")
    selling_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                        help_text="Per base unit. Falls back to the product price when empty.")
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    grn = models.ForeignKey("purchases.GoodsReceivedNote", null=True, blank=True, on_delete=models.PROTECT, related_name="batches")
    quantity_on_hand = models.BigIntegerField(default=0, help_text="Whole base units.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    status_reason = models.CharField(max_length=255, blank=True)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["expiry_date", "received_at", "id"]
        verbose_name_plural = "batches"
        constraints = [
            # The database itself refuses negative stock, whatever the application does.
            models.CheckConstraint(condition=Q(quantity_on_hand__gte=0), name="batch_quantity_not_negative"),
            models.UniqueConstraint(
                fields=["branch", "product", "batch_number", "expiry_date", "purchase_cost"], name="uniq_batch_lot"),
        ]
        indexes = [
            models.Index(fields=["branch", "product", "expiry_date"]),
            models.Index(fields=["branch", "expiry_date"]),
        ]

    def __str__(self):
        return f"{self.product} / {self.batch_number}"

    def is_expired(self, on_date=None) -> bool:
        return self.expiry_date <= (on_date or timezone.localdate())


class StockMovement(ImmutableModel):
    """The stock ledger. Append-only: corrections are new rows, never edits."""

    class Type(models.TextChoices):
        OPENING = "opening", "Opening stock"
        PURCHASE_RECEIPT = "purchase_receipt", "Goods received"
        PURCHASE_RETURN = "purchase_return", "Returned to supplier"
        SALE = "sale", "Sale"
        SALE_RETURN = "sale_return", "Customer return"
        SALE_CANCEL = "sale_cancel", "Sale cancelled"
        ADJUSTMENT = "adjustment", "Stock adjustment"
        TRANSFER_OUT = "transfer_out", "Transfer out"
        TRANSFER_IN = "transfer_in", "Transfer in"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="movements")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    quantity = models.BigIntegerField(help_text="Signed base units: positive in, negative out.")
    balance_after = models.BigIntegerField(help_text="Batch quantity after this movement.")
    unit_cost = models.DecimalField(**COST)
    source_type = models.CharField(max_length=40, help_text="Document kind that caused the movement.")
    source_id = models.BigIntegerField(null=True, blank=True)
    source_number = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=~Q(quantity=0), name="movement_quantity_nonzero")]
        indexes = [
            models.Index(fields=["branch", "product", "created_at"]),
            models.Index(fields=["source_type", "source_id"]),
        ]

    @property
    def value(self) -> Decimal:
        return self.quantity * self.unit_cost


class StockAdjustment(TimeStampedModel):
    class Reason(models.TextChoices):
        OPENING = "opening", "Opening stock"
        DAMAGED = "damaged", "Damaged"
        LOST = "lost", "Lost"
        EXPIRED = "expired", "Expired write-off"
        COUNT = "count", "Physical count correction"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="adjustments")
    number = models.CharField(max_length=40, unique=True)
    reason = models.CharField(max_length=12, choices=Reason.choices)
    note = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class StockAdjustmentItem(models.Model):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    # Either an existing batch, or the details of a batch to create (opening stock / found stock).
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    batch_number = models.CharField(max_length=60, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    unit_cost = models.DecimalField(**COST, null=True, blank=True)
    quantity_delta = models.BigIntegerField(help_text="Signed base units.")

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(quantity_delta=0), name="adjustment_delta_nonzero")]
