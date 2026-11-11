import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import DeviceToken, ExpiryAlert, Notification
from .push import PushNotConfigured, send_push

logger = logging.getLogger(__name__)
PUSH = Notification.Push


@shared_task
def send_push_task(notification_id: int) -> str:
    notification = Notification.objects.filter(pk=notification_id).first()
    if notification is None or notification.push_status in (PUSH.SENT, PUSH.SKIPPED):
        return "noop"
    tokens = list(DeviceToken.objects.filter(user_id=notification.user_id).values_list("token", flat=True))
    if not tokens:
        notification.push_status = PUSH.SKIPPED
        notification.save(update_fields=["push_status"])
        return "no-device"
    try:
        delivered, invalid = send_push(tokens, notification.title, notification.body,
                                       {**notification.data, "notification_id": notification.pk})
        if invalid:
            DeviceToken.objects.filter(token__in=invalid).delete()
        notification.push_status = PUSH.SENT if delivered else PUSH.FAILED
        notification.push_error = "" if delivered else "No device accepted the message."
    except PushNotConfigured as exc:
        notification.push_status, notification.push_error = PUSH.SKIPPED, str(exc)[:255]
    except Exception as exc:  # network or FCM error: keep it for the retry job
        logger.exception("Push failed for notification %s", notification_id)
        notification.push_status, notification.push_error = PUSH.FAILED, str(exc)[:255]
    notification.push_attempts += 1
    notification.save(update_fields=["push_status", "push_error", "push_attempts"])
    return notification.push_status


@shared_task
def retry_failed_push() -> int:
    recent = timezone.now() - timedelta(days=1)
    ids = list(Notification.objects.filter(
        push_status=PUSH.FAILED, push_attempts__lt=settings.PUSH_MAX_ATTEMPTS, created_at__gte=recent
    ).values_list("pk", flat=True)[:500])
    for pk in ids:
        send_push_task.delay(pk)
    return len(ids)


@shared_task
def scan_stock_levels() -> int:
    """Safety net: re-check every medicine with a reorder level (alerts normally fire on the stock change itself)."""
    from apps.branches.models import Branch
    from apps.catalog.models import Product

    from .services import evaluate_stock_level

    checked = 0
    for branch in Branch.objects.filter(is_active=True):
        for product in Product.objects.filter(is_active=True, reorder_level__gt=0).select_related("base_unit"):
            with transaction.atomic():
                evaluate_stock_level(branch, product)
            checked += 1
    return checked


@shared_task
def scan_expiry() -> int:
    """Near-expiry (per configured window) and expired-stock alerts, sent once per batch and window."""
    from apps.branches.models import Branch, BusinessProfile
    from apps.inventory.models import Batch

    from .services import notify_permission

    today = timezone.localdate()
    windows = sorted(BusinessProfile.get().near_expiry_days or [30, 60, 90])
    sent = 0
    for branch in Branch.objects.filter(is_active=True):
        fresh: dict[int, list] = {}
        batches = Batch.objects.filter(branch=branch, quantity_on_hand__gt=0,
                                       expiry_date__lte=today + timedelta(days=windows[-1])).select_related("product")
        for batch in batches:
            days_left = (batch.expiry_date - today).days
            window = 0 if days_left <= 0 else next(w for w in windows if days_left <= w)
            _, created = ExpiryAlert.objects.get_or_create(batch=batch, window_days=window)
            if created:
                fresh.setdefault(window, []).append(batch)
        for window, items in fresh.items():
            names = ", ".join(f"{b.product} ({b.batch_number})" for b in items[:3])
            more = f" and {len(items) - 3} more" if len(items) > 3 else ""
            with transaction.atomic():
                if window == 0:
                    notify_permission(branch, "inventory.view", type_="expired_stock",
                                      title=f"{len(items)} batch(es) have expired", body=f"{names}{more}",
                                      data={"url": "medipos://expiry", "window": 0})
                else:
                    notify_permission(branch, "inventory.view", type_="near_expiry",
                                      title=f"{len(items)} batch(es) expire within {window} days", body=f"{names}{more}",
                                      data={"url": "medipos://expiry", "window": window})
            sent += 1
    return sent
