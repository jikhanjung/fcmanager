from django.test import TestCase

from apps.clubs.models import Club

from .models import Notice


class NoticeViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.get_or_create(slug="fcsky", defaults={"name": "FC Sky"})[0]
        cls.pub = Notice.objects.create(club=cls.club, title="공개 공지", body="내용")
        cls.hidden = Notice.objects.create(
            club=cls.club, title="비공개", body="x", is_published=False)

    def test_list_shows_only_published(self):
        resp = self.client.get("/fcsky/notices/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "공개 공지")
        self.assertNotContains(resp, "비공개")

    def test_detail_published_ok(self):
        self.assertEqual(
            self.client.get(f"/fcsky/notices/{self.pub.pk}/").status_code, 200)

    def test_detail_unpublished_404(self):
        self.assertEqual(
            self.client.get(f"/fcsky/notices/{self.hidden.pk}/").status_code, 404)
