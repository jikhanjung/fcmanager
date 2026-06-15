"""운영진용 팀·선수 편집 폼 (사이트 내 관리)."""
from django import forms
from django.utils.text import slugify

from .models import Player, Team, TeamMembership


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "slug", "age_group", "founded_date", "logo", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control",
                                            "placeholder": "URL용 영문 식별자 (예: sky-60). 비우면 자동"}),
            "age_group": forms.Select(attrs={"class": "form-select"}),
            "founded_date": forms.DateInput(attrs={"class": "form-control", "type": "date"},
                                            format="%Y-%m-%d"),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["founded_date"].required = False

    def clean_slug(self):
        # 모델 SlugField는 ASCII만 허용. 한글 이름은 슬러그화 시 비므로 'team' 폴백.
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("name", "")) or "team"
        base, i = slug, 2
        while Team.objects.filter(slug=slug).exclude(pk=self.instance.pk or 0).exists():
            slug, i = f"{base}-{i}", i + 1
        return slug


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name", "birth_year", "position", "squad", "photo", "bio"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "birth_year": forms.NumberInput(attrs={"class": "form-control",
                                                    "min": 1940, "max": 2020}),
            "position": forms.Select(attrs={"class": "form-select"}),
            "squad": forms.TextInput(attrs={"class": "form-control",
                                            "placeholder": "예: 50대초 (선택)"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class MembershipForm(forms.ModelForm):
    """팀 소속 정보(등번호·주장). 선수 폼과 함께 사용."""

    class Meta:
        model = TeamMembership
        fields = ["jersey_number", "is_captain"]
        widgets = {
            "jersey_number": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "is_captain": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
