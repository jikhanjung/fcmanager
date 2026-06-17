from django.test import TestCase
from django.utils import timezone

from apps.clubs.models import Club
from apps.competitions.models import Competition, CompetitionEntry
from apps.teams.models import Team

from .models import Match, Opponent


class MatchResultTest(TestCase):
    """Match.result 프로퍼티(승/무/패/미정) 검증 — home/away entry 기준 우리 관점."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="클럽", slug="c")
        cls.team = Team.objects.create(name="우리", slug="us", age_group="50", club=cls.club)
        cls.opp = Opponent.objects.create(name="상대")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT)
        cls.our_e = CompetitionEntry.objects.create(competition=cls.comp, team=cls.team)
        cls.opp_e = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.opp)

    def _match(self, gf, ga):
        # 우리 팀을 home 으로 두면 our_score=home_score.
        return Match.objects.create(
            club=self.club, competition=self.comp, kickoff=timezone.now(),
            home_entry=self.our_e, away_entry=self.opp_e,
            home_score=gf, away_score=ga)

    def test_win(self):
        self.assertEqual(self._match(2, 1).result, "W")

    def test_draw(self):
        self.assertEqual(self._match(1, 1).result, "D")

    def test_loss(self):
        self.assertEqual(self._match(0, 2).result, "L")

    def test_unscored_is_none(self):
        self.assertIsNone(self._match(None, None).result)
