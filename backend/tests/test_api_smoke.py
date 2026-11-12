"""Every read endpoint and report answers for an owner with real data behind it."""
from datetime import timedelta
from decimal import Decimal

import pytest

from apps.customers.models import Customer
from apps.purchases import services as purchases

from .conftest import days
from .test_sales import sell

pytestmark = pytest.mark.django_db

LISTS = [
    "/api/v1/auth/me/", "/api/v1/auth/roles/", "/api/v1/auth/users/", "/api/v1/branches/", "/api/v1/branches/profile/",
    "/api/v1/catalog/products/", "/api/v1/catalog/units/", "/api/v1/catalog/categories/", "/api/v1/catalog/manufacturers/",
    "/api/v1/catalog/barcodes/", "/api/v1/catalog/branch-prices/", "/api/v1/catalog/products/export/",
    "/api/v1/inventory/stock/", "/api/v1/inventory/stock/?state=low&search=pan", "/api/v1/inventory/batches/?in_stock=1",
    "/api/v1/inventory/movements/", "/api/v1/inventory/adjustments/",
    "/api/v1/suppliers/", "/api/v1/suppliers/prices/", "/api/v1/suppliers/payments/",
    "/api/v1/customers/", "/api/v1/customers/payments/",
    "/api/v1/purchases/requisitions/", "/api/v1/purchases/requisitions/current/", "/api/v1/purchases/orders/",
    "/api/v1/purchases/grns/", "/api/v1/purchases/returns/",
    "/api/v1/sales/", "/api/v1/sales/returns/", "/api/v1/sales/shifts/", "/api/v1/sales/shifts/current/",
    "/api/v1/accounting/accounts/", "/api/v1/accounting/journal/", "/api/v1/accounting/expenses/",
    "/api/v1/accounting/statements/", "/api/v1/accounting/statements/?statement=profit_and_loss",
    "/api/v1/accounting/statements/?statement=balance_sheet&consolidated=1",
    "/api/v1/notifications/", "/api/v1/notifications/unread-count/", "/api/v1/notifications/preferences/",
    "/api/v1/notifications/alerts/", "/api/v1/audit/logs/",
    "/api/v1/reports/dashboard/", "/api/v1/reports/sales/", "/api/v1/reports/sales/?consolidated=1",
    *[f"/api/v1/reports/sales/?group={g}" for g in ("day", "product", "category", "cashier", "customer", "payment_method")],
    "/api/v1/reports/sales/?group=product&export=csv",
    "/api/v1/reports/purchases/?group=supplier", "/api/v1/reports/purchases/?group=product",
    *[f"/api/v1/reports/inventory/?report={r}" for r in (
        "valuation", "low_stock", "out_of_stock", "near_expiry", "expired", "fast_moving", "slow_moving", "dead_stock")],
    "/api/schema/",
]


@pytest.fixture
def busy_branch(branch, owner, cashier, make_product, stock, supplier):
    product = make_product("Panadol", reorder_level=50, max_stock=200)
    grn = purchases.save_grn(branch=branch, user=owner, supplier=supplier, items=[{
        "product": product, "packaging": product.box, "quantity": 1, "unit_cost": Decimal("90.00"),
        "batch_number": "G1", "expiry_date": days(20)}])
    purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=owner)
    stock(branch, product, 5, "OLD", days(-2))
    customer = Customer.objects.create(name="Ali", credit_limit=Decimal("500"))
    sale = sell(branch, cashier, product, 6, product.strip, customer=customer,
                pay=[{"method": "credit", "amount": "100"}, {"method": "cash", "amount": "20"}])
    return {"product": product, "sale": sale, "customer": customer, "supplier": supplier}


@pytest.mark.parametrize("url", LISTS)
def test_read_endpoints_answer(api, owner, branch, busy_branch, url):
    response = api(owner, branch).get(url)
    assert response.status_code == 200, getattr(response, "data", response.content[:300])


def test_figures_agree_across_reports(api, owner, branch, busy_branch):
    client = api(owner, branch)
    totals = client.get("/api/v1/reports/sales/").data
    by_product = client.get("/api/v1/reports/sales/?group=product").data["rows"]
    pnl = client.get("/api/v1/accounting/statements/?statement=profit_and_loss").data
    assert Decimal(totals["net_sales"]) == Decimal("120.00")  # 6 strips x 10 x 2.00
    assert Decimal(totals["gross_profit"]) == Decimal(by_product[0]["profit"]) == pnl["gross_profit"] == Decimal("66.00")
    balance = client.get("/api/v1/accounting/statements/?statement=balance_sheet").data
    assert balance["assets"] == balance["liabilities_and_equity"]
    valuation = sum(Decimal(r["value"]) for r in client.get("/api/v1/reports/inventory/?report=valuation").data["rows"])
    assert valuation == Decimal(client.get("/api/v1/reports/dashboard/").data["stock_value"])
    assert [r["batch_number"] for r in client.get("/api/v1/reports/inventory/?report=expired").data["rows"]] == ["OLD"]
    assert [r["batch_number"] for r in client.get("/api/v1/reports/inventory/?report=near_expiry").data["rows"]] == ["G1"]


