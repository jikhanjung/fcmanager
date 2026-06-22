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

    def test_pause_freezes_clock_at_paused_moment(self):
        """일시정지 중엔 멈춘 시각 기준으로 시계가 동결(이후 시간 흘러도 그대로)."""
        now = timezone.now()
        match = self._match(status=Match.Status.LIVE, period=Match.Period.FIRST,
                            live_started_at=now - timedelta(minutes=20),
                            paused_at=now - timedelta(minutes=5))
        # 멈춘 시각 기준 경과 = 20분 - 5분 = 15분(현재 시각과 무관).
        self.assertAlmostEqual(_elapsed_seconds(match), 15 * 60, delta=60)

    def test_pause_action_only_while_in_half(self):
        """일시정지는 전·후반 진행 중에만 동작(하프타임 땐 무시)."""
        live = self._match(status=Match.Status.LIVE, period=Match.Period.FIRST,
                           live_started_at=timezone.now() - timedelta(minutes=3))
        self._act(live, action="pause")
        live.refresh_from_db()
        self.assertIsNotNone(live.paused_at)

        ht = self._match(status=Match.Status.LIVE, period=Match.Period.HALFTIME,
                         live_started_at=timezone.now() - timedelta(minutes=40))
        self._act(ht, action="pause")
        ht.refresh_from_db()
        self.assertIsNone(ht.paused_at)

    def test_resume_accumulates_paused_time(self):
        """재개하면 멈춰 있던 시간이 누적 정지에 더해지고 시계가 이어서 흐른다."""
        now = timezone.now()
        match = self._match(status=Match.Status.LIVE, period=Match.Period.FIRST,
                            live_started_at=now - timedelta(minutes=20),
                            paused_at=now - timedelta(minutes=5))
        self._act(match, action="resume")
        match.refresh_from_db()
        self.assertIsNone(match.paused_at)
        self.assertGreaterEqual(match.paused_seconds, 4 * 60)
        # 재개 직후 경과 = 20분 - 약 5분 = 약 15분.
        self.assertAlmostEqual(_elapsed_seconds(match), 15 * 60, delta=60)

    def test_start_half_clears_pause_state(self):
        """후반 시작은 전반의 정지 누적을 초기화한다."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.FIRST,
                            live_started_at=timezone.now() - timedelta(minutes=20),
                            paused_seconds=120)
        self._act(match, action="start_second")
        match.refresh_from_db()
        self.assertEqual(match.paused_seconds, 0)
        self.assertIsNone(match.paused_at)

    # ── 연장전 / 승부차기 ──
    # setUpTestData 의 대회는 half_length=30(→정규 60분), extra_half 기본 15분.

    def test_extra_time_flow(self):
        """후반 → 연장 전반 → 연장 휴식 → 연장 후반 → 승부차기 단계 전환."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.SECOND)
        self._act(match, action="start_et")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.ET_FIRST)
        self.assertIsNotNone(match.et_first_started_at)

        self._act(match, action="et_halftime")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.ET_HALFTIME)

        self._act(match, action="et_start_second")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.ET_SECOND)
        self.assertIsNotNone(match.et_second_started_at)

        self._act(match, action="penalties")
        match.refresh_from_db()
        self.assertEqual(match.period, Match.Period.PENALTIES)

    def test_extra_time_clock_continues_from_fulltime(self):
        """연장 전반 시계는 정규 풀타임(2×30=60분)부터 이어서 흐른다."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.ET_FIRST,
                            et_first_started_at=timezone.now() - timedelta(minutes=3))
        self.assertAlmostEqual(_elapsed_seconds(match), 63 * 60, delta=60)

    def test_extra_time_second_half_clock(self):
        """연장 후반 시계 = 정규(60) + 연장전반(15) + 경과."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.ET_SECOND,
                            et_second_started_at=timezone.now() - timedelta(minutes=2))
        self.assertAlmostEqual(_elapsed_seconds(match), 77 * 60, delta=60)

    def test_et_halftime_frozen(self):
        """연장 휴식엔 시계가 60+15=75분에서 정지."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.ET_HALFTIME,
                            et_first_started_at=timezone.now() - timedelta(minutes=20))
        self.assertEqual(_elapsed_seconds(match), 75 * 60)

    def test_event_tagged_extra_time_half(self):
        """연장 전반 득점은 half=3 으로 태깅."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.ET_FIRST,
                            et_first_started_at=timezone.now())
        self._act(match, action="goal", side="OUR", player=self.player.pk, minute="95")
        goal = match.events.get(event_type=MatchEvent.EventType.GOAL)
        self.assertEqual(goal.half, 3)

    def test_penalty_shootout_score_and_winner(self):
        """승부차기 킥 집계 → 본점수 동점 시 승부차기 승자가 경기 승자."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.PENALTIES)
        self._act(match, action="pso_goal", side="OUR")
        self._act(match, action="pso_goal", side="OUR")
        self._act(match, action="pso_goal", side="OPPONENT")
        self._act(match, action="pso_miss", side="OPPONENT")
        match.refresh_from_db()
        # 본점수는 득점 이벤트 없어 0-0(동점), 승부차기 2-1.
        self.assertEqual(match.our_pso_score, 2)
        self.assertEqual(match.opponent_pso_score, 1)
        self.assertTrue(match.decided_by_penalties)
        self.assertEqual(match.winner_entry, match.home_entry)  # 우리=home

    def test_no_pso_events_means_null_scores(self):
        """승부차기 이벤트가 없으면 PSO 스코어는 None(집계 안 함)."""
        match = self._match(status=Match.Status.LIVE, period=Match.Period.SECOND)
        self._act(match, action="goal", side="OUR", player=self.player.pk, minute="10")
        match.refresh_from_db()
        self.assertIsNone(match.home_pso_score)
        self.assertIsNone(match.away_pso_score)


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
