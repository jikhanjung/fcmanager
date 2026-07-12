"""운영진용 경기 결과 편집 폼 (사이트 내 직접 편집)."""
from django import forms
from django.forms import inlineformset_factory

from apps.competitions.models import CompetitionEntry, Division
from apps.teams.models import Player

from .models import Match, MatchEvent, MatchVideo, extract_youtube_id


def _entry_label(entry):
    """참가팀 드롭다운 라벨: 이름 (+ 부문이 있으면 부문명)."""
    if entry.division_id:
        return f"{entry.name} ({entry.division.label})"
    return entry.name


def _competition_entries(competition_id):
    """한 대회에 등록된 참가팀 선택지 queryset."""
    return (
        CompetitionEntry.objects
        .filter(competition_id=competition_id)
        .select_related("team", "opponent", "division")
        .order_by("division__age_group", "team__name", "opponent__name")
    )


class OpponentMatchResultForm(forms.ModelForm):
    """상대팀 간 경기(반대편 준결승 등) 결과 입력. 저장 시 연결된 결승 상대가 자동 갱신.

    참가팀 개편 후 '상대팀 간 경기'도 우리 팀 entry 가 없는 일반 Match → home/away 입력.
    """

    class Meta:
        model = Match
        fields = ["home_score", "away_score", "kickoff", "note"]
        widgets = {
            "home_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "away_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "kickoff": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kickoff"].required = False
        self.fields["note"].required = False


class MatchResultForm(forms.ModelForm):
    """경기 정보(대진·일시·장소·부문) + 최종 스코어·상태·연장/승부차기·비고."""

    class Meta:
        model = Match
        fields = [
            "home_entry", "away_entry", "division", "stage", "status",
            "kickoff", "venue",
            "home_score", "away_score",
            "went_to_extra_time", "home_pso_score", "away_pso_score", "note",
        ]
        widgets = {
            "home_entry": forms.Select(attrs={"class": "form-select"}),
            "away_entry": forms.Select(attrs={"class": "form-select"}),
            "division": forms.Select(attrs={"class": "form-select"}),
            "stage": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "kickoff": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"),
            "venue": forms.TextInput(attrs={"class": "form-control"}),
            "home_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "away_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "went_to_extra_time": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "home_pso_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "away_pso_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 홈/원정 참가팀·부문 선택지는 이 경기의 대회(competition)로 제한.
        entries = CompetitionEntry.objects.none()
        divisions = Division.objects.none()
        if self.instance and self.instance.competition_id:
            entries = _competition_entries(self.instance.competition_id)
            divisions = Division.objects.filter(
                competition_id=self.instance.competition_id)
        self.fields["division"].queryset = divisions
        for fname in ("home_entry", "away_entry"):
            self.fields[fname].queryset = entries
            self.fields[fname].required = True
            # 드롭다운 라벨은 참가팀 이름(+부문)만(기본 __str__ 의 '이름 - 대회' 대신).
            self.fields[fname].label_from_instance = _entry_label

    def clean(self):
        cleaned = super().clean()
        home_entry = cleaned.get("home_entry")
        away_entry = cleaned.get("away_entry")
        if home_entry and away_entry and home_entry == away_entry:
            raise forms.ValidationError("홈팀과 원정팀은 서로 다른 팀이어야 합니다.")
        home_pso = cleaned.get("home_pso_score")
        away_pso = cleaned.get("away_pso_score")
        home_score = cleaned.get("home_score")
        away_score = cleaned.get("away_score")
        # 승부차기는 한쪽만 입력하면 안 된다(둘 다 입력하거나 둘 다 비움).
        if (home_pso is None) != (away_pso is None):
            raise forms.ValidationError(
                "승부차기 점수는 양 팀 모두 입력하거나 모두 비워 주세요."
            )
        # 승부차기는 본점수가 동점일 때만 의미가 있다.
        if home_pso is not None and away_pso is not None:
            if home_score is None or away_score is None or home_score != away_score:
                raise forms.ValidationError(
                    "승부차기는 정규/연장 종료 시 동점일 때만 입력할 수 있습니다. "
                    "본점수를 동점으로 맞춰 주세요."
                )
        return cleaned


class MatchCreateForm(forms.ModelForm):
    """대회 상세에서 경기 추가(대진·일정). 스코어·이벤트는 저장 후 '결과 편집'에서 입력."""

    class Meta:
        model = Match
        fields = ["division", "stage", "home_entry", "away_entry",
                  "kickoff", "venue", "status", "note"]
        widgets = {
            "division": forms.Select(attrs={"class": "form-select"}),
            "stage": forms.Select(attrs={"class": "form-select"}),
            "home_entry": forms.Select(attrs={"class": "form-select"}),
            "away_entry": forms.Select(attrs={"class": "form-select"}),
            "kickoff": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"),
            "venue": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, competition, **kwargs):
        super().__init__(*args, **kwargs)
        self.competition = competition
        self.fields["division"].queryset = competition.divisions.all()
        entries = _competition_entries(competition.id)
        for fname in ("home_entry", "away_entry"):
            self.fields[fname].queryset = entries
            self.fields[fname].required = True
            self.fields[fname].label_from_instance = _entry_label
        self.fields["division"].help_text = "부문이 있는 대회면 선택(순위표 집계 기준)."

    def clean(self):
        cleaned = super().clean()
        home_entry = cleaned.get("home_entry")
        away_entry = cleaned.get("away_entry")
        if home_entry and away_entry and home_entry == away_entry:
            raise forms.ValidationError("홈팀과 원정팀은 서로 다른 팀이어야 합니다.")
        return cleaned


class MatchEventForm(forms.ModelForm):
    """득점·카드·교체 등 이벤트 한 줄.

    득점(GOAL) 행에서는 '도움' 선수를 함께 입력할 수 있다(저장 시 ASSIST 이벤트로 동기화).
    도움은 별도 행으로 표시하지 않고 득점 행에서만 관리한다.
    team_players 가 주어지면 선수 선택지를 해당 팀 등록 선수로 제한한다.
    """

    assist_player = forms.ModelChoiceField(
        queryset=Player.objects.all(), required=False, label="도움(득점 시)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def __init__(self, *args, team_players=None, **kwargs):
        super().__init__(*args, **kwargs)
        if team_players is not None:
            self.fields["player"].queryset = team_players
            self.fields["assist_player"].queryset = team_players
        # 편집 시: 득점 행에 연결된 기존 도움 선수를 초기값으로(명시적 링크 사용).
        inst = getattr(self, "instance", None)
        if inst and inst.pk and inst.event_type == MatchEvent.EventType.GOAL:
            assist = inst.assists.first()
            if assist:
                self.fields["assist_player"].initial = assist.player_id

    class Meta:
        model = MatchEvent
        fields = ["event_type", "side", "player", "minute", "description"]
        widgets = {
            "event_type": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "side": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "player": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "minute": forms.NumberInput(attrs={
                "class": "form-control form-control-sm", "min": 0,
                "style": "max-width:6rem",
            }),
            "description": forms.TextInput(attrs={
                "class": "form-control form-control-sm", "style": "max-width:24rem",
            }),
        }


# 경기 1건에 딸린 이벤트들을 한 화면에서 편집. 빈 줄 3개 + 삭제 체크 제공.
MatchEventFormSet = inlineformset_factory(
    Match,
    MatchEvent,
    form=MatchEventForm,
    extra=3,
    can_delete=True,
)


class MatchVideoForm(forms.ModelForm):
    """경기 유튜브 영상 한 줄."""

    class Meta:
        model = MatchVideo
        fields = ["url", "title"]
        widgets = {
            "url": forms.TextInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "유튜브 링크 (youtu.be/... 또는 watch?v=...)",
            }),
            "title": forms.TextInput(attrs={
                "class": "form-control form-control-sm", "placeholder": "제목(선택)",
            }),
        }

    def clean_url(self):
        url = (self.cleaned_data.get("url") or "").strip()
        if url and not extract_youtube_id(url):
            raise forms.ValidationError("유효한 유튜브 링크가 아닙니다.")
        return url


MatchVideoFormSet = inlineformset_factory(
    Match, MatchVideo, form=MatchVideoForm, extra=2, can_delete=True,
)