def test_money_flows_through_the_api(api, owner, branch, busy_branch):
    client = api(owner, branch)
    customer, supplier = busy_branch["customer"], busy_branch["supplier"]
    assert client.get(f"/api/v1/customers/{customer.pk}/").data["balance"] == "100.00"
    paid = client.post("/api/v1/customers/payments/", {"customer": customer.pk, "amount": "40", "method": "cash"}, format="json")
    assert paid.status_code == 201, paid.data
    assert client.get(f"/api/v1/customers/{customer.pk}/").data["balance"] == "60.00"
    too_much = client.post("/api/v1/customers/payments/", {"customer": customer.pk, "amount": "999"}, format="json")
    assert too_much.status_code == 400

    assert client.get(f"/api/v1/suppliers/{supplier.pk}/").data["balance"] == "90.00"
    assert client.post("/api/v1/suppliers/payments/", {"supplier": supplier.pk, "amount": "90", "method": "bank"},
                       format="json").status_code == 201
    ledger = client.get(f"/api/v1/suppliers/{supplier.pk}/ledger/").data
    assert ledger[-1]["balance"] == Decimal("0.00")

    expense_account = next(a for a in client.get("/api/v1/accounting/accounts/").data if a["code"] == "6000")
    expense = client.post("/api/v1/accounting/expenses/", {
        "account": expense_account["id"], "amount": "25.50", "description": "Electricity", "date": str(days(0))}, format="json")
    assert expense.status_code == 201, expense.data
    pnl = client.get("/api/v1/accounting/statements/?statement=profit_and_loss").data
    assert pnl["expenses"] == Decimal("25.50") and pnl["net_profit"] == pnl["gross_profit"] - Decimal("25.50")

    shift = client.post("/api/v1/sales/shifts/open/", {"opening_cash": "100"}, format="json")
    assert shift.status_code == 201, shift.data
    assert client.post("/api/v1/sales/shifts/open/", {"opening_cash": "100"}, format="json").status_code == 409
    sale = client.post("/api/v1/sales/", {"items": [{"product": busy_branch["product"].pk, "quantity": 5}],
                                          "payments": [{"method": "cash", "amount": "20"}]}, format="json")
    assert sale.status_code == 201 and sale.data["change_due"] == "10.00"
    closed = client.post(f"/api/v1/sales/shifts/{shift.data['id']}/close/", {"closing_cash": "110"}, format="json")
    assert closed.status_code == 200 and closed.data["expected_cash"] == "110.00"


def test_notification_centre_and_devices(api, owner, branch, busy_branch):
    client = api(owner, branch)  # the fixture's sale left 40 on the shelf, below the reorder level of 50
    assert client.get("/api/v1/notifications/unread-count/").data["unread"] == 1
    notification = client.get("/api/v1/notifications/?unread=1").data["results"][0]
    assert notification["type"] == "low_stock" and notification["data"]["alert_id"]
    assert client.post(f"/api/v1/notifications/{notification['id']}/read/").status_code == 204
    assert client.get("/api/v1/notifications/unread-count/").data["unread"] == 0
    assert client.post("/api/v1/notifications/devices/", {"token": "fcm-token-1", "platform": "android"}, format="json").status_code == 204
    assert client.put("/api/v1/notifications/preferences/", [{"type": "low_stock", "push": False}], format="json").status_code == 200
    assert client.delete("/api/v1/notifications/devices/", {"token": "fcm-token-1"}, format="json").status_code == 204
    alert_id = notification["data"]["alert_id"]
    assert client.get(f"/api/v1/notifications/alerts/{alert_id}/").data["status"] == "open"


