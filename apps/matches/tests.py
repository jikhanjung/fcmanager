from django.test import TestCase
from django.utils import timezone

from apps.competitions.models import Competition
from apps.teams.models import Team

from .models import Match, Opponent


class MatchResultTest(TestCase):
    """Match.result 프로퍼티(승/무/패/미정) 검증."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="우리", slug="us", age_group="50")
        cls.opp = Opponent.objects.create(name="상대")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT)

    def _match(self, gf, ga):
        return Match.objects.create(
            our_team=self.team, opponent=self.opp, competition=self.comp,
            kickoff=timezone.now(), our_score=gf, opponent_score=ga)

    def test_win(self):
        self.assertEqual(self._match(2, 1).result, "W")

    def test_draw(self):
        self.assertEqual(self._match(1, 1).result, "D")

    def test_loss(self):
        self.assertEqual(self._match(0, 2).result, "L")

    def test_unscored_is_none(self):
        self.assertIsNone(self._match(None, None).result)
