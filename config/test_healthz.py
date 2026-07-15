"""/healthz 상태 3종 — ok / degraded / unhealthy (0.6.24, devlog 094).

degraded 는 smoke 가 배포를 막는 유일한 무인-검사 채널이다(계약 §smoke). 그 계약을 못 박는다:
  - 센티넬이 있으면 degraded 이되 **200**(트래픽 의미론은 건드리지 않는다)
  - DB 가 죽으면 unhealthy(503) 가 **우선**(연결도 안 되면 손상 여부는 부차적)
"""
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase

from apps.clubs.models import Club
from config import views_health
from config.version import VERSION


class HealthzTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 도메인 불변식(club>0)을 smoke 가 본다 — 테스트에서도 한 개는 있어야 ok.
        Club.objects.create(name="테스트 클럽", slug="test-club")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_dir = Path(self._tmp.name)
        # 센티넬 경로는 DB 위치에서 유도된다(규약이 한 곳에서만 오게) — 테스트 DB 는 in-memory 라
        # settings 의 NAME 만 tmp 로 갈아끼운다. 이미 열린 커넥션은 자기 settings_dict 를 쓰므로 무해.
        patcher = mock.patch.dict(
            settings.DATABASES["default"], {"NAME": str(self.db_dir / "db.sqlite3")}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @property
    def sentinel(self) -> Path:
        return self.db_dir / views_health.SENTINEL_NAME

    def get(self):
        res = self.client.get("/healthz")
        return res, json.loads(res.content)

    def test_ok(self):
        res, body = self.get()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["version"], VERSION)
        self.assertTrue(body["db"])
        # smoke 가 보는 도메인 불변식은 "0 아님" — 정확한 수는 마이그레이션 시드에 달렸으니 세지 않는다.
        self.assertGreater(body["counts"]["club"], 0)
        self.assertIn("match", body["counts"])
        self.assertNotIn("integrity", body)

    def test_degraded_is_200_with_reason(self):
        self.sentinel.write_text("2026-07-15 09:00:00 backup_db.py: PRAGMA integrity_check 실패.\n상세\n")
        res, body = self.get()
        self.assertEqual(res.status_code, 200, "degraded 는 503 이 아니다 — 서빙은 되고 있다")
        self.assertEqual(body["status"], "degraded")
        self.assertIn("integrity_check 실패", body["integrity"])
        self.assertNotIn("상세", body["integrity"], "첫 줄만 노출")

    def test_unhealthy_wins_over_degraded(self):
        self.sentinel.write_text("손상\n")
        with mock.patch.object(views_health.connection, "cursor", side_effect=Exception("db down")):
            res, body = self.get()
        self.assertEqual(res.status_code, 503)
        self.assertEqual(body["status"], "unhealthy")
        self.assertNotIn("integrity", body)

    def test_unreadable_sentinel_is_treated_as_absent(self):
        """헬스가 센티넬 때문에 죽으면 안 된다 — 없는 것으로 본다."""
        self.sentinel.mkdir()  # 파일이 아니라 디렉터리 → read_text 가 OSError
        res, body = self.get()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body["status"], "ok")

    def test_sentinel_path_is_derived_from_db_location(self):
        """규약이 backup_db.py 와 한 곳에서 맞물리는지 — 이름·자리 둘 다."""
        from scripts import backup_db

        self.assertEqual(views_health.SENTINEL_NAME, backup_db.SENTINEL_NAME)
        backup_db.raise_sentinel(self.db_dir, ["page 3 malformed"])
        res, body = self.get()
        self.assertEqual(body["status"], "degraded")
        self.assertIn("integrity_check 실패", body["integrity"])
