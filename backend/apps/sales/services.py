"""POS business logic: pricing, completing, holding, cancelling and returning sales."""
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounting import services as accounting
from apps.audit.services import log_action
from apps.branches.models import BusinessProfile, next_document_number
from apps.catalog.services import base_unit_price, get_packaging, to_base_units
from apps.common.exceptions import BusinessError
from apps.common.money import ZERO, money
from apps.customers.models import Customer
from apps.customers.services import customer_balance
from apps.inventory import services as inventory
from apps.inventory.models import StockMovement
from apps.inventory.services import Source

from .models import Sale, SaleItem, SaleItemBatch, SalePayment, SaleReturn, SaleReturnItem, Shift

HUNDRED = Decimal("100")
REAL_MONEY = ("cash", "card", "bank", "wallet")


@dataclass
class PricedLine:
    product: object
    packaging: object
    batch: object | None
    quantity: int
    quantity_base: int
    unit_price: Decimal
    gross: Decimal
    discount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal


def price_lines(*, branch, user, customer, items: list[dict], invoice_discount=ZERO) -> tuple[list[PricedLine], dict]:
    """Server-side pricing. The client never decides prices, tax or totals."""
    if not items:
        raise serializers.ValidationError({"items": "Add at least one item."})
    profile = BusinessProfile.get()
    tier = customer.price_tier if customer else "retail"
    order = inventory.issue_order()
    lines: list[PricedLine] = []
    for item in items:
        product = item["product"]
        if not product.is_active:
            raise BusinessError(f"{product} is not active.", code="product_inactive")
        packaging = item.get("packaging") or get_packaging(product, None)
        if packaging.product_id != product.pk:
            raise serializers.ValidationError({"items": f"Packaging {packaging.pk} does not belong to {product}."})
        if not packaging.can_sell:
            raise BusinessError(f"{product} cannot be sold by the {packaging.unit.name}.", code="unit_not_sellable")
        quantity_base = to_base_units(packaging, item["quantity"])
        batch = item.get("batch")
        if batch is not None and (batch.branch_id != branch.pk or batch.product_id != product.pk):
            raise serializers.ValidationError({"items": f"Batch {batch.pk} is not a batch of {product} in this branch."})
        price_batch = batch or inventory.sellable_batches(branch, product).order_by(*order).first()
        unit_price = base_unit_price(product, branch, batch=price_batch, tier=tier) * packaging.factor
        gross = money(unit_price * item["quantity"])
        discount = money(item.get("discount_amount") or ZERO)
        if discount < ZERO or discount > gross:
            raise serializers.ValidationError({"items": f"Discount on {product} must be between 0 and {gross}."})
        if discount > money(gross * product.max_discount_percent / HUNDRED):
            raise BusinessError(f"Discount on {product} is above its {product.max_discount_percent}% limit.", code="discount_limit")
        lines.append(PricedLine(product, packaging, batch, item["quantity"], quantity_base, unit_price, gross,
                                discount, product.tax_rate, ZERO, ZERO))

    subtotal = sum((l.gross for l in lines), ZERO)
    after_line_discounts = sum((l.gross - l.discount for l in lines), ZERO)
    invoice_discount = money(invoice_discount or ZERO)
    if invoice_discount < ZERO or invoice_discount > after_line_discounts:
        raise serializers.ValidationError({"invoice_discount": "Invoice discount is larger than the invoice."})
    # Spread the invoice discount over the lines so tax and later returns stay exact.
    remaining = invoice_discount
    for index, line in enumerate(lines):
        base = line.gross - line.discount
        if index == len(lines) - 1:
            share = remaining
        else:
            share = money(invoice_discount * base / after_line_discounts) if after_line_discounts else ZERO
            share = min(share, remaining, base)
        remaining -= share
        line.discount += share
        taxable = line.gross - line.discount
        if profile.prices_include_tax:
            line.tax_amount = money(taxable * line.tax_rate / (HUNDRED + line.tax_rate))
            line.line_total = taxable
        else:
            line.tax_amount = money(taxable * line.tax_rate / HUNDRED)
            line.line_total = taxable + line.tax_amount

    discount_total = sum((l.discount for l in lines), ZERO)
    if subtotal and not user.is_owner:
        percent = discount_total * HUNDRED / subtotal
        if percent > user.max_discount_percent:
            raise BusinessError(
                f"Total discount of {percent:.2f}% is above your limit of {user.max_discount_percent}%.", code="discount_limit")
    totals = {
        "subtotal": subtotal,
        "discount_total": discount_total,
        "invoice_discount": invoice_discount,
        "tax_total": sum((l.tax_amount for l in lines), ZERO),
        "total": sum((l.line_total for l in lines), ZERO),
    }
    return lines, totals


