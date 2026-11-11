from django.urls import path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("alerts", api.StockAlertViewSet, basename="stock-alert")
router.register("", api.NotificationViewSet, basename="notification")

urlpatterns = [
    path("devices/", api.DeviceView.as_view(), name="device"),
    path("preferences/", api.PreferenceView.as_view(), name="notification-preferences"),
] + router.urls
