from django.db import models, transaction

from apps.common.models import TimeStampedModel


class Branch(TimeStampedModel):
    class Kind(models.TextChoices):
        STORE = "store", "Store"
        WAREHOUSE = "warehouse", "Warehouse"

    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=12, unique=True, help_text="Short code used in document numbers.")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.STORE)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "branches"

    def __str__(self):
        return self.name


class BusinessProfile(TimeStampedModel):
    """Singleton with business-wide configuration."""

    class Costing(models.TextChoices):
        FEFO = "fefo", "First expiry, first out"
        FIFO = "fifo", "First in, first out"

    name = models.CharField(max_length=160, default="MediPos Pharmacy")
    legal_name = models.CharField(max_length=160, blank=True)
    tax_number = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="PKR")
    timezone = models.CharField(max_length=64, default="Asia/Karachi")
    language = models.CharField(max_length=8, default="en")
    stock_issue_policy = models.CharField(max_length=4, choices=Costing.choices, default=Costing.FEFO)
    near_expiry_days = models.JSONField(default=list, help_text="Warning windows in days, e.g. [30, 60, 90].")
    prices_include_tax = models.BooleanField(default=True, help_text="Retail prices already contain sales tax (MRP).")
    receipt_footer = models.CharField(max_length=240, blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        if not self.near_expiry_days:
            self.near_expiry_days = [30, 60, 90]
        super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "BusinessProfile":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DocumentSequence(models.Model):
    """Gap-free, per-branch document numbering (invoices, GRNs, POs...)."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="sequences")
    doc_type = models.CharField(max_length=20)
    prefix = models.CharField(max_length=12, blank=True)
    next_number = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["branch", "doc_type"], name="uniq_sequence_per_branch")]


DEFAULT_PREFIXES = {
    "sale": "INV",
    "sale_return": "SRN",
    "purchase_order": "PO",
    "grn": "GRN",
    "purchase_return": "PRN",
    "requisition": "REQ",
    "adjustment": "ADJ",
    "transfer": "TRF",
}


def next_document_number(branch: Branch, doc_type: str) -> str:
    """Must be called inside a transaction; the row lock serialises concurrent callers."""
    with transaction.atomic():
        seq, _ = DocumentSequence.objects.select_for_update().get_or_create(
            branch=branch, doc_type=doc_type, defaults={"prefix": DEFAULT_PREFIXES.get(doc_type, doc_type.upper())}
        )
        number = seq.next_number
        seq.next_number = number + 1
        seq.save(update_fields=["next_number"])
    return f"{seq.prefix}-{branch.code.upper()}-{number:06d}"
