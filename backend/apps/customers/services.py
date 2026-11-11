from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from apps.accounting import services as accounting
from apps.audit.services import log_action
from apps.common.money import ZERO, money

from .models import Customer, CustomerPayment


def customer_balance(customer: Customer) -> Decimal:
    """Outstanding receivable: credit sales − credit refunds − payments received."""
    from apps.sales.models import SalePayment, SaleReturn

    credit = SalePayment.objects.filter(sale__customer=customer, sale__status="completed", method="credit").aggregate(
        t=Sum("amount"))["t"] or ZERO
    refunded = SaleReturn.objects.filter(sale__customer=customer, refund_method="credit").aggregate(t=Sum("total"))["t"] or ZERO
    paid = customer.payments.aggregate(t=Sum("amount"))["t"] or ZERO
    return credit - refunded - paid


@transaction.atomic
def receive_customer_payment(*, customer, branch, user, amount, method="cash", reference="", idempotency_key=None) -> CustomerPayment:
    if idempotency_key:
        existing = CustomerPayment.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
    Customer.objects.select_for_update().get(pk=customer.pk)
    amount = money(amount)
    if amount <= ZERO:
        raise serializers.ValidationError({"amount": "Amount must be positive."})
    if method not in ("cash", "bank", "card", "wallet"):
        raise serializers.ValidationError({"method": "Unknown payment method."})
    if amount > customer_balance(customer):
        raise serializers.ValidationError({"amount": "The amount is more than the customer owes."})
    payment = CustomerPayment.objects.create(customer=customer, branch=branch, amount=amount, method=method,
                                             reference=reference, idempotency_key=idempotency_key or None, created_by=user)
    accounting.post_customer_payment(payment, user)
    log_action(user=user, action="customer.payment", obj=payment, branch=branch, summary=f"{customer.name}: {amount}")
    return payment
