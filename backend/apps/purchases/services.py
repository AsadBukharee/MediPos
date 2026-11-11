import math
from collections import defaultdict
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounting import services as accounting
from apps.audit.services import log_action
from apps.branches.models import next_document_number
from apps.common.exceptions import BusinessError
from apps.common.money import money
from apps.inventory import services as inventory
from apps.inventory.models import StockMovement
from apps.inventory.services import Source
from apps.suppliers.models import SupplierProduct

from .models import (GoodsReceivedNote, GRNItem, PurchaseOrder, PurchaseOrderItem, PurchaseRequisition,
                     PurchaseReturn, PurchaseReturnItem, RequisitionItem)

REQ = PurchaseRequisition.Status
PO = PurchaseOrder.Status
GRN = GoodsReceivedNote.Status


def _check_packaging(product, packaging):
    if packaging.product_id != product.pk:
        raise serializers.ValidationError(f"Packaging {packaging.pk} does not belong to {product}.")


# --- Order list / requisitions ----------------------------------------------------------------

def open_order_list(branch, user) -> PurchaseRequisition:
    """The single draft requisition of a branch, created on first use."""
    existing = PurchaseRequisition.objects.select_for_update().filter(branch=branch, status=REQ.DRAFT).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            return PurchaseRequisition.objects.create(
                branch=branch, number=next_document_number(branch, "requisition"), created_by=user)
    except IntegrityError:  # another request opened it first
        return PurchaseRequisition.objects.select_for_update().get(branch=branch, status=REQ.DRAFT)


@transaction.atomic
def add_to_order_list(*, branch, product, quantity: int, user, supplier=None, note="") -> RequisitionItem:
    if quantity <= 0:
        raise serializers.ValidationError({"quantity": "Quantity must be greater than zero."})
    requisition = open_order_list(branch, user)
    item, created = RequisitionItem.objects.get_or_create(
        requisition=requisition, product=product,
        defaults={"quantity": quantity, "supplier": supplier or product.preferred_supplier, "requested_by": user, "note": note})
    if not created:
        item.quantity = quantity  # the latest request wins; the same medicine is never listed twice
        if supplier:
            item.supplier = supplier
        item.save(update_fields=["quantity", "supplier", "updated_at"])
    log_action(user=user, action="order_list.add", obj=item, branch=branch, summary=f"{product} x{quantity}")
    return item


def _lock_requisition(requisition_id, branch) -> PurchaseRequisition:
    try:
        return PurchaseRequisition.objects.select_for_update().get(pk=requisition_id, branch=branch)
    except PurchaseRequisition.DoesNotExist:
        raise serializers.ValidationError("Requisition not found.")


@transaction.atomic
def submit_requisition(*, requisition_id, branch, user) -> PurchaseRequisition:
    requisition = _lock_requisition(requisition_id, branch)
    if requisition.status != REQ.DRAFT:
        raise BusinessError(f"Requisition {requisition.number} is already {requisition.status}.", code="bad_status")
    if not requisition.items.exists():
        raise BusinessError("The order list is empty.", code="empty")
    requisition.status = REQ.PENDING
    requisition.save(update_fields=["status", "updated_at"])
    log_action(user=user, action="requisition.submit", obj=requisition, branch=branch, summary=requisition.number)
    from apps.notifications.services import notify_permission

    transaction.on_commit(lambda: notify_permission(
        branch, "purchases.approve", type_="purchase_approval", title="Purchase requisition needs approval",
        body=f"{requisition.number} is waiting for approval.", data={"requisition_id": requisition.pk}))
    return requisition


@transaction.atomic
def decide_requisition(*, requisition_id, branch, user, approve: bool) -> PurchaseRequisition:
    requisition = _lock_requisition(requisition_id, branch)
    if requisition.status != REQ.PENDING:
        raise BusinessError(f"Requisition {requisition.number} is {requisition.status}, not pending.", code="bad_status")
    requisition.status = REQ.APPROVED if approve else REQ.REJECTED
    requisition.decided_by, requisition.decided_at = user, timezone.now()
    requisition.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    log_action(user=user, action="requisition.approve" if approve else "requisition.reject", obj=requisition,
               branch=branch, summary=requisition.number)
    return requisition


