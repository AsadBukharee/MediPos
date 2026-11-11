from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel

PRICE = {"max_digits": 14, "decimal_places": 4}
PERCENT = {"max_digits": 5, "decimal_places": 2}
percent_validators = [MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]


class Category(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Manufacturer(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Unit(TimeStampedModel):
    """A unit of measure or pack: tablet, strip, box, carton, bottle, ml..."""

    name = models.CharField(max_length=40, unique=True)
    abbreviation = models.CharField(max_length=12)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


class Product(TimeStampedModel):
    name = models.CharField(max_length=200, db_index=True)
    generic_name = models.CharField(max_length=200, blank=True, db_index=True)
    brand = models.CharField(max_length=120, blank=True)
    manufacturer = models.ForeignKey(Manufacturer, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    strength = models.CharField(max_length=60, blank=True)
    dosage_form = models.CharField(max_length=60, blank=True)
    sku = models.CharField(max_length=40, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/", null=True, blank=True)
    requires_prescription = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Stock is always counted in the base unit (the smallest sellable unit), as whole numbers.
    base_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    # Prices are per base unit.
    purchase_price = models.DecimalField(**PRICE, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    retail_price = models.DecimalField(**PRICE, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    wholesale_price = models.DecimalField(**PRICE, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    tax_rate = models.DecimalField(**PERCENT, default=Decimal("0"), validators=percent_validators)
    max_discount_percent = models.DecimalField(**PERCENT, default=Decimal("100"), validators=percent_validators)

    # Reorder policy, in base units.
    min_stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    max_stock = models.PositiveIntegerField(default=0, help_text="Target stock after reordering.")
    preferred_supplier = models.ForeignKey(
        "suppliers.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="preferred_products"
    )

    duplicate_key = models.CharField(max_length=420, editable=False, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return " ".join(part for part in [self.name, self.strength] if part)

    def save(self, *args, **kwargs):
        self.duplicate_key = self.build_duplicate_key(self.name, self.strength, self.dosage_form, self.manufacturer_id)
        super().save(*args, **kwargs)

    @staticmethod
    def build_duplicate_key(name, strength, dosage_form, manufacturer_id) -> str:
        return "|".join([normalize(name), normalize(strength), normalize(dosage_form), str(manufacturer_id or "")])


class ProductPackaging(TimeStampedModel):
    """How many base units a pack holds, e.g. Strip = 10 tablets, Box = 100 tablets."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="packagings")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    factor = models.PositiveIntegerField(help_text="Base units in one of this unit. 1 for the base unit itself.")
    is_default_sale = models.BooleanField(default=False)
    is_default_purchase = models.BooleanField(default=False)
    can_sell = models.BooleanField(default=True)

    class Meta:
        ordering = ["factor"]
        constraints = [
            models.UniqueConstraint(fields=["product", "unit"], name="uniq_packaging_unit"),
            models.CheckConstraint(condition=Q(factor__gte=1), name="packaging_factor_positive"),
        ]

    def __str__(self):
        return f"{self.unit.name} x{self.factor}"


class Barcode(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="barcodes")
    packaging = models.ForeignKey(ProductPackaging, null=True, blank=True, on_delete=models.CASCADE, related_name="barcodes")
    code = models.CharField(max_length=64, unique=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "code"]

    def __str__(self):
        return self.code


class BranchPrice(TimeStampedModel):
    """Optional branch-specific retail price (per base unit)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="branch_prices")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="prices")
    retail_price = models.DecimalField(**PRICE, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "branch"], name="uniq_branch_price")]
