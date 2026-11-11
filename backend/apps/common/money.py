from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    """Round to currency precision. All money maths in MediPos uses Decimal."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
