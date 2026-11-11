from django.urls import path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("accounts", api.AccountViewSet, basename="account")
router.register("journal", api.JournalEntryViewSet, basename="journal")
router.register("expenses", api.ExpenseViewSet, basename="expense")
urlpatterns = [path("statements/", api.StatementView.as_view(), name="statements")] + router.urls
