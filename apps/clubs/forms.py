from django import forms
from django.utils.text import slugify

from .middleware import PLATFORM_SEGMENTS
from .models import Club


class ClubForm(forms.ModelForm):
    """클럽 생성/수정. slug 는 비우면 이름에서 자동 생성."""

    class Meta:
        model = Club
        fields = ["name", "slug", "logo"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "클럽 이름"}),
            "slug": forms.TextInput(attrs={"class": "form-control",
                                           "placeholder": "주소 (예: fcsky) — 비우면 자동"}),
        }
        help_texts = {"slug": "사이트 주소가 됩니다: /<slug>/"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip().lower()
        if not slug:
            slug = slugify(self.cleaned_data.get("name") or "", allow_unicode=False)
        if not slug:
            raise forms.ValidationError("주소를 입력하거나 영문 이름을 쓰세요.")
        if slug in PLATFORM_SEGMENTS:
            raise forms.ValidationError("사용할 수 없는 주소입니다.")
        if Club.objects.filter(slug=slug).exclude(pk=self.instance.pk or 0).exists():
            raise forms.ValidationError("이미 사용 중인 주소입니다.")
        return slug
