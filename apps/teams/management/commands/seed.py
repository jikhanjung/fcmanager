"""FC Sky 초기 데이터 시드 스크립트 (실데이터).

출처:
  - K7 선수 명단: KFA 통합경기정보 시스템 — 2026 K7 서초구 디비전 리그
    (서울서초구 FC스카이축구회) 참가선수 명단.
  - 50대 경기/조편성: 제35회 서초구청장기 축구대회 추첨표·대진표(2026-06-14).

사용:
    python manage.py seed          # 데이터 생성(중복 없이, get_or_create)
    python manage.py seed --flush  # 기존 데이터 전부 삭제 후 재생성
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.teams.models import Team, Player, TeamMembership
from apps.competitions.models import (
    Season, Competition, Division, CompetitionEntry, Award,
)

# Team.AgeGroup -> Division.AgeGroup
_AGE_TO_DIVISION = {"K7": "2030", "40": "40", "50": "50"}
from apps.matches.models import Opponent, Match, MatchEvent, OpponentMatch


# ── 시드 정의 ───────────────────────────────────────────────────────────

SEASON = {"name": "2026", "year": 2026, "is_current": True}

TEAMS = [
    {"name": "스카이 K7", "slug": "sky-k7", "age_group": Team.AgeGroup.K7,
     "description": "서울 서초구 FC스카이축구회 20-30대 팀. "
                    "2026 K7 서초구 디비전 리그 및 서초구청장기(2-30대) 참가."},
    {"name": "스카이 40대", "slug": "sky-40", "age_group": Team.AgeGroup.FORTIES,
     "description": "FC 스카이 40대 팀. 제35회 서초구청장기 축구대회 출전."},
    {"name": "스카이 50대", "slug": "sky-50", "age_group": Team.AgeGroup.FIFTIES,
     "description": "FC 스카이 50대 팀. 제35회 서초구청장기 축구대회 출전."},
]

# 팀 slug -> 선수 명단 (이름, 포지션, 등번호)
# K7: KFA 등록 명단 그대로. 50대: 서초구청장기 득점·도움 기록에 등장한 선수.
ROSTERS = {
    "sky-k7": [
        ("강민혁", "GK", 1), ("박대현", "DF", 2), ("박준혁", "MF", 4),
        ("최민수", "DF", 5), ("오채민", "DF", 6), ("박주성", "FW", 7),
        ("박남준", "MF", 8), ("김민성", "FW", 9), ("서원서", "MF", 10),
        ("박주승", "FW", 11), ("강일규", "MF", 12), ("김성원", "DF", 14),
        ("동재민", "MF", 16), ("최경필", "MF", 17), ("박찬영", "MF", 18),
        ("함기헌", "FW", 19), ("이한서", "DF", 20), ("이종택", "MF", 22),
        ("이상호", "FW", 23), ("김준성", "MF", 24), ("김현서", "MF", 25),
        ("이호경", "MF", 26), ("오건우", "FW", 29), ("강민우", "FW", 30),
        ("공은혁", "GK", 31), ("구자헌", "DF", 52), ("최창원", "MF", 57),
        ("김정민", "DF", 69), ("이윤수", "DF", 77), ("엄길헌", "FW", 83),
        ("김지훈", "MF", 84), ("신윤수", "MF", 86), ("이시호", "FW", 88),
        ("김지한", "GK", 90), ("임도훈", "MF", 99),
    ],
    # 40대 스쿼드: 서초구청장기 득점자. 엄길헌·최창원·신윤수는 K7 명단과 동일인
    # (대회에 따라 K7/40대 스쿼드를 오감 — 팀 인원은 대회마다 변동). 도정구는 신규.
    "sky-40": [
        ("엄길헌", "FW", None), ("최창원", "MF", None),
        ("도정구", "", None), ("신윤수", "MF", None),
    ],
    "sky-50": [
        ("한성준", "", None), ("심종신", "", None),
        ("김흥식", "", None), ("윤기우", "", None),
    ],
}

COMPETITIONS = [
    {"name": "2026 K7 서초구 디비전 리그", "slug": "k7-seocho-2026",
     "kind": Competition.Kind.LEAGUE, "organizer": "서초구축구협회"},
    {"name": "제35회 서초구청장기 축구대회", "slug": "seocho-cup-35",
     "kind": Competition.Kind.TOURNAMENT, "organizer": "서초구청",
     "description": "50대 부문 A조: 신반포·스카이·방현."},
]

# 팀 slug -> 출전 대회 slug 목록
ENTRIES = {
    "sky-k7": ["k7-seocho-2026", "seocho-cup-35"],
    "sky-40": ["seocho-cup-35"],
    "sky-50": ["seocho-cup-35"],
}

# 상대팀: K7 디비전 리그 동일 디비전 팀 + 서초구청장기 상대.
OPPONENTS = [
    "ACI", "FC오키나와", "리얼FC", "시누쓰", "HUMBLEFC",  # K7 디비전
    "신반포", "방현", "내곡", "온누리공사랑",              # 서초구청장기
]

# 경기 (제35회 서초구청장기, 2026-06-14). 부문별 경기장:
#   2-30대=인재개발원, 40대=반포종합운동장, 50대=언남고.
# K7 디비전 리그 경기 일정/결과는 소스에 없어 미등록(상대팀만 등록).
# 득점자 정보가 있는 50대 방현전만 GOAL/ASSIST 이벤트를 기록하고,
# 나머지는 스코어 + 실점(상대 GOAL)만 기록(우리 득점자 미상).
MATCHES = [
    # ── 2-30대 (K7) ──
    {
        # 1경기(11:30 방현) 8:0. 득점자 단축명→정식명: 주성=박주성, 민성=김민성, 찬영=박찬영.
        "our": "sky-k7", "opp": "방현", "comp": "seocho-cup-35",
        "kickoff": datetime(2026, 6, 14, 11, 30), "is_home": False,
        "venue": "인재개발원", "our_score": 8, "opp_score": 0,
        "events": [
            {"side": "OUR", "type": "GOAL", "player": "박주성"},
            {"side": "OUR", "type": "GOAL", "player": "박주성"},
            {"side": "OUR", "type": "GOAL", "player": "동재민"},
            {"side": "OUR", "type": "GOAL", "player": "김민성"},
            {"side": "OUR", "type": "GOAL", "player": "박찬영"},
            {"side": "OUR", "type": "GOAL", "player": "박주성"},
            {"side": "OUR", "type": "GOAL", "player": "김민성"},
            {"side": "OUR", "type": "GOAL", "player": "김민성"},
        ],
    },
    {
        # 2경기(15:30 내곡) 8:0. 1~6골 득점자 미확보, 7·8골만 확인(주성=박주성, 주승=박주승 PK).
        "our": "sky-k7", "opp": "내곡", "comp": "seocho-cup-35",
        "kickoff": datetime(2026, 6, 14, 15, 30), "is_home": True,
        "venue": "인재개발원", "our_score": 8, "opp_score": 0,
        "events": [
            {"side": "OUR", "type": "GOAL", "player": "박주성"},
            {"side": "OUR", "type": "GOAL", "player": "박주승", "desc": "PK"},
        ],
    },
    # ── 40대 ──
    {
        # 7:0 중 득점자 5골 확인(나머지 2골 미상). 길헌=엄길헌, 창원=최창원, 정구=도정구.
        "our": "sky-40", "opp": "온누리공사랑", "comp": "seocho-cup-35",
        "kickoff": datetime(2026, 6, 14, 13, 30), "is_home": True,
        "venue": "반포종합운동장", "our_score": 7, "opp_score": 0,
        "events": [
            {"side": "OUR", "type": "GOAL", "player": "엄길헌"},
            {"side": "OUR", "type": "GOAL", "player": "엄길헌"},
            {"side": "OUR", "type": "GOAL", "player": "최창원"},
            {"side": "OUR", "type": "GOAL", "player": "도정구"},
            {"side": "OUR", "type": "GOAL", "player": "신윤수"},
        ],
    },
    {
        # 3:1 중 엄길헌 1골 확인(나머지 2골 미상), 실점 1.
        "our": "sky-40", "opp": "신반포", "comp": "seocho-cup-35",
        "kickoff": datetime(2026, 6, 14, 15, 30), "is_home": False,
        "venue": "반포종합운동장", "our_score": 3, "opp_score": 1,
        "events": [
            {"side": "OUR", "type": "GOAL", "player": "엄길헌"},
            {"side": "OPPONENT", "type": "GOAL"},
        ],
    },
    # ── 50대 ──
    {
        "our": "sky-50", "opp": "신반포", "comp": "seocho-cup-35",
        "kickoff": datetime(2026, 6, 14, 10, 30), "is_home": False,
        "venue": "언남고", "our_score": 0, "opp_score": 2,
        "events": [
            {"side": "OPPONENT", "type": "GOAL"},
            {"side": "OPPONENT", "type": "GOAL"},
        ],
    },
    {
        "our": "sky-50", "opp": "방현", "comp": "seocho-cup-35",
        "kickoff": datetime(2026, 6, 14, 14, 30), "is_home": True,
        "venue": "언남고", "our_score": 3, "opp_score": 0,
        "events": [
            {"side": "OUR", "type": "GOAL", "player": "한성준"},
            {"side": "OUR", "type": "ASSIST", "player": "김흥식"},
            {"side": "OUR", "type": "GOAL", "player": "심종신"},
            {"side": "OUR", "type": "ASSIST", "player": "한성준"},
            {"side": "OUR", "type": "GOAL", "player": "한성준"},
            {"side": "OUR", "type": "ASSIST", "player": "윤기우"},
        ],
    },
]

# 상대팀 간 경기(우리 팀이 끼지 않은 경기) — 조 순위 보정용.
OPPONENT_MATCHES = [
    # 서초구청장기 50대 A조 (신반포·스카이·방현) 중 우리 미참여 경기.
    {"comp": "seocho-cup-35", "age": Team.AgeGroup.FIFTIES,
     "home": "신반포", "away": "방현", "home_score": 4, "away_score": 2},
]


class Command(BaseCommand):
    help = "FC Sky 초기 데이터(실데이터)를 생성한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="기존 데이터를 모두 삭제한 뒤 다시 생성한다.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("기존 데이터 삭제 중...")
            for model in (MatchEvent, Match, OpponentMatch, Opponent, Award,
                          CompetitionEntry,
                          TeamMembership, Player, Competition, Team, Season):
                model.objects.all().delete()

        # 1) 시즌
        season, _ = Season.objects.get_or_create(
            year=SEASON["year"], defaults=SEASON)

        # 2) 팀
        teams = {}
        for t in TEAMS:
            team, _ = Team.objects.get_or_create(slug=t["slug"], defaults=t)
            teams[t["slug"]] = team

        # 3) 선수 + 소속
        players = {}
        for slug, roster in ROSTERS.items():
            team = teams[slug]
            for name, pos, number in roster:
                player, _ = Player.objects.get_or_create(
                    name=name, defaults={"position": pos})
                players[name] = player
                TeamMembership.objects.get_or_create(
                    player=player, team=team, season=season,
                    defaults={"jersey_number": number, "is_active": True})

        # 4) 대회
        comps = {}
        for c in COMPETITIONS:
            comp, _ = Competition.objects.get_or_create(slug=c["slug"], defaults=c)
            comps[c["slug"]] = comp

        # 5) 대회 출전
        for slug, comp_slugs in ENTRIES.items():
            for cslug in comp_slugs:
                CompetitionEntry.objects.get_or_create(
                    team=teams[slug], competition=comps[cslug], season=season)

        # 6) 상대팀
        opponents = {}
        for name in OPPONENTS:
            opp, _ = Opponent.objects.get_or_create(name=name)
            opponents[name] = opp

        # 7) 경기 + 이벤트
        for m in MATCHES:
            kickoff = timezone.make_aware(m["kickoff"])
            match, created = Match.objects.get_or_create(
                our_team=teams[m["our"]], opponent=opponents[m["opp"]],
                competition=comps[m["comp"]], season=season, kickoff=kickoff,
                defaults={
                    "is_home": m["is_home"], "venue": m["venue"],
                    "status": Match.Status.FINISHED,
                    "our_score": m["our_score"], "opponent_score": m["opp_score"],
                })
            if created:
                for ev in m["events"]:
                    MatchEvent.objects.create(
                        match=match,
                        side=ev["side"],
                        event_type=ev["type"],
                        player=players.get(ev["player"]) if ev.get("player") else None,
                        description=ev.get("desc", ""),
                    )

        # 7-1) 상대팀 간 경기
        for om in OPPONENT_MATCHES:
            OpponentMatch.objects.get_or_create(
                competition=comps[om["comp"]], season=season,
                age_group=om["age"], home=opponents[om["home"]],
                away=opponents[om["away"]],
                defaults={"home_score": om["home_score"],
                          "away_score": om["away_score"]},
            )

        # 8) 부문(Division) 백필 — 0004_backfill_divisions 마이그레이션과 동일 규칙.
        #    여러 연령대가 출전한 대회에만 부문 생성, 명단/경기/출전에 귀속.
        self._apply_divisions(teams.values(), comps.values())

    def _apply_divisions(self, teams, comps):
        def div(comp, team):
            ag = _AGE_TO_DIVISION.get(team.age_group, "OPEN")
            return Division.objects.filter(competition=comp, age_group=ag).first()

        for comp in comps:
            ages = {_AGE_TO_DIVISION.get(e.team.age_group, "OPEN")
                    for e in CompetitionEntry.objects.filter(
                        competition=comp).select_related("team")}
            if len(ages) > 1:
                for ag in ages:
                    Division.objects.get_or_create(competition=comp, age_group=ag)

        for e in CompetitionEntry.objects.select_related("team", "competition"):
            e.division = div(e.competition, e.team)
            e.save(update_fields=["division"])
        for mt in Match.objects.select_related("our_team", "competition"):
            mt.division = div(mt.competition, mt.our_team)
            mt.save(update_fields=["division"])
        for team in teams:
            ag = _AGE_TO_DIVISION.get(team.age_group, "OPEN")
            entries = list(CompetitionEntry.objects.filter(team=team)
                           .select_related("competition")
                           .order_by("-competition__year", "-competition_id"))
            target_comp = target_div = None
            for e in entries:
                d = Division.objects.filter(
                    competition=e.competition, age_group=ag).first()
                if d:
                    target_comp, target_div = e.competition, d
                    break
            if target_comp is None and entries:
                target_comp = entries[0].competition
            if target_comp is not None:
                TeamMembership.objects.filter(team=team).update(
                    competition=target_comp, division=target_div)

        self.stdout.write(self.style.SUCCESS(
            f"시드 완료: 팀 {Team.objects.count()} · 선수 {Player.objects.count()} · "
            f"대회 {Competition.objects.count()} · 상대팀 {Opponent.objects.count()} · "
            f"경기 {Match.objects.count()} · 이벤트 {MatchEvent.objects.count()} · "
            f"상대간 {OpponentMatch.objects.count()} · 입상 {Award.objects.count()}"))
