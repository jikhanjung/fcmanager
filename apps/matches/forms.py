"""운영진용 경기 결과 편집 폼 (사이트 내 직접 편집)."""
from django import forms
from django.forms import inlineformset_factory

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
    """득점·도움·카드 등 이벤트 한 줄.

    team_players 가 주어지면 선수 선택지를 해당 팀 등록 선수로 제한한다.
    """

    def __init__(self, *args, team_players=None, **kwargs):
        super().__init__(*args, **kwargs)
        if team_players is not None:
            self.fields["player"].queryset = team_players

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