@transaction.atomic
def convert_requisition(*, requisition_id, branch, user) -> list[PurchaseOrder]:
    """Group approved lines by supplier and raise one draft purchase order per supplier."""
    requisition = _lock_requisition(requisition_id, branch)
    if requisition.status != REQ.APPROVED:
        raise BusinessError("Only an approved requisition can be converted to purchase orders.", code="bad_status")
    items = list(requisition.items.select_related("product", "supplier", "product__preferred_supplier")
                 .prefetch_related("product__packagings"))
    groups = defaultdict(list)
    missing = []
    for item in items:
        supplier = item.supplier or item.product.preferred_supplier
        (groups[supplier].append(item) if supplier else missing.append(str(item.product)))
    if missing:
        raise BusinessError("Choose a supplier for: " + ", ".join(missing), code="supplier_missing")
    orders = []
    for supplier, lines in groups.items():
        order = PurchaseOrder.objects.create(
            branch=branch, supplier=supplier, number=next_document_number(branch, "purchase_order"), created_by=user,
            note=f"From {requisition.number}")
        for line in lines:
            packagings = list(line.product.packagings.all())
            packaging = next((p for p in packagings if p.is_default_purchase), None) or max(packagings, key=lambda p: p.factor)
            agreed = SupplierProduct.objects.filter(supplier=supplier, product=line.product).first()
            if agreed and agreed.packaging_id == packaging.pk:
                price = agreed.price
            elif agreed and agreed.packaging is None:
                price = agreed.price * packaging.factor
            else:
                price = line.product.purchase_price * packaging.factor
            po_item = PurchaseOrderItem.objects.create(
                order=order, product=line.product, packaging=packaging,
                quantity=math.ceil(line.quantity / packaging.factor), unit_price=price)
            line.po_item = po_item
            line.save(update_fields=["po_item", "updated_at"])
        orders.append(order)
    requisition.status = REQ.ORDERED
    requisition.save(update_fields=["status", "updated_at"])
    log_action(user=user, action="requisition.convert", obj=requisition, branch=branch,
               summary=f"{requisition.number} → {', '.join(o.number for o in orders)}")
    return orders


def refresh_requisition_progress(po_items) -> None:
    """Move requisitions to partially received / fulfilled as their PO lines arrive."""
    requisitions = PurchaseRequisition.objects.filter(
        items__po_item__in=po_items, status__in=[REQ.ORDERED, REQ.PARTIALLY_RECEIVED]).distinct()
    for requisition in requisitions:
        lines = [i.po_item for i in requisition.items.select_related("po_item__packaging") if i.po_item_id]
        if lines and all(line.outstanding_base == 0 for line in lines):
            requisition.status = REQ.FULFILLED
        elif any(line.received_base > 0 for line in lines):
            requisition.status = REQ.PARTIALLY_RECEIVED
        requisition.save(update_fields=["status", "updated_at"])


# --- Purchase orders ------------------------------------------------------------------------

@transaction.atomic
def save_purchase_order(*, branch, user, supplier, items: list[dict], expected_date=None, note="", order=None) -> PurchaseOrder:
    if not items:
        raise serializers.ValidationError({"items": "Add at least one line."})
    if order is None:
        order = PurchaseOrder.objects.create(
            branch=branch, supplier=supplier, number=next_document_number(branch, "purchase_order"),
            expected_date=expected_date, note=note, created_by=user)
    else:
        order = PurchaseOrder.objects.select_for_update().get(pk=order.pk, branch=branch)
        if order.status != PO.DRAFT:
            raise BusinessError("Only a draft purchase order can be edited.", code="bad_status")
        order.supplier, order.expected_date, order.note = supplier, expected_date, note
        order.save()
        order.items.all().delete()
    for item in items:
        _check_packaging(item["product"], item["packaging"])
        PurchaseOrderItem.objects.create(order=order, product=item["product"], packaging=item["packaging"],
                                         quantity=item["quantity"], unit_price=item["unit_price"])
    log_action(user=user, action="purchase_order.save", obj=order, branch=branch, summary=order.number)
    return order


