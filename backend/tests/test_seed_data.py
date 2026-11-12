"""The sample data has to be data the app itself would accept: stock, books and ledger in step."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db.models import Sum

from apps.accounting.models import JournalEntry
from apps.accounting.services import INVENTORY, account_balance, trial_balance
from apps.branches.models import Branch
from apps.catalog.models import Barcode, Category, Manufacturer, Product, ProductPackaging, Unit
from apps.catalog.barcodes import is_valid_gtin
from apps.customers.models import Customer
from apps.inventory.models import Batch, StockMovement
from apps.inventory.selectors import stock_value
from apps.notifications.models import StockAlert
from apps.purchases.models import GoodsReceivedNote, PurchaseOrder
from apps.sales.models import Sale, SaleReturn
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def seeded(django_db_setup, django_db_blocker):
    """Seed once for the whole module; the assertions below only read.

    The seeder commits, so the rows outlive a test transaction: empty the database again
    afterwards or the next module starts with a branch and a catalogue it did not create.
    """
    with django_db_blocker.unblock():
        call_command("seed_data", days=3, password="Seeded-pass-2026", no_images=True, force=True, verbosity=0)
        yield
        call_command("flush", interactive=False, allow_cascade=True, verbosity=0)


def test_every_kind_of_master_record_is_there(seeded):
    assert Product.objects.count() >= 10
    assert Unit.objects.count() >= 10
    assert Category.objects.count() >= 10
    assert Manufacturer.objects.count() >= 10
    assert Supplier.objects.count() >= 10
    assert Customer.objects.count() >= 10
    assert get_user_model().objects.count() >= 10
    assert Branch.objects.count() >= 3
    assert {user.role for user in get_user_model().objects.all()} >= {
        "owner", "branch_admin", "pharmacist", "cashier", "inventory_manager",
        "purchase_officer", "accountant", "auditor"}


def test_the_catalogue_is_usable(seeded):
    for product in Product.objects.prefetch_related("packagings", "barcodes"):
        packs = list(product.packagings.all())
        assert any(pack.factor == 1 and pack.unit_id == product.base_unit_id for pack in packs), product
        assert product.duplicate_key, f"{product} has no duplicate key, so duplicate detection would miss it"
        assert product.retail_price > product.purchase_price, product
    assert ProductPackaging.objects.count() >= 30
    codes = list(Barcode.objects.values_list("code", flat=True))
    assert len(codes) >= 10 and len(set(codes)) == len(codes)
    assert all(is_valid_gtin(code) for code in codes)


def test_there_is_a_trading_history_in_every_state(seeded):
    assert Sale.objects.filter(status="completed").count() >= 30
    assert Sale.objects.filter(status="held").exists()
    assert SaleReturn.objects.count() >= 5
    assert GoodsReceivedNote.objects.filter(status="confirmed").count() >= 3
    assert GoodsReceivedNote.objects.filter(status="draft").exists()
    assert PurchaseOrder.objects.filter(status="draft").exists()
    assert PurchaseOrder.objects.exclude(status="draft").exists()
    assert StockAlert.objects.filter(status="added").exists()
    # History was backdated, not all stamped today.
    assert Sale.objects.dates("completed_at", "day").count() >= 3


def test_stock_books_and_ledger_agree(seeded):
    branches = list(Branch.objects.all())
    rows = trial_balance(branches=branches)
    assert sum(row["debit"] for row in rows) == sum(row["credit"] for row in rows)

    # Every unit on a shelf arrived through the ledger, and nothing is negative.
    assert StockMovement.objects.aggregate(total=Sum("quantity"))["total"] == \
        Batch.objects.aggregate(total=Sum("quantity_on_hand"))["total"]
    assert not Batch.objects.filter(quantity_on_hand__lt=0).exists()

    valuation = sum((stock_value(branch) for branch in branches), Decimal("0"))
    assert valuation.quantize(Decimal("0.01")) == account_balance(INVENTORY, branches)
    assert not JournalEntry.objects.filter(lines__isnull=True).exists()


def test_it_refuses_to_run_over_live_data(seeded, settings):
    settings.DEBUG = True  # otherwise the "development only" guard answers first
    with pytest.raises(CommandError, match="already has sales"):
        call_command("seed_data", days=1, force=False, verbosity=0)


def test_it_refuses_to_run_outside_development(seeded, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="meant for development"):
        call_command("seed_data", days=1, verbosity=0)
