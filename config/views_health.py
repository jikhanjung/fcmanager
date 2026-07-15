"""헬스 엔드포인트 — 배포 계약 `smoke` 동사가 찌르는 가벼운 상태 확인.

반환: 버전 + DB 연결 + 핵심 운영 테이블 행 수. 인증 불요, 가볍게 유지.

상태 3종 (0.6.24~ — 계약 §smoke, cdGTS 0.1.68 동형):
  ok        200 — 정상
  degraded  200 — hourly backup_db.py 가 DB 손상을 발견(센티넬 존재). **서빙은 되고 있다.**
  unhealthy 503 — DB 연결 실패 / 마이그레이션 미완 (종전 status 값 "error" 를 계약 이름으로 정렬)

degraded 가 왜 503 이 아닌가: 503 의 의미는 "이 컨테이너에 트래픽을 보내지 말라"인데, btree 한 곳이
깨진 것과 서빙 불능은 다르다. 재시작이 고칠 수 없는 조건으로 LB 에서 빼거나 restart 루프를 돌리면 손해만 난다.
smoke 는 status=="ok" 만 통과시키므로 **200 이어도 배포 게이트는 그대로 걸린다** — 트래픽 의미론 없이 게이트만.

fcmanager 는 SECURE_SSL_REDIRECT 를 Django 에서 켜지 않지만(HTTPS 는 앞단 nginx 담당),
smoke 는 관례대로 `X-Forwarded-Proto: https` 를 실어 로컬(127.0.0.1) 평문 검증한다.
경로 예약: `/healthz` 첫 세그먼트는 TenantMiddleware 의 PLATFORM_SEGMENTS 에 등록돼
클럽 슬러그로 해석되지 않는다.
"""
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

from .version import VERSION

# scripts/backup_db.py 가 DB 디렉터리에 남기는 손상 플래그. 이름을 양쪽에서 맞춘다.
# stat 한 번 — /healthz 에서 integrity_check 를 직접 돌리지 않는 건 의도다(공개·무인증 엔드포인트에
# full scan 을 걸면 DoS 표면이 된다). 비싼 검사는 매시 cron 이 한 번만 한다.
SENTINEL_NAME = "INTEGRITY_FAIL"


def _integrity_sentinel() -> str | None:
    """DB 옆에 손상 플래그가 있으면 그 첫 줄(타임스탬프+사유)을 돌려준다."""
    try:
        sentinel = Path(settings.DATABASES["default"]["NAME"]).parent / SENTINEL_NAME
        return sentinel.read_text().splitlines()[0]
    except (OSError, KeyError, TypeError, IndexError):
        return None  # 없음 = 정상 (in-memory 테스트 DB 포함)


def healthz(request):
    payload = {"status": "ok", "version": VERSION, "db": False, "counts": {}}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        payload["db"] = True

        # 핵심 운영 테이블 행 수 — smoke 의 "행 수 0 아님" 불변식용. 가볍게 count 만.
        from apps.clubs.models import Club
        from apps.matches.models import Match

        payload["counts"] = {
            "club": Club.objects.count(),
            "match": Match.objects.count(),
        }
    except Exception as exc:  # DB down / 마이그레이션 미완 등
        payload["status"] = "unhealthy"
        payload["error"] = str(exc)
        return JsonResponse(payload, status=503)

    # unhealthy 가 우선 — 연결조차 안 되면 손상 여부는 부차적. 건전할 때만 센티넬을 본다.
    if sentinel := _integrity_sentinel():
        payload["status"] = "degraded"
        payload["integrity"] = sentinel

    return JsonResponse(payload)