def current_shift(branch, user) -> Shift | None:
    return Shift.objects.filter(branch=branch, cashier=user, status=Shift.Status.OPEN).first()


def _existing_sale(branch, key):
    return Sale.objects.filter(branch=branch, idempotency_key=key).first() if key else None


def create_sale(*, branch, user, items, payments=(), customer=None, invoice_discount=ZERO, prescription_reference="",
                note="", hold=False, idempotency_key=None) -> Sale:
    """Create and (unless held) complete a sale. Safe to retry with the same idempotency key."""
    existing = _existing_sale(branch, idempotency_key)
    if existing:
        return existing
    try:
        with transaction.atomic():
            lines, totals = price_lines(branch=branch, user=user, customer=customer, items=items, invoice_discount=invoice_discount)
            sale = Sale.objects.create(
                branch=branch, cashier=user, customer=customer, note=note, prescription_reference=prescription_reference,
                idempotency_key=idempotency_key or None, **totals)
            SaleItem.objects.bulk_create([
                SaleItem(sale=sale, product=l.product, packaging=l.packaging, requested_batch=l.batch, quantity=l.quantity,
                         quantity_base=l.quantity_base, unit_price=l.unit_price, discount_amount=l.discount,
                         tax_rate=l.tax_rate, tax_amount=l.tax_amount, line_total=l.line_total)
                for l in lines
            ])
            if hold:
                log_action(user=user, action="sale.hold", obj=sale, branch=branch, summary=f"Held invoice #{sale.pk}")
                return sale
            return _finalize(sale, list(payments), user)
    except IntegrityError:
        existing = _existing_sale(branch, idempotency_key)  # a concurrent duplicate request won the race
        if existing:
            return existing
        raise


@transaction.atomic
def complete_held_sale(*, sale_id, branch, user, payments, prescription_reference="") -> Sale:
    sale = _lock_sale(sale_id, branch)
    if sale.status == Sale.Status.COMPLETED:
        return sale
    if sale.status != Sale.Status.HELD:
        raise BusinessError("This invoice was cancelled.", code="bad_status")
    if prescription_reference:
        sale.prescription_reference = prescription_reference
    return _finalize(sale, list(payments), user)


def _lock_sale(sale_id, branch) -> Sale:
    try:
        return Sale.objects.select_for_update().get(pk=sale_id, branch=branch)
    except Sale.DoesNotExist:
        raise serializers.ValidationError("Invoice not found.")


def _finalize(sale: Sale, payments: list[dict], user) -> Sale:
    """Validate payment, deduct stock by FEFO, post accounts. Runs inside the caller's transaction."""
    branch = sale.branch
    items = list(sale.items.select_related("product__base_unit", "packaging").order_by("product_id", "id"))

    needs_rx = [str(i.product) for i in items if i.product.requires_prescription]
    if needs_rx and not (sale.prescription_reference or sale.prescription_file):
        raise BusinessError("A prescription is required for: " + ", ".join(needs_rx), code="prescription_required")

    paid = ZERO
    cash = ZERO
    credit = ZERO
    cleaned = []
    for payment in payments:
        amount = money(payment["amount"])
        if amount <= ZERO:
            raise serializers.ValidationError({"payments": "Payment amounts must be positive."})
        method = payment["method"]
        if method not in SalePayment.Method.values:
            raise serializers.ValidationError({"payments": f"Unknown payment method: {method}."})
        paid += amount
        cash += amount if method == "cash" else ZERO
        credit += amount if method == "credit" else ZERO
        cleaned.append(SalePayment(sale=sale, method=method, amount=amount, reference=payment.get("reference", "")))
    if paid < sale.total:
        raise BusinessError(f"Payment is short by {sale.total - paid}.", code="underpaid")
    change = paid - sale.total
    if change > cash:
        raise BusinessError("Only cash can be overpaid; change is given in cash.", code="overpaid")
    if credit:
        if sale.customer_id is None:
            raise BusinessError("Choose a customer to sell on credit.", code="customer_required")
        customer = Customer.objects.select_for_update().get(pk=sale.customer_id)
        if customer_balance(customer) + credit > customer.credit_limit:
            raise BusinessError(f"{customer.name} would exceed the credit limit of {customer.credit_limit}.", code="credit_limit")

    sale.number = next_document_number(branch, "sale")
    source = Source("sale", sale.pk, sale.number)
    cost_total = Decimal("0")
    for item in items:  # ordered by product so concurrent sales lock batches in the same order
        allocations = inventory.issue_stock(
            branch=branch, product=item.product, quantity=item.quantity_base, user=user, source=source,
            batch_id=item.requested_batch_id, evaluate=False)
        SaleItemBatch.objects.bulk_create([
            SaleItemBatch(sale_item=item, batch=a.batch, quantity=a.quantity, unit_cost=a.unit_cost) for a in allocations])
        item.cost_total = sum((a.quantity * a.unit_cost for a in allocations), Decimal("0"))
        item.save(update_fields=["cost_total"])
        cost_total += item.cost_total
    SalePayment.objects.bulk_create(cleaned)

    sale.status = Sale.Status.COMPLETED
    sale.paid_total, sale.change_due, sale.cost_total = paid, change, cost_total
    sale.completed_at = timezone.now()
    sale.shift = current_shift(branch, user)
    sale.save()
    accounting.post_sale(sale, user)
    log_action(user=user, action="sale.complete", obj=sale, branch=branch, summary=sale.number,
               changes={"total": sale.total, "discount": sale.discount_total})
    for product in {item.product for item in items}:
        inventory._after_change(branch, product)
    return sale


