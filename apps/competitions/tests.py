from django.test import TestCase
from django.utils import timezone

from apps.clubs.models import Club
from apps.matches.models import Match, Opponent
from apps.teams.models import Team

from .models import Competition, CompetitionEntry, Division


class StandingsTest(TestCase):
    """부문 순위표: 모든 참가팀(entry) 경기를 home/away 로 합산 검증."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="클럽", slug="c")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT, year=2026)
        cls.div = Division.objects.create(competition=cls.comp, age_group="50")
        cls.team = Team.objects.create(name="우리", slug="us", age_group="50", club=cls.club)
        cls.a = Opponent.objects.create(name="A")
        cls.b = Opponent.objects.create(name="B")
        e_team = CompetitionEntry.objects.create(
            competition=cls.comp, division=cls.div, team=cls.team)
        e_a = CompetitionEntry.objects.create(
            competition=cls.comp, division=cls.div, opponent=cls.a)
        e_b = CompetitionEntry.objects.create(
            competition=cls.comp, division=cls.div, opponent=cls.b)

        def m(home_e, away_e, hs, as_):
            Match.objects.create(
                club=cls.club, competition=cls.comp, division=cls.div,
                stage=Match.Stage.GROUP, kickoff=timezone.now(),
                status=Match.Status.FINISHED,
                home_entry=home_e, away_entry=away_e, home_score=hs, away_score=as_)

        m(e_team, e_a, 3, 0)   # 우리 3:0 A
        m(e_team, e_b, 1, 1)   # 우리 1:1 B
        m(e_a, e_b, 2, 0)      # A 2:0 B (상대팀 간)

    def test_group_ordering_and_points(self):
        resp = self.client.get("/c/standings/", {"competition": "cup"})
        self.assertEqual(resp.status_code, 200)
        groups = resp.context["groups"]
        self.assertEqual(len(groups), 1)
        table = groups[0]["table"]
        # 우리 4점(1승1무), A 3점(1승1패), B 1점(1무1패)
        self.assertEqual([r["name"] for r in table], ["우리", "A", "B"])
        self.assertEqual(table[0]["pts"], 4)
        self.assertTrue(table[0]["is_ours"])

    def test_opponent_match_counted(self):
        resp = self.client.get("/c/standings/", {"competition": "cup"})
        table = resp.context["groups"][0]["table"]
        b = next(r for r in table if r["name"] == "B")
        # 우리전 + A전 = 2경기 (상대팀 간 경기 포함됨)
        self.assertEqual(b["p"], 2)
