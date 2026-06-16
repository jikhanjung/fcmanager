from django.test import TestCase
from django.utils import timezone

from apps.matches.models import Match, Opponent, OpponentMatch
from apps.teams.models import Team

from .models import Competition


class StandingsTest(TestCase):
    """조별 순위표: 우리 경기 + 상대팀 간 경기 합산 검증."""

    @classmethod
    def setUpTestData(cls):
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT, year=2026)
        cls.team = Team.objects.create(name="우리", slug="us", age_group="50")
        cls.a = Opponent.objects.create(name="A")
        cls.b = Opponent.objects.create(name="B")

        def m(opp, gf, ga):
            Match.objects.create(
                our_team=cls.team, opponent=opp, competition=cls.comp,
                kickoff=timezone.now(),
                status=Match.Status.FINISHED, our_score=gf, opponent_score=ga)

        m(cls.a, 3, 0)   # 우리 3:0 A (승)
        m(cls.b, 1, 1)   # 우리 1:1 B (무)
        # 상대팀 간: A 2:0 B
        OpponentMatch.objects.create(
            competition=cls.comp, age_group="50",
            home=cls.a, away=cls.b, home_score=2, away_score=0)

    def test_group_ordering_and_points(self):
        resp = self.client.get("/standings/", {"competition": "cup"})
        self.assertEqual(resp.status_code, 200)
        groups = resp.context["groups"]
        self.assertEqual(len(groups), 1)
        table = groups[0]["table"]

        # 우리 4점(1승1무), A 3점(1승1패), B 1점(1무1패)
        self.assertEqual([r["name"] for r in table], ["우리", "A", "B"])
        self.assertEqual(table[0]["pts"], 4)
        self.assertTrue(table[0]["is_ours"])

    def test_opponent_match_counted(self):
        resp = self.client.get("/standings/", {"competition": "cup"})
        table = resp.context["groups"][0]["table"]
        b = next(r for r in table if r["name"] == "B")
        # 우리전 + A전 = 2경기 (상대팀 간 경기 포함됨)
        self.assertEqual(b["p"], 2)
