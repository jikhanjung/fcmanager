"""운영진용 대회 편집 폼 (사이트 내 관리)."""
from django import forms
from django.utils.text import slugify

from .models import Award, Competition, CompetitionEntry, Division


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
        # 부문별 길이 오버라이드는 이 폼이 아니라 부문 설정 화면(division_edit)에서 편집.
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


class CompetitionEntryForm(forms.Form):
    """대회 참가팀 추가/편집. 우리 팀(team) 또는 외부팀 이름 중 정확히 하나를 입력.

    외부팀 이름이 기존 Opponent 와 일치하면 연결하고, 없으면 새로 등록한다.
    (Opponent 는 클럽 간 공유되므로 이름을 바꾸지 않고 항상 이름으로 찾거나 만든다.)
    """

    division = forms.ModelChoiceField(
        queryset=Division.objects.none(), label="부문", required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="부문이 없는 대회면 비워 둔다.",
    )
    team = forms.ModelChoiceField(
        queryset=None, label="우리 팀", required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="우리 클럽 팀이 참가하는 경우 선택.",
    )
    opponent_name = forms.CharField(
        label="외부팀 이름", required=False, max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "list": "opponent-names",
                                      "placeholder": "예: 서초FC"}),
        help_text="외부팀이면 이름을 입력(기존 외부팀과 이름이 같으면 자동 연결, 없으면 새로 등록).",
    )
    note = forms.CharField(
        label="비고", required=False, max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, competition, club, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.teams.models import Team
        self.competition = competition
        self.club = club
        self.instance = instance
        self.fields["division"].queryset = competition.divisions.all()
        self.fields["team"].queryset = Team.objects.filter(club=club)
        if instance is not None and not self.is_bound:
            self.initial.update({
                "division": instance.division_id,
                "team": instance.team_id,
                "opponent_name": instance.opponent.name if instance.opponent_id else "",
                "note": instance.note,
            })

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get("team")
        opponent_name = (cleaned.get("opponent_name") or "").strip()
        cleaned["opponent_name"] = opponent_name
        if bool(team) == bool(opponent_name):
            raise forms.ValidationError(
                "'우리 팀' 또는 '외부팀 이름' 중 하나만 입력해 주세요.")
        # 같은 대회·부문 중복 참가 검사.
        qs = CompetitionEntry.objects.filter(
            competition=self.competition, division=cleaned.get("division"))
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        dup = (qs.filter(team=team) if team
               else qs.filter(opponent__name=opponent_name))
        if dup.exists():
            raise forms.ValidationError("이미 이 대회/부문에 등록된 참가팀입니다.")
        return cleaned

    def save(self):
        from apps.matches.models import Opponent
        cd = self.cleaned_data
        entry = self.instance or CompetitionEntry(competition=self.competition)
        entry.division = cd.get("division")
        if cd.get("team"):
            entry.team, entry.opponent = cd["team"], None
        else:
            opponent, _ = Opponent.objects.get_or_create(name=cd["opponent_name"])
            entry.team, entry.opponent = None, opponent
        entry.note = cd.get("note") or ""
        entry.save()
        return entry


class AwardForm(forms.ModelForm):
    """입상 내역 추가/수정 (명예의 전당). 팀·선수 선택은 현재 클럽으로 한정."""

    class Meta:
        model = Award
        fields = ["title", "competition", "team", "player", "rank",
                  "date_awarded", "description"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control",
                                            "placeholder": "예: 우승, 준우승, 득점왕"}),
            "competition": forms.Select(attrs={"class": "form-select"}),
            "team": forms.Select(attrs={"class": "form-select"}),
            "player": forms.Select(attrs={"class": "form-select"}),
            "rank": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "date_awarded": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.teams.models import Player, Team
        self.fields["competition"].queryset = Competition.objects.order_by("-year", "name")
        self.fields["team"].queryset = Team.objects.filter(club=club)
        self.fields["player"].queryset = Player.objects.filter(club=club).order_by("name")
        self.fields["team"].help_text = "팀 수상이면 선택."
        self.fields["player"].help_text = "개인 수상이면 선택."


class DivisionOverrideForm(forms.ModelForm):
    """부문 표시명·시간 오버라이드 편집. 비우면 대회(Competition) 기본값을 사용."""

    class Meta:
        model = Division
        fields = ["name", "half_length_minutes", "extra_half_minutes", "extra_time_single"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control",
                                           "placeholder": "비우면 연령 부문 표시명 사용"}),
            "half_length_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 90,
                       "placeholder": "대회 기본값"}),
            "extra_half_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 60,
                       "placeholder": "대회 기본값"}),
            "extra_time_single": forms.NullBooleanSelect(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # NullBooleanSelect 의 "알 수 없음"을 도메인 언어로 교체.
        self.fields["extra_time_single"].widget.choices = [
            ("unknown", "대회 기본값 사용"),
            ("true", "단일 진행"),
            ("false", "전·후반 진행"),
        ]
