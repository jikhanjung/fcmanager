"""운영진용 대회 편집 폼 (사이트 내 관리)."""
from django import forms
from django.utils.text import slugify

from .models import Competition, Division


class CompetitionForm(forms.ModelForm):
    """대회 생성/수정 + 연령 부문(체크박스) 동기화."""

    divisions = forms.MultipleChoiceField(
        label="부문", choices=Division.AgeGroup.choices, required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="대회에 둘 연령 부문을 선택(없는 대회도 가능).",
    )

    class Meta:
        model = Competition
        fields = ["name", "slug", "kind", "year", "half_length_minutes",
                  "extra_half_minutes", "extra_time_single", "organizer", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control",
                                           "placeholder": "URL용 영문 식별자. 비우면 자동"}),
            "kind": forms.Select(attrs={"class": "form-select"}),
            "year": forms.NumberInput(attrs={"class": "form-control", "min": 2000, "max": 2100}),
            "half_length_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 90}),
            "extra_half_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 60}),
            "extra_time_single": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "organizer": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["half_length_minutes"].help_text = (
            "전·후반 한 쪽 길이. 중계 콘솔 시계·후반 시작점 기준.")
        self.fields["extra_half_minutes"].help_text = (
            "연장 한 쪽 길이(녹아웃 동점 시). 단일 연장이면 이 값의 2배가 전체 연장.")
        # 부문별 길이 오버라이드는 드물어 폼에서 노출하지 않음(필요 시 Admin에서 편집).
        if self.instance.pk:
            self.fields["divisions"].initial = list(
                self.instance.divisions.values_list("age_group", flat=True))

    def clean_slug(self):
        # SlugField는 ASCII만 허용. 한글 이름은 slugify 시 비므로 'competition' 폴백 + 중복 회피.
        slug = (self.cleaned_data.get("slug")
                or slugify(self.cleaned_data.get("name", "")) or "competition")
        base, i = slug, 2
        while Competition.objects.filter(slug=slug).exclude(pk=self.instance.pk or 0).exists():
            slug, i = f"{base}-{i}", i + 1
        return slug

    def save(self, commit=True):
        comp = super().save(commit=commit)
        if commit:
            self.sync_divisions(comp)
        return comp

    def sync_divisions(self, comp):
        """선택된 부문에 맞춰 Division 행을 생성/삭제(없는 것 추가, 빠진 것 제거).

        기존 부문의 길이 오버라이드(half_length_minutes)는 건드리지 않는다(Admin 편집 보존).
        """
        selected = set(self.cleaned_data.get("divisions") or [])
        existing = set(comp.divisions.values_list("age_group", flat=True))
        for ag in selected - existing:
            Division.objects.create(competition=comp, age_group=ag)
        comp.divisions.filter(age_group__in=(existing - selected)).delete()
