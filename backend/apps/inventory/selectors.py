"""Read-side queries for stock. Complex reads live here, not in views."""
from datetime import timedelta

from django.db.models import DecimalField, ExpressionWrapper, F, IntegerField, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.catalog.models import Product

from .models import Batch


def _sum(expression, **kwargs):
    return Coalesce(Sum(expression, **kwargs), Value(0), output_field=IntegerField())


def products_with_stock(branch, on_date=None):
    """Products annotated with on-hand and sellable quantities for one branch."""
    today = on_date or timezone.localdate()
    in_branch = Q(batches__branch=branch)
    sellable = in_branch & Q(batches__status=Batch.Status.ACTIVE, batches__expiry_date__gt=today)
    return Product.objects.annotate(
        on_hand=_sum("batches__quantity_on_hand", filter=in_branch),
        sellable=_sum("batches__quantity_on_hand", filter=sellable),
        nearest_expiry=Min("batches__expiry_date", filter=sellable & Q(batches__quantity_on_hand__gt=0)),
    )


def sellable_quantity(branch, product) -> int:
    today = timezone.localdate()
    return Batch.objects.filter(
        branch=branch, product=product, status=Batch.Status.ACTIVE, expiry_date__gt=today
    ).aggregate(total=_sum("quantity_on_hand"))["total"]


def low_stock(branch):
    return products_with_stock(branch).filter(is_active=True, reorder_level__gt=0, sellable__lte=F("reorder_level"))


def out_of_stock(branch):
    return products_with_stock(branch).filter(is_active=True, sellable=0)


def near_expiry(branch, days: int):
    today = timezone.localdate()
    return Batch.objects.filter(
        branch=branch, quantity_on_hand__gt=0, expiry_date__gt=today, expiry_date__lte=today + timedelta(days=days)
    ).select_related("product")


def expired(branch):
    return Batch.objects.filter(
        branch=branch, quantity_on_hand__gt=0, expiry_date__lte=timezone.localdate()).select_related("product")


def stock_value(branch):
    """Stock valued at actual batch cost."""
    value = ExpressionWrapper(F("quantity_on_hand") * F("purchase_cost"), output_field=DecimalField(max_digits=20, decimal_places=6))
    return Batch.objects.filter(branch=branch).aggregate(
        total=Coalesce(Sum(value), Value(0), output_field=DecimalField(max_digits=20, decimal_places=6)))["total"]
