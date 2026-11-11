from decimal import Decimal

from rest_framework import serializers

from apps.common.exceptions import BusinessError

from .models import BranchPrice, Product, ProductPackaging


def to_base_units(packaging: ProductPackaging, quantity: int) -> int:
    """Convert a whole number of packs to base units. Fractions of a pack are never accepted."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise serializers.ValidationError("Quantity must be a whole number of the chosen unit.")
    if quantity <= 0:
        raise serializers.ValidationError("Quantity must be greater than zero.")
    return quantity * packaging.factor


def get_packaging(product: Product, packaging_id) -> ProductPackaging:
    """The requested packaging, or the base unit packaging when none is given."""
    packagings = list(product.packagings.all())
    if packaging_id is None:
        for packaging in packagings:
            if packaging.factor == 1:
                return packaging
        raise BusinessError(f"{product} has no base-unit packaging configured.", code="no_packaging")
    for packaging in packagings:
        if packaging.pk == packaging_id:
            return packaging
    raise serializers.ValidationError(f"Packaging {packaging_id} does not belong to {product}.")


def base_unit_price(product: Product, branch, *, batch=None, tier: str = "retail") -> Decimal:
    """Selling price per base unit: wholesale tier → batch price → branch price → product price."""
    if tier == "wholesale" and product.wholesale_price > 0:
        return product.wholesale_price
    if batch is not None and batch.selling_price is not None:
        return batch.selling_price
    override = BranchPrice.objects.filter(product=product, branch=branch).values_list("retail_price", flat=True).first()
    return override if override is not None else product.retail_price
