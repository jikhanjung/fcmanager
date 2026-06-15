"""운영진용 공지사항 작성 폼 (사이트 내 관리)."""
from django import forms

from .models import Notice


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ["title", "body", "is_pinned", "is_published"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "is_pinned": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
