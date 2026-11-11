import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.services import log_action
from apps.common.api import MasterDataViewSet
from apps.common.uploads import validate_upload

from .barcodes import clean_barcode, generate_internal_ean13, is_valid_gtin
from .models import Barcode, BranchPrice, Category, Manufacturer, Product, ProductPackaging, Unit


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ManufacturerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = ["id", "name"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "abbreviation"]


class PackagingSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    class Meta:
        model = ProductPackaging
        fields = ["id", "unit", "unit_name", "factor", "is_default_sale", "is_default_purchase", "can_sell"]


class BarcodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Barcode
        fields = ["id", "product", "packaging", "code", "is_primary"]

    def validate_code(self, value):
        code = clean_barcode(value)
        if not code:
            raise serializers.ValidationError("Barcode is empty.")
        if code.isdigit() and len(code) in (8, 12, 13, 14) and not is_valid_gtin(code):
            raise serializers.ValidationError("Check digit is wrong for an EAN/UPC/GTIN barcode.")
        return code

    def validate(self, attrs):
        packaging = attrs.get("packaging")
        product = attrs.get("product") or getattr(self.instance, "product", None)
        if packaging and product and packaging.product_id != product.pk:
            raise serializers.ValidationError({"packaging": "Packaging belongs to another product."})
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    packagings = PackagingSerializer(many=True, required=False)
    barcodes = BarcodeSerializer(many=True, read_only=True)
    base_unit_name = serializers.CharField(source="base_unit.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    manufacturer_name = serializers.CharField(source="manufacturer.name", read_only=True, default="")
    allow_duplicate = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Product
        fields = [
            "id", "name", "generic_name", "brand", "manufacturer", "manufacturer_name", "category", "category_name",
            "strength", "dosage_form", "sku", "description", "image", "requires_prescription", "is_active",
            "base_unit", "base_unit_name", "purchase_price", "retail_price", "wholesale_price", "tax_rate",
            "max_discount_percent", "min_stock", "reorder_level", "max_stock", "preferred_supplier",
            "packagings", "barcodes", "allow_duplicate",
        ]

    def validate_image(self, value):
        return validate_upload(value, images_only=True)

    def validate(self, attrs):
        instance = self.instance
        get = lambda name: attrs.get(name, getattr(instance, name, None))  # noqa: E731
        manufacturer = get("manufacturer")
        key = Product.build_duplicate_key(get("name"), get("strength"), get("dosage_form"), getattr(manufacturer, "pk", None))
        duplicates = Product.objects.filter(duplicate_key=key)
        if instance:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists() and not attrs.get("allow_duplicate"):
            raise serializers.ValidationError({
                "name": "A medicine with the same name, strength, form and manufacturer already exists.",
                "duplicates": list(duplicates.values_list("id", flat=True)),
            })
        reorder, minimum, maximum = get("reorder_level") or 0, get("min_stock") or 0, get("max_stock") or 0
        if maximum and maximum < max(reorder, minimum):
            raise serializers.ValidationError({"max_stock": "Maximum stock must be above the reorder and minimum levels."})
        return attrs

    def _sync_packagings(self, product, rows, user):
        """Create/update packs; record every conversion change so history is never lost."""
        if not any(row["factor"] == 1 and row["unit"] == product.base_unit for row in rows):
            rows = [{"unit": product.base_unit, "factor": 1, "is_default_sale": not rows, "is_default_purchase": not rows}] + rows
        existing = {p.unit_id: p for p in product.packagings.all()}
        for row in rows:
            row = {k: v for k, v in row.items() if k != "id"}
            unit = row["unit"]
            if unit == product.base_unit and row["factor"] != 1:
                raise serializers.ValidationError({"packagings": "The base unit must have a factor of 1."})
            current = existing.get(unit.pk)
            if current is None:
                packaging = ProductPackaging.objects.create(product=product, **row)
                log_action(user=user, action="packaging.create", obj=packaging, summary=f"{product}: {packaging}",
                           changes={"factor": [None, packaging.factor]})
            else:
                if current.factor != row["factor"]:
                    from apps.inventory.models import Batch

                    if Batch.objects.filter(product=product, quantity_on_hand__gt=0).exists() and current.factor == 1:
                        raise serializers.ValidationError({"packagings": "The base unit cannot change while stock exists."})
                    log_action(user=user, action="packaging.update", obj=current, summary=f"{product}: {current}",
                               changes={"factor": [current.factor, row["factor"]]})
                for field, value in row.items():
                    setattr(current, field, value)
                current.save()

    @transaction.atomic
    def create(self, validated_data):
        packagings = validated_data.pop("packagings", [])
        validated_data.pop("allow_duplicate", None)
        product = super().create(validated_data)
        self._sync_packagings(product, packagings, self.context["request"].user)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        packagings = validated_data.pop("packagings", None)
        validated_data.pop("allow_duplicate", None)
        if "base_unit" in validated_data and validated_data["base_unit"] != instance.base_unit:
            raise serializers.ValidationError({"base_unit": "The base unit cannot be changed after creation."})
        product = super().update(instance, validated_data)
        if packagings is not None:
            self._sync_packagings(product, packagings, self.context["request"].user)
        return product


class CatalogBase(MasterDataViewSet):
    read_perm = "catalog.view"
    write_perm = "catalog.manage"


class CategoryViewSet(CatalogBase):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields = ["name"]


class ManufacturerViewSet(CatalogBase):
    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer
    search_fields = ["name"]


class UnitViewSet(CatalogBase):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    search_fields = ["name"]


class BarcodeViewSet(CatalogBase):
    queryset = Barcode.objects.select_related("product")
    serializer_class = BarcodeSerializer
    filterset_fields = ["product"]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Create an in-store EAN-13 for a product (optionally for one of its packs)."""
        with transaction.atomic():
            data = {**request.data, "code": generate_internal_ean13()}
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


EXPORT_COLUMNS = ["sku", "name", "generic_name", "brand", "manufacturer", "category", "strength", "dosage_form",
                  "base_unit", "purchase_price", "retail_price", "wholesale_price", "tax_rate", "min_stock",
                  "reorder_level", "max_stock", "requires_prescription", "barcode"]


class ProductViewSet(CatalogBase):
    queryset = Product.objects.select_related("base_unit", "category", "manufacturer").prefetch_related(
        "packagings__unit", "barcodes")
    serializer_class = ProductSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    search_fields = ["name", "generic_name", "brand", "sku", "barcodes__code"]
    filterset_fields = ["category", "manufacturer", "is_active", "requires_prescription"]
    ordering_fields = ["name", "sku", "retail_price"]
    http_method_names = ["get", "post", "patch", "head", "options"]  # medicines are deactivated, not deleted

    def get_queryset(self):
        return super().get_queryset().distinct()

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        """Exact barcode (or SKU) lookup used by scanners."""
        code = clean_barcode(request.query_params.get("barcode", ""))
        if not code:
            raise serializers.ValidationError({"barcode": "This query parameter is required."})
        barcode = Barcode.objects.select_related("product").filter(code=code, product__is_active=True).first()
        product = barcode.product if barcode else Product.objects.filter(sku__iexact=code, is_active=True).first()
        if product is None:
            return Response({"detail": "No medicine matches this barcode."}, status=status.HTTP_404_NOT_FOUND)
        product = self.get_queryset().get(pk=product.pk)
        data = self.get_serializer(product).data
        data["scanned_packaging"] = barcode.packaging_id if barcode else None
        return Response(data)

    @action(detail=False, methods=["get"])
    def duplicates(self, request):
        q = request.query_params
        key = Product.build_duplicate_key(q.get("name"), q.get("strength"), q.get("dosage_form"), q.get("manufacturer"))
        return Response(self.get_serializer(self.get_queryset().filter(duplicate_key=key), many=True).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="medicines.csv"'
        writer = csv.writer(response)
        writer.writerow(EXPORT_COLUMNS)
        for p in self.filter_queryset(self.get_queryset()):
            primary = next(iter(p.barcodes.all()), None)
            writer.writerow([
                p.sku, p.name, p.generic_name, p.brand, p.manufacturer.name if p.manufacturer else "",
                p.category.name if p.category else "", p.strength, p.dosage_form, p.base_unit.name,
                p.purchase_price, p.retail_price, p.wholesale_price, p.tax_rate, p.min_stock, p.reorder_level,
                p.max_stock, "yes" if p.requires_prescription else "no", primary.code if primary else "",
            ])
        return response

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_csv(self, request):
        """Upsert medicines by SKU from a CSV with the same columns as the export."""
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "Upload a CSV file."})
        if upload.size > 5 * 1024 * 1024:
            raise serializers.ValidationError({"file": "The file is larger than 5 MB."})
        try:
            rows = list(csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig"))))
        except UnicodeDecodeError:
            raise serializers.ValidationError({"file": "The file must be UTF-8 encoded CSV."})
        created = updated = 0
        errors = []
        for line, row in enumerate(rows, start=2):
            try:
                with transaction.atomic():
                    was_created = self._import_row({k: (v or "").strip() for k, v in row.items() if k})
                created += was_created
                updated += not was_created
            except (serializers.ValidationError, InvalidOperation, ValueError) as exc:
                errors.append({"line": line, "error": str(getattr(exc, "detail", exc))})
        log_action(user=request.user, action="catalog.import", request=request,
                   summary=f"{created} created, {updated} updated, {len(errors)} failed")
        return Response({"created": created, "updated": updated, "errors": errors})

    def _import_row(self, row) -> bool:
        if not row.get("sku") or not row.get("name"):
            raise serializers.ValidationError("sku and name are required.")
        unit, _ = Unit.objects.get_or_create(
            name__iexact=row.get("base_unit") or "Tablet",
            defaults={"name": row.get("base_unit") or "Tablet", "abbreviation": (row.get("base_unit") or "tab")[:6]},
        )
        values = {
            "name": row["name"], "generic_name": row.get("generic_name", ""), "brand": row.get("brand", ""),
            "strength": row.get("strength", ""), "dosage_form": row.get("dosage_form", ""),
            "requires_prescription": row.get("requires_prescription", "").lower() in {"yes", "true", "1"},
        }
        for field in ["purchase_price", "retail_price", "wholesale_price", "tax_rate"]:
            if row.get(field):
                values[field] = Decimal(row[field])
        for field in ["min_stock", "reorder_level", "max_stock"]:
            if row.get(field):
                values[field] = int(row[field])
        if row.get("manufacturer"):
            values["manufacturer"] = Manufacturer.objects.get_or_create(name=row["manufacturer"])[0]
        if row.get("category"):
            values["category"] = Category.objects.get_or_create(name=row["category"])[0]
        product = Product.objects.filter(sku=row["sku"]).first()
        created = product is None
        if created:
            product = Product(sku=row["sku"], base_unit=unit)
        for field, value in values.items():
            setattr(product, field, value)
        product.full_clean(exclude=["duplicate_key", "image"])
        product.save()
        ProductPackaging.objects.get_or_create(
            product=product, unit=product.base_unit,
            defaults={"factor": 1, "is_default_sale": True, "is_default_purchase": True})
        code = clean_barcode(row.get("barcode", ""))
        if code and not Barcode.objects.filter(code=code).exists():
            Barcode.objects.create(product=product, code=code, is_primary=not product.barcodes.exists())
        return created


class BranchPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchPrice
        fields = ["id", "product", "branch", "retail_price"]


class BranchPriceViewSet(CatalogBase):
    serializer_class = BranchPriceSerializer
    queryset = BranchPrice.objects.none()  # for schema generation; see get_queryset
    filterset_fields = ["product", "branch"]

    def get_queryset(self):
        return BranchPrice.objects.filter(branch__in=self.request.user.accessible_branches()).order_by("id")

    def perform_create(self, serializer):
        if not self.request.user.can_access_branch(serializer.validated_data["branch"]):
            raise serializers.ValidationError({"branch": "You do not have access to this branch."})
        super().perform_create(serializer)
