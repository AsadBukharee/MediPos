from decimal import Decimal

import pytest

from apps.accounting.services import PAYABLE, account_balance
from apps.common.exceptions import BusinessError
from apps.inventory.models import Batch, StockMovement
from apps.inventory.selectors import sellable_quantity
from apps.purchases import services as purchases
from apps.purchases.selectors import on_order_quantity
from apps.suppliers.services import pay_supplier, supplier_balance

from .conftest import days

pytestmark = pytest.mark.django_db


def make_order(branch, owner, supplier, product, boxes=5):
    return purchases.save_purchase_order(branch=branch, user=owner, supplier=supplier, items=[
        {"product": product, "packaging": product.box, "quantity": boxes, "unit_price": Decimal("100.00")}])


def receive(branch, owner, supplier, product, boxes, order=None, batch="G1"):
    line = {"product": product, "packaging": product.box, "quantity": boxes, "unit_cost": Decimal("100.00"),
            "batch_number": batch, "expiry_date": days(400)}
    if order is not None:
        line["po_item"] = order.items.get()
    return purchases.save_grn(branch=branch, user=owner, supplier=supplier, purchase_order=order, items=[line])


def test_purchase_order_never_changes_stock(branch, owner, supplier, product):
    order = make_order(branch, owner, supplier, product)
    purchases.transition_purchase_order(order_id=order.pk, branch=branch, user=owner, action="approve")
    purchases.transition_purchase_order(order_id=order.pk, branch=branch, user=owner, action="mark_ordered")
    assert sellable_quantity(branch, product) == 0
    assert not StockMovement.objects.exists()
    assert on_order_quantity(branch, product) == 500


def test_draft_grn_does_nothing_and_confirm_posts_exactly_once(branch, owner, supplier, product):
    grn = receive(branch, owner, supplier, product, 2)
    assert sellable_quantity(branch, product) == 0  # draft: no stock, no accounts
    assert account_balance(PAYABLE, [branch]) == 0

    purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=owner)
    purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=owner)  # duplicate click / retry
    assert sellable_quantity(branch, product) == 200
    assert StockMovement.objects.filter(source_type="grn", source_id=grn.pk).count() == 1
    assert account_balance(PAYABLE, [branch]) == Decimal("200.00")
    batch = Batch.objects.get(product=product)
    assert batch.purchase_cost == Decimal("1.000000") and batch.grn_id == grn.pk
    with pytest.raises(BusinessError):
        purchases.cancel_grn(grn_id=grn.pk, branch=branch, user=owner)


def test_partial_receiving_updates_the_order(branch, owner, supplier, product):
    order = make_order(branch, owner, supplier, product, boxes=5)
    with pytest.raises(BusinessError):  # not approved yet
        receive(branch, owner, supplier, product, 2, order)
    purchases.transition_purchase_order(order_id=order.pk, branch=branch, user=owner, action="approve")
    first = receive(branch, owner, supplier, product, 2, order)
    purchases.confirm_grn(grn_id=first.pk, branch=branch, user=owner)
    order.refresh_from_db()
    assert order.status == "partially_received" and on_order_quantity(branch, product) == 300
    second = receive(branch, owner, supplier, product, 3, order, batch="G2")
    purchases.confirm_grn(grn_id=second.pk, branch=branch, user=owner)
    order.refresh_from_db()
    assert order.status == "received" and on_order_quantity(branch, product) == 0


def test_expired_goods_cannot_be_received(branch, owner, supplier, product):
    with pytest.raises(BusinessError) as error:
        purchases.save_grn(branch=branch, user=owner, supplier=supplier, items=[{
            "product": product, "packaging": product.box, "quantity": 1, "unit_cost": Decimal("1"),
            "batch_number": "OLD", "expiry_date": days(-1)}])
    assert error.value.code == "batch_expired"


def test_supplier_balance_payments_and_returns(branch, owner, supplier, product):
    grn = receive(branch, owner, supplier, product, 2)
    purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=owner)
    assert supplier_balance(supplier) == Decimal("200.00")
    pay_supplier(supplier=supplier, branch=branch, user=owner, amount="80", idempotency_key="pay-1")
    pay_supplier(supplier=supplier, branch=branch, user=owner, amount="80", idempotency_key="pay-1")  # retry
    assert supplier_balance(supplier) == Decimal("120.00")
    purchases.create_purchase_return(branch=branch, user=owner, supplier=supplier, reason="short dated",
                                     items=[{"batch": Batch.objects.get(product=product), "quantity": 50}])
    assert supplier_balance(supplier) == Decimal("70.00")
    assert account_balance(PAYABLE, [branch]) == Decimal("70.00")
    assert sellable_quantity(branch, product) == 150
