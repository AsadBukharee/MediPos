from pathlib import Path

from django.conf import settings
from rest_framework import serializers

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_upload(upload, *, images_only: bool = False):
    """Reject oversized files and anything that is not an allowed type."""
    if upload is None:
        return upload
    allowed = IMAGE_EXTENSIONS if images_only else settings.ALLOWED_UPLOAD_EXTENSIONS
    if Path(upload.name).suffix.lower() not in allowed:
        raise serializers.ValidationError(f"Allowed file types: {', '.join(sorted(allowed))}.")
    if upload.size > settings.MAX_UPLOAD_BYTES:
        raise serializers.ValidationError("The file is too large.")
    return upload
