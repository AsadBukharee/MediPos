from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from apps.accounting import services as accounting
from apps.audit.services import log_action
from apps.common.money import ZERO, money

from .models import Supplier, SupplierPayment


def supplier_balance(supplier: Supplier, branches=None) -> Decimal:
    """Amount owed to the supplier: opening + received goods − returns − payments."""
    from apps.purchases.models import GoodsReceivedNote, PurchaseReturn

    grns = GoodsReceivedNote.objects.filter(supplier=supplier, status=GoodsReceivedNote.Status.CONFIRMED)
    returns = PurchaseReturn.objects.filter(supplier=supplier)
    payments = SupplierPayment.objects.filter(supplier=supplier)
    if branches is not None:
        grns, returns, payments = (qs.filter(branch__in=branches) for qs in (grns, returns, payments))
    total = lambda qs, field: qs.aggregate(t=Sum(field))["t"] or ZERO  # noqa: E731
    return supplier.opening_balance + total(grns, "total") - total(returns, "total") - total(payments, "amount")


def supplier_ledger(supplier: Supplier, branches) -> list[dict]:
    from apps.purchases.models import GoodsReceivedNote, PurchaseReturn

    rows = [{"date": supplier.created_at, "type": "opening", "reference": "", "debit": ZERO, "credit": supplier.opening_balance}]
    for grn in GoodsReceivedNote.objects.filter(supplier=supplier, branch__in=branches, status="confirmed"):
        rows.append({"date": grn.confirmed_at, "type": "grn", "reference": grn.number, "debit": ZERO, "credit": grn.total})
    for ret in PurchaseReturn.objects.filter(supplier=supplier, branch__in=branches):
        rows.append({"date": ret.created_at, "type": "return", "reference": ret.number, "debit": ret.total, "credit": ZERO})
    for pay in SupplierPayment.objects.filter(supplier=supplier, branch__in=branches):
        rows.append({"date": pay.created_at, "type": "payment", "reference": pay.reference or f"PAY-{pay.pk}",
                     "debit": pay.amount, "credit": ZERO})
    rows[1:] = sorted(rows[1:], key=lambda r: r["date"])
    balance = ZERO
    for row in rows:
        balance += row["credit"] - row["debit"]
        row["balance"] = balance
    return rows


@transaction.atomic
def pay_supplier(*, supplier, branch, user, amount, method="cash", reference="", note="", grn=None,
                 idempotency_key=None) -> SupplierPayment:
    if idempotency_key:
        existing = SupplierPayment.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
    amount = money(amount)
    if amount <= ZERO:
        raise serializers.ValidationError({"amount": "Amount must be positive."})
    if method not in SupplierPayment.Method.values:
        raise serializers.ValidationError({"method": "Unknown payment method."})
    if grn is not None and (grn.supplier_id != supplier.pk or grn.branch_id != branch.pk):
        raise serializers.ValidationError({"grn": "The GRN belongs to another supplier or branch."})
    payment = SupplierPayment.objects.create(
        supplier=supplier, branch=branch, amount=amount, method=method, reference=reference, note=note, grn=grn,
        idempotency_key=idempotency_key or None, created_by=user)
    accounting.post_supplier_payment(payment, user)
    log_action(user=user, action="supplier.payment", obj=payment, branch=branch,
               summary=f"{supplier.name}: {amount}", changes={"amount": amount, "method": method})
    return payment
