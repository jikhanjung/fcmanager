from django.test import TestCase

from apps.clubs.models import Club
from apps.notices.models import Notice


class TenantIsolationTest(TestCase):
    """멀티테넌트 격리: 한 클럽 경로에서 다른 클럽 데이터가 보이지 않는다."""

    @classmethod
    def setUpTestData(cls):
        cls.a = Club.objects.create(name="A클럽", slug="a")
        cls.b = Club.objects.create(name="B클럽", slug="b")
        Notice.objects.create(club=cls.a, title="A전용공지", body="x")
        Notice.objects.create(club=cls.b, title="B전용공지", body="y")

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

    def test_platform_root_redirects_to_a_club(self):
        self.assertEqual(self.client.get("/").status_code, 302)
