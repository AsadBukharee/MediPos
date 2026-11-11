import pytest

from apps.common.exceptions import BusinessError
from apps.notifications import services as alerts
from apps.notifications.models import Notification, StockAlert
from apps.purchases import services as purchases
from apps.purchases.models import PurchaseRequisition

from .conftest import days
from .test_sales import sell

pytestmark = pytest.mark.django_db


@pytest.fixture
def medicine(make_product):
    return make_product("Brufen", reorder_level=20, max_stock=100)


def test_alert_fires_once_and_resets_when_stock_recovers(branch, medicine, stock, cashier, make_user):
    manager = make_user("inventory_manager")
    stock(branch, medicine, 30)
    assert not StockAlert.objects.exists()

    sell(branch, cashier, medicine, 10)  # 20 left: reaches the threshold
    alert = StockAlert.objects.get()
    assert (alert.kind, alert.status, alert.triggered_quantity, alert.suggested_quantity) == ("low_stock", "open", 20, 80)
    assert Notification.objects.filter(user=manager, type="low_stock").count() == 1
    assert not Notification.objects.filter(user=cashier).exists()  # cashiers are not alert recipients

    sell(branch, cashier, medicine, 5)  # still low: no duplicate alert
    assert StockAlert.objects.count() == 1
    assert Notification.objects.filter(user=manager, type="low_stock").count() == 1

    stock(branch, medicine, 50, "B2")  # recovers above the threshold
    alert.refresh_from_db()
    assert alert.status == "resolved"

    sell(branch, cashier, medicine, 50)  # breaches again: a new alert
    assert StockAlert.objects.exclude(status="resolved").count() == 1
    assert Notification.objects.filter(user=manager, type="low_stock").count() == 2


def test_suggestion_considers_on_order_and_reserved_stock(branch, medicine, stock, cashier, owner, supplier):
    from apps.sales import services as sales

    stock(branch, medicine, 20)
    assert alerts.suggested_reorder_quantity(branch, medicine) == 80  # target 100 - 20 on hand
    order = purchases.save_purchase_order(branch=branch, user=owner, supplier=supplier, items=[
        {"product": medicine, "packaging": medicine.strip, "quantity": 3, "unit_price": "10"}])
    assert alerts.suggested_reorder_quantity(branch, medicine) == 80  # a draft order does not count
    purchases.transition_purchase_order(order_id=order.pk, branch=branch, user=owner, action="approve")
    assert alerts.suggested_reorder_quantity(branch, medicine) == 50  # 30 tablets on order
    sales.create_sale(branch=branch, user=cashier, items=[{"product": medicine, "packaging": None, "quantity": 5}], hold=True)
    assert alerts.suggested_reorder_quantity(branch, medicine) == 55  # 5 reserved on a held invoice


def test_add_to_order_list_skip_and_convert_to_purchase_orders(api, branch, medicine, make_product, stock, cashier, make_user, supplier):
    manager, admin = make_user("inventory_manager"), make_user("branch_admin")
    other = make_product("Risek", reorder_level=10, max_stock=40)
    medicine.preferred_supplier = other.preferred_supplier = supplier
    medicine.save(), other.save()
    stock(branch, medicine, 25), stock(branch, other, 12)
    sell(branch, cashier, medicine, 10), sell(branch, cashier, other, 5)
    first, second = StockAlert.objects.order_by("id")

    m = api(manager, branch)
    assert api(cashier, branch).post(f"/api/v1/notifications/alerts/{first.pk}/skip/").status_code == 403
    assert m.post(f"/api/v1/notifications/alerts/{second.pk}/skip/").data["status"] == "skipped"
    added = m.post(f"/api/v1/notifications/alerts/{first.pk}/add-to-order/", {"quantity": 120}, format="json")
    assert added.status_code == 200 and added.data["requested_quantity"] == 120
    m.post(f"/api/v1/notifications/alerts/{first.pk}/add-to-order/", {"quantity": 150}, format="json")  # edit quantity
    m.post(f"/api/v1/notifications/alerts/{second.pk}/add-to-order/", format="json")  # changed their mind: uses suggestion

    current = m.get("/api/v1/purchases/requisitions/current/").data
    assert sorted((i["product"], i["quantity"]) for i in current["items"]) == sorted([(medicine.pk, 150), (other.pk, 33)])

    rid = current["id"]
    assert m.post(f"/api/v1/purchases/requisitions/{rid}/submit/").data["status"] == "pending"
    assert m.post(f"/api/v1/purchases/requisitions/{rid}/approve/").status_code == 403
    a = api(admin, branch)
    assert a.post(f"/api/v1/purchases/requisitions/{rid}/approve/").data["status"] == "approved"
    converted = a.post(f"/api/v1/purchases/requisitions/{rid}/convert/")
    assert converted.status_code == 200 and len(converted.data["purchase_orders"]) == 1  # grouped by supplier
    order = a.get(f"/api/v1/purchases/orders/{converted.data['purchase_orders'][0]['id']}/").data
    assert sorted((i["product"], i["quantity"], i["packaging_factor"]) for i in order["items"]) == sorted(
        [(medicine.pk, 2, 100), (other.pk, 1, 100)])  # rounded up to whole boxes
    assert PurchaseRequisition.objects.get(pk=rid).status == "ordered"


def test_acting_on_a_resolved_alert_is_refused(branch, medicine, stock, cashier, owner):
    stock(branch, medicine, 25)
    sell(branch, cashier, medicine, 10)
    alert = StockAlert.objects.get()
    stock(branch, medicine, 100, "B2")
    with pytest.raises(BusinessError):
        alerts.act_on_alert(alert_id=alert.pk, branch=branch, user=owner, action="add", quantity=10)
