"""Double-entry postings. Business documents call these; nothing else writes journal rows."""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.audit.services import log_action
from apps.common.exceptions import BusinessError
from apps.common.money import ZERO, money

from .models import Account, Expense, FinancialPeriod, JournalEntry, JournalLine

A = Account.Type
DEFAULT_ACCOUNTS = {
    "1000": ("Cash in hand", A.ASSET),
    "1010": ("Bank", A.ASSET),
    "1020": ("Card clearing", A.ASSET),
    "1030": ("Mobile wallet", A.ASSET),
    "1100": ("Accounts receivable", A.ASSET),
    "1200": ("Inventory", A.ASSET),
    "2000": ("Accounts payable", A.LIABILITY),
    "2100": ("Sales tax payable", A.LIABILITY),
    "3000": ("Opening balance equity", A.EQUITY),
    "4000": ("Sales revenue", A.INCOME),
    "5000": ("Cost of goods sold", A.EXPENSE),
    "5100": ("Inventory write-offs and adjustments", A.EXPENSE),
    "6000": ("Operating expenses", A.EXPENSE),
}
CASH, BANK, CARD, WALLET, RECEIVABLE, INVENTORY = "1000", "1010", "1020", "1030", "1100", "1200"
PAYABLE, TAX_PAYABLE, OPENING_EQUITY, REVENUE, COGS, WRITE_OFF = "2000", "2100", "3000", "4000", "5000", "5100"
PAYMENT_ACCOUNTS = {"cash": CASH, "bank": BANK, "card": CARD, "wallet": WALLET, "credit": RECEIVABLE}


def ensure_default_accounts() -> None:
    for code, (name, type_) in DEFAULT_ACCOUNTS.items():
        Account.objects.get_or_create(code=code, defaults={"name": name, "type": type_, "is_system": True})


def account(code: str) -> Account:
    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        ensure_default_accounts()
        return Account.objects.get(code=code)


@transaction.atomic
def post_entry(*, branch, user, memo: str, lines: list[tuple[str, Decimal, Decimal]], source=None, date=None,
               reversal_of=None) -> JournalEntry | None:
    """lines: (account code, debit, credit). Same-account lines are merged; the entry must balance."""
    date = date or timezone.localdate()
    if FinancialPeriod.objects.filter(is_closed=True, start_date__lte=date, end_date__gte=date).exists():
        raise BusinessError(f"The financial period containing {date} is closed.", code="period_closed")
    net: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for code, debit, credit in lines:
        net[code] += money(debit) - money(credit)
    net = {code: amount for code, amount in net.items() if amount != ZERO}
    if not net:
        return None
    if sum(net.values()) != ZERO:
        raise BusinessError(f"Journal entry does not balance: {memo}", code="unbalanced_entry")
    entry = JournalEntry.objects.create(
        branch=branch, date=date, memo=memo[:255], posted_by=user, reversal_of=reversal_of,
        source_type=getattr(source, "type", ""), source_id=getattr(source, "id", None),
        source_number=getattr(source, "number", ""))
    JournalLine.objects.bulk_create([
        JournalLine(entry=entry, account=account(code), debit=max(amount, ZERO), credit=max(-amount, ZERO))
        for code, amount in sorted(net.items())
    ])
    return entry


@transaction.atomic
def reverse_entries(*, source, user, memo: str) -> list[JournalEntry]:
    """Post mirror-image entries for every unreversed entry of a document."""
    reversals = []
    entries = JournalEntry.objects.filter(
        source_type=source.type, source_id=source.id, reversal_of__isnull=True, reversed_by__isnull=True)
    for entry in entries.prefetch_related("lines__account"):
        lines = [(line.account.code, line.credit, line.debit) for line in entry.lines.all()]
        reversals.append(post_entry(branch=entry.branch, user=user, memo=memo, lines=lines, source=source, reversal_of=entry))
    return reversals


# --- Document postings ----------------------------------------------------------------------

def post_sale(sale, user):
    from apps.inventory.services import Source

    lines = [(PAYMENT_ACCOUNTS[p.method], p.amount, ZERO) for p in sale.payments.all()]
    if sale.change_due:
        lines.append((CASH, ZERO, sale.change_due))
    lines += [(REVENUE, ZERO, sale.total - sale.tax_total), (TAX_PAYABLE, ZERO, sale.tax_total)]
    cost = money(sale.cost_total)
    lines += [(COGS, cost, ZERO), (INVENTORY, ZERO, cost)]
    return post_entry(branch=sale.branch, user=user, memo=f"Sale {sale.number}", lines=lines,
                      source=Source("sale", sale.pk, sale.number))


def post_sale_return(sale_return, user, restocked_cost: Decimal):
    from apps.inventory.services import Source

    refund_account = PAYMENT_ACCOUNTS[sale_return.refund_method]
    cost = money(restocked_cost)
    lines = [
        (REVENUE, sale_return.total - sale_return.tax_total, ZERO),
        (TAX_PAYABLE, sale_return.tax_total, ZERO),
        (refund_account, ZERO, sale_return.total),
        (INVENTORY, cost, ZERO),
        (COGS, ZERO, cost),
    ]
    return post_entry(branch=sale_return.branch, user=user, memo=f"Sales return {sale_return.number}", lines=lines,
                      source=Source("sale_return", sale_return.pk, sale_return.number))


def post_grn(grn, user, inventory_value: Decimal):
    from apps.inventory.services import Source

    value = money(inventory_value)
    # The supplier is owed the invoice total; stock is valued at batch cost. Any sub-cent
    # difference from per-unit cost rounding goes to the adjustments account.
    lines = [(INVENTORY, value, ZERO), (PAYABLE, ZERO, grn.total), (WRITE_OFF, grn.total - value, ZERO)]
    return post_entry(branch=grn.branch, user=user, memo=f"Goods received {grn.number}", lines=lines,
                      source=Source("grn", grn.pk, grn.number))


