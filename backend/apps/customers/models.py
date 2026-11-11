from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel

MONEY = {"max_digits": 14, "decimal_places": 2}


class Customer(TimeStampedModel):
    class Tier(models.TextChoices):
        RETAIL = "retail", "Retail"
        WHOLESALE = "wholesale", "Wholesale"

    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    price_tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.RETAIL)
    credit_limit = models.DecimalField(**MONEY, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    loyalty_points = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomerPayment(models.Model):
    """Money received against a customer's credit balance."""

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY)
    method = models.CharField(max_length=10, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    idempotency_key = models.CharField(max_length=80, null=True, blank=True, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="customer_payment_positive")]
