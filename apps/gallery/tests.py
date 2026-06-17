from django.test import TestCase

from apps.clubs.models import Club

from .models import GalleryItem


class GalleryViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.get_or_create(slug="fcsky", defaults={"name": "FC Sky"})[0]
        cls.pub = GalleryItem.objects.create(club=cls.club, title="우승 사진", caption="c")
        GalleryItem.objects.create(club=cls.club, title="비공개컷", is_published=False)

    def test_list_ok_and_filters_published(self):
        resp = self.client.get("/fcsky/gallery/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "우승 사진")
        self.assertNotContains(resp, "비공개컷")

    def test_is_video_property(self):
        v = GalleryItem(video_url="https://youtu.be/x")
        self.assertTrue(v.is_video)
        self.assertFalse(self.pub.is_video)
