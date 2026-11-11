from django.contrib import admin

from .models import Account, FinancialPeriod


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "type", "is_system", "is_active")
    list_filter = ("type",)

    def has_delete_permission(self, request, obj=None):
        return False  # accounts with postings must never disappear


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    """Closing a period here blocks any new posting dated inside it."""

    list_display = ("start_date", "end_date", "is_closed", "closed_by")
