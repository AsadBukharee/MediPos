"""Development data: a branch, units, a supplier, a few medicines with opening stock.

    python manage.py seed_demo --owner admin --password '<choose one>'
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounting.services import ensure_default_accounts
from apps.branches.models import Branch, BusinessProfile
from apps.catalog.barcodes import generate_internal_ean13
from apps.catalog.models import Barcode, Category, Manufacturer, Product, ProductPackaging, Unit
from apps.inventory import services as inventory
from apps.inventory.models import StockAdjustment
from apps.suppliers.models import Supplier

MEDICINES = [
    # name, generic, strength, form, category, strips per box, tablets per strip, cost/tab, price/tab, rx, reorder
    ("Panadol", "Paracetamol", "500mg", "Tablet", "Analgesics", 20, 10, "1.20", "1.70", False, 200),
    ("Brufen", "Ibuprofen", "400mg", "Tablet", "Analgesics", 3, 10, "2.50", "3.40", False, 120),
    ("Augmentin", "Amoxicillin + Clavulanate", "625mg", "Tablet", "Antibiotics", 1, 6, "38.00", "46.00", True, 60),
    ("Risek", "Omeprazole", "20mg", "Capsule", "Gastro", 2, 7, "14.00", "18.50", False, 70),
    ("Glucophage", "Metformin", "500mg", "Tablet", "Diabetes", 5, 10, "2.10", "2.90", True, 150),
    ("Loprin", "Aspirin", "75mg", "Tablet", "Cardiac", 3, 10, "0.90", "1.30", False, 150),
]


class Command(BaseCommand):
    help = "Load demo master data and opening stock (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--owner", default="", help="Create this owner account if it does not exist.")
        parser.add_argument("--password", default="", help="Password for --owner.")

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        ensure_default_accounts()
        BusinessProfile.get()
        branch, _ = Branch.objects.get_or_create(code="main", defaults={"name": "Main Branch"})

        owner = User.objects.filter(role="owner").first() or User.objects.filter(is_superuser=True).first()
        if options["owner"] and not User.objects.filter(username=options["owner"]).exists():
            if len(options["password"]) < 8:
                raise CommandError("Give --password with at least 8 characters.")
            owner = User.objects.create_user(options["owner"], password=options["password"], role="owner", is_staff=True)
        if owner is None:
            raise CommandError("No owner exists. Run again with --owner and --password.")

        tablet, _ = Unit.objects.get_or_create(name="Tablet", defaults={"abbreviation": "tab"})
        capsule, _ = Unit.objects.get_or_create(name="Capsule", defaults={"abbreviation": "cap"})
        strip, _ = Unit.objects.get_or_create(name="Strip", defaults={"abbreviation": "strip"})
        box, _ = Unit.objects.get_or_create(name="Box", defaults={"abbreviation": "box"})
        for name, abbreviation in [("Carton", "ctn"), ("Bottle", "btl"), ("ml", "ml")]:
            Unit.objects.get_or_create(name=name, defaults={"abbreviation": abbreviation})
        supplier, _ = Supplier.objects.get_or_create(name="Demo Distributors", defaults={"phone": "000-0000000"})
        maker, _ = Manufacturer.objects.get_or_create(name="Demo Pharma")

        created = 0
        for index, (name, generic, strength, form, category, strips, per_strip, cost, price, rx, reorder) in enumerate(MEDICINES, 1):
            sku = f"MED-{index:04d}"
            if Product.objects.filter(sku=sku).exists():
                continue
            base = capsule if form == "Capsule" else tablet
            product = Product.objects.create(
                name=name, generic_name=generic, strength=strength, dosage_form=form, sku=sku, base_unit=base,
                category=Category.objects.get_or_create(name=category)[0], manufacturer=maker,
                purchase_price=Decimal(cost), retail_price=Decimal(price), requires_prescription=rx,
                reorder_level=reorder, min_stock=reorder // 2, max_stock=reorder * 4, preferred_supplier=supplier)
            ProductPackaging.objects.create(product=product, unit=base, factor=1, is_default_sale=True)
            ProductPackaging.objects.create(product=product, unit=strip, factor=per_strip)
            pack = ProductPackaging.objects.create(product=product, unit=box, factor=per_strip * strips, is_default_purchase=True)
            Barcode.objects.create(product=product, packaging=pack, code=generate_internal_ean13(), is_primary=True)
            adjustment = inventory.request_adjustment(
                branch=branch, user=owner, reason=StockAdjustment.Reason.OPENING, note="Demo opening stock",
                items=[{"product": product, "batch_number": f"B{index:03d}A", "unit_cost": Decimal(cost),
                        "expiry_date": timezone.localdate() + timedelta(days=45 + index * 60),
                        "quantity_delta": reorder * 3}])
            inventory.decide_adjustment(adjustment_id=adjustment.pk, branch=branch, user=owner, approve=True)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Demo data ready: branch '{branch.name}', {created} new medicine(s)."))
