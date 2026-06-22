from django.test import TestCase
from django.utils import timezone

from apps.clubs.models import Club
from apps.matches.models import Match, Opponent
from apps.teams.models import Team

from .forms import CompetitionForm
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


class CompetitionFormHalfLengthTest(TestCase):
    """대회 편집 폼: 대회 전후반 길이 저장 + 부문 길이 오버라이드는 폼에서 안 건드림."""

    def _data(self, **over):
        data = {
            "name": "컵", "slug": "cup", "kind": Competition.Kind.TOURNAMENT,
            "year": 2026, "half_length_minutes": 30,
            "extra_half_minutes": 15,
            "organizer": "", "description": "",
            "divisions": ["2030", "50"],
        }
        data.update(over)
        return data

    def test_saves_competition_half_length(self):
        form = CompetitionForm(self._data())
        self.assertTrue(form.is_valid(), form.errors)
        comp = form.save()
        self.assertEqual(comp.half_length_minutes, 30)
        # 폼은 부문별 오버라이드를 노출하지 않으므로 신규 부문은 길이 미설정(=대회값 사용).
        self.assertIsNone(comp.divisions.get(age_group="50").half_length_minutes)

    def test_form_has_no_division_override_fields(self):
        form = CompetitionForm(self._data())
        self.assertNotIn("half_min_50", form.fields)
        self.assertNotIn("half_min_2030", form.fields)

    def test_resync_preserves_admin_set_division_length(self):
        """Admin 등에서 설정한 부문 길이는 폼 재저장 시 보존."""
        form = CompetitionForm(self._data())
        comp = form.save()
        d50 = comp.divisions.get(age_group="50")
        d50.half_length_minutes = 25   # Admin 에서 설정했다고 가정
        d50.save()
        # 같은 부문 구성으로 폼 재저장.
        CompetitionForm(self._data(), instance=comp).save()
        d50.refresh_from_db()
        self.assertEqual(d50.half_length_minutes, 25)        # 보존됨
        # 경기 적용 길이: 부문 오버라이드 우선.
        m = Match(club=Club.objects.create(name="K", slug="k"),
                  competition=comp, division=d50)
        self.assertEqual(m.half_length_minutes, 25)
