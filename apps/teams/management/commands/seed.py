"""샘플 데이터 시드 스크립트.

사용:
    python manage.py seed          # 샘플 데이터 생성(중복 없이)
    python manage.py seed --flush  # 기존 샘플 데이터 삭제 후 재생성

get_or_create 기반이라 여러 번 실행해도 안전하다.
"""
from datetime import date, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.teams.models import Team, Player, TeamMembership
from apps.competitions.models import Season, Competition, CompetitionEntry, Award
from apps.matches.models import Opponent, Match, MatchEvent


# ── 시드 정의 ───────────────────────────────────────────────────────────

SEASON = {"name": "2026", "year": 2026, "is_current": True,
          "start_date": date(2026, 3, 1), "end_date": date(2026, 11, 30)}

TEAMS = [
    {"name": "FC Sky K7", "slug": "fcsky-k7", "age_group": Team.AgeGroup.K7,
     "founded_date": date(2007, 3, 1),
     "description": "FC Sky의 20-30대 주축 팀. K7 리그와 시민리그에 출전한다."},
    {"name": "FC Sky 40", "slug": "fcsky-40", "age_group": Team.AgeGroup.FORTIES,
     "founded_date": date(2012, 3, 1),
     "description": "FC Sky 40대 팀. 구청장기·협회장기 대회에 출전한다."},
    {"name": "FC Sky 50", "slug": "fcsky-50", "age_group": Team.AgeGroup.FIFTIES,
     "founded_date": date(2015, 3, 1),
     "description": "FC Sky 50대 팀. 베테랑들의 노련함이 강점이다."},
]

# 팀 slug -> 선수 명단 (이름, 포지션, 등번호, 출생연도, 주장여부)
ROSTERS = {
    "fcsky-k7": [
        ("김도현", Player.Position.GK, 1, 1995, False),
        ("이준서", Player.Position.DF, 4, 1996, True),
        ("박지훈", Player.Position.DF, 5, 1994, False),
        ("최민재", Player.Position.MF, 6, 1997, False),
        ("정우진", Player.Position.MF, 8, 1998, False),
        ("강태영", Player.Position.MF, 10, 1995, False),
        ("윤성호", Player.Position.FW, 9, 1996, False),
        ("임현우", Player.Position.FW, 11, 1999, False),
    ],
    "fcsky-40": [
        ("한상우", Player.Position.GK, 21, 1982, False),
        ("오세훈", Player.Position.DF, 3, 1980, True),
        ("신영록", Player.Position.DF, 13, 1983, False),
        ("배준호", Player.Position.MF, 7, 1981, False),
        ("문대성", Player.Position.MF, 15, 1984, False),
        ("조현식", Player.Position.FW, 19, 1982, False),
    ],
    "fcsky-50": [
        ("권혁수", Player.Position.GK, 1, 1972, False),
        ("남기훈", Player.Position.DF, 2, 1970, True),
        ("황보성", Player.Position.MF, 8, 1973, False),
        ("서동철", Player.Position.MF, 14, 1971, False),
        ("고영호", Player.Position.FW, 9, 1972, False),
    ],
}

COMPETITIONS = [
    {"name": "구청장기 대회", "slug": "gucheongjang", "kind": Competition.Kind.TOURNAMENT,
     "organizer": "구청"},
    {"name": "협회장기 대회", "slug": "hyeophoejang", "kind": Competition.Kind.TOURNAMENT,
     "organizer": "축구협회"},
    {"name": "K7 리그", "slug": "k7-league", "kind": Competition.Kind.LEAGUE,
     "organizer": "K7 리그 운영위"},
    {"name": "시민리그", "slug": "siminleague", "kind": Competition.Kind.LEAGUE,
     "organizer": "시 체육회"},
]

# 팀 slug -> 출전 대회 slug 목록
ENTRIES = {
    "fcsky-k7": ["k7-league", "siminleague", "gucheongjang"],
    "fcsky-40": ["gucheongjang", "hyeophoejang"],
    "fcsky-50": ["gucheongjang", "hyeophoejang"],
}

OPPONENTS = [
    "유나이티드FC", "한빛축구단", "그린필드FC", "강변FC",
    "올스타즈", "드림팀FC", "블루윙즈",
]

