"""Report queries. Every figure is derived from posted documents and ledgers, never stored twice."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncDay, TruncHour, TruncMonth, TruncWeek
from django.utils import timezone

from apps.common.money import ZERO, money
from apps.customers.models import Customer
from apps.customers.services import customer_balance
from apps.inventory import selectors as stock
from apps.inventory.models import Batch, StockMovement
from apps.purchases.models import GoodsReceivedNote, GRNItem
from apps.sales.models import Sale, SaleItem, SalePayment, SaleReturn
from apps.suppliers.models import Supplier
from apps.suppliers.services import supplier_balance

DEC = DecimalField(max_digits=20, decimal_places=6)


def _dsum(expression):
    return Coalesce(Sum(expression, output_field=DEC), Value(Decimal("0")), output_field=DEC)


def _period(qs, field, date_from, date_to):
    if date_from:
        qs = qs.filter(**{f"{field}__date__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{field}__date__lte": date_to})
    return qs


def completed_sales(branches, date_from=None, date_to=None):
    return _period(Sale.objects.filter(branch__in=branches, status=Sale.Status.COMPLETED), "completed_at", date_from, date_to)


def sale_returns(branches, date_from=None, date_to=None):
    return _period(SaleReturn.objects.filter(branch__in=branches), "created_at", date_from, date_to)


def sales_totals(branches, date_from=None, date_to=None) -> dict:
    sales = completed_sales(branches, date_from, date_to).aggregate(
        gross=_dsum("subtotal"), discount=_dsum("discount_total"), tax=_dsum("tax_total"), total=_dsum("total"),
        cost=_dsum("cost_total"), count=Count("id"))
    returns = sale_returns(branches, date_from, date_to).aggregate(total=_dsum("total"), tax=_dsum("tax_total"), count=Count("id"))
    returned_cost = StockMovement.objects.filter(branch__in=branches, movement_type=StockMovement.Type.SALE_RETURN)
    returned_cost = _period(returned_cost, "created_at", date_from, date_to).aggregate(
        v=_dsum(ExpressionWrapper(F("quantity") * F("unit_cost"), output_field=DEC)))["v"]
    net_revenue = (sales["total"] - sales["tax"]) - (returns["total"] - returns["tax"])
    cost = sales["cost"] - returned_cost
    return {
        "invoices": sales["count"], "gross_sales": money(sales["gross"]), "discounts": money(sales["discount"]),
        "tax": money(sales["tax"] - returns["tax"]), "sales_total": money(sales["total"]),
        "returns": returns["count"], "returns_total": money(returns["total"]),
        "net_sales": money(sales["total"] - returns["total"]), "net_revenue": money(net_revenue),
        "cost_of_goods_sold": money(cost), "gross_profit": money(net_revenue - cost),
    }


SALES_GROUPS = {
    "product": ("product", "product__name"),
    "category": ("product__category", "product__category__name"),
    "cashier": ("sale__cashier", "sale__cashier__username"),
    "customer": ("sale__customer", "sale__customer__name"),
}


def sales_by(group: str, branches, date_from=None, date_to=None, limit=None) -> list[dict]:
    if group == "day":
        rows = (completed_sales(branches, date_from, date_to).annotate(day=TruncDate("completed_at")).values("day")
                .annotate(invoices=Count("id"), total=_dsum("total"), cost=_dsum("cost_total"), tax=_dsum("tax_total"))
                .order_by("day"))
        return [{"key": r["day"], "label": str(r["day"]), "invoices": r["invoices"], "total": money(r["total"]),
                 "profit": money(r["total"] - r["tax"] - r["cost"])} for r in rows]
    if group == "payment_method":
        rows = (SalePayment.objects.filter(sale__in=completed_sales(branches, date_from, date_to)).values("method")
                .annotate(total=_dsum("amount"), payments=Count("id")).order_by("-total"))
        return [{"key": r["method"], "label": r["method"], "payments": r["payments"], "total": money(r["total"])} for r in rows]
    if group not in SALES_GROUPS:
        raise ValueError("Unknown grouping.")
    key, label = SALES_GROUPS[group]
    items = SaleItem.objects.filter(sale__in=completed_sales(branches, date_from, date_to))
    sold = F("quantity_base") - F("returned_base")
    rows = (items.values(key, label).annotate(
        quantity=Coalesce(Sum(sold), Value(0)),
        revenue=_dsum(F("line_total") - F("tax_amount") - F("refunded_amount") + F("refunded_tax")),
        cost=_dsum(ExpressionWrapper(F("cost_total") * sold / F("quantity_base"), output_field=DEC)),
        discount=_dsum("discount_amount"),
    ).order_by("-revenue"))
    if limit:
        rows = rows[:limit]
    return [{"key": r[key], "label": r[label] or "—", "quantity": r["quantity"], "revenue": money(r["revenue"]),
             "discount": money(r["discount"]), "cost": money(r["cost"]), "profit": money(r["revenue"] - r["cost"])}
            for r in rows]


def purchases_by(group: str, branches, date_from=None, date_to=None) -> list[dict]:
    grns = _period(GoodsReceivedNote.objects.filter(branch__in=branches, status="confirmed"), "confirmed_at", date_from, date_to)
    if group == "supplier":
        rows = grns.values("supplier", "supplier__name").annotate(total=_dsum("total"), documents=Count("id")).order_by("-total")
        return [{"key": r["supplier"], "label": r["supplier__name"], "documents": r["documents"], "total": money(r["total"])} for r in rows]
    value = ExpressionWrapper(F("quantity") * F("unit_cost"), output_field=DEC)
    rows = (GRNItem.objects.filter(grn__in=grns).values("product", "product__name")
            .annotate(total=_dsum(value), quantity=Coalesce(Sum(F("quantity") * F("packaging__factor")), Value(0)))
            .order_by("-total"))
    return [{"key": r["product"], "label": r["product__name"], "quantity": r["quantity"], "total": money(r["total"])} for r in rows]


def stock_rows(report: str, branch, days: int = 30) -> list[dict]:
    today = timezone.localdate()
    if report in ("low_stock", "out_of_stock"):
        qs = stock.low_stock(branch) if report == "low_stock" else stock.out_of_stock(branch)
        return [{"product": p.pk, "name": str(p), "sku": p.sku, "sellable": p.sellable, "on_hand": p.on_hand,
                 "reorder_level": p.reorder_level, "max_stock": p.max_stock} for p in qs.order_by("name")]
    if report in ("near_expiry", "expired"):
        qs = stock.near_expiry(branch, days) if report == "near_expiry" else stock.expired(branch)
        return [{"batch": b.pk, "product": b.product_id, "name": str(b.product), "batch_number": b.batch_number,
                 "expiry_date": b.expiry_date, "days_left": (b.expiry_date - today).days, "quantity": b.quantity_on_hand,
                 "value": money(b.quantity_on_hand * b.purchase_cost)} for b in qs.order_by("expiry_date")]
    if report == "valuation":
        value = ExpressionWrapper(F("quantity_on_hand") * F("purchase_cost"), output_field=DEC)
        rows = (Batch.objects.filter(branch=branch, quantity_on_hand__gt=0).values("product", "product__name", "product__sku")
                .annotate(quantity=Sum("quantity_on_hand"), value=_dsum(value)).order_by("-value"))
        return [{"product": r["product"], "name": r["product__name"], "sku": r["product__sku"], "quantity": r["quantity"],
                 "value": money(r["value"])} for r in rows]
    if report in ("fast_moving", "slow_moving", "dead_stock"):
        since = timezone.now() - timedelta(days=days)
        sold = Coalesce(Sum("movements__quantity", filter=Q(
            movements__branch=branch, movements__movement_type="sale", movements__created_at__gte=since)), Value(0))
        last_sale = Max("movements__created_at", filter=Q(movements__branch=branch, movements__movement_type="sale"))
        qs = stock.products_with_stock(branch)
        # products_with_stock joins batches; movement sums are computed separately to avoid row multiplication.
        from apps.catalog.models import Product

        activity = {p.pk: p for p in Product.objects.annotate(sold=sold, last_sale=last_sale)}
        rows = []
        for p in qs.filter(on_hand__gt=0) if report != "fast_moving" else qs:
            a = activity[p.pk]
            units = -a.sold
            if report == "dead_stock" and units > 0:
                continue
            if report == "fast_moving" and units <= 0:
                continue
            rows.append({"product": p.pk, "name": str(p), "sku": p.sku, "on_hand": p.on_hand, "sold": units,
                         "last_sale": a.last_sale})
        rows.sort(key=lambda r: r["sold"], reverse=(report == "fast_moving"))
        return rows[:200]
    raise ValueError("Unknown report.")


def dashboard(branch) -> dict:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    branches = [branch]
    today_totals = sales_totals(branches, today, today)
    month_totals = sales_totals(branches, month_start, today)
    purchases = GoodsReceivedNote.objects.filter(
        branch=branch, status="confirmed", confirmed_at__date__gte=month_start).aggregate(t=_dsum("total"))["t"]
    payables = sum((max(supplier_balance(s, branches), ZERO) for s in Supplier.objects.filter(is_active=True)), ZERO)
    receivables = sum((customer_balance(c) for c in Customer.objects.filter(credit_limit__gt=0)), ZERO)
    return {
        "today_sales": today_totals["net_sales"],
        "today_invoices": today_totals["invoices"],
        "month_revenue": month_totals["net_sales"],
        "month_gross_profit": month_totals["gross_profit"],
        "month_purchases": money(purchases),
        "stock_value": money(stock.stock_value(branch)),
        "low_stock_count": stock.low_stock(branch).filter(sellable__gt=0).count(),
        "out_of_stock_count": stock.out_of_stock(branch).filter(reorder_level__gt=0).count(),
        "near_expiry_count": stock.near_expiry(branch, 30).count(),
        "expired_count": stock.expired(branch).count(),
        "supplier_payables": money(payables),
        "customer_receivables": money(receivables),
        "top_products": sales_by("product", branches, month_start, today, limit=5),
        "sales_chart": sales_by("day", branches, today - timedelta(days=13), today),
    }


# --- Sales trend over time (one line per medicine) ------------------------------------------

TREND_BUCKETS = {"hour": TruncHour, "day": TruncDay, "week": TruncWeek, "month": TruncMonth}
MAX_TREND_SERIES = 8  # the categorical palette has eight slots; more lines cannot be told apart
MAX_TREND_BUCKETS = 400


def _bucket_starts(bucket: str, date_from, date_to) -> list[datetime]:
    """Every bucket start in the range, in local time, matching how the database truncates."""
    starts: list[datetime] = []
    if bucket == "hour":
        cursor, end = datetime.combine(date_from, time.min), datetime.combine(date_to, time.max)
        while cursor <= end:
            starts.append(cursor)
            cursor += timedelta(hours=1)
    elif bucket == "day":
        cursor = date_from
        while cursor <= date_to:
            starts.append(datetime.combine(cursor, time.min))
            cursor += timedelta(days=1)
    elif bucket == "week":
        cursor = date_from - timedelta(days=date_from.weekday())  # Monday, as TruncWeek does
        while cursor <= date_to:
            starts.append(datetime.combine(cursor, time.min))
            cursor += timedelta(days=7)
    else:
        cursor = date_from.replace(day=1)
        while cursor <= date_to:
            starts.append(datetime.combine(cursor, time.min))
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    tz = timezone.get_current_timezone()
    return [timezone.make_aware(start, tz) for start in starts]


def _bucket_label(bucket: str, start: datetime) -> str:
    return start.strftime("%Y-%m-%dT%H:00") if bucket == "hour" else start.date().isoformat()


def sales_trend(*, branches, products, date_from, date_to, bucket: str = "day") -> dict:
    """How much of each medicine was sold per period, as parallel series on one time axis.

    Every series carries a value for every bucket (0 where nothing sold), so the lines share
    one x axis and a quiet period reads as zero instead of a gap the chart would draw through.
    Quantities are what was sold at the time of sale, in base units; later returns are not
    subtracted, because they belong to the day they came back, not the day of the sale.
    """
    if bucket not in TREND_BUCKETS:
        raise ValueError(f"Unknown bucket. Use one of: {', '.join(TREND_BUCKETS)}.")
    if not products:
        raise ValueError("Choose at least one medicine.")
    if len(products) > MAX_TREND_SERIES:
        raise ValueError(f"Up to {MAX_TREND_SERIES} medicines can be compared at once.")
    starts = _bucket_starts(bucket, date_from, date_to)
    if not starts:
        raise ValueError("The date range is empty.")
    if len(starts) > MAX_TREND_BUCKETS:
        raise ValueError(f"That range needs {len(starts)} {bucket} points; choose a wider period or a shorter range.")

    rows = (
        SaleItem.objects.filter(sale__in=completed_sales(branches, date_from, date_to), product__in=products)
        .annotate(t=TREND_BUCKETS[bucket]("sale__completed_at"))
        .values("product_id", "t")
        .annotate(quantity=Coalesce(Sum("quantity_base"), Value(0)), revenue=_dsum("line_total"))
    )
    found = {(row["product_id"], row["t"]): row for row in rows}
    index = {start: position for position, start in enumerate(starts)}

    series = []
    for product in products:
        quantities = [0] * len(starts)
        revenues = [ZERO] * len(starts)
        for start in starts:
            row = found.get((product.pk, start))
            if row:
                position = index[start]
                quantities[position] = row["quantity"]
                revenues[position] = money(row["revenue"])
        peak = max(quantities)
        series.append({
            "product": product.pk,
            "label": str(product),
            "unit": product.base_unit.name,
            "quantity": quantities,
            "revenue": revenues,
            "total_quantity": sum(quantities),
            "total_revenue": money(sum(revenues, ZERO)),
            # The point of the chart: when this medicine moved most.
            "peak_quantity": peak,
            "peak_bucket": _bucket_label(bucket, starts[quantities.index(peak)]) if peak else None,
        })
    series.sort(key=lambda row: row["total_quantity"], reverse=True)
    return {
        "bucket": bucket,
        "date_from": date_from,
        "date_to": date_to,
        "buckets": [_bucket_label(bucket, start) for start in starts],
        "series": series,
    }
