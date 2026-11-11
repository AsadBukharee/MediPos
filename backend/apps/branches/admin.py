from django.contrib import admin

from .models import Branch, BusinessProfile, DocumentSequence

admin.site.register(Branch)
admin.site.register(BusinessProfile)


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    """Invoice / document numbering: change a prefix here."""

    list_display = ("branch", "doc_type", "prefix", "next_number")
    readonly_fields = ("next_number",)
