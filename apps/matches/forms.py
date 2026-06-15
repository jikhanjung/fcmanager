"""운영진용 경기 결과 편집 폼 (사이트 내 직접 편집)."""
from django import forms
from django.forms import inlineformset_factory

from apps.teams.models import Player

from .models import Match, MatchEvent


class MatchResultForm(forms.ModelForm):
    """최종 스코어·상태·비고."""

    class Meta:
        model = Match
        fields = ["status", "our_score", "opponent_score", "note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "our_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "opponent_score": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
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
        # 편집 시: 득점 행에 짝지어진 기존 도움 선수를 초기값으로.
        inst = getattr(self, "instance", None)
        if inst and inst.pk and inst.event_type == MatchEvent.EventType.GOAL:
            assist = inst.match.events.filter(
                event_type=MatchEvent.EventType.ASSIST,
                side=inst.side, minute=inst.minute,
            ).first()
            if assist:
                self.fields["assist_player"].initial = assist.player_id

    class Meta:
        model = MatchEvent
        fields = ["event_type", "side", "player", "minute", "description"]
        widgets = {
            "event_type": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "side": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "player": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "minute": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 0}),
            "description": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        }


# 경기 1건에 딸린 이벤트들을 한 화면에서 편집. 빈 줄 3개 + 삭제 체크 제공.
MatchEventFormSet = inlineformset_factory(
    Match,
    MatchEvent,
    form=MatchEventForm,
    extra=3,
    can_delete=True,
)
