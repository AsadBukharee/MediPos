from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.common.exceptions import BusinessError, InsufficientStock
from apps.inventory import services as inventory
from apps.inventory.models import Batch, StockMovement
from apps.inventory.selectors import sellable_quantity
from apps.inventory.services import Source

from .conftest import days

pytestmark = pytest.mark.django_db


def test_fefo_takes_the_earliest_expiry_first(branch, product, stock, owner):
    late = stock(branch, product, 50, "LATE", days(300))
    early = stock(branch, product, 30, "EARLY", days(40))
    allocations = inventory.issue_stock(branch=branch, product=product, quantity=40, user=owner, source=Source("test"))
    assert [(a.batch.batch_number, a.quantity) for a in allocations] == [("EARLY", 30), ("LATE", 10)]
    early.refresh_from_db(), late.refresh_from_db()
    assert (early.quantity_on_hand, late.quantity_on_hand) == (0, 40)


def test_fifo_policy_uses_receipt_order(branch, product, stock, owner):
    from apps.branches.models import BusinessProfile

    profile = BusinessProfile.get()
    profile.stock_issue_policy = "fifo"
    profile.save()
    stock(branch, product, 10, "FIRST-IN", days(300))
    stock(branch, product, 10, "SECOND-IN", days(40))
    allocations = inventory.issue_stock(branch=branch, product=product, quantity=5, user=owner, source=Source("test"))
    assert allocations[0].batch.batch_number == "FIRST-IN"


def test_expired_and_blocked_batches_are_never_issued(branch, product, stock, owner):
    stock(branch, product, 100, "EXPIRED", days(-1))
    stock(branch, product, 100, "TODAY", days(0))
    blocked = stock(branch, product, 100, "BLOCKED", days(200))
    inventory.set_batch_status(batch_id=blocked.pk, branch=branch, status="blocked", reason="recall", user=owner)
    good = stock(branch, product, 5, "GOOD", days(200))
    assert sellable_quantity(branch, product) == 5
    with pytest.raises(InsufficientStock):
        inventory.issue_stock(branch=branch, product=product, quantity=6, user=owner, source=Source("test"))
    with pytest.raises(BusinessError) as expired:
        inventory.issue_stock(branch=branch, product=product, quantity=1, user=owner, source=Source("test"),
                              batch_id=Batch.objects.get(batch_number="EXPIRED").pk)
    assert expired.value.code == "batch_expired"
    good.refresh_from_db()
    assert good.quantity_on_hand == 5  # the failed attempts changed nothing


def test_every_change_writes_an_immutable_ledger_row(branch, product, stock, owner):
    batch = stock(branch, product, 10)
    inventory.issue_stock(branch=branch, product=product, quantity=4, user=owner, source=Source("test"))
    rows = list(StockMovement.objects.filter(batch=batch).order_by("id"))
    assert [(r.quantity, r.balance_after) for r in rows] == [(10, 10), (-4, 6)]
    assert sum(r.quantity for r in rows) == Batch.objects.get(pk=batch.pk).quantity_on_hand
    rows[0].note = "tampered"
    with pytest.raises(RuntimeError):
        rows[0].save()
    with pytest.raises(RuntimeError):
        rows[0].delete()


def test_database_refuses_negative_stock(branch, product, stock):
    batch = stock(branch, product, 1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Batch.objects.filter(pk=batch.pk).update(quantity_on_hand=-1)


def test_stock_is_isolated_per_branch(branch, other_branch, product, stock, owner):
    stock(other_branch, product, 50)
    assert sellable_quantity(branch, product) == 0
    with pytest.raises(InsufficientStock):
        inventory.issue_stock(branch=branch, product=product, quantity=1, user=owner, source=Source("test"))


def test_adjustment_needs_approval_by_someone_else(branch, product, stock, make_user, api):
    batch = stock(branch, product, 20)
    manager = make_user("inventory_manager")
    admin = make_user("branch_admin")
    payload = {"reason": "damaged", "note": "broken strip", "items": [{"batch": batch.pk, "quantity_delta": -5}]}
    created = api(manager, branch).post("/api/v1/inventory/adjustments/", payload, format="json")
    assert created.status_code == 201, created.data
    batch.refresh_from_db()
    assert batch.quantity_on_hand == 20  # pending: nothing posted yet

    url = f"/api/v1/inventory/adjustments/{created.data['id']}/approve/"
    assert api(manager, branch).post(url).status_code == 403  # role cannot approve
    assert api(admin, branch).post(url).status_code == 200
    batch.refresh_from_db()
    assert batch.quantity_on_hand == 15
    assert api(admin, branch).post(url).status_code == 409  # cannot be posted twice
    batch.refresh_from_db()
    assert batch.quantity_on_hand == 15


def test_unit_conversion_rejects_fractions(product):
    from rest_framework.exceptions import ValidationError

    from apps.catalog.services import to_base_units

    assert to_base_units(product.box, 2) == 200
    assert to_base_units(product.strip, 3) == 30
    for bad in (1.5, Decimal("0.5"), 0, -1, True):
        with pytest.raises(ValidationError):
            to_base_units(product.strip, bad)
