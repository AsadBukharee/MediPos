from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import ImmutableModel, TimeStampedModel

MONEY = {"max_digits": 16, "decimal_places": 2}


class Account(TimeStampedModel):
    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    code = models.CharField(max_length=12, unique=True)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=Type.choices)
    is_system = models.BooleanField(default=False, help_text="Used by automatic postings; cannot be removed.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def is_debit_normal(self) -> bool:
        return self.type in (self.Type.ASSET, self.Type.EXPENSE)


class FinancialPeriod(TimeStampedModel):
    """A closed period rejects new postings dated inside it."""

    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-start_date"]
        constraints = [models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="period_dates_ordered")]


class JournalEntry(ImmutableModel):
    """A posted, balanced entry. Mistakes are corrected with a reversal entry, never by editing."""

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="journal_entries")
    date = models.DateField(db_index=True)
    memo = models.CharField(max_length=255)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.BigIntegerField(null=True, blank=True)
    source_number = models.CharField(max_length=40, blank=True)
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "journal entries"
        indexes = [models.Index(fields=["source_type", "source_id"])]


class JournalLine(ImmutableModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(**MONEY, default=Decimal("0"))
    credit = models.DecimalField(**MONEY, default=Decimal("0"))
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(debit__gte=0) & Q(credit__gte=0), name="journal_line_not_negative"),
            models.CheckConstraint(
                condition=(Q(debit__gt=0) & Q(credit=0)) | (Q(debit=0) & Q(credit__gt=0)), name="journal_line_one_sided"),
        ]


class Expense(models.Model):
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="expenses")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+", limit_choices_to={"type": "expense"})
    amount = models.DecimalField(**MONEY)
    paid_from = models.CharField(max_length=10, default="cash")
    description = models.CharField(max_length=255)
    date = models.DateField()
    entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="expense")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="expense_positive")]
