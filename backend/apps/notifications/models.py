from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel


class DeviceToken(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=10, default="android")


class Notification(models.Model):
    class Push(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Not sent"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    type = models.CharField(max_length=40, db_index=True)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500, blank=True)
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    push_status = models.CharField(max_length=10, choices=Push.choices, default=Push.PENDING, db_index=True)
    push_attempts = models.PositiveSmallIntegerField(default=0)
    push_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at"])]


class NotificationPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    type = models.CharField(max_length=40)
    in_app = models.BooleanField(default=True)
    push = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "type"], name="uniq_notification_preference")]


class StockAlert(TimeStampedModel):
    class Kind(models.TextChoices):
        LOW = "low_stock", "Low stock"
        OUT = "out_of_stock", "Out of stock"

    class Status(models.TextChoices):
        OPEN = "open", "Waiting for a decision"
        ADDED = "added", "Added to order list"
        SKIPPED = "skipped", "Skipped"
        RESOLVED = "resolved", "Stock recovered"

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="stock_alerts")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="stock_alerts")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    triggered_quantity = models.BigIntegerField(help_text="Sellable base units when the alert fired.")
    suggested_quantity = models.PositiveIntegerField(default=0)
    requested_quantity = models.PositiveIntegerField(null=True, blank=True)
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acted_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One live alert per medicine per branch: the same low-stock condition never alerts twice.
            models.UniqueConstraint(fields=["branch", "product"], condition=~Q(status="resolved"), name="one_live_stock_alert"),
        ]


class ExpiryAlert(models.Model):
    """Remembers which expiry warning was already sent for a batch (window 0 = expired)."""

    batch = models.ForeignKey("inventory.Batch", on_delete=models.CASCADE, related_name="expiry_alerts")
    window_days = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["batch", "window_days"], name="uniq_expiry_alert")]
