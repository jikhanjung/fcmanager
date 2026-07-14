"""MatchEvent.side 값 마이그레이션: OUR/OPPONENT(우리 클럽 기준) → HOME/AWAY(절대 기준).

경기별로 우리 팀 entry 가 홈인지 원정인지 보고 변환한다(devlog P06 §2.2).
- 우리 경기(our_entry 존재): our_is_home = our_entry == home_entry
    OUR → HOME if our_is_home else AWAY / OPPONENT → 반대
- 상대팀 경기(our_entry 없음): detail 템플릿 컨벤션(OUR=홈) 유지 → OUR→HOME, OPPONENT→AWAY
reverse 는 위 규칙의 역(롤백 대비).
"""
from django.db import migrations


def _our_is_home(match, home, away):
    """우리 팀 entry 가 홈이면 True, 원정이면 False, 상대팀 경기면 None."""
    if home is not None and home.club_id is not None and home.club_id == match.club_id:
        return True
    if away is not None and away.club_id is not None and away.club_id == match.club_id:
        return False
    return None


def forward(apps, schema_editor):
    MatchEvent = apps.get_model("matches", "MatchEvent")
    qs = MatchEvent.objects.select_related(
        "match", "match__home_entry", "match__away_entry"
    )
    for ev in qs:
        m = ev.match
        our_is_home = _our_is_home(m, m.home_entry, m.away_entry)
        if ev.side == "OUR":
            ev.side = "AWAY" if our_is_home is False else "HOME"
        elif ev.side == "OPPONENT":
            ev.side = "HOME" if our_is_home is False else "AWAY"
        else:
            continue
        ev.save(update_fields=["side"])


def reverse(apps, schema_editor):
    MatchEvent = apps.get_model("matches", "MatchEvent")
    qs = MatchEvent.objects.select_related(
        "match", "match__home_entry", "match__away_entry"
    )
    for ev in qs:
        m = ev.match
        our_is_home = _our_is_home(m, m.home_entry, m.away_entry)
        our_side = "AWAY" if our_is_home is False else "HOME"
        if ev.side == our_side:
            ev.side = "OUR"
        elif ev.side in ("HOME", "AWAY"):
            ev.side = "OPPONENT"
        else:
            continue
        ev.save(update_fields=["side"])


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0019_alter_matchevent_side"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