def test_sales_trend_puts_each_medicine_on_a_shared_time_axis(api, owner, branch, cashier, make_product, stock):
    """The admin chart: units sold per medicine per day, so the busiest day stands out."""
    from django.utils import timezone

    from apps.sales.models import Sale

    panadol, brufen, risek = make_product("Panadol"), make_product("Brufen"), make_product("Risek")
    for product in (panadol, brufen, risek):
        stock(branch, product, 500)
    today = timezone.localdate()

    def sell_on(product, quantity, days_ago):
        sale = sell(branch, cashier, product, quantity)
        when = timezone.now() - timedelta(days=days_ago)
        Sale.objects.filter(pk=sale.pk).update(completed_at=when)
        return sale

    sell_on(panadol, 3, 4)
    sell_on(panadol, 20, 2)   # Panadol's busiest day
    sell_on(panadol, 5, 2)    # same day, so it adds up: 25
    sell_on(brufen, 7, 3)
    # Risek sells nothing: it must still come back as a flat zero line, not vanish.

    client = api(owner, branch)
    products = f"{panadol.pk},{brufen.pk},{risek.pk}"
    response = client.get("/api/v1/reports/sales/trend/", {
        "products": products, "date_from": str(today - timedelta(days=6)), "date_to": str(today)})
    assert response.status_code == 200, response.data
    data = response.data
    assert data["buckets"] == [str(today - timedelta(days=offset)) for offset in range(6, -1, -1)]

    by_label = {row["label"]: row for row in data["series"]}
    assert [row["label"] for row in data["series"]] == ["Panadol", "Brufen", "Risek"]  # busiest first
    assert len(by_label["Panadol"]["quantity"]) == len(data["buckets"])  # every series shares the axis
    assert by_label["Panadol"]["quantity"] == [0, 0, 3, 0, 25, 0, 0]
    assert by_label["Panadol"]["peak_bucket"] == str(today - timedelta(days=2))
    assert by_label["Panadol"]["total_quantity"] == 28
    assert by_label["Panadol"]["total_revenue"] == Decimal("56.00")
    assert by_label["Brufen"]["quantity"] == [0, 0, 0, 7, 0, 0, 0]
    assert by_label["Risek"]["quantity"] == [0] * 7 and by_label["Risek"]["peak_bucket"] is None

    weekly = client.get("/api/v1/reports/sales/trend/", {
        "products": products, "bucket": "week", "date_from": str(today - timedelta(days=6)), "date_to": str(today)}).data
    assert sum(sum(row["quantity"]) for row in weekly["series"]) == 35  # same units, coarser buckets

    hourly = client.get("/api/v1/reports/sales/trend/", {"products": products, "bucket": "hour"})
    assert hourly.status_code == 400  # 30 days of hours is past the point cap
    assert client.get("/api/v1/reports/sales/trend/", {
        "products": products, "bucket": "hour", "date_from": str(today), "date_to": str(today)}).status_code == 200


def test_sales_trend_input_is_checked(api, owner, branch, product, make_product):
    client = api(owner, branch)
    bad = [
        {},
        {"products": ""},
        {"products": "abc"},
        {"products": "999999"},
        {"products": str(product.pk), "bucket": "fortnight"},
        {"products": ",".join(str(product.pk) for _ in range(9))},
        {"products": str(product.pk), "date_from": "2026-06-01", "date_to": "2026-05-01"},
    ]
    for params in bad:
        assert client.get("/api/v1/reports/sales/trend/", params).status_code == 400, params
    assert client.get("/api/v1/reports/sales/trend/", {"products": str(product.pk)}).status_code == 200


def test_sales_trend_is_branch_scoped_and_permissioned(api, cashier, owner, make_user, branch, other_branch, product, stock):
    from django.utils import timezone

    stock(branch, product, 100)
    sell(branch, cashier, product, 4)
    today = timezone.localdate()
    params = {"products": str(product.pk), "date_from": str(today), "date_to": str(today)}

    assert api(cashier, branch).get("/api/v1/reports/sales/trend/", params).status_code == 403  # no reports.view
    owner_in_main = api(owner, branch).get("/api/v1/reports/sales/trend/", params).data
    assert owner_in_main["series"][0]["quantity"] == [4]
    owner_elsewhere = api(owner, other_branch).get("/api/v1/reports/sales/trend/", params).data
    assert owner_elsewhere["series"][0]["quantity"] == [0]  # the other branch sold none of it
    consolidated = api(owner, other_branch).get(
        "/api/v1/reports/sales/trend/", {**params, "consolidated": 1}).data
    assert consolidated["series"][0]["quantity"] == [4]

    csv_export = api(owner, branch).get("/api/v1/reports/sales/trend/", {**params, "export": "csv"})
    assert csv_export["Content-Type"] == "text/csv"
    assert str(product) in csv_export.content.decode()
