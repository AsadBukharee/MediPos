import json

from django.core.serializers.json import DjangoJSONEncoder

from .models import AuditLog


def _client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def log_action(*, user, action, obj=None, branch=None, summary="", changes=None, request=None) -> AuditLog:
    """Append an audit record. Called from services so every business operation leaves a trail."""
    safe_changes = json.loads(json.dumps(changes or {}, cls=DjangoJSONEncoder))
    return AuditLog.objects.create(
        user=user if getattr(user, "pk", None) else None,
        branch=branch if branch is not None else getattr(request, "branch", None),
        action=action,
        object_type=obj._meta.label_lower if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        summary=summary[:255],
        changes=safe_changes,
        ip_address=_client_ip(request),
    )


def diff_instance(instance, new_values: dict) -> dict:
    """{field: [old, new]} for the fields that actually change."""
    changes = {}
    for field, new in new_values.items():
        old = getattr(instance, field, None)
        old_cmp = getattr(old, "pk", old)
        new_cmp = getattr(new, "pk", new)
        if old_cmp != new_cmp:
            changes[field] = [old_cmp, new_cmp]
    return changes
