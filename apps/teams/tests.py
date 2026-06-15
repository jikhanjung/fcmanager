from django.core.management import call_command
from django.test import TestCase

from apps.matches.models import Match
from apps.teams.models import Player, Team


class PublicPagesSmokeTest(TestCase):
    """시드 데이터 기반 공개 페이지 스모크 테스트."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed")

    def test_list_pages_ok(self):
        for url in ["/", "/teams/", "/matches/", "/matches/scorers/",
                    "/stats/", "/standings/", "/awards/", "/notices/",
                    "/gallery/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_detail_pages_ok(self):
        self.assertEqual(
            self.client.get(f"/matches/{Match.objects.first().pk}/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/players/{Player.objects.first().pk}/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/teams/{Team.objects.first().slug}/").status_code, 200)

    def test_seed_idempotent(self):
        before = Player.objects.count()
        call_command("seed")  # 다시 실행해도 중복 생성 없음
        self.assertEqual(Player.objects.count(), before)
