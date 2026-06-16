"""대진 자동 진행(feeder) — 준결승 결과 입력 시 결승을 자동 갱신.

- 반대편 준결승(OpponentMatch) 결과 입력 → 그 승자를 결승(opponent_feeder로 연결된
  Match)의 상대로 자동 기입.
- 우리 준결승(Match) 결과 입력 → 우리가 지면 거기서 진출하는 경기(advance_feeder)를
  '진출 실패'(취소)로, 이기면 예정으로 복구.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Match, OpponentMatch

_LOST_NOTE = "준결승 탈락으로 결승 불참"


def _fill_opponent_from_feeder(final):
    om = final.opponent_feeder
    if om is None:
        return
    winner = om.winner
    if winner is not None and final.opponent_id != winner.id:
        final.opponent = winner
        final.save(update_fields=["opponent", "updated_at"])


def _apply_advancement(sf):
    result = sf.result
    if result is None:
        return
    for final in sf.advances_to.all():
        if result == "L" and final.status != Match.Status.CANCELLED:
            final.status = Match.Status.CANCELLED
            if _LOST_NOTE not in (final.note or ""):
                final.note = (final.note + " · " if final.note else "") + _LOST_NOTE
            final.save(update_fields=["status", "note", "updated_at"])
        elif result == "W" and final.status == Match.Status.CANCELLED:
            final.status = Match.Status.SCHEDULED
            final.save(update_fields=["status", "updated_at"])


@receiver(post_save, sender=OpponentMatch)
def opponent_match_saved(sender, instance, **kwargs):
    for final in instance.feeds_opponent_of.all():
        _fill_opponent_from_feeder(final)


@receiver(post_save, sender=Match)
def match_saved(sender, instance, **kwargs):
    _apply_advancement(instance)
