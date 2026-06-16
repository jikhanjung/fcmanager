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


class MembershipAddForm(forms.ModelForm):
    """팀에 선수 추가 = 기존 Player(멤버 마스터)에서 선택해 소속을 만든다.

    Player 자체는 별도로 관리하고, 여기서는 새 Player를 만들지 않는다.
    이미 해당 팀·시즌 명단에 있는 선수는 선택지에서 제외(중복 소속 방지).
    """

    class Meta:
        model = TeamMembership
        fields = ["player", "jersey_number", "is_captain"]
        widgets = {
            "player": forms.Select(attrs={"class": "form-select"}),
            "jersey_number": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "is_captain": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, team=None, season=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        self.season = season
        self.fields["player"].label = "선수 선택"
        self.fields["player"].empty_label = "— 선수 선택 —"
        qs = Player.objects.order_by("name")
        if team is not None:
            taken = TeamMembership.objects.filter(
                team=team, season=season).values_list("player_id", flat=True)
            qs = qs.exclude(pk__in=list(taken))
        self.fields["player"].queryset = qs

    def clean(self):
        cleaned = super().clean()
        player = cleaned.get("player")
        if player and self.team is not None and TeamMembership.objects.filter(
                player=player, team=self.team, season=self.season).exists():
            raise forms.ValidationError("이미 이 팀 명단에 있는 선수입니다.")
        return cleaned