@transaction.atomic
def transition_purchase_order(*, order_id, branch, user, action: str) -> PurchaseOrder:
    """Purchase orders never touch stock: only a confirmed GRN does."""
    try:
        order = PurchaseOrder.objects.select_for_update().get(pk=order_id, branch=branch)
    except PurchaseOrder.DoesNotExist:
        raise serializers.ValidationError("Purchase order not found.")
    allowed = {
        "approve": ({PO.DRAFT}, PO.APPROVED),
        "mark_ordered": ({PO.APPROVED}, PO.ORDERED),
        "cancel": ({PO.DRAFT, PO.APPROVED, PO.ORDERED}, PO.CANCELLED),
    }
    if action not in allowed:
        raise serializers.ValidationError("Unknown action.")
    sources, target = allowed[action]
    if order.status not in sources:
        raise BusinessError(f"Purchase order {order.number} is {order.status}; cannot {action.replace('_', ' ')}.", code="bad_status")
    if action == "cancel" and order.grns.filter(status=GRN.CONFIRMED).exists():
        raise BusinessError("Goods have already been received against this order.", code="has_receipts")
    order.status = target
    if action == "approve":
        order.approved_by, order.approved_at = user, timezone.now()
    order.save()
    log_action(user=user, action=f"purchase_order.{action}", obj=order, branch=branch, summary=order.number)
    return order


# --- Goods received notes -------------------------------------------------------------------

@transaction.atomic
def save_grn(*, branch, user, supplier, items: list[dict], purchase_order=None, supplier_invoice_number="",
             supplier_invoice_date=None, note="", grn=None) -> GoodsReceivedNote:
    """Create or replace a draft GRN. A draft does not affect stock or accounts."""
    if not items:
        raise serializers.ValidationError({"items": "Add at least one line."})
    if purchase_order is not None:
        purchase_order = PurchaseOrder.objects.get(pk=purchase_order.pk)  # current status, not a stale copy
        if purchase_order.branch_id != branch.pk or purchase_order.supplier_id != supplier.pk:
            raise serializers.ValidationError({"purchase_order": "The order belongs to another branch or supplier."})
        if purchase_order.status not in PurchaseOrder.OPEN_STATUSES:
            raise BusinessError(f"Purchase order {purchase_order.number} is {purchase_order.status}; approve it first.",
                                code="bad_status")
    header = {"supplier": supplier, "purchase_order": purchase_order, "note": note,
              "supplier_invoice_number": supplier_invoice_number, "supplier_invoice_date": supplier_invoice_date}
    if grn is None:
        grn = GoodsReceivedNote.objects.create(
            branch=branch, number=next_document_number(branch, "grn"), created_by=user, **header)
    else:
        grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn.pk, branch=branch)
        if grn.status != GRN.DRAFT:
            raise BusinessError("Only a draft GRN can be edited.", code="bad_status")
        for field, value in header.items():
            setattr(grn, field, value)
        grn.items.all().delete()
    total = Decimal("0")
    for item in items:
        _check_packaging(item["product"], item["packaging"])
        po_item = item.get("po_item")
        if po_item is not None and (purchase_order is None or po_item.order_id != purchase_order.pk
                                    or po_item.product_id != item["product"].pk):
            raise serializers.ValidationError({"items": "A line points at a different purchase order line."})
        if item["expiry_date"] <= timezone.localdate():
            raise BusinessError(f"{item['product']} batch {item['batch_number']} has already expired.", code="batch_expired")
        GRNItem.objects.create(grn=grn, **{k: item.get(k) for k in (
            "po_item", "product", "packaging", "quantity", "unit_cost", "batch_number", "expiry_date",
            "manufacturing_date", "selling_price")}, damaged_quantity=item.get("damaged_quantity") or 0)
        total += item["quantity"] * item["unit_cost"]
    grn.total = money(total)
    grn.save()
    return grn


