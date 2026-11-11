"""Every change to stock goes through this module, inside a transaction, with row locks.

Rules enforced here:
* stock only changes together with a StockMovement row (the ledger),
* expired, blocked and quarantined batches are never issued for sale,
* issuing follows FEFO (or FIFO when configured),
* quantities can never go negative (checked here and by a database constraint).
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.services import log_action
from apps.branches.models import BusinessProfile, next_document_number
from apps.common.exceptions import BusinessError, InsufficientStock

from .models import Batch, StockAdjustment, StockAdjustmentItem, StockMovement


@dataclass(frozen=True)
class Source:
    """The document that caused a stock movement."""

    type: str
    id: int | None = None
    number: str = ""


@dataclass(frozen=True)
class Allocation:
    batch: Batch
    quantity: int
    unit_cost: Decimal


def _post(batch: Batch, delta: int, movement_type: str, user, source: Source, note: str = "") -> StockMovement:
    """Apply a signed change to an already-locked batch and write the ledger row."""
    new_balance = batch.quantity_on_hand + delta
    if new_balance < 0:
        raise InsufficientStock(
            f"Batch {batch.batch_number} of {batch.product} has {batch.quantity_on_hand}, cannot remove {-delta}.")
    batch.quantity_on_hand = new_balance
    batch.save(update_fields=["quantity_on_hand", "updated_at"])
    return StockMovement.objects.create(
        branch=batch.branch, product=batch.product, batch=batch, movement_type=movement_type, quantity=delta,
        balance_after=new_balance, unit_cost=batch.purchase_cost, source_type=source.type, source_id=source.id,
        source_number=source.number, note=note[:255], user=user,
    )


def _after_change(branch, product):
    from apps.notifications.services import evaluate_stock_level

    evaluate_stock_level(branch, product)


def lock_batch(batch_id: int, branch) -> Batch:
    try:
        return Batch.objects.select_for_update().select_related("product", "branch").get(pk=batch_id, branch=branch)
    except Batch.DoesNotExist:
        raise serializers.ValidationError(f"Batch {batch_id} was not found in this branch.")


def sellable_batches(branch, product, on_date=None):
    today = on_date or timezone.localdate()
    return Batch.objects.filter(
        branch=branch, product=product, status=Batch.Status.ACTIVE, quantity_on_hand__gt=0, expiry_date__gt=today)


def issue_order() -> list[str]:
    if BusinessProfile.get().stock_issue_policy == BusinessProfile.Costing.FIFO:
        return ["received_at", "id"]
    return ["expiry_date", "received_at", "id"]


@transaction.atomic
def receive_stock(*, branch, product, batch_number, expiry_date, quantity: int, unit_cost: Decimal, user,
                  source: Source, movement_type=StockMovement.Type.PURCHASE_RECEIPT, manufacturing_date=None,
                  selling_price=None, supplier=None, grn=None, evaluate=True) -> Batch:
    if quantity <= 0:
        raise serializers.ValidationError("Received quantity must be positive.")
    if not batch_number:
        raise serializers.ValidationError("Batch number is required.")
    if manufacturing_date and manufacturing_date >= expiry_date:
        raise serializers.ValidationError("Manufacturing date must be before the expiry date.")
    unit_cost = Decimal(unit_cost).quantize(Decimal("0.000001"))
    batch, created = Batch.objects.select_for_update().get_or_create(
        branch=branch, product=product, batch_number=batch_number.strip(), expiry_date=expiry_date,
        purchase_cost=unit_cost,
        defaults={"manufacturing_date": manufacturing_date, "selling_price": selling_price, "supplier": supplier, "grn": grn},
    )
    if not created and selling_price is not None and batch.selling_price != selling_price:
        batch.selling_price = selling_price
        batch.save(update_fields=["selling_price", "updated_at"])
    _post(batch, quantity, movement_type, user, source)
    if evaluate:
        _after_change(branch, product)
    return batch


@transaction.atomic
def issue_stock(*, branch, product, quantity: int, user, source: Source,
                movement_type=StockMovement.Type.SALE, batch_id: int | None = None, evaluate=True) -> list[Allocation]:
    """Take `quantity` base units from sellable batches. All or nothing."""
    if quantity <= 0:
        raise serializers.ValidationError("Issued quantity must be positive.")
    batches = sellable_batches(branch, product).select_for_update().order_by(*issue_order())
    if batch_id is not None:
        batches = batches.filter(pk=batch_id)
    remaining = quantity
    allocations: list[Allocation] = []
    for batch in batches:
        take = min(batch.quantity_on_hand, remaining)
        _post(batch, -take, movement_type, user, source)
        allocations.append(Allocation(batch=batch, quantity=take, unit_cost=batch.purchase_cost))
        remaining -= take
        if remaining == 0:
            break
    if remaining:
        if batch_id is not None and not allocations:
            chosen = Batch.objects.filter(pk=batch_id, branch=branch, product=product).first()
            if chosen and chosen.is_expired():
                raise BusinessError(f"Batch {chosen.batch_number} of {product} has expired.", code="batch_expired")
            if chosen and chosen.status != Batch.Status.ACTIVE:
                raise BusinessError(f"Batch {chosen.batch_number} of {product} is {chosen.status}.", code="batch_blocked")
        raise InsufficientStock(
            f"Only {quantity - remaining} of {quantity} {product.base_unit.name}(s) of {product} are available for sale.")
    if evaluate:
        _after_change(branch, product)
    return allocations


@transaction.atomic
def change_batch(*, batch_id: int, branch, delta: int, movement_type: str, user, source: Source, note="",
                 evaluate=True) -> StockMovement:
    """Signed change to one specific batch (returns, write-offs, corrections)."""
    batch = lock_batch(batch_id, branch)
    movement = _post(batch, delta, movement_type, user, source, note)
    if evaluate:
        _after_change(branch, batch.product)
    return movement


@transaction.atomic
def set_batch_status(*, batch_id: int, branch, status: str, reason: str, user) -> Batch:
    batch = lock_batch(batch_id, branch)
    if status not in Batch.Status.values:
        raise serializers.ValidationError({"status": "Unknown status."})
    old = batch.status
    batch.status, batch.status_reason = status, reason[:255]
    batch.save(update_fields=["status", "status_reason", "updated_at"])
    log_action(user=user, action="batch.status", obj=batch, branch=branch, summary=str(batch),
               changes={"status": [old, status], "reason": reason})
    _after_change(branch, batch.product)
    return batch


# --- Stock adjustments (request → approval → posting) -----------------------------------------

@transaction.atomic
def request_adjustment(*, branch, user, reason: str, note: str, items: list[dict]) -> StockAdjustment:
    if not items:
        raise serializers.ValidationError({"items": "Add at least one line."})
    adjustment = StockAdjustment.objects.create(
        branch=branch, number=next_document_number(branch, "adjustment"), reason=reason, note=note, requested_by=user)
    for item in items:
        batch = item.get("batch")
        if batch is not None:
            if batch.branch_id != branch.pk:
                raise serializers.ValidationError({"items": f"Batch {batch.pk} belongs to another branch."})
            product = batch.product
        else:
            product = item.get("product")
            missing = [f for f in ("product", "batch_number", "expiry_date", "unit_cost") if item.get(f) in (None, "")]
            if missing:
                raise serializers.ValidationError({"items": f"New batch lines need: {', '.join(missing)}."})
            if item["quantity_delta"] <= 0:
                raise serializers.ValidationError({"items": "A new batch can only be added with a positive quantity."})
        StockAdjustmentItem.objects.create(
            adjustment=adjustment, product=product, batch=batch, batch_number=item.get("batch_number", ""),
            expiry_date=item.get("expiry_date"), unit_cost=item.get("unit_cost"), quantity_delta=item["quantity_delta"])
    log_action(user=user, action="adjustment.request", obj=adjustment, branch=branch, summary=adjustment.number)
    return adjustment


@transaction.atomic
def decide_adjustment(*, adjustment_id: int, branch, user, approve: bool) -> StockAdjustment:
    from apps.accounting.services import post_stock_adjustment

    try:
        adjustment = StockAdjustment.objects.select_for_update().get(pk=adjustment_id, branch=branch)
    except StockAdjustment.DoesNotExist:
        raise serializers.ValidationError("Adjustment not found.")
    if adjustment.status != StockAdjustment.Status.PENDING:
        raise BusinessError(f"Adjustment {adjustment.number} is already {adjustment.status}.", code="already_decided")
    if approve and adjustment.requested_by_id == user.pk and not user.is_owner:
        raise BusinessError("You cannot approve your own adjustment.", code="self_approval")
    adjustment.status = StockAdjustment.Status.APPROVED if approve else StockAdjustment.Status.REJECTED
    adjustment.decided_by, adjustment.decided_at = user, timezone.now()
    adjustment.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    if approve:
        source = Source("stock_adjustment", adjustment.pk, adjustment.number)
        opening = adjustment.reason == StockAdjustment.Reason.OPENING
        movements = []
        for item in adjustment.items.select_related("product").order_by("product_id", "id"):
            if item.batch_id:
                movements.append(change_batch(
                    batch_id=item.batch_id, branch=branch, delta=item.quantity_delta,
                    movement_type=StockMovement.Type.ADJUSTMENT, user=user, source=source, note=adjustment.note))
            else:
                batch = receive_stock(
                    branch=branch, product=item.product, batch_number=item.batch_number, expiry_date=item.expiry_date,
                    quantity=item.quantity_delta, unit_cost=item.unit_cost, user=user, source=source,
                    movement_type=StockMovement.Type.OPENING if opening else StockMovement.Type.ADJUSTMENT)
                item.batch = batch
                item.save(update_fields=["batch"])
                movements.append(batch.movements.order_by("-id").first())
        post_stock_adjustment(adjustment, movements, user)
    log_action(user=user, action="adjustment.approve" if approve else "adjustment.reject", obj=adjustment,
               branch=branch, summary=adjustment.number)
    return adjustment
