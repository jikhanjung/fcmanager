from django.db import models
from django.urls import reverse


class Notice(models.Model):
    """공지사항."""

    club = models.ForeignKey(
        "clubs.Club", on_delete=models.CASCADE, related_name="notices",
        verbose_name="클럽",
    )
    title = models.CharField("제목", max_length=200)
    body = models.TextField("내용")
    is_pinned = models.BooleanField("상단 고정", default=False)
    is_published = models.BooleanField("게시", default=True)

    created_at = models.DateTimeField("작성일", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "공지사항"
        verbose_name_plural = "공지사항"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("notices:detail", kwargs={"pk": self.pk})
