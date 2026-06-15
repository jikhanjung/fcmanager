from django.contrib import admin

from .models import Notice


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ["title", "is_pinned", "is_published", "created_at"]
    list_filter = ["is_pinned", "is_published"]
    search_fields = ["title", "body"]
    list_editable = ["is_pinned", "is_published"]