def post_purchase_return(purchase_return, user, inventory_value: Decimal):
    from apps.inventory.services import Source

    value = money(inventory_value)
    return post_entry(
        branch=purchase_return.branch, user=user, memo=f"Supplier return {purchase_return.number}",
        lines=[(PAYABLE, value, ZERO), (INVENTORY, ZERO, value)],
        source=Source("purchase_return", purchase_return.pk, purchase_return.number))


def post_supplier_payment(payment, user):
    from apps.inventory.services import Source

    return post_entry(
        branch=payment.branch, user=user, memo=f"Payment to {payment.supplier.name}",
        lines=[(PAYABLE, payment.amount, ZERO), (PAYMENT_ACCOUNTS[payment.method], ZERO, payment.amount)],
        source=Source("supplier_payment", payment.pk))


def post_customer_payment(payment, user):
    from apps.inventory.services import Source

    return post_entry(
        branch=payment.branch, user=user, memo=f"Payment from {payment.customer.name}",
        lines=[(PAYMENT_ACCOUNTS.get(payment.method, CASH), payment.amount, ZERO), (RECEIVABLE, ZERO, payment.amount)],
        source=Source("customer_payment", payment.pk))


def post_stock_adjustment(adjustment, movements, user):
    from apps.inventory.services import Source

    value = money(sum((m.quantity * m.unit_cost for m in movements), Decimal("0")))
    contra = OPENING_EQUITY if adjustment.reason == "opening" else WRITE_OFF
    # value > 0 means stock came in: debit inventory. value < 0: credit inventory, debit the write-off.
    lines = [(INVENTORY, value, ZERO), (contra, ZERO, value)]
    return post_entry(branch=adjustment.branch, user=user, memo=f"Stock adjustment {adjustment.number}", lines=lines,
                      source=Source("stock_adjustment", adjustment.pk, adjustment.number))


@transaction.atomic
def record_expense(*, branch, user, account_obj: Account, amount: Decimal, paid_from: str, description: str, date=None) -> Expense:
    if account_obj.type != A.EXPENSE:
        raise serializers.ValidationError({"account": "Choose an expense account."})
    if paid_from not in ("cash", "bank", "card", "wallet"):
        raise serializers.ValidationError({"paid_from": "Unknown payment source."})
    amount = money(amount)
    if amount <= ZERO:
        raise serializers.ValidationError({"amount": "Amount must be positive."})
    date = date or timezone.localdate()
    entry = post_entry(branch=branch, user=user, memo=f"Expense: {description}", date=date,
                       lines=[(account_obj.code, amount, ZERO), (PAYMENT_ACCOUNTS[paid_from], ZERO, amount)])
    expense = Expense.objects.create(branch=branch, account=account_obj, amount=amount, paid_from=paid_from,
                                     description=description, date=date, entry=entry, created_by=user)
    log_action(user=user, action="expense.create", obj=expense, branch=branch, summary=description)
    return expense


# --- Statements -----------------------------------------------------------------------------

def trial_balance(*, branches, date_from=None, date_to=None) -> list[dict]:
    lines = JournalLine.objects.filter(entry__branch__in=branches)
    if date_from:
        lines = lines.filter(entry__date__gte=date_from)
    if date_to:
        lines = lines.filter(entry__date__lte=date_to)
    totals = {row["account"]: row for row in lines.values("account").annotate(debit=Sum("debit"), credit=Sum("credit"))}
    rows = []
    for acc in Account.objects.all():
        row = totals.get(acc.pk)
        if not row:
            continue
        net = (row["debit"] or ZERO) - (row["credit"] or ZERO)
        rows.append({"code": acc.code, "name": acc.name, "type": acc.type,
                     "debit": max(net, ZERO), "credit": max(-net, ZERO)})
    return rows


def account_balance(code: str, branches) -> Decimal:
    """Balance in the account's normal direction."""
    acc = account(code)
    sums = JournalLine.objects.filter(account=acc, entry__branch__in=branches).aggregate(d=Sum("debit"), c=Sum("credit"))
    net = (sums["d"] or ZERO) - (sums["c"] or ZERO)
    return net if acc.is_debit_normal else -net


def profit_and_loss(*, branches, date_from=None, date_to=None) -> dict:
    rows = trial_balance(branches=branches, date_from=date_from, date_to=date_to)
    income = sum((r["credit"] - r["debit"] for r in rows if r["type"] == A.INCOME), ZERO)
    cogs = sum((r["debit"] - r["credit"] for r in rows if r["code"] == COGS), ZERO)
    expenses = sum((r["debit"] - r["credit"] for r in rows if r["type"] == A.EXPENSE and r["code"] != COGS), ZERO)
    return {"revenue": income, "cost_of_goods_sold": cogs, "gross_profit": income - cogs,
            "expenses": expenses, "net_profit": income - cogs - expenses}


def balance_sheet(*, branches, date_to=None) -> dict:
    rows = trial_balance(branches=branches, date_to=date_to)
    assets = sum((r["debit"] - r["credit"] for r in rows if r["type"] == A.ASSET), ZERO)
    liabilities = sum((r["credit"] - r["debit"] for r in rows if r["type"] == A.LIABILITY), ZERO)
    equity = sum((r["credit"] - r["debit"] for r in rows if r["type"] == A.EQUITY), ZERO)
    retained = profit_and_loss(branches=branches, date_to=date_to)["net_profit"]
    return {"assets": assets, "liabilities": liabilities, "equity": equity, "retained_earnings": retained,
            "liabilities_and_equity": liabilities + equity + retained}
