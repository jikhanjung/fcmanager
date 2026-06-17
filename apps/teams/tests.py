from django.contrib.auth.models import User
from django.test import TestCase

from apps.clubs.models import Club


def _fcsky():
    # 마이그레이션이 fcsky 클럽을 만들지만, 명시적으로 보장.
    return Club.objects.get_or_create(slug="fcsky", defaults={"name": "FC Sky"})[0]


class PublicPagesSmokeTest(TestCase):
    """테넌트(/fcsky/) 공개 페이지 스모크."""

    @classmethod
    def setUpTestData(cls):
        cls.club = _fcsky()

    def test_list_pages_ok(self):
        for url in ["/fcsky/", "/fcsky/teams/", "/fcsky/matches/", "/fcsky/matches/scorers/",
                    "/fcsky/stats/", "/fcsky/standings/", "/fcsky/awards/",
                    "/fcsky/notices/", "/fcsky/gallery/", "/fcsky/competitions/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_unknown_club_404(self):
        self.assertEqual(self.client.get("/nope/").status_code, 404)

    def test_platform_root_landing(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "/fcsky/")


class AuthTest(TestCase):
    """운영진 로그인 / 방문자 구분 (테넌트 경로)."""

    @classmethod
    def setUpTestData(cls):
        from apps.clubs.models import ClubMembership
        club = _fcsky()
        cls.staff = User.objects.create_user(
            "관리자아이디", password="pw1234", is_staff=True)
        # 클럽별 권한: fcsky 운영진으로 등록(관리 메뉴 노출).
        ClubMembership.objects.create(
            user=cls.staff, club=club, role=ClubMembership.Role.OWNER)

    def test_login_page_ok(self):
        resp = self.client.get("/fcsky/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "운영진 로그인")

    def test_anonymous_sees_login_link(self):
        resp = self.client.get("/fcsky/")
        self.assertContains(resp, "로그인")
        self.assertNotContains(resp, "로그아웃")

    def test_staff_sees_admin_and_logout(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/fcsky/")
        self.assertContains(resp, "로그아웃")
        self.assertContains(resp, "/admin/")

    def test_logout_redirects(self):
        self.client.force_login(self.staff)
        resp = self.client.post("/fcsky/accounts/logout/")
        self.assertEqual(resp.status_code, 302)