@transaction.atomic
def cancel_sale(*, sale_id, branch, user, reason: str) -> Sale:
    """Cancel a held invoice, or fully reverse a completed one (stock and accounts)."""
    sale = _lock_sale(sale_id, branch)
    if sale.status == Sale.Status.CANCELLED:
        return sale
    if not reason.strip():
        raise serializers.ValidationError({"reason": "A reason is required."})
    if sale.status == Sale.Status.COMPLETED:
        if sale.returns.exists():
            raise BusinessError("This invoice has returns; return the remaining items instead.", code="has_returns")
        source = Source("sale", sale.pk, sale.number)
        products = set()
        allocations = SaleItemBatch.objects.filter(sale_item__sale=sale).select_related("sale_item__product").order_by("batch_id")
        for allocation in allocations:
            inventory.change_batch(batch_id=allocation.batch_id, branch=branch, delta=allocation.quantity,
                                   movement_type=StockMovement.Type.SALE_CANCEL, user=user, source=source,
                                   note=reason, evaluate=False)
            products.add(allocation.sale_item.product)
        accounting.reverse_entries(source=source, user=user, memo=f"Cancel sale {sale.number}")
        for product in products:
            inventory._after_change(branch, product)
    sale.status = Sale.Status.CANCELLED
    sale.cancelled_by, sale.cancelled_at, sale.cancel_reason = user, timezone.now(), reason[:255]
    sale.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason", "updated_at"])
    log_action(user=user, action="sale.cancel", obj=sale, branch=branch, summary=sale.number or f"Held #{sale.pk}",
               changes={"reason": reason})
    return sale


