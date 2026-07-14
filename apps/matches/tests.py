import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.clubs.models import Club
from apps.competitions.models import Competition, CompetitionEntry, Division
from apps.teams.models import Player, Team, TeamMembership

from .models import Match, MatchEvent, Opponent
from .services import recompute_score
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


class SideTranslationTest(TestCase):
    """콘솔 UI(OUR/OPPONENT)를 절대 기준(HOME/AWAY)으로 번역해 저장하는지 검증."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="클럽", slug="c")
        cls.team = Team.objects.create(name="우리", slug="us", age_group="50", club=cls.club)
        cls.opp = Opponent.objects.create(name="상대")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT)
        cls.our_e = CompetitionEntry.objects.create(competition=cls.comp, team=cls.team)
        cls.opp_e = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.opp)
        cls.player = Player.objects.create(name="홍길동", club=cls.club)

    def _act(self, match, **post):
        req = RequestFactory().post("/", post)
        req.session = {}
        setattr(req, "_messages", FallbackStorage(req))
        _handle_live_action(req, match, Player.objects.filter(pk=self.player.pk))

    def _match(self, *, our_home):
        # our_home=True → 우리 팀이 홈, False → 우리 팀이 원정.
        h, a = (self.our_e, self.opp_e) if our_home else (self.opp_e, self.our_e)
        return Match.objects.create(
            club=self.club, competition=self.comp, kickoff=timezone.now(),
            home_entry=h, away_entry=a, status=Match.Status.LIVE,
            period=Match.Period.FIRST)

    def test_our_goal_saved_home_when_our_team_home(self):
        match = self._match(our_home=True)
        self._act(match, action="goal", side="OUR", player=self.player.pk, minute="10")
        goal = match.events.get(event_type=MatchEvent.EventType.GOAL)
        self.assertEqual(goal.side, MatchEvent.Side.HOME)
        self.assertEqual(goal.player_id, self.player.pk)

    def test_our_goal_saved_away_when_our_team_away(self):
        match = self._match(our_home=False)
        self._act(match, action="goal", side="OUR", player=self.player.pk, minute="10")
        goal = match.events.get(event_type=MatchEvent.EventType.GOAL)
        self.assertEqual(goal.side, MatchEvent.Side.AWAY)
        self.assertEqual(goal.player_id, self.player.pk)

    def test_opponent_goal_saved_home_when_our_team_away(self):
        match = self._match(our_home=False)
        self._act(match, action="goal", side="OPPONENT", minute="10")
        goal = match.events.get(event_type=MatchEvent.EventType.GOAL)
        self.assertEqual(goal.side, MatchEvent.Side.HOME)
        self.assertIsNone(goal.player_id)  # 상대 이벤트엔 선수 링크 없음

    def test_score_reflects_side_when_our_team_away(self):
        """우리 팀 원정 경기: 우리 득점=원정 점수, 상대 득점=홈 점수로 집계."""
        match = self._match(our_home=False)
        self._act(match, action="goal", side="OUR", player=self.player.pk, minute="10")
        self._act(match, action="goal", side="OPPONENT", minute="20")
        self._act(match, action="goal", side="OPPONENT", minute="30")
        match.refresh_from_db()
        self.assertEqual(match.away_score, 1)  # 우리(원정) 1골
        self.assertEqual(match.home_score, 2)  # 상대(홈) 2골
        self.assertEqual(match.our_score, 1)
        self.assertEqual(match.opponent_score, 2)


class RecomputeScoreTest(TestCase):
    """recompute_score: side(HOME/AWAY) 기준 집계 + 상대팀 간 경기 산출."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="클럽", slug="c")
        cls.comp = Competition.objects.create(
            name="컵", slug="cup", kind=Competition.Kind.TOURNAMENT)
        cls.opp_a = Opponent.objects.create(name="A팀")
        cls.opp_b = Opponent.objects.create(name="B팀")
        cls.ea = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.opp_a)
        cls.eb = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.opp_b)

    def test_opponent_vs_opponent_score_from_events(self):
        """우리 팀 미참가 경기도 이벤트(HOME/AWAY)로 스코어 산출. 자책골은 상대 진영 산입."""
        match = Match.objects.create(
            club=self.club, competition=self.comp, kickoff=timezone.now(),
            home_entry=self.ea, away_entry=self.eb)
        ET = MatchEvent.EventType
        S = MatchEvent.Side
        MatchEvent.objects.create(match=match, event_type=ET.GOAL, side=S.HOME,
                                  description="빈선규")
        MatchEvent.objects.create(match=match, event_type=ET.GOAL, side=S.HOME,
                                  description="오봉준")
        MatchEvent.objects.create(match=match, event_type=ET.GOAL, side=S.AWAY,
                                  description="정준완")
        # 원정팀 선수의 자책골 → 홈 득점으로 산입.
        MatchEvent.objects.create(match=match, event_type=ET.OWN_GOAL, side=S.AWAY,
                                  description="심재영")
        recompute_score(match)
        match.refresh_from_db()
        self.assertEqual(match.home_score, 3)  # 홈 2골 + 원정 자책 1
        self.assertEqual(match.away_score, 1)  # 원정 1골


