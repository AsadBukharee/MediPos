from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessError(APIException):
    """A business rule was violated (e.g. insufficient stock, expired batch)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "business_rule"
    default_detail = "The operation violates a business rule."

    def __init__(self, detail=None, code=None):
        super().__init__(detail=detail, code=code or self.default_code)
        self.code = code or self.default_code


class InsufficientStock(BusinessError):
    default_code = "insufficient_stock"
    default_detail = "Not enough sellable stock."


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.messages)
    response = drf_exception_handler(exc, context)
    if response is None and isinstance(exc, IntegrityError):
        return Response(
            {"detail": "The change conflicts with existing data.", "code": "integrity_error"},
            status=status.HTTP_409_CONFLICT,
        )
    if response is not None and isinstance(exc, BusinessError):
        response.data = {"detail": str(exc.detail), "code": exc.code}
    return response