@transaction.atomic
def create_sale_return(*, branch, user, sale_id, items: list[dict], reason: str, refund_method="cash",
                       idempotency_key=None) -> SaleReturn:
    """Full or partial return against the original invoice, back into the original batches."""
    if idempotency_key:
        existing = SaleReturn.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
    sale = _lock_sale(sale_id, branch)
    if sale.status != Sale.Status.COMPLETED:
        raise BusinessError("Only completed invoices can be returned.", code="bad_status")
    if not items:
        raise serializers.ValidationError({"items": "Choose at least one item to return."})
    if refund_method not in SalePayment.Method.values:
        raise serializers.ValidationError({"refund_method": "Unknown refund method."})
    if refund_method == "credit" and sale.customer_id is None:
        raise BusinessError("Refund to credit needs a customer on the invoice.", code="customer_required")

    sale_return = SaleReturn.objects.create(
        branch=branch, sale=sale, number=next_document_number(branch, "sale_return"), reason=reason[:255],
        refund_method=refund_method, idempotency_key=idempotency_key or None, created_by=user,
        shift=current_shift(branch, user))
    source = Source("sale_return", sale_return.pk, sale_return.number)
    total = tax_total = ZERO
    restocked_cost = Decimal("0")
    products = set()
    seen = set()
    for row in items:
        sale_item = SaleItem.objects.select_for_update().select_related("product").filter(
            pk=getattr(row["sale_item"], "pk", row["sale_item"]), sale=sale).first()
        if sale_item is None or sale_item.pk in seen:
            raise serializers.ValidationError({"items": "Each line must be a different item of this invoice."})
        seen.add(sale_item.pk)
        quantity = row["quantity_base"]
        remaining = sale_item.quantity_base - sale_item.returned_base
        if quantity <= 0 or quantity > remaining:
            raise BusinessError(f"Only {remaining} of {sale_item.product} can still be returned.", code="return_exceeds_sale")
        if quantity == remaining:  # last piece: refund exactly what is left, no rounding drift
            amount = sale_item.line_total - sale_item.refunded_amount
            tax = sale_item.tax_amount - sale_item.refunded_tax
        else:
            amount = money(sale_item.line_total * quantity / sale_item.quantity_base)
            tax = money(sale_item.tax_amount * quantity / sale_item.quantity_base)
        restock = row.get("restock", True)
        to_place = quantity
        for allocation in sale_item.allocations.select_for_update().order_by("-id"):
            take = min(allocation.quantity - allocation.returned_quantity, to_place)
            if take <= 0:
                continue
            if restock:
                inventory.change_batch(batch_id=allocation.batch_id, branch=branch, delta=take,
                                       movement_type=StockMovement.Type.SALE_RETURN, user=user, source=source,
                                       note=reason, evaluate=False)
                restocked_cost += take * allocation.unit_cost
            allocation.returned_quantity += take
            allocation.save(update_fields=["returned_quantity"])
            to_place -= take
            if to_place == 0:
                break
        sale_item.returned_base += quantity
        sale_item.refunded_amount += amount
        sale_item.refunded_tax += tax
        sale_item.save(update_fields=["returned_base", "refunded_amount", "refunded_tax"])
        SaleReturnItem.objects.create(sale_return=sale_return, sale_item=sale_item, quantity_base=quantity,
                                      restock=restock, amount=amount)
        total += amount
        tax_total += tax
        products.add(sale_item.product)
    sale_return.total, sale_return.tax_total = total, tax_total
    sale_return.save(update_fields=["total", "tax_total", "updated_at"])
    accounting.post_sale_return(sale_return, user, restocked_cost)
    log_action(user=user, action="sale.return", obj=sale_return, branch=branch,
               summary=f"{sale_return.number} against {sale.number}", changes={"total": total, "reason": reason})
    for product in products:
        inventory._after_change(branch, product)
    return sale_return


# --- Cashier shifts -------------------------------------------------------------------------

@transaction.atomic
def open_shift(*, branch, user, opening_cash) -> Shift:
    if current_shift(branch, user):
        raise BusinessError("You already have an open shift in this branch.", code="shift_open")
    opening_cash = money(opening_cash or ZERO)
    if opening_cash < ZERO:
        raise serializers.ValidationError({"opening_cash": "Opening cash cannot be negative."})
    shift = Shift.objects.create(branch=branch, cashier=user, opening_cash=opening_cash)
    log_action(user=user, action="shift.open", obj=shift, branch=branch, changes={"opening_cash": opening_cash})
    return shift


def shift_expected_cash(shift: Shift) -> Decimal:
    sales = Sale.objects.filter(shift=shift, status=Sale.Status.COMPLETED)
    cash_in = SalePayment.objects.filter(sale__in=sales, method="cash").aggregate(t=Sum("amount"))["t"] or ZERO
    change = sales.aggregate(t=Sum("change_due"))["t"] or ZERO
    refunds = shift.returns.filter(refund_method="cash").aggregate(t=Sum("total"))["t"] or ZERO
    return shift.opening_cash + cash_in - change - refunds


@transaction.atomic
def close_shift(*, shift_id, branch, user, closing_cash, note="") -> Shift:
    try:
        shift = Shift.objects.select_for_update().get(pk=shift_id, branch=branch)
    except Shift.DoesNotExist:
        raise serializers.ValidationError("Shift not found.")
    if shift.cashier_id != user.pk and not user.has_perm_code("sales.cancel"):
        raise BusinessError("Only the cashier or a manager can close this shift.", code="forbidden")
    if shift.status == Shift.Status.CLOSED:
        return shift
    shift.expected_cash = shift_expected_cash(shift)
    shift.closing_cash = money(closing_cash)
    shift.status, shift.closed_at, shift.note = Shift.Status.CLOSED, timezone.now(), note[:255]
    shift.save()
    log_action(user=user, action="shift.close", obj=shift, branch=branch,
               changes={"expected": shift.expected_cash, "counted": shift.closing_cash,
                        "difference": shift.closing_cash - shift.expected_cash})
    return shift