@transaction.atomic
def confirm_grn(*, grn_id, branch, user) -> GoodsReceivedNote:
    """Post a GRN: stock goes up exactly once, however many times this is called."""
    try:
        grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id, branch=branch)
    except GoodsReceivedNote.DoesNotExist:
        raise serializers.ValidationError("GRN not found.")
    if grn.status == GRN.CONFIRMED:
        return grn  # duplicate request: already posted, nothing more to do
    if grn.status != GRN.DRAFT:
        raise BusinessError(f"GRN {grn.number} is {grn.status}.", code="bad_status")
    items = list(grn.items.select_related("product", "packaging").order_by("product_id", "id"))
    if not items:
        raise BusinessError("The GRN has no lines.", code="empty")
    source = Source("grn", grn.pk, grn.number)
    inventory_value = Decimal("0")
    po_items = []
    for item in items:
        base_quantity = item.quantity * item.packaging.factor
        batch = inventory.receive_stock(
            branch=branch, product=item.product, batch_number=item.batch_number, expiry_date=item.expiry_date,
            manufacturing_date=item.manufacturing_date, quantity=base_quantity,
            unit_cost=item.unit_cost / item.packaging.factor, selling_price=item.selling_price,
            supplier=grn.supplier, grn=grn, user=user, source=source)
        item.batch = batch
        item.save(update_fields=["batch"])
        inventory_value += base_quantity * batch.purchase_cost
        if item.po_item_id:
            po_item = PurchaseOrderItem.objects.select_for_update().get(pk=item.po_item_id)
            po_item.received_base += base_quantity
            po_item.save(update_fields=["received_base"])
            po_items.append(po_item)
    if grn.purchase_order_id:
        order = PurchaseOrder.objects.select_for_update().get(pk=grn.purchase_order_id)
        lines = list(order.items.select_related("packaging"))
        order.status = PO.RECEIVED if all(l.outstanding_base == 0 for l in lines) else PO.PARTIALLY_RECEIVED
        order.save(update_fields=["status", "updated_at"])
        refresh_requisition_progress(po_items)
    grn.status, grn.confirmed_by, grn.confirmed_at = GRN.CONFIRMED, user, timezone.now()
    grn.save(update_fields=["status", "confirmed_by", "confirmed_at", "updated_at"])
    accounting.post_grn(grn, user, inventory_value)
    log_action(user=user, action="grn.confirm", obj=grn, branch=branch, summary=grn.number, changes={"total": grn.total})
    from apps.notifications.services import notify_permission

    transaction.on_commit(lambda: notify_permission(
        branch, "purchases.view", type_="goods_received", title="Goods received",
        body=f"{grn.number} from {grn.supplier.name} was received.", data={"grn_id": grn.pk}, exclude=user))
    return grn


@transaction.atomic
def cancel_grn(*, grn_id, branch, user) -> GoodsReceivedNote:
    grn = GoodsReceivedNote.objects.select_for_update().get(pk=grn_id, branch=branch)
    if grn.status != GRN.DRAFT:
        raise BusinessError("A confirmed GRN cannot be cancelled; raise a supplier return instead.", code="bad_status")
    grn.status = GRN.CANCELLED
    grn.save(update_fields=["status", "updated_at"])
    log_action(user=user, action="grn.cancel", obj=grn, branch=branch, summary=grn.number)
    return grn


# --- Supplier returns and payments -----------------------------------------------------------

@transaction.atomic
def create_purchase_return(*, branch, user, supplier, reason: str, items: list[dict], grn=None) -> PurchaseReturn:
    if not items:
        raise serializers.ValidationError({"items": "Add at least one line."})
    if grn is not None and (grn.branch_id != branch.pk or grn.supplier_id != supplier.pk):
        raise serializers.ValidationError({"grn": "The GRN belongs to another branch or supplier."})
    purchase_return = PurchaseReturn.objects.create(
        branch=branch, supplier=supplier, grn=grn, reason=reason,
        number=next_document_number(branch, "purchase_return"), created_by=user)
    source = Source("purchase_return", purchase_return.pk, purchase_return.number)
    value = Decimal("0")
    for item in sorted(items, key=lambda i: i["batch"].pk):
        movement = inventory.change_batch(
            batch_id=item["batch"].pk, branch=branch, delta=-item["quantity"],
            movement_type=StockMovement.Type.PURCHASE_RETURN, user=user, source=source, note=reason)
        PurchaseReturnItem.objects.create(purchase_return=purchase_return, batch=movement.batch,
                                          quantity=item["quantity"], unit_cost=movement.unit_cost)
        value += item["quantity"] * movement.unit_cost
    purchase_return.total = money(value)
    purchase_return.save(update_fields=["total", "updated_at"])
    accounting.post_purchase_return(purchase_return, user, value)
    log_action(user=user, action="purchase_return.create", obj=purchase_return, branch=branch, summary=purchase_return.number)
    return purchase_return
