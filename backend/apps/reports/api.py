import csv

from django.http import HttpResponse
from django.utils.dateparse import parse_date
from rest_framework import serializers
from rest_framework.response import Response

from apps.common.api import BranchAPIView
from apps.common.schema import documented

from . import selectors


def _dates(request):
    q = request.query_params
    return parse_date(q.get("date_from") or ""), parse_date(q.get("date_to") or "")


def _branches(request):
    """One branch by default; consolidated=1 covers every branch the user may see."""
    if request.query_params.get("consolidated") in {"1", "true"}:
        return list(request.user.accessible_branches())
    return [request.branch]


def _table(request, rows: list[dict], name: str):
    if request.query_params.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
        if rows:
            writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return response
    return Response({"rows": rows})


class ReportView(BranchAPIView):
    read_perm = "reports.view"


class DashboardView(ReportView):
    @documented("Branch dashboard figures")
    def get(self, request):
        return Response(selectors.dashboard(request.branch))


class SalesReportView(ReportView):
    """?group=day|product|category|cashier|customer|payment_method"""

    @documented("Sales totals, or sales grouped by day/product/category/cashier/customer/payment_method",
                params=("group", "date_from", "date_to", "consolidated", "export"))
    def get(self, request):
        date_from, date_to = _dates(request)
        group = request.query_params.get("group", "")
        branches = _branches(request)
        if not group:
            return Response(selectors.sales_totals(branches, date_from, date_to))
        try:
            rows = selectors.sales_by(group, branches, date_from, date_to)
        except ValueError as exc:
            raise serializers.ValidationError({"group": str(exc)})
        return _table(request, rows, f"sales-by-{group}")


class PurchaseReportView(ReportView):
    """?group=supplier|product"""

    @documented("Purchases grouped by supplier or product", params=("group", "date_from", "date_to", "consolidated", "export"))
    def get(self, request):
        date_from, date_to = _dates(request)
        group = request.query_params.get("group", "supplier")
        if group not in ("supplier", "product"):
            raise serializers.ValidationError({"group": "Use supplier or product."})
        return _table(request, selectors.purchases_by(group, _branches(request), date_from, date_to), f"purchases-by-{group}")


class InventoryReportView(ReportView):
    """?report=valuation|low_stock|out_of_stock|near_expiry|expired|fast_moving|slow_moving|dead_stock&days=30"""

    read_perm = "inventory.view"

    @documented("Inventory reports: valuation, low/out of stock, expiry, fast/slow/dead stock", params=("report", "days", "export"))
    def get(self, request):
        report = request.query_params.get("report", "valuation")
        try:
            days = max(1, min(int(request.query_params.get("days", 30)), 3650))
            rows = selectors.stock_rows(report, request.branch, days)
        except ValueError as exc:
            raise serializers.ValidationError({"report": str(exc)})
        return _table(request, rows, report)
