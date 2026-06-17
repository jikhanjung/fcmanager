"""운영진용 경기 결과 편집 폼 (사이트 내 직접 편집)."""
from django import forms
from django.forms import inlineformset_factory

from apps.teams.models import Player

from .models import Match, MatchEvent, MatchVideo, extract_youtube_id


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
    """최종 스코어·상태·비고."""

    class Meta:
        model = Match
        fields = ["stage", "status", "home_score", "away_score", "note"]
        widgets = {
            "stage": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "home_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "away_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


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
