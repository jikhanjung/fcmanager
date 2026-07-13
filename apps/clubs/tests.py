from django.test import TestCase

from apps.clubs.models import Club
from apps.notices.models import Notice
from apps.teams.models import Player, Team


class TenantIsolationTest(TestCase):
    """멀티테넌트 격리: 한 클럽 경로에서 다른 클럽 데이터가 보이지 않는다."""

    @classmethod
    def setUpTestData(cls):
        cls.a = Club.objects.create(name="A클럽", slug="a")
        cls.b = Club.objects.create(name="B클럽", slug="b")
        Notice.objects.create(club=cls.a, title="A전용공지", body="x")
        Notice.objects.create(club=cls.b, title="B전용공지", body="y")
        cls.a_team = Team.objects.create(club=cls.a, name="A팀", slug="ateam", age_group="50")
        cls.b_team = Team.objects.create(club=cls.b, name="B팀", slug="bteam", age_group="50")
        cls.b_player = Player.objects.create(club=cls.b, name="B선수")

    def test_team_list_and_detail_isolated(self):
        ra = self.client.get("/a/teams/")
        self.assertContains(ra, "A팀")
        self.assertNotContains(ra, "B팀")
        # 교차: A 경로로 B 팀 상세 → 404
        self.assertEqual(self.client.get(f"/a/teams/{self.b_team.slug}/").status_code, 404)

    def test_player_detail_isolated(self):
        self.assertEqual(self.client.get(f"/a/players/{self.b_player.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/b/players/{self.b_player.pk}/").status_code, 200)

    def test_notice_list_scoped_to_club(self):
        ra = self.client.get("/a/notices/")
        self.assertContains(ra, "A전용공지")
        self.assertNotContains(ra, "B전용공지")
        rb = self.client.get("/b/notices/")
        self.assertContains(rb, "B전용공지")
        self.assertNotContains(rb, "A전용공지")

    def test_cross_club_detail_404(self):
        b_notice = Notice.objects.get(title="B전용공지")
        # A 경로로 B 공지 상세 접근 → 404
        self.assertEqual(
            self.client.get(f"/a/notices/{b_notice.pk}/").status_code, 404)

    def test_unknown_club_404(self):
        self.assertEqual(self.client.get("/zzz/notices/").status_code, 404)

    def test_platform_root_landing(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "/a/")


class ClubPermissionTest(TestCase):
    """클럽별 운영진 권한 + 온보딩."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from apps.clubs.models import ClubMembership
        cls.a = Club.objects.create(name="A", slug="a")
        cls.b = Club.objects.create(name="B", slug="b")
        cls.a_staff = User.objects.create_user("astaff", password="pw")
        ClubMembership.objects.create(user=cls.a_staff, club=cls.a,
                                      role=ClubMembership.Role.STAFF)

    def test_own_club_management_ok(self):
        self.client.force_login(self.a_staff)
        self.assertEqual(self.client.get("/a/teams/add/").status_code, 200)

    def test_other_club_management_forbidden(self):
        self.client.force_login(self.a_staff)
        self.assertEqual(self.client.get("/b/teams/add/").status_code, 403)

    def test_anonymous_management_redirects_login(self):
        self.assertEqual(self.client.get("/a/teams/add/").status_code, 302)

    def test_club_create_makes_owner(self):
        from django.contrib.auth.models import User
        from apps.clubs.models import ClubMembership
        u = User.objects.create_user("owner", password="pw")
        self.client.force_login(u)
        resp = self.client.post("/clubs/new/", {"name": "새클럽", "slug": "new"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ClubMembership.objects.filter(
            user=u, club__slug="new", role=ClubMembership.Role.OWNER).exists())


class HealthzTest(TestCase):
    """배포 계약 smoke 가 찌르는 /healthz — 테넌트 미들웨어를 통과해 플랫폼 경로로 동작."""

    def test_healthz_ok(self):
        from config.version import VERSION
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], VERSION)
        self.assertTrue(data["db"])
        self.assertIn("club", data["counts"])
        self.assertIn("match", data["counts"])

    def test_healthz_not_a_club_slug(self):
        # PLATFORM_SEGMENTS 예약 — 클럽 슬러그로 해석돼 404 나면 안 된다.
        Club.objects.create(name="아무클럽", slug="c")
        self.assertEqual(self.client.get("/healthz").status_code, 200)
