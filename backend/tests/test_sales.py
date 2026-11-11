import threading
from decimal import Decimal

import pytest
from django.db import connection

from apps.accounting.services import INVENTORY, account_balance
from apps.common.exceptions import BusinessError, InsufficientStock
from apps.inventory.models import Batch, StockMovement
from apps.inventory.selectors import sellable_quantity, stock_value
from apps.sales import services as sales
from apps.sales.models import Sale

from .conftest import days

pytestmark = pytest.mark.django_db


def sell(branch, user, product, quantity, packaging=None, pay=None, **extra):
    items = [{"product": product, "packaging": packaging, "quantity": quantity}]
    if pay is None:
        _, totals = sales.price_lines(branch=branch, user=user, customer=extra.get("customer"), items=items,
                                      invoice_discount=extra.get("invoice_discount", 0))
        pay = [{"method": "cash", "amount": totals["total"]}]
    return sales.create_sale(branch=branch, user=user, items=items, payments=pay, **extra)


def test_sale_deducts_stock_by_fefo_and_records_batch_cost(branch, product, stock, cashier):
    stock(branch, product, 30, "EARLY", days(40), cost="1.00")
    stock(branch, product, 100, "LATE", days(300), cost="1.50")
    sale = sell(branch, cashier, product, 4, product.strip)  # 40 tablets
    assert sale.status == "completed" and sale.number.startswith("INV-MAIN-")
    assert sale.total == Decimal("80.00")  # 4 strips x 10 tablets x 2.00
    assert sale.cost_total == Decimal("45.00")  # 30 x 1.00 + 10 x 1.50: actual batch cost
    assert sellable_quantity(branch, product) == 90
    assert StockMovement.objects.filter(source_type="sale", source_id=sale.pk).count() == 2


def test_cannot_oversell(branch, product, stock, cashier):
    stock(branch, product, 5)
    with pytest.raises(InsufficientStock):
        sell(branch, cashier, product, 6, pay=[{"method": "cash", "amount": 100}])
    assert sellable_quantity(branch, product) == 5
    assert not Sale.objects.exists()  # the whole sale rolled back


def test_expired_batch_cannot_be_sold(branch, product, stock, cashier):
    stock(branch, product, 50, "OLD", days(-3))
    with pytest.raises(InsufficientStock):
        sell(branch, cashier, product, 1, pay=[{"method": "cash", "amount": 10}])


def test_duplicate_request_creates_one_sale(branch, product, stock, cashier):
    stock(branch, product, 10)
    first = sell(branch, cashier, product, 2, idempotency_key="abc-123")
    second = sell(branch, cashier, product, 2, idempotency_key="abc-123")
    assert first.pk == second.pk
    assert sellable_quantity(branch, product) == 8


def test_prescription_is_required(branch, make_product, stock, cashier):
    rx = make_product("Augmentin", requires_prescription=True)
    stock(branch, rx, 10)
    with pytest.raises(BusinessError) as error:
        sell(branch, cashier, rx, 1)
    assert error.value.code == "prescription_required"
    assert sell(branch, cashier, rx, 1, prescription_reference="RX-9").status == "completed"


def test_discount_limit_per_user(branch, product, stock, cashier, owner):
    stock(branch, product, 100)
    items = [{"product": product, "packaging": None, "quantity": 10, "discount_amount": Decimal("3.00")}]  # 15%
    with pytest.raises(BusinessError) as error:
        sales.price_lines(branch=branch, user=cashier, customer=None, items=items)  # cashier limit is 10%
    assert error.value.code == "discount_limit"
    _, totals = sales.price_lines(branch=branch, user=owner, customer=None, items=items)
    assert totals["total"] == Decimal("17.00")


def test_split_payment_and_change(branch, product, stock, cashier):
    stock(branch, product, 100)
    sale = sell(branch, cashier, product, 10, pay=[{"method": "card", "amount": "15"}, {"method": "cash", "amount": "10"}])
    assert (sale.paid_total, sale.change_due) == (Decimal("25.00"), Decimal("5.00"))
    with pytest.raises(BusinessError):  # change cannot come out of a card payment
        sell(branch, cashier, product, 10, pay=[{"method": "card", "amount": "25"}])
    with pytest.raises(BusinessError):
        sell(branch, cashier, product, 10, pay=[{"method": "cash", "amount": "19.99"}])


def test_credit_sale_respects_the_credit_limit(branch, product, stock, cashier):
    from apps.customers.models import Customer
    from apps.customers.services import customer_balance

    stock(branch, product, 100)
    customer = Customer.objects.create(name="Ali", credit_limit=Decimal("30"))
    with pytest.raises(BusinessError):
        sell(branch, cashier, product, 10, pay=[{"method": "credit", "amount": "20"}])  # no customer
    sell(branch, cashier, product, 10, customer=customer, pay=[{"method": "credit", "amount": "20"}])
    assert customer_balance(customer) == Decimal("20.00")
    with pytest.raises(BusinessError) as error:
        sell(branch, cashier, product, 10, customer=customer, pay=[{"method": "credit", "amount": "20"}])
    assert error.value.code == "credit_limit"


