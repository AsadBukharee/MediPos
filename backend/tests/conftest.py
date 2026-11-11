from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounting.services import ensure_default_accounts
from apps.branches.models import Branch
from apps.catalog.models import Product, ProductPackaging, Unit
from apps.inventory import services as inventory
from apps.inventory.models import StockMovement
from apps.inventory.services import Source
from apps.suppliers.models import Supplier

User = get_user_model()


def days(n: int):
    return timezone.localdate() + timedelta(days=n)


@pytest.fixture(autouse=True)
def _accounts(db):
    ensure_default_accounts()


@pytest.fixture
def branch(db):
    return Branch.objects.create(name="Main", code="main")


@pytest.fixture
def other_branch(db):
    return Branch.objects.create(name="Second", code="two")


@pytest.fixture
def make_user(db, branch):
    def make(role, username=None, branches=None, **extra):
        user = User.objects.create_user(username or role, password="Str0ng-pass!", role=role, **extra)
        user.branches.set(branches if branches is not None else [branch])
        return user

    return make


@pytest.fixture
def owner(make_user):
    return make_user("owner")


@pytest.fixture
def cashier(make_user):
    return make_user("cashier", max_discount_percent=Decimal("10"))


@pytest.fixture
def api():
    def client_for(user, branch=None):
        client = APIClient()
        client.force_authenticate(user)
        if branch is not None:
            client.credentials(HTTP_X_BRANCH_ID=str(branch.pk))
        return client

    return client_for


@pytest.fixture
def units(db):
    return {name: Unit.objects.create(name=name, abbreviation=name[:3].lower()) for name in ("Tablet", "Strip", "Box")}


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(name="Acme Distributors")


@pytest.fixture
def make_product(db, units):
    counter = {"n": 0}

    def make(name="Panadol", price="2.00", cost="1.00", **extra):
        counter["n"] += 1
        product = Product.objects.create(
            name=name, sku=f"SKU-{counter['n']}", base_unit=units["Tablet"], retail_price=Decimal(price),
            purchase_price=Decimal(cost), **extra)
        product.tablet = ProductPackaging.objects.create(product=product, unit=units["Tablet"], factor=1, is_default_sale=True)
        product.strip = ProductPackaging.objects.create(product=product, unit=units["Strip"], factor=10)
        product.box = ProductPackaging.objects.create(product=product, unit=units["Box"], factor=100, is_default_purchase=True)
        return product

    return make


@pytest.fixture
def product(make_product):
    return make_product()


@pytest.fixture
def stock(owner):
    """Put stock on the shelf directly through the inventory service."""

    def add(branch, product, quantity, batch_number="B1", expiry=None, cost="1.00", **extra):
        return inventory.receive_stock(
            branch=branch, product=product, batch_number=batch_number, expiry_date=expiry or days(365),
            quantity=quantity, unit_cost=Decimal(cost), user=owner, source=Source("test"),
            movement_type=StockMovement.Type.OPENING, **extra)

    return add