# 경기: (우리팀 slug, 상대팀, 대회 slug, 며칠 후(D-day 기준), 홈여부, 우리득점, 상대득점)
#   점수가 None 이면 예정 경기(SCHEDULED), 아니면 종료(FINISHED).
MATCHES = [
    ("fcsky-k7", "유나이티드FC", "k7-league",   -28, True,  3, 1),
    ("fcsky-k7", "한빛축구단",   "k7-league",   -21, False, 2, 2),
    ("fcsky-k7", "그린필드FC",   "siminleague", -14, True,  1, 0),
    ("fcsky-k7", "강변FC",       "k7-league",   -7,  False, 0, 2),
    ("fcsky-k7", "올스타즈",     "k7-league",    4,  True,  None, None),
    ("fcsky-k7", "드림팀FC",     "siminleague",  11, False, None, None),
    ("fcsky-40", "블루윙즈",     "gucheongjang",-20, True,  2, 0),
    ("fcsky-40", "유나이티드FC", "hyeophoejang",-6,  False, 1, 1),
    ("fcsky-40", "한빛축구단",   "gucheongjang", 6,  True,  None, None),
    ("fcsky-50", "그린필드FC",   "gucheongjang",-12, True,  1, 2),
    ("fcsky-50", "강변FC",       "hyeophoejang", 9,  False, None, None),
]

# 입상 내역: (팀 slug, 대회 slug, 수상명, 순위)
AWARDS = [
    ("fcsky-k7", "k7-league",    "준우승", 2),
    ("fcsky-40", "gucheongjang", "우승",   1),
    ("fcsky-50", "hyeophoejang", "3위",    3),
]


class Command(BaseCommand):
    help = "FC Sky 샘플 데이터를 생성한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="기존 데이터를 모두 삭제한 뒤 다시 생성한다.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("기존 데이터 삭제 중...")
            for model in (MatchEvent, Match, Opponent, Award, CompetitionEntry,
                          TeamMembership, Player, Competition, Team, Season):
                model.objects.all().delete()

        today = timezone.localdate()

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
            for name, pos, number, birth, is_captain in roster:
                player, _ = Player.objects.get_or_create(
                    name=name, defaults={"position": pos, "birth_year": birth})
                players[name] = player
                TeamMembership.objects.get_or_create(
                    player=player, team=team, season=season,
                    defaults={"jersey_number": number, "is_captain": is_captain,
                              "is_active": True})

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
        for tslug, oppname, cslug, offset, is_home, gf, ga in MATCHES:
            kickoff = timezone.make_aware(
                timezone.datetime.combine(today + timedelta(days=offset), time(15, 0)))
            finished = gf is not None
            match, created = Match.objects.get_or_create(
                our_team=teams[tslug], opponent=opponents[oppname],
                competition=comps[cslug], season=season, kickoff=kickoff,
                defaults={
                    "is_home": is_home,
                    "venue": "구민운동장" if is_home else "원정 구장",
                    "status": Match.Status.FINISHED if finished else Match.Status.SCHEDULED,
                    "our_score": gf, "opponent_score": ga,
                })
            # 종료 경기에 한해 우리 팀 득점 이벤트 생성(공격수/미드필더에 배분)
            if created and finished and gf:
                scorers = [m.player for m in TeamMembership.objects.filter(
                    team=teams[tslug], season=season,
                    player__position__in=[Player.Position.FW, Player.Position.MF]
                ).select_related("player")]
                for i in range(gf):
                    if not scorers:
                        break
                    scorer = scorers[i % len(scorers)]
                    MatchEvent.objects.create(
                        match=match, side=MatchEvent.Side.OUR, player=scorer,
                        event_type=MatchEvent.EventType.GOAL, minute=15 + i * 20)

        # 8) 입상 내역
        for tslug, cslug, title, rank in AWARDS:
            Award.objects.get_or_create(
                team=teams[tslug], competition=comps[cslug], season=season,
                title=title, defaults={"rank": rank})

        self.stdout.write(self.style.SUCCESS(
            f"시드 완료: 팀 {Team.objects.count()} · 선수 {Player.objects.count()} · "
            f"대회 {Competition.objects.count()} · 경기 {Match.objects.count()} · "
            f"이벤트 {MatchEvent.objects.count()} · 입상 {Award.objects.count()}"))
