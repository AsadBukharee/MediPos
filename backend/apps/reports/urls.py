from django.urls import path

from . import api

urlpatterns = [
    path("dashboard/", api.DashboardView.as_view(), name="dashboard"),
    path("sales/", api.SalesReportView.as_view(), name="sales-report"),
    path("sales/trend/", api.SalesTrendView.as_view(), name="sales-trend"),
    path("purchases/", api.PurchaseReportView.as_view(), name="purchase-report"),
    path("inventory/", api.InventoryReportView.as_view(), name="inventory-report"),
]
