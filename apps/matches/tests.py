from datetime import timedelta

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.clubs.models import Club
from apps.competitions.models import Competition, CompetitionEntry, Division
from apps.teams.models import Player, Team

from .models import Match, MatchEvent, Opponent
from .views import _elapsed_seconds, _handle_live_action


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


class LivePeriodTest(TestCase):
    """중계 콘솔 전후반 진행: 단계 전환·시계·이벤트 전/후반 태깅."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="클럽", slug="c")
        cls.team = Team.objects.create(name="우리", slug="us", age_group="50", club=cls.club)
        cls.opp = Opponent.objects.create(name="상대")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT,
            half_length_minutes=30)
        cls.our_e = CompetitionEntry.objects.create(competition=cls.comp, team=cls.team)
        cls.opp_e = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.opp)
        cls.player = Player.objects.create(name="홍길동", club=cls.club)

    def _match(self, **kw):
        return Match.objects.create(
            club=self.club, competition=self.comp, kickoff=timezone.now(),
            home_entry=self.our_e, away_entry=self.opp_e, **kw)

    def _act(self, match, **post):
        req = RequestFactory().post("/", post)
        req.session = {}
        setattr(req, "_messages", FallbackStorage(req))
        _handle_live_action(req, match, Player.objects.filter(pk=self.player.pk))

    def test_stage_flow(self):
        """전반 시작 → 하프타임 → 후반 시작 → 종료 단계 전환과 시각 기록."""
        match = self._match(status=Match.Status.SCHEDULED)
        self._act(match, action="start_first")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.FIRST)
        self.assertEqual(match.status, Match.Status.LIVE)
        self.assertIsNotNone(match.live_started_at)

        self._act(match, action="halftime")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.HALFTIME)

        self._act(match, action="start_second")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.SECOND)
        self.assertIsNotNone(match.second_half_started_at)

        self._act(match, action="finish")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.FINISHED)
        self.assertEqual(match.status, Match.Status.FINISHED)

    def test_first_start_resets_stale_time(self):
        """전반 시작은 옛 시각·후반 시각을 무시하고 새로 세팅."""
        stale = timezone.now() - timedelta(hours=2)
        match = self._match(status=Match.Status.FINISHED, period=Match.Period.FINISHED,
                            live_started_at=stale, second_half_started_at=stale)
        self._act(match, action="start_first")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.FIRST)
        self.assertGreater(match.live_started_at, stale)
        self.assertIsNone(match.second_half_started_at)

    def test_second_half_clock_continues(self):
        """후반 시계는 전후반 길이(30분)부터 이어서 흐른다."""
        now = timezone.now()
        match = self._match(status=Match.Status.LIVE, period=Match.Period.SECOND,
                            live_started_at=now - timedelta(minutes=40),
                            second_half_started_at=now - timedelta(minutes=5))
        # 30분(전반) + 약 5분(후반 경과) ≈ 35분.
        elapsed = _elapsed_seconds(match)
        self.assertGreaterEqual(elapsed, 30 * 60 + 4 * 60)
        self.assertLessEqual(elapsed, 30 * 60 + 6 * 60)

    def test_halftime_clock_frozen_at_half_length(self):
        """하프타임엔 시계가 전후반 길이에서 정지."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.HALFTIME,
                            live_started_at=timezone.now() - timedelta(minutes=40))
        self.assertEqual(_elapsed_seconds(match), 30 * 60)

    def test_event_tagged_with_half(self):
        """후반 진행 중 기록한 득점은 half=2 로 태깅."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.SECOND,
                            second_half_started_at=timezone.now())
        self._act(match, action="goal", side="OUR", player=self.player.pk, minute="35")
        goal = match.events.get(event_type=MatchEvent.EventType.GOAL)
        self.assertEqual(goal.half, 2)


class HalfLengthResolutionTest(TestCase):
    """전후반 길이 해석: 부문(Division) 오버라이드 → 대회 기본값."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="클럽", slug="c")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT,
            half_length_minutes=45)
        cls.div = Division.objects.create(
            competition=cls.comp, age_group="50", half_length_minutes=25)
        cls.div_default = Division.objects.create(
            competition=cls.comp, age_group="40")  # 오버라이드 없음

    def _match(self, division):
        return Match(club=self.club, competition=self.comp, division=division)

    def test_uses_competition_default_when_no_division(self):
        self.assertEqual(self._match(None).half_length_minutes, 45)

    def test_division_override_applies(self):
        self.assertEqual(self._match(self.div).half_length_minutes, 25)

    def test_division_without_override_falls_back(self):
        self.assertEqual(self._match(self.div_default).half_length_minutes, 45)
