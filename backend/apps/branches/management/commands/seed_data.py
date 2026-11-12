"""Fill an empty database with a believable pharmacy: catalogue, stock, purchases, sales, books.

    python manage.py seed_data                 # master data + 60 days of trading
    python manage.py seed_data --days 120      # a longer history
    python manage.py seed_data --reset         # wipe what a previous run made, then seed again
    python manage.py seed_data --master-only   # just the catalogue, suppliers, customers, users

Master data comes from the fixtures in apps/*/fixtures/. Everything that moves stock or money is
created through the same services the API uses, so the stock ledger, the batches and the journal
agree with each other exactly as they would in real use.
"""
import logging
import random
import secrets
import shutil
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.accounting.models import Account, Expense, JournalEntry
from apps.accounting.services import ensure_default_accounts, record_expense
from apps.audit.models import AuditLog
from apps.branches.models import Branch
from apps.catalog.models import Product
from apps.common.exceptions import BusinessError
from rest_framework.exceptions import ValidationError
from apps.customers.models import Customer
from apps.customers.services import customer_balance, receive_customer_payment
from apps.inventory import services as inventory
from apps.inventory.models import Batch, StockAdjustment, StockMovement
from apps.inventory.selectors import sellable_quantity
from apps.notifications.models import StockAlert
from apps.notifications.services import act_on_alert
from apps.purchases import services as purchases
from apps.purchases.models import GoodsReceivedNote, PurchaseOrder, PurchaseRequisition
from apps.sales import services as sales
from apps.sales.models import Sale, SaleReturn, Shift
from apps.suppliers.models import Supplier
from apps.suppliers.services import pay_supplier, supplier_balance

FIXTURES = ["01_branches", "02_catalog", "03_suppliers", "04_customers", "05_accounts"]

# username, first name, last name, role, branch codes, discount limit
PEOPLE = [
    ("owner", "Asad", "Bukharee", "owner", ["main", "gul", "whse"], "100"),
    ("manager", "Sadia", "Iqbal", "branch_admin", ["main"], "25"),
    ("gulshan.manager", "Nabeel", "Ahmed", "branch_admin", ["gul"], "25"),
    ("pharmacist", "Hina", "Shah", "pharmacist", ["main"], "15"),
    ("pharmacist2", "Zeeshan", "Ali", "pharmacist", ["gul"], "15"),
    ("cashier", "Moiz", "Raza", "cashier", ["main"], "10"),
    ("cashier2", "Areeba", "Khan", "cashier", ["gul"], "10"),
    ("storekeeper", "Junaid", "Baig", "inventory_manager", ["main", "whse"], "0"),
    ("purchaser", "Mehwish", "Younus", "purchase_officer", ["main", "gul", "whse"], "0"),
    ("accounts", "Rizwan", "Haider", "accountant", ["main", "gul", "whse"], "0"),
    ("auditor", "Shazia", "Malik", "auditor", ["main", "gul", "whse"], "0"),
]

# Tables a previous seed filled. Master data (branches, catalogue, suppliers, customers) is left
# alone because loaddata rewrites it by primary key.
TRANSACTIONAL = [
    "sales.SaleReturnItem", "sales.SaleReturn", "sales.SaleItemBatch", "sales.SaleItem",
    "sales.SalePayment", "sales.Sale", "sales.Shift",
    "purchases.PurchaseReturnItem", "purchases.PurchaseReturn", "purchases.GRNItem",
    "purchases.GoodsReceivedNote", "purchases.PurchaseOrderItem", "purchases.PurchaseOrder",
    "purchases.RequisitionItem", "purchases.PurchaseRequisition",
    "inventory.StockAdjustmentItem", "inventory.StockAdjustment", "inventory.StockMovement", "inventory.Batch",
    "accounting.Expense", "accounting.JournalLine", "accounting.JournalEntry", "accounting.FinancialPeriod",
    "suppliers.SupplierPayment", "customers.CustomerPayment",
    "notifications.ExpiryAlert", "notifications.StockAlert", "notifications.Notification",
    "audit.AuditLog", "branches.DocumentSequence",
]