def test_held_invoice_does_not_touch_stock_until_completed(branch, product, stock, cashier):
    stock(branch, product, 10)
    held = sales.create_sale(branch=branch, user=cashier, items=[{"product": product, "packaging": None, "quantity": 3}], hold=True)
    assert held.status == "held" and held.number is None
    assert sellable_quantity(branch, product) == 10
    done = sales.complete_held_sale(sale_id=held.pk, branch=branch, user=cashier, payments=[{"method": "cash", "amount": "6"}])
    assert done.status == "completed" and sellable_quantity(branch, product) == 7
    again = sales.complete_held_sale(sale_id=held.pk, branch=branch, user=cashier, payments=[{"method": "cash", "amount": "6"}])
    assert again.pk == done.pk and sellable_quantity(branch, product) == 7


def test_partial_and_full_return_preserve_history(branch, product, stock, cashier, owner):
    batch = stock(branch, product, 20)
    sale = sell(branch, cashier, product, 10)
    item = sale.items.get()
    first = sales.create_sale_return(branch=branch, user=owner, sale_id=sale.pk, reason="wrong item",
                                     items=[{"sale_item": item.pk, "quantity_base": 3}])
    assert first.total == Decimal("6.00")
    with pytest.raises(BusinessError) as error:
        sales.create_sale_return(branch=branch, user=owner, sale_id=sale.pk, reason="too many",
                                 items=[{"sale_item": item.pk, "quantity_base": 8}])
    assert error.value.code == "return_exceeds_sale"
    second = sales.create_sale_return(branch=branch, user=owner, sale_id=sale.pk, reason="rest, damaged",
                                      items=[{"sale_item": item.pk, "quantity_base": 7, "restock": False}])
    assert first.total + second.total == sale.total
    batch.refresh_from_db()
    assert batch.quantity_on_hand == 13  # 20 - 10 sold + 3 restocked; the damaged 7 stay off the shelf
    ledger = list(StockMovement.objects.filter(batch=batch).order_by("id").values_list("movement_type", "quantity"))
    assert ledger == [("opening", 20), ("sale", -10), ("sale_return", 3)]  # nothing overwritten
    sale.refresh_from_db()
    assert sale.status == "completed"  # the original invoice is untouched


def test_cancel_reverses_stock_and_accounts(branch, product, stock, cashier, owner):
    stock(branch, product, 20)
    before = account_balance(INVENTORY, [branch])
    sale = sell(branch, cashier, product, 10)
    sales.cancel_sale(sale_id=sale.pk, branch=branch, user=owner, reason="customer left")
    assert sellable_quantity(branch, product) == 20
    assert account_balance(INVENTORY, [branch]) == before
    assert StockMovement.objects.filter(movement_type="sale_cancel").count() == 1


def test_inventory_ledger_reconciles_with_accounts(branch, product, stock, cashier, owner, supplier):
    """Stock valuation, the stock ledger and the Inventory GL account must tell the same story."""
    from apps.purchases import services as purchases

    grn = purchases.save_grn(branch=branch, user=owner, supplier=supplier, items=[{
        "product": product, "packaging": product.box, "quantity": 2, "unit_cost": Decimal("125.00"),
        "batch_number": "G1", "expiry_date": days(200)}])
    purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=owner)
    sale = sell(branch, cashier, product, 3, product.strip)
    sales.create_sale_return(branch=branch, user=owner, sale_id=sale.pk, reason="r",
                             items=[{"sale_item": sale.items.get().pk, "quantity_base": 10}])
    valuation = stock_value(branch)
    ledger_value = sum(m.quantity * m.unit_cost for m in StockMovement.objects.filter(branch=branch))
    assert valuation == ledger_value == Decimal("225.00")  # 200 - 30 + 10 tablets at 1.25
    assert account_balance(INVENTORY, [branch]) == Decimal("225.00")
    from apps.accounting.services import trial_balance

    rows = trial_balance(branches=[branch])
    assert sum(r["debit"] for r in rows) == sum(r["credit"] for r in rows)


@pytest.mark.django_db(transaction=True)
def test_concurrent_sales_cannot_oversell(branch, product, stock, cashier):
    if connection.vendor != "postgresql":
        pytest.skip("Row locking needs PostgreSQL.")
    stock(branch, product, 10)
    results = []

    def worker():
        try:
            sell(branch, cashier, product, 1, pay=[{"method": "cash", "amount": "2"}])
            results.append("sold")
        except InsufficientStock:
            results.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(25)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("sold") == 10 and results.count("refused") == 15
    assert Batch.objects.get(product=product).quantity_on_hand == 0
    assert Sale.objects.filter(status="completed").count() == 10
    assert Sale.objects.values("number").distinct().count() == 10  # no duplicate invoice numbers
