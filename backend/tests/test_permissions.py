from decimal import Decimal

import pytest

from .conftest import days

pytestmark = pytest.mark.django_db


def test_anonymous_requests_are_rejected(client):
    assert client.get("/api/v1/catalog/products/").status_code == 401
    assert client.get("/api/health/").status_code == 200


def test_login_returns_tokens_and_profile(client, cashier, branch):
    response = client.post("/api/v1/auth/login/", {"username": "cashier", "password": "Str0ng-pass!"}, content_type="application/json")
    assert response.status_code == 200
    body = response.json()
    assert body["access"] and body["refresh"]
    assert body["user"]["role"] == "cashier" and "sales.create" in body["user"]["permissions"]
    assert [b["code"] for b in body["user"]["branches"]] == ["main"]
    bad = client.post("/api/v1/auth/login/", {"username": "cashier", "password": "nope"}, content_type="application/json")
    assert bad.status_code == 401


def test_branch_isolation_is_enforced_on_the_server(api, cashier, owner, branch, other_branch, product, stock):
    stock(other_branch, product, 40)
    # A cashier of Main cannot switch to the other branch by sending its id.
    assert api(cashier, other_branch).get("/api/v1/inventory/stock/").status_code == 403
    assert api(cashier, other_branch).post("/api/v1/sales/", {}, format="json").status_code == 403
    # In their own branch they see none of the other branch's stock or batches.
    rows = api(cashier, branch).get("/api/v1/inventory/stock/").data["results"]
    assert [r["on_hand"] for r in rows] == [0]
    assert api(cashier, branch).get("/api/v1/inventory/batches/").data["count"] == 0
    other_batch = other_branch.batches.get()
    assert api(cashier, branch).get(f"/api/v1/inventory/batches/{other_batch.pk}/").status_code == 404
    # The owner can work in both.
    assert api(owner, other_branch).get("/api/v1/inventory/batches/").data["count"] == 1


def test_role_restrictions(api, make_user, cashier, branch, supplier, product, stock):
    stock(branch, product, 10)
    c = api(cashier, branch)
    assert c.post("/api/v1/catalog/products/", {}, format="json").status_code == 403
    assert c.get("/api/v1/purchases/grns/").status_code == 403
    assert c.get("/api/v1/audit/logs/").status_code == 403
    assert c.get("/api/v1/accounting/journal/").status_code == 403
    assert c.post("/api/v1/suppliers/payments/", {"supplier": supplier.pk, "amount": "5"}, format="json").status_code == 403

    sale = c.post("/api/v1/sales/", {"items": [{"product": product.pk, "quantity": 2}],
                                     "payments": [{"method": "cash", "amount": "4.00"}]}, format="json")
    assert sale.status_code == 201, sale.data
    # Cashiers cannot refund or cancel; a pharmacist can refund, only managers can cancel.
    refund = {"sale": sale.data["id"], "reason": "x", "items": [{"sale_item": sale.data["items"][0]["id"], "quantity_base": 1}]}
    assert c.post("/api/v1/sales/returns/", refund, format="json").status_code == 403
    assert c.post(f"/api/v1/sales/{sale.data['id']}/cancel/", {"reason": "x"}, format="json").status_code == 403
    pharmacist = api(make_user("pharmacist"), branch)
    assert pharmacist.post("/api/v1/sales/returns/", refund, format="json").status_code == 201
    assert pharmacist.post(f"/api/v1/sales/{sale.data['id']}/cancel/", {"reason": "x"}, format="json").status_code == 403

    auditor = api(make_user("auditor"), branch)
    assert auditor.get("/api/v1/audit/logs/").status_code == 200
    assert auditor.post("/api/v1/sales/", {}, format="json").status_code == 403