HOURS = [9, 10, 10, 11, 11, 12, 12, 13, 14, 15, 16, 17, 17, 18, 18, 19, 19, 20, 21]
METHODS = ["cash"] * 7 + ["card"] * 2 + ["wallet"]


def short_supply(product) -> bool:
    """A few lines the distributor keeps letting the shop down on.

    They start below their reorder level and the weekly delivery skips them, so the low-stock
    alerts and the order list always have something real in them.
    """
    return product.pk % 7 == 4


class Command(BaseCommand):
    help = "Load the sample fixtures and generate a trading history from them."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=60, help="Days of trading history (default 60).")
        parser.add_argument("--password", default="", help="Password for the sample users. A strong one is generated if omitted.")
        parser.add_argument("--reset", action="store_true", help="Delete everything a previous seed created first.")
        parser.add_argument("--master-only", action="store_true", help="Fixtures, images and users; no stock or trading.")
        parser.add_argument("--no-images", action="store_true", help="Skip the medicine pack images.")
        parser.add_argument("--seed", type=int, default=20261112, help="Random seed, so two runs produce the same data.")
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG off or data already present.")

    def handle(self, *args, **options):
        self.random = random.Random(options["seed"])
        self.verbose = options["verbosity"] > 0
        # Each sale and receipt queues a push notification; without Firebase configured every one
        # of them logs a line. Keep the seeder's own output readable.
        logging.getLogger("celery").setLevel(logging.WARNING)
        days = max(1, min(options["days"], 730))

        if not settings.DEBUG and not options["force"]:
            raise CommandError("seed_data writes sample data and is meant for development. Pass --force to override.")
        if Sale.objects.exists() and not (options["reset"] or options["force"]):
            raise CommandError("This database already has sales. Use --reset to replace the sample data, or --force to add to it.")

        if options["reset"]:
            self.reset()
        self.load_fixtures()
        if options["no_images"]:
            Product.objects.update(image="")  # the fixtures point at files that were not copied
        else:
            self.copy_images()
        password = options["password"] or f"Medipos-{secrets.token_urlsafe(9)}"
        if len(password) < 8:
            raise CommandError("--password needs at least 8 characters.")
        people = self.create_users(password)

        if options["master_only"]:
            self.report(password, people)
            return

        branches = {branch.code: branch for branch in Branch.objects.all()}
        products = list(Product.objects.select_related("base_unit").prefetch_related("packagings").order_by("pk"))
        self.opening_stock(branches, products, people)
        self.purchasing(branches, products, people, days)
        self.trading(branches, products, people, days)
        self.returns(branches, people)
        self.adjustments(branches, people)
        self.money(branches, people, days)
        self.reordering(branches, people)
        self.shifts(branches, people)
        self.report(password, people)

    # --- plumbing ---------------------------------------------------------------------------

    def say(self, message):
        if self.verbose:
            self.stdout.write(f"  {message}")

    def reset(self):
        tables = [django_apps.get_model(label)._meta.db_table for label in TRANSACTIONAL]
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
            else:
                # SQLite has no TRUNCATE. These tables reference each other in both directions
                # (a supplier payment points at a goods received note, an expiry alert at a
                # batch), so there is no delete order that satisfies every key: turn the checks
                # off for the sweep, then let Django put them back and verify.
                with connection.constraint_checks_disabled():
                    for table in tables:
                        cursor.execute(f'DELETE FROM "{table}"')
                connection.check_constraints(table_names=tables)
        self.say(f"cleared {len(tables)} tables")

    def load_fixtures(self):
        call_command("loaddata", *FIXTURES, verbosity=0)
        ensure_default_accounts()
        # loaddata writes rows raw, so Product.save() never runs: recompute what it maintains.
        for product in Product.objects.all():
            product.save(update_fields=["duplicate_key", "updated_at"])
        self.say(f"fixtures: {Product.objects.count()} medicines, {Supplier.objects.count()} suppliers, "
                 f"{Customer.objects.count()} customers, {Branch.objects.count()} branches")

    def copy_images(self):
        source = Path(django_apps.get_app_config("catalog").path) / "fixtures" / "images"
        target = Path(settings.MEDIA_ROOT) / "products"
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        for product in Product.objects.all():
            image = source / f"{product.sku.lower()}.png"
            if image.exists():
                shutil.copyfile(image, target / image.name)  # the fixture already points the field here
                copied += 1
        self.say(f"images: {copied} medicine packs copied into {target}")

    def create_users(self, password):
        User = get_user_model()
        codes = {branch.code: branch for branch in Branch.objects.all()}
        people = {}
        for username, first, last, role, branch_codes, discount in PEOPLE:
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role,
                          "email": f"{username.replace('.', '')}@medipos.example",
                          "max_discount_percent": Decimal(discount), "is_active": True,
                          "is_staff": role == "owner", "is_superuser": False},
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            user.branches.set([codes[code] for code in branch_codes if code in codes])
            people[username] = user
        self.say(f"users: {len(people)} accounts, one per role")
        return people

    def backdate(self, when, source_type, source_id):
        """Move a posted document and everything it wrote back in time, so history looks real."""
        JournalEntry.objects.filter(source_type=source_type, source_id=source_id).update(date=when.date(), created_at=when)
        StockMovement.objects.filter(source_type=source_type, source_id=source_id).update(created_at=when)

    def moment(self, days_ago, hour=None):
        when = (timezone.localtime() - timedelta(days=days_ago)).replace(
            hour=hour if hour is not None else self.random.choice(HOURS),
            minute=self.random.randrange(60), second=self.random.randrange(60), microsecond=0)
        # Never stamp a document in the future, however late in the day the seed runs.
        return min(when, timezone.localtime() - timedelta(minutes=5))

    # --- the data ---------------------------------------------------------------------------

    def opening_stock(self, branches, products, people):
        """Two or three batches per medicine, with a few short-dated and expired ones to find."""
        owner, keeper = people["owner"], people["storekeeper"]
        today = timezone.localdate()
        made = 0
        for code, branch in branches.items():
            share = products if code != "whse" else products[::2]
            items = []
            for index, product in enumerate(share):
                base = max(product.reorder_level, 20)
                if short_supply(product):
                    lots = [(max(2, round(base * 0.4)), 260 + index * 4)]
                else:
                    lots = [(round(base * 2.2), 320 + index * 5), (round(base * 1.4), 150 + index * 3)]
                    if index % 5 == 0:                  # short-dated stock for the expiry report
                        lots.append((round(base * 0.25) or 5, 20 + index))
                    if index % 11 == 0:                 # and a little that has already expired
                        lots.append((round(base * 0.1) or 3, -12 - index))
                for lot, (quantity, offset) in enumerate(lots, 1):
                    items.append({
                        "product": product,
                        "batch_number": f"{product.sku[-4:]}-{code.upper()}{lot}",
                        "expiry_date": today + timedelta(days=offset),
                        "unit_cost": product.purchase_price,
                        "quantity_delta": int(quantity),
                    })
            adjustment = inventory.request_adjustment(
                branch=branch, user=keeper, reason=StockAdjustment.Reason.OPENING,
                note="Opening stock at go-live", items=items)
            inventory.decide_adjustment(adjustment_id=adjustment.pk, branch=branch, user=owner, approve=True)
            made += len(items)
        self.say(f"opening stock: {made} batches across {len(branches)} branches")

    def purchasing(self, branches, products, people, days):
        """Orders and goods received notes in every state a buyer sees."""
        buyer, keeper, manager = people["purchaser"], people["storekeeper"], people["manager"]
        today = timezone.localdate()
        by_supplier = {}
        for product in products:
            by_supplier.setdefault(product.preferred_supplier_id, []).append(product)
        counts = {"orders": 0, "received": 0, "drafts": 0}

        for position, (supplier_id, supplier_products) in enumerate(sorted(by_supplier.items())):
            if supplier_id is None:
                continue
            supplier = Supplier.objects.get(pk=supplier_id)
            branch = branches["main"] if position % 3 else branches["gul"]
            chosen = self.random.sample(supplier_products, min(4, len(supplier_products)))
            lines = []
            for product in chosen:
                pack = next((p for p in product.packagings.all() if p.is_default_purchase), None) \
                    or max(product.packagings.all(), key=lambda p: p.factor)
                lines.append({"product": product, "packaging": pack,
                              "quantity": self.random.randint(2, 8),
                              "unit_price": (product.purchase_price * pack.factor).quantize(Decimal("0.0001"))})
            order = purchases.save_purchase_order(
                branch=branch, user=buyer, supplier=supplier, items=lines,
                expected_date=today + timedelta(days=self.random.randint(2, 12)),
                note="Monthly replenishment")
            counts["orders"] += 1
            if position % 5 == 4:                        # one left waiting for approval
                counts["drafts"] += 1
                continue
            purchases.transition_purchase_order(order_id=order.pk, branch=branch, user=manager, action="approve")
            purchases.transition_purchase_order(order_id=order.pk, branch=branch, user=buyer, action="mark_ordered")
            if position % 5 == 3:                        # one approved but not delivered yet
                continue

            whole = position % 5 != 2                    # and one delivered only in part
            when = self.moment(self.random.randint(5, max(6, days - 5)), hour=self.random.choice([9, 10, 11]))
            grn_items = []
            for line in order.items.select_related("product", "packaging").all():
                quantity = line.quantity if whole else max(1, line.quantity // 2)
                grn_items.append({
                    "po_item": line, "product": line.product, "packaging": line.packaging,
                    "quantity": quantity, "unit_cost": line.unit_price,
                    "batch_number": f"{line.product.sku[-4:]}-G{order.pk:03d}",
                    "expiry_date": today + timedelta(days=self.random.randint(240, 640)),
                    "damaged_quantity": 1 if position % 7 == 0 else 0,
                })
            grn = purchases.save_grn(branch=branch, user=keeper, supplier=supplier, purchase_order=order,
                                     items=grn_items, supplier_invoice_number=f"INV-{supplier.pk:02d}-{order.pk:04d}",
                                     supplier_invoice_date=when.date())
            if position % 9 == 1:                        # a delivery still being checked in
                counts["drafts"] += 1
                continue
            purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=keeper)
            GoodsReceivedNote.objects.filter(pk=grn.pk).update(confirmed_at=when, created_at=when)
            self.backdate(when, "grn", grn.pk)
            counts["received"] += 1
        self.say(f"purchasing: {counts['orders']} purchase orders, {counts['received']} goods received notes, "
                 f"{counts['drafts']} left open")

    def trading(self, branches, products, people, days):
        """The sales history the reports and the trend chart read."""
        tills = {"main": [people["cashier"], people["pharmacist"], people["manager"]],
                 "gul": [people["cashier2"], people["pharmacist2"]]}
        credit_customers = list(Customer.objects.filter(credit_limit__gt=0))
        walk_in = list(Customer.objects.filter(credit_limit=0))
        # A pharmacy sells a handful of things constantly and the rest occasionally.
        popular = products[:8]
        weighted = popular * 5 + products
        made = held = 0

        deliveries = 0
        for days_ago in range(days, -1, -1):
            weekend = (timezone.localdate() - timedelta(days=days_ago)).weekday() >= 5
            for code, staff in tills.items():
                branch = branches[code]
                if days_ago % 7 == 0:  # the distributor's weekly round, before the shop opens
                    deliveries += self.deliver(branch, products, self.moment(days_ago, hour=8), people)
                count = self.random.randint(7, 13) if code == "main" else self.random.randint(5, 9)
                count += 3 if weekend else 0
                for _ in range(count):
                    user = self.random.choice(staff)
                    items = []
                    basket = {product.pk: product for product in self.random.sample(weighted, self.random.randint(1, 3))}
                    for product in basket.values():
                        packs = [p for p in product.packagings.all() if p.can_sell]
                        pack = self.random.choice(packs) if len(packs) > 1 and self.random.random() < 0.45 else \
                            next(p for p in packs if p.factor == 1)
                        items.append({"product": product, "packaging": pack,
                                      "quantity": self.random.randint(1, 3 if pack.factor > 1 else 20)})
                    customer = None
                    if self.random.random() < 0.3:
                        customer = self.random.choice(credit_customers if self.random.random() < 0.4 else walk_in)
                    try:
                        priced, totals = sales.price_lines(branch=branch, user=user, customer=customer, items=items)
                    except (BusinessError, ValidationError):
                        continue
                    total = totals["total"]
                    if total <= 0:
                        continue
                    method = self.random.choice(METHODS)
                    on_credit = customer is not None and customer.credit_limit > 0 and self.random.random() < 0.35
                    if on_credit and customer_balance(customer) + total > customer.credit_limit:
                        on_credit = False
                    if on_credit:
                        payments = [{"method": "credit", "amount": total}]
                    elif method == "cash":
                        payments = [{"method": "cash", "amount": (total / 10).to_integral_value(rounding="ROUND_CEILING") * 10}]
                    else:
                        payments = [{"method": method, "amount": total}]
                    needs_rx = any(line.product.requires_prescription for line in priced)
                    try:
                        sale = sales.create_sale(
                            branch=branch, user=user, items=items, payments=payments, customer=customer,
                            prescription_reference=f"RX-{self.random.randrange(1000, 9999)}" if needs_rx else "")
                    except (BusinessError, ValidationError):
                        continue
                    when = self.moment(days_ago)
                    Sale.objects.filter(pk=sale.pk).update(completed_at=when, created_at=when, updated_at=when)
                    self.backdate(when, "sale", sale.pk)
                    AuditLog.objects.filter(object_type="sales.sale", object_id=str(sale.pk)).update(created_at=when)
                    made += 1

        for code in ("main", "gul"):   # a couple of invoices parked at the counter
            branch, user = branches[code], tills[code][0]
            product = self.random.choice(products[:10])
            try:
                sales.create_sale(branch=branch, user=user, hold=True,
                                  items=[{"product": product, "packaging": None, "quantity": 4}])
                held += 1
            except (BusinessError, ValidationError):
                pass
        self.say(f"trading: {made} invoices over {days} days, {held} held at the counter, "
                 f"{deliveries} weekly deliveries received")

    def deliver(self, branch, products, when, people):
        """Top the shelves back up, the way a distributor's weekly load does."""
        keeper = people["storekeeper"]
        today = timezone.localdate()
        supplier = Supplier.objects.get(pk=(when.day % 4) + 1)
        items = []
        for product in products:
            if short_supply(product):
                continue
            target = max(product.reorder_level, 20) * 3
            missing = target - sellable_quantity(branch, product)
            if missing < target * 0.4:
                continue
            pack = next((p for p in product.packagings.all() if p.is_default_purchase), None) \
                or max(product.packagings.all(), key=lambda p: p.factor)
            items.append({
                "product": product, "packaging": pack,
                "quantity": max(1, -(-int(missing) // pack.factor)),
                "unit_cost": (product.purchase_price * pack.factor).quantize(Decimal("0.0001")),
                "batch_number": f"{product.sku[-4:]}-W{when.strftime('%y%m%d')}",
                "expiry_date": today + timedelta(days=self.random.randint(300, 700)),
            })
        if not items:
            return 0
        grn = purchases.save_grn(branch=branch, user=keeper, supplier=supplier, items=items,
                                 supplier_invoice_number=f"WK-{when.strftime('%y%m%d')}-{branch.code.upper()}",
                                 supplier_invoice_date=when.date(), note="Weekly delivery")
        purchases.confirm_grn(grn_id=grn.pk, branch=branch, user=keeper)
        GoodsReceivedNote.objects.filter(pk=grn.pk).update(confirmed_at=when, created_at=when, updated_at=when)
        self.backdate(when, "grn", grn.pk)
        return 1

    def returns(self, branches, people):
        pharmacist = people["pharmacist"]
        recent = list(Sale.objects.filter(status=Sale.Status.COMPLETED, branch=branches["main"])
                      .order_by("-completed_at")[:120])
        made = 0
        for sale in self.random.sample(recent, min(12, len(recent))):
            item = sale.items.first()
            if item is None or item.quantity_base < 2:
                continue
            quantity = max(1, item.quantity_base // 2)
            # A day or two after the sale, but never in the future on a short history.
            when = min(sale.completed_at + timedelta(days=self.random.randint(1, 3)),
                       timezone.now() - timedelta(hours=1))
            try:
                sale_return = sales.create_sale_return(
                    branch=sale.branch, user=pharmacist, sale_id=sale.pk,
                    items=[{"sale_item": item.pk, "quantity_base": quantity, "restock": self.random.random() > 0.3}],
                    reason=self.random.choice(["Wrong strength", "Patient reaction", "Damaged strip", "Duplicate purchase"]))
            except (BusinessError, ValidationError):
                continue
            SaleReturn.objects.filter(pk=sale_return.pk).update(created_at=when, updated_at=when)
            self.backdate(when, "sale_return", sale_return.pk)
            made += 1
        self.say(f"returns: {made} customer returns")

    def adjustments(self, branches, people):
        """Damage and losses, some still waiting for a manager."""
        keeper, owner = people["storekeeper"], people["owner"]
        pending = approved = 0
        for index in range(10):
            branch = branches["main"] if index % 3 else branches["gul"]
            batch = (Batch.objects.filter(branch=branch, quantity_on_hand__gt=10)
                     .order_by("?").first())
            if batch is None:
                continue
            adjustment = inventory.request_adjustment(
                branch=branch, user=keeper,
                reason=self.random.choice(["damaged", "lost", "count"]),
                note=self.random.choice(["Broken in transit", "Not found during count", "Water damage on shelf"]),
                items=[{"batch": batch, "quantity_delta": -self.random.randint(1, 6)}])
            if index % 3 == 0:
                pending += 1
                continue
            inventory.decide_adjustment(adjustment_id=adjustment.pk, branch=branch, user=owner, approve=True)
            approved += 1
        self.say(f"adjustments: {approved} approved, {pending} waiting for a manager")

    def money(self, branches, people, days):
        """Supplier payments, customer settlements and running costs."""
        accountant, owner = people["accounts"], people["owner"]
        paid = 0
        for supplier in Supplier.objects.all():
            balance = supplier_balance(supplier)
            if balance <= 0:
                continue
            amount = (balance if self.random.random() < 0.4 else balance / 2).quantize(Decimal("0.01"))
            if amount <= 0:
                continue
            payment = pay_supplier(supplier=supplier, branch=branches["main"], user=accountant, amount=amount,
                                   method=self.random.choice(["bank", "cash", "wallet"]),
                                   reference=f"CHQ-{self.random.randrange(10000, 99999)}")
            when = self.moment(self.random.randint(1, max(2, days // 2)))
            self.backdate(when, "supplier_payment", payment.pk)
            paid += 1

        received = 0
        for customer in Customer.objects.filter(credit_limit__gt=0):
            balance = customer_balance(customer)
            if balance <= 0:
                continue
            amount = (balance / 2).quantize(Decimal("0.01"))
            if amount <= 0:
                continue
            payment = receive_customer_payment(customer=customer, branch=branches["main"], user=accountant,
                                               amount=amount, method=self.random.choice(["cash", "bank"]))
            self.backdate(self.moment(self.random.randint(1, 20)), "customer_payment", payment.pk)
            received += 1

        costs = [("6100", "Monthly rent", "85000"), ("6200", "Electricity bill", "24500"),
                 ("6200", "Internet and phone", "6800"), ("6300", "Staff salaries", "310000"),
                 ("6400", "Delivery rider fuel", "9400"), ("6500", "Pamphlet printing", "12000"),
                 ("6600", "Chiller servicing", "15500"), ("6000", "Packing bags", "7200"),
                 ("6000", "Cleaning supplies", "3100"), ("6400", "Courier to Gulshan branch", "4200"),
                 ("6600", "POS printer repair", "5600"), ("6500", "Shop signage", "18000")]
        for index, (code, description, amount) in enumerate(costs):
            account = Account.objects.get(code=code)
            date = (timezone.localdate() - timedelta(days=self.random.randint(1, days)))
            record_expense(branch=branches["main"], user=owner, account_obj=account, amount=Decimal(amount),
                           paid_from=self.random.choice(["cash", "bank"]), description=description, date=date)
        self.say(f"money: {paid} supplier payments, {received} customer settlements, {len(costs)} expenses")

    def reordering(self, branches, people):
        """Turn the low-stock alerts the selling produced into a real order list."""
        keeper, manager = people["storekeeper"], people["manager"]
        branch = branches["main"]
        open_alerts = list(StockAlert.objects.filter(branch=branch, status=StockAlert.Status.OPEN)[:9])
        # Skip a couple the way a storekeeper does, but never skip the only one there is.
        skip_at = {3, 7} if len(open_alerts) >= 4 else ({len(open_alerts) - 1} if len(open_alerts) > 1 else set())
        added = skipped = 0
        for index, alert in enumerate(open_alerts[:8]):
            if index in skip_at:
                act_on_alert(alert_id=alert.pk, branch=branch, user=keeper, action="skip")
                skipped += 1
            else:
                act_on_alert(alert_id=alert.pk, branch=branch, user=keeper, action="add",
                             quantity=alert.suggested_quantity or 50)
                added += 1

        orders = 0
        requisition = PurchaseRequisition.objects.filter(branch=branch, status="draft").first()
        if requisition and requisition.items.exists():
            purchases.submit_requisition(requisition_id=requisition.pk, branch=branch, user=keeper)
            purchases.decide_requisition(requisition_id=requisition.pk, branch=branch, user=manager, approve=True)
            orders = len(purchases.convert_requisition(requisition_id=requisition.pk, branch=branch, user=manager))
            # Leave a second order list open, the way a branch always has one on the go.
            second = StockAlert.objects.filter(branch=branch, status=StockAlert.Status.OPEN).first()
            if second:
                act_on_alert(alert_id=second.pk, branch=branch, user=keeper, action="add",
                             quantity=second.suggested_quantity or 50)
        self.say(f"reordering: {added} medicines added to the order list, {skipped} skipped, "
                 f"{orders} purchase orders raised from it")

    def shifts(self, branches, people):
        closed = sales.open_shift(branch=branches["main"], user=people["cashier"], opening_cash=Decimal("5000"))
        sales.close_shift(shift_id=closed.pk, branch=branches["main"], user=people["cashier"],
                          closing_cash=Decimal("5000"), note="Counted at close, drawer agreed")
        sales.open_shift(branch=branches["gul"], user=people["cashier2"], opening_cash=Decimal("3000"))
        self.say("shifts: one closed, one open at the Gulshan till")

    def report(self, password, people):
        if not self.verbose:
            return
        counts = [
            ("Branches", Branch.objects.count()), ("Users", len(people)),
            ("Medicines", Product.objects.count()), ("Batches", Batch.objects.count()),
            ("Suppliers", Supplier.objects.count()), ("Customers", Customer.objects.count()),
            ("Purchase orders", PurchaseOrder.objects.count()), ("Goods received notes", GoodsReceivedNote.objects.count()),
            ("Invoices", Sale.objects.count()), ("Sales returns", SaleReturn.objects.count()),
            ("Stock movements", StockMovement.objects.count()), ("Journal entries", JournalEntry.objects.count()),
            ("Expenses", Expense.objects.count()), ("Stock alerts", StockAlert.objects.count()),
            ("Shifts", Shift.objects.count()),
        ]
        width = max(len(label) for label, _ in counts)
        self.stdout.write("")
        for label, value in counts:
            self.stdout.write(f"  {label.ljust(width)}  {value:>7,}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  Sign in as any of: {', '.join(sorted(people))}"))
        self.stdout.write(self.style.SUCCESS(f"  Password for all of them: {password}"))
