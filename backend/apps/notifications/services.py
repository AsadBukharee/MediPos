from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounts import permissions as perms
from apps.audit.services import log_action
from apps.common.exceptions import BusinessError
from apps.inventory.selectors import sellable_quantity

from .models import Notification, NotificationPreference, StockAlert

ALERT = StockAlert.Status
NOTIFICATION_TYPES = {
    "low_stock": "Low stock",
    "out_of_stock": "Out of stock",
    "near_expiry": "Near expiry",
    "expired_stock": "Expired stock",
    "purchase_approval": "Purchase approval requests",
    "goods_received": "Goods received",
    "purchase_order": "Purchase order status",
}


def recipients(branch, perm_code: str, exclude=None):
    """Active users whose role grants `perm_code` and who can work in `branch`."""
    roles = [role for role, codes in perms.ROLE_PERMISSIONS.items() if perm_code in codes]
    User = get_user_model()
    owners = Q(role=perms.OWNER) | Q(is_superuser=True)
    users = User.objects.filter(is_active=True).filter(owners | Q(role__in=roles, branches=branch)).distinct()
    return users.exclude(pk=exclude.pk) if exclude is not None else users


def notify(users, *, branch, type_: str, title: str, body: str = "", data: dict | None = None) -> list[Notification]:
    from .tasks import send_push_task

    users = list(users)
    prefs = {p.user_id: p for p in NotificationPreference.objects.filter(user__in=users, type=type_)}
    created = []
    for user in users:
        pref = prefs.get(user.pk)
        if pref and not pref.in_app and not pref.push:
            continue
        push_wanted = pref.push if pref else True
        created.append(Notification.objects.create(
            user=user, branch=branch, type=type_, title=title[:160], body=body[:500],
            data={**(data or {}), "type": type_, "branch_id": branch.pk if branch else ""},
            push_status=Notification.Push.PENDING if push_wanted else Notification.Push.SKIPPED))
    for notification in created:
        if notification.push_status == Notification.Push.PENDING:
            transaction.on_commit(lambda pk=notification.pk: send_push_task.delay(pk))
    return created


def notify_permission(branch, perm_code, *, type_, title, body="", data=None, exclude=None):
    return notify(recipients(branch, perm_code, exclude), branch=branch, type_=type_, title=title, body=body, data=data)


# --- Reordering -----------------------------------------------------------------------------

def reserved_quantity(branch, product) -> int:
    """Base units sitting on held invoices."""
    from apps.sales.models import SaleItem

    return SaleItem.objects.filter(sale__branch=branch, sale__status="held", product=product).aggregate(
        total=Sum("quantity_base"))["total"] or 0


def suggested_reorder_quantity(branch, product, available: int | None = None) -> int:
    """Target stock minus what is free on the shelf and what is already on order."""
    from apps.purchases.selectors import on_order_quantity

    available = sellable_quantity(branch, product) if available is None else available
    target = product.max_stock or max(product.reorder_level * 2, product.min_stock)
    free = available - reserved_quantity(branch, product)
    return max(target - free - on_order_quantity(branch, product), 0)


def evaluate_stock_level(branch, product) -> StockAlert | None:
    """Raise, escalate or reset the stock alert for one medicine. Call after any stock change."""
    live = StockAlert.objects.select_for_update().filter(branch=branch, product=product).exclude(status=ALERT.RESOLVED).first()
    available = sellable_quantity(branch, product)
    breached = product.is_active and product.reorder_level > 0 and available <= product.reorder_level
    if not breached:
        if live:  # stock recovered: reset so the next breach alerts again
            live.status, live.resolved_at = ALERT.RESOLVED, timezone.now()
            live.save(update_fields=["status", "resolved_at", "updated_at"])
        return None
    kind = StockAlert.Kind.OUT if available == 0 else StockAlert.Kind.LOW
    if live is None:
        try:
            with transaction.atomic():
                live = StockAlert.objects.create(
                    branch=branch, product=product, kind=kind, triggered_quantity=available,
                    suggested_quantity=suggested_reorder_quantity(branch, product, available))
        except IntegrityError:  # a concurrent sale raised the same alert first
            return StockAlert.objects.filter(branch=branch, product=product).exclude(status=ALERT.RESOLVED).first()
        _announce(live)
    elif live.kind == StockAlert.Kind.LOW and kind == StockAlert.Kind.OUT:
        live.kind, live.triggered_quantity = kind, available
        live.save(update_fields=["kind", "triggered_quantity", "updated_at"])
        if live.status == ALERT.OPEN:
            _announce(live)
    return live


def _announce(alert: StockAlert) -> None:
    product, unit = alert.product, alert.product.base_unit.name.lower()
    if alert.kind == StockAlert.Kind.OUT:
        title, body = f"Out of stock: {product}", f"No sellable stock left. Suggested order: {alert.suggested_quantity} {unit}(s)."
    else:
        title = f"Low stock: {product}"
        body = f"{alert.triggered_quantity} {unit}(s) left (reorder at {product.reorder_level}). Suggested order: {alert.suggested_quantity}."
    notify_permission(alert.branch, "alerts.act", type_=alert.kind, title=title, body=body,
                      data={"alert_id": alert.pk, "product_id": product.pk, "suggested_quantity": alert.suggested_quantity,
                            "category": "stock_alert", "url": f"medipos://alerts/{alert.pk}"})


@transaction.atomic
def act_on_alert(*, alert_id, branch, user, action: str, quantity: int | None = None) -> StockAlert:
    """Add to Order List / Skip. Safe to repeat: the same action twice changes nothing."""
    from apps.purchases.services import add_to_order_list

    try:
        alert = StockAlert.objects.select_for_update().select_related("product").get(pk=alert_id, branch=branch)
    except StockAlert.DoesNotExist:
        raise serializers.ValidationError("Alert not found.")
    if alert.status == ALERT.RESOLVED:
        raise BusinessError("Stock has already recovered for this medicine.", code="alert_resolved")
    if action == "skip":
        if alert.status == ALERT.ADDED:
            raise BusinessError("This medicine is already on the order list.", code="already_added")
        alert.status = ALERT.SKIPPED
    elif action == "add":
        quantity = alert.suggested_quantity if quantity is None else quantity
        if quantity <= 0:
            raise serializers.ValidationError({"quantity": "Enter the quantity to order."})
        add_to_order_list(branch=branch, product=alert.product, quantity=quantity, user=user, note="From stock alert")
        alert.status, alert.requested_quantity = ALERT.ADDED, quantity
    else:
        raise serializers.ValidationError({"action": "Use add or skip."})
    alert.acted_by, alert.acted_at = user, timezone.now()
    alert.save(update_fields=["status", "requested_quantity", "acted_by", "acted_at", "updated_at"])
    log_action(user=user, action=f"alert.{action}", obj=alert, branch=branch, summary=str(alert.product),
               changes={"quantity": quantity})
    return alert