def test_pos_api_flow_with_barcode_quote_and_idempotency(api, cashier, owner, branch, product, stock):
    stock(branch, product, 50, expiry=days(90))
    created = api(owner).post("/api/v1/catalog/barcodes/generate/", {"product": product.pk, "packaging": product.strip.pk}, format="json")
    assert created.status_code == 201, created.data
    c = api(cashier, branch)
    found = c.get("/api/v1/catalog/products/lookup/", {"barcode": created.data["code"]})
    assert found.status_code == 200 and found.data["scanned_packaging"] == product.strip.pk

    cart = {"items": [{"product": product.pk, "packaging": product.strip.pk, "quantity": 2}]}
    quote = c.post("/api/v1/sales/quote/", cart, format="json")
    assert quote.status_code == 200 and quote.data["total"] == "40.00"
    assert c.post("/api/v1/sales/quote/", {"items": [{"product": product.pk, "quantity": 1.5}]}, format="json").status_code == 400

    body = {**cart, "payments": [{"method": "cash", "amount": "50"}]}
    first = c.post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
    retry = c.post("/api/v1/sales/", body, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
    assert first.status_code == retry.status_code == 201
    assert first.data["id"] == retry.data["id"] and first.data["change_due"] == "10.00"
    assert first.data["items"][0]["allocations"][0]["quantity"] == 20
    oversell = c.post("/api/v1/sales/", {"items": [{"product": product.pk, "quantity": 31}],
                                         "payments": [{"method": "cash", "amount": "62"}]}, format="json")
    assert oversell.status_code == 409 and oversell.data["code"] == "insufficient_stock"

    dashboard = api(owner, branch).get("/api/v1/reports/dashboard/")
    assert dashboard.status_code == 200 and Decimal(dashboard.data["today_sales"]) == Decimal("40.00")
    assert api(owner, branch).get("/api/v1/audit/logs/", {"action": "sale.complete"}).data["count"] == 1


def test_duplicate_medicine_is_detected(api, owner, units):
    payload = {"name": "Panadol", "strength": "500mg", "dosage_form": "Tablet", "sku": "P-1", "base_unit": units["Tablet"].pk,
               "retail_price": "2.00", "packagings": [{"unit": units["Strip"].pk, "factor": 10}]}
    first = api(owner).post("/api/v1/catalog/products/", payload, format="json")
    assert first.status_code == 201, first.data
    assert sorted(p["factor"] for p in first.data["packagings"]) == [1, 10]  # base unit added automatically
    clash = api(owner).post("/api/v1/catalog/products/", {**payload, "name": " panadol ", "sku": "P-2"}, format="json")
    assert clash.status_code == 400 and "duplicates" in clash.data
    forced = api(owner).post("/api/v1/catalog/products/", {**payload, "sku": "P-2", "allow_duplicate": True}, format="json")
    assert forced.status_code == 201


def test_cors_allows_the_configured_origins(client, settings, cashier):
    """The web app is served from another origin (Vercel), so CORS has to let it through."""
    settings.CORS_ALLOWED_ORIGINS = ["https://medipos.vercel.app"]
    settings.CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://medipos-[a-z0-9-]+\.vercel\.app$"]
    url = "/api/v1/auth/login/"

    def origin_allowed(origin: str) -> bool:
        preflight = client.options(url, HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
        return preflight.headers.get("access-control-allow-origin") == origin

    assert origin_allowed("https://medipos.vercel.app")
    assert origin_allowed("https://medipos-git-feature-asad.vercel.app")  # preview deployment
    assert not origin_allowed("https://medipos.attacker.example")
    assert not origin_allowed("https://evil.vercel.app")


def test_signed_in_user_lands_on_a_shop_not_a_warehouse(api, make_user, branch, other_branch):
    """The client opens on the first branch it is given, so a warehouse must never lead."""
    from apps.branches.models import Branch

    warehouse = Branch.objects.create(name="A Central Warehouse", code="whse", kind="warehouse")
    user = make_user("branch_admin", branches=[warehouse, other_branch, branch])
    branches = api(user).get("/api/v1/auth/me/").data["branches"]
    assert [item["kind"] for item in branches] == ["store", "store", "warehouse"]
    assert branches[0]["name"] == "Main"  # alphabetical within the shops


def test_pos_can_sell_from_a_named_batch(api, cashier, owner, branch, product, stock):
    """FEFO is the default, but a pharmacist can hand over a specific batch."""
    stock(branch, product, 20, "EARLY", days(30))
    later = stock(branch, product, 20, "LATER", days(400))
    c = api(cashier, branch)

    offered = c.get(f"/api/v1/inventory/stock/{product.pk}/batches/").data
    assert {row["batch_number"] for row in offered} == {"EARLY", "LATER"}

    body = {"items": [{"product": product.pk, "quantity": 5, "batch": later.pk}],
            "payments": [{"method": "cash", "amount": "10"}]}
    sale = c.post("/api/v1/sales/", body, format="json")
    assert sale.status_code == 201, sale.data
    allocations = sale.data["items"][0]["allocations"]
    assert [(row["batch_number"], row["quantity"]) for row in allocations] == [("LATER", 5)]

    # The default still takes the earliest expiry.
    auto = c.post("/api/v1/sales/", {"items": [{"product": product.pk, "quantity": 5}],
                                     "payments": [{"method": "cash", "amount": "10"}]}, format="json")
    assert auto.data["items"][0]["allocations"][0]["batch_number"] == "EARLY"

    # Asking for more than that batch holds is refused, and nothing is taken from another.
    greedy = c.post("/api/v1/sales/", {"items": [{"product": product.pk, "quantity": 16, "batch": later.pk}],
                                       "payments": [{"method": "cash", "amount": "40"}]}, format="json")
    assert greedy.status_code == 409 and greedy.data["code"] == "insufficient_stock"
    later.refresh_from_db()
    assert later.quantity_on_hand == 15
