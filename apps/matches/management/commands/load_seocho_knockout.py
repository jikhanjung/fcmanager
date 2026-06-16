"""제35회 서초구청장기 — 스카이 준결승/결승 일정 입력 (멱등).

출처: data/sky_0616.zip (카카오톡 캡처, 2026-06-16). 상세 추출 내용은
data/seocho35_준결승결승_요약.md 참고.

- 운영서버에서도 안전하게 돌도록 모든 객체를 이름/슬러그 기준 get_or_create.
  (로컬 PK에 의존하지 않음 — 운영 데이터와 충돌 없이 추가만 함)
- 생성 대상: 스카이가 치르는 4경기(준결승 40대·20·30대 + 결승 40대·20·30대).
  결승 상대는 준결승 승자라 아직 미정 → 상대팀 "미정"으로 두고 SCHEDULED.
  운영서버에서 준결승 종료 후 상대팀만 교체하면 됨.

사용:
    python manage.py load_seocho_knockout
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.competitions.models import Competition, CompetitionEntry, Division
from apps.matches.models import Match, Opponent, OpponentMatch
from apps.teams.models import Team

# Team.AgeGroup -> Division.AgeGroup
AGE_TO_DIVISION = {"K7": "2030", "40": "40", "50": "50"}


SEASON = {"name": "2026", "year": 2026, "is_current": True}

COMPETITION = {
    "name": "제35회 서초구청장기 축구대회", "slug": "seocho-cup-35",
    "kind": Competition.Kind.TOURNAMENT, "organizer": "서초구청",
}

# 슬러그 -> 팀 정의 (seed.py 와 동일 슬러그. 없으면 생성).
TEAMS = {
    "sky-40": {"name": "스카이 40대", "slug": "sky-40",
               "age_group": Team.AgeGroup.FORTIES},
    "sky-k7": {"name": "스카이 K7", "slug": "sky-k7",
               "age_group": Team.AgeGroup.K7},
}

# 스카이 녹아웃 경기 (2026-06-21). 결승 상대는 반대편 준결승 승자(미정).
#   round: 표시용, our: 팀 슬러그, opp: 상대팀명, kickoff, venue, is_home(대진표 좌측=홈)
#   결승은 자동 진행 연결:
#     advance_from: 우리 준결승 상대명(우리가 이겨야 결승 진출)
#     other_sf: (홈, 원정) 반대편 준결승 → 그 승자가 결승 상대로 자동 기입
MATCHES = [
    {"round": "준결승", "our": "sky-40", "opp": "양재",
     "kickoff": datetime(2026, 6, 21, 10, 0), "venue": "언남고등학교", "is_home": True},
    {"round": "준결승", "our": "sky-k7", "opp": "서초크루",
     "kickoff": datetime(2026, 6, 21, 11, 0), "venue": "양재근린공원", "is_home": True},
    {"round": "결승", "our": "sky-40", "opp": "미정",
     "kickoff": datetime(2026, 6, 21, 14, 0), "venue": "양재근린공원", "is_home": True,
     "note": "준결승(스카이/양재) 승자 vs (매현/신반포) 승자",
     "advance_from": "양재", "other_sf": ("매현", "신반포")},
    {"round": "결승", "our": "sky-k7", "opp": "미정",
     "kickoff": datetime(2026, 6, 21, 15, 0), "venue": "양재근린공원", "is_home": True,
     "note": "준결승(스카이/서초크루) 승자 vs (서초/ACI) 승자",
     "advance_from": "서초크루", "other_sf": ("서초", "ACI")},
]


class Command(BaseCommand):
    help = "제35회 서초구청장기 스카이 준결승/결승 일정을 입력한다(멱등)."

    @transaction.atomic
    def handle(self, *args, **options):
        comp, _ = Competition.objects.get_or_create(
            slug=COMPETITION["slug"],
            defaults={**COMPETITION, "year": SEASON["year"]})

        teams = {}
        divisions = {}  # team slug -> Division
        for slug, t in TEAMS.items():
            team, _ = Team.objects.get_or_create(slug=slug, defaults=t)
            teams[slug] = team
            div, _ = Division.objects.get_or_create(
                competition=comp, age_group=AGE_TO_DIVISION.get(team.age_group, "OPEN"))
            divisions[slug] = div
            CompetitionEntry.objects.get_or_create(
                team=team, competition=comp, division=div)

        stage_map = {"준결승": Match.Stage.SEMI, "결승": Match.Stage.FINAL}
        created = 0
        sf_by_opp = {}   # 우리 준결승: 상대명 -> Match (결승 advance_feeder 연결용)
        finals = []      # (final Match, data) — feeder 연결을 모든 경기 생성 후 수행
        for m in MATCHES:
            opp, _ = Opponent.objects.get_or_create(name=m["opp"])
            kickoff = timezone.make_aware(m["kickoff"])
            note = f"{COMPETITION['name']} {m['round']}"
            if m.get("note"):
                note += f" — {m['note']}"
            match, was_created = Match.objects.get_or_create(
                our_team=teams[m["our"]], opponent=opp, competition=comp,
                kickoff=kickoff,
                defaults={
                    "division": divisions[m["our"]],
                    "stage": stage_map.get(m["round"], Match.Stage.GROUP),
                    "is_home": m["is_home"], "venue": m["venue"],
                    "status": Match.Status.SCHEDULED, "note": note,
                },
            )
            created += int(was_created)
            if m["round"] == "준결승":
                sf_by_opp[m["opp"]] = match
            if m.get("other_sf"):
                finals.append((match, m))
            label = "생성" if was_created else "이미 있음"
            self.stdout.write(
                f"  [{label}] {m['round']} {match.our_team} vs {opp} "
                f"@ {m['venue']} ({m['kickoff']:%m-%d %H:%M})")

        # 결승 자동 진행 연결: 반대편 준결승(OpponentMatch) 생성 + feeder 지정.
        linked = 0
        for final, m in finals:
            home, _ = Opponent.objects.get_or_create(name=m["other_sf"][0])
            away, _ = Opponent.objects.get_or_create(name=m["other_sf"][1])
            other_sf, _ = OpponentMatch.objects.get_or_create(
                competition=comp, age_group=final.our_team.age_group,
                home=home, away=away,
                defaults={"stage": Match.Stage.SEMI,
                          "note": f"{COMPETITION['name']} 준결승(반대편)"},
            )
            our_sf = sf_by_opp.get(m["advance_from"])
            changed = []
            if final.opponent_feeder_id != other_sf.id:
                final.opponent_feeder = other_sf; changed.append("opponent_feeder")
            if our_sf and final.advance_feeder_id != our_sf.id:
                final.advance_feeder = our_sf; changed.append("advance_feeder")
            if changed:
                final.save(update_fields=changed + ["updated_at"])
                linked += 1

        self.stdout.write(self.style.SUCCESS(
            f"완료: 경기 {created}건 신규 / 총 {len(MATCHES)}건 처리, 결승 {linked}건 대진 연결. "
            "반대편 준결승 결과를 입력하면 결승 상대가 자동 기입됩니다."))
