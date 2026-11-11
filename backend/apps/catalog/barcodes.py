"""GTIN (EAN-8 / UPC-A / EAN-13 / GTIN-14) validation and in-store EAN-13 generation."""
from django.db import transaction

GTIN_LENGTHS = {8, 12, 13, 14}
INTERNAL_PREFIX = "20"  # GS1 reserves prefixes 20-29 for in-store numbering


def gtin_check_digit(body: str) -> int:
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def is_valid_gtin(code: str) -> bool:
    return code.isdigit() and len(code) in GTIN_LENGTHS and gtin_check_digit(code[:-1]) == int(code[-1])


def clean_barcode(code: str) -> str:
    return "".join(str(code or "").split())


def generate_internal_ean13() -> str:
    from .models import Barcode

    with transaction.atomic():
        last = (
            Barcode.objects.select_for_update()
            .filter(code__startswith=INTERNAL_PREFIX, code__regex=r"^\d{13}$")
            .order_by("-code")
            .first()
        )
        sequence = int(last.code[2:12]) + 1 if last else 1
        body = f"{INTERNAL_PREFIX}{sequence:010d}"
        return body + str(gtin_check_digit(body))