class ImportResultsTest(TestCase):
    """import_results 명령: 매칭·스코어·이벤트(side/선수/미상)·멱등 검증."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="스카이", slug="sky")
        cls.comp = Competition.objects.create(
            name="K7 서초", slug="k7-seocho-2026",
            kind=Competition.Kind.LEAGUE, half_length_minutes=30)
        # 우리 팀(스카이 K7) + 상대팀 3개.
        cls.us = Team.objects.create(name="스카이 K7", slug="sky-k7",
                                     age_group="K7", club=cls.club)
        cls.sinus = Opponent.objects.create(name="시누쓰")
        cls.humble = Opponent.objects.create(name="HUMBLEFC")
        cls.aci = Opponent.objects.create(name="ACI")
        cls.e_us = CompetitionEntry.objects.create(competition=cls.comp, team=cls.us)
        cls.e_sinus = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.sinus)
        cls.e_humble = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.humble)
        cls.e_aci = CompetitionEntry.objects.create(competition=cls.comp, opponent=cls.aci)
        # 우리 선수(로스터).
        cls.park = Player.objects.create(name="박찬영", club=cls.club)
        TeamMembership.objects.create(player=cls.park, team=cls.us, competition=cls.comp)

        cls.kickoff = timezone.make_aware(
            timezone.datetime(2026, 7, 12, 11, 20))
        # 우리 경기: 시누쓰(홈) 0-2 스카이 K7(원정) — 기존 픽스처(스코어 있음).
        cls.our_match = Match.objects.create(
            club=cls.club, competition=cls.comp, kickoff=cls.kickoff,
            home_entry=cls.e_sinus, away_entry=cls.e_us,
            home_score=0, away_score=2, status=Match.Status.FINISHED)
        # 상대팀 간 경기: HUMBLEFC(홈) vs ACI(원정) — 스코어 없음(픽스처만).
        cls.opp_match = Match.objects.create(
            club=cls.club, competition=cls.comp,
            kickoff=timezone.make_aware(timezone.datetime(2026, 7, 12, 12, 30)),
            home_entry=cls.e_humble, away_entry=cls.e_aci)

    def _write(self, name, text):
        d = Path(tempfile.mkdtemp())
        p = d / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_opponent_match_score_and_events(self):
        """상대팀 간 경기: 스코어 + 홈/원정 득점자·자책골 반영, 우리 리더보드 불변."""
        md = self._write("humble-aci.md", (
            "---\n"
            "competition: k7-seocho-2026\n"
            "date: 2026-07-12\n"
            "kickoff: \"12:30\"\n"
            "home: HUMBLEFC\n"
            "away: ACI\n"
            "score: 4-2\n"
            "half_minutes: 30\n"
            "---\n\n"
            "## 이벤트\n"
            "| 분 | 팀 | 유형 | 선수 | 도움 |\n"
            "|----|----|------|------|------|\n"
            "| 21 | ACI | 득점 | 빈선규 | |\n"
            "| 23 | ACI | 득점 | 정준완 | |\n"
            "| 40 | HUMBLEFC | 득점 | 오봉준 | |\n"
            "| 50 | ACI | 자책골 | 심재영 | |\n"
            "| 58 | HUMBLEFC | 득점 | 김준수 | |\n"
            "| 60 | HUMBLEFC | 득점 | (미상) | |\n"
        ))
        call_command("import_results", md, "--apply")
        self.opp_match.refresh_from_db()
        self.assertEqual(self.opp_match.home_score, 4)
        self.assertEqual(self.opp_match.away_score, 2)
        self.assertEqual(self.opp_match.status, Match.Status.FINISHED)

        evs = list(self.opp_match.events.filter(
            event_type=MatchEvent.EventType.GOAL).order_by("minute"))
        self.assertEqual(len(evs), 5)   # 자책골은 GOAL 아님
        # 첫 득점: ACI(원정) 빈선규 → side=AWAY, player 없음(상대), description 보존.
        first = evs[0]
        self.assertEqual(first.side, MatchEvent.Side.AWAY)
        self.assertIsNone(first.player_id)
        self.assertEqual(first.description, "빈선규")
        self.assertEqual(first.half, 1)   # 21' ≤ 30 → 전반
        # 미상 득점: description 공란, half=2(60'>30).
        unknown = evs[-1]
        self.assertEqual(unknown.description, "")
        self.assertEqual(unknown.half, 2)
        # 자책골: 원정팀 심재영 → side=AWAY.
        own = self.opp_match.events.get(event_type=MatchEvent.EventType.OWN_GOAL)
        self.assertEqual(own.side, MatchEvent.Side.AWAY)
        # 우리 리더보드(player 링크 이벤트)는 이 경기에서 0.
        self.assertFalse(self.opp_match.events.filter(player__isnull=False).exists())

    def test_our_match_events_link_player_and_side(self):
        """우리 경기(스카이 원정): 우리 선수는 Player 링크, side=AWAY 로 저장."""
        md = self._write("sinus-sky.md", (
            "---\n"
            "competition: k7-seocho-2026\n"
            "date: 2026-07-12\n"
            "kickoff: \"11:20\"\n"
            "home: 시누쓰\n"
            "away: 스카이 K7\n"
            "score: 0-2\n"
            "half_minutes: 30\n"
            "---\n\n"
            "## 이벤트\n"
            "| 분 | 팀 | 유형 | 선수 | 도움 |\n"
            "|----|----|------|------|------|\n"
            "| 14 | 스카이 K7 | 득점 | 박찬영 | |\n"
            "| 21 | 스카이 K7 | 득점 | 동재민 | |\n"
        ))
        call_command("import_results", md, "--apply")
        self.our_match.refresh_from_db()
        self.assertEqual((self.our_match.home_score, self.our_match.away_score), (0, 2))
        goals = list(self.our_match.events.filter(
            event_type=MatchEvent.EventType.GOAL).order_by("minute"))
        self.assertEqual(len(goals), 2)
        # 박찬영: 로스터에 있으니 Player 링크 + side=AWAY(스카이=원정).
        self.assertEqual(goals[0].player_id, self.park.pk)
        self.assertEqual(goals[0].side, MatchEvent.Side.AWAY)
        # 동재민: 로스터에 없음 → player=null + description 보존.
        self.assertIsNone(goals[1].player_id)
        self.assertEqual(goals[1].description, "동재민")

    def test_idempotent(self):
        """두 번 적용해도 이벤트 수·스코어 동일(멱등)."""
        text = (
            "---\ncompetition: k7-seocho-2026\ndate: 2026-07-12\n"
            "kickoff: \"12:30\"\nhome: HUMBLEFC\naway: ACI\nscore: 1-0\n"
            "half_minutes: 30\n---\n\n## 이벤트\n"
            "| 분 | 팀 | 유형 | 선수 | 도움 |\n|--|--|--|--|--|\n"
            "| 40 | HUMBLEFC | 득점 | 오봉준 | |\n"
        )
        md = self._write("h.md", text)
        call_command("import_results", md, "--apply")
        call_command("import_results", md, "--apply")
        self.opp_match.refresh_from_db()
        self.assertEqual(self.opp_match.events.filter(
            event_type=MatchEvent.EventType.GOAL).count(), 1)
        self.assertEqual(self.opp_match.home_score, 1)

    def test_dry_run_writes_nothing(self):
        md = self._write("h.md", (
            "---\ncompetition: k7-seocho-2026\ndate: 2026-07-12\n"
            "kickoff: \"12:30\"\nhome: HUMBLEFC\naway: ACI\nscore: 3-1\n"
            "half_minutes: 30\n---\n"
        ))
        call_command("import_results", md)   # --apply 없음
        self.opp_match.refresh_from_db()
        self.assertIsNone(self.opp_match.home_score)

    def test_no_event_section_keeps_events(self):
        """이벤트 섹션 없는 파일은 스코어만 만지고 기존 이벤트 보존."""
        MatchEvent.objects.create(
            match=self.opp_match, event_type=MatchEvent.EventType.GOAL,
            side=MatchEvent.Side.HOME, description="기존골")
        md = self._write("h.md", (
            "---\ncompetition: k7-seocho-2026\ndate: 2026-07-12\n"
            "kickoff: \"12:30\"\nhome: HUMBLEFC\naway: ACI\nscore: 2-2\n"
            "half_minutes: 30\n---\n"
        ))
        call_command("import_results", md, "--apply")
        self.opp_match.refresh_from_db()
        self.assertEqual(self.opp_match.away_score, 2)
        self.assertEqual(self.opp_match.events.count(), 1)   # 보존


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
