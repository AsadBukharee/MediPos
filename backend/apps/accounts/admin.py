from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class MediPosUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("MediPos", {"fields": ("role", "branches", "phone", "max_discount_percent")}),)
    list_display = ("username", "role", "is_active", "last_login")
    list_filter = ("role", "is_active")
