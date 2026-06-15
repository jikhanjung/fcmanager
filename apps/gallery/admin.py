from django.contrib import admin

from .models import GalleryItem


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ["__str__", "event_date", "has_image", "has_video",
                    "is_published"]
    list_filter = ["is_published"]
    search_fields = ["title", "caption"]
    list_editable = ["is_published"]

    @admin.display(boolean=True, description="사진")
    def has_image(self, obj):
        return bool(obj.image)

    @admin.display(boolean=True, description="영상")
    def has_video(self, obj):
        return bool(obj.video_url)
