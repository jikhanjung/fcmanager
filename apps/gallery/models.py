from django.db import models


class GalleryItem(models.Model):
    """갤러리 항목 (사진 또는 영상 링크)."""

    club = models.ForeignKey(
        "clubs.Club", on_delete=models.CASCADE, related_name="gallery_items",
        verbose_name="클럽",
    )
    title = models.CharField("제목", max_length=200, blank=True)
    image = models.ImageField("사진", upload_to="gallery/%Y/%m/", blank=True)
    video_url = models.URLField("영상 링크", blank=True, help_text="YouTube 등 외부 영상")
    caption = models.CharField("설명", max_length=300, blank=True)
    event_date = models.DateField("촬영/행사일", null=True, blank=True)
    is_published = models.BooleanField("게시", default=True)

    created_at = models.DateTimeField("등록일", auto_now_add=True)

    class Meta:
        verbose_name = "갤러리"
        verbose_name_plural = "갤러리"
        ordering = ["-event_date", "-created_at"]

    def __str__(self):
        return self.title or f"갤러리 #{self.pk}"

    @property
    def is_video(self):
        return bool(self.video_url) and not self.image
