"""대진 자동 진행(feeder) — 준결승 결과 입력 시 결승을 자동 갱신.

- 반대편 준결승(Match) 결과 입력 → 그 승자(winner_entry)를 결승의 상대 자리(away_entry)에
  자동 기입. (결승은 opponent_feeder 로 그 준결승을 가리킴)
- 우리 준결승(Match) 결과 입력 → 우리가 지면 거기서 진출하는 결승(advance_feeder)을
  '취소'로, 이기면 예정으로 복구.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Match

_LOST_NOTE = "준결승 탈락으로 결승 불참"


def _fill_finals_from_feeder(feeder):
    we = feeder.winner_entry
    if we is None:
        return
    for final in feeder.feeds_opponent_of.all():
        if final.away_entry_id != we.id:
            final.away_entry = we
            final.save(update_fields=["away_entry", "updated_at"])


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


@receiver(post_save, sender=Match)
def match_saved(sender, instance, **kwargs):
    _fill_finals_from_feeder(instance)
    _apply_advancement(instance)
