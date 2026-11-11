from django.db.models import F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce, Greatest

from .models import PurchaseOrder, PurchaseOrderItem


def on_order_quantity(branch, product) -> int:
    """Base units on open purchase orders that have not arrived yet."""
    outstanding = Greatest(F("quantity") * F("packaging__factor") - F("received_base"), Value(0))
    return PurchaseOrderItem.objects.filter(
        order__branch=branch, order__status__in=PurchaseOrder.OPEN_STATUSES, product=product
    ).aggregate(total=Coalesce(Sum(outstanding, output_field=IntegerField()), Value(0)))["total"]
