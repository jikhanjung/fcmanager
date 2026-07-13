"""헬스 엔드포인트 — 배포 계약 `smoke` 동사가 찌르는 가벼운 상태 확인.

반환: 버전 + DB 연결 + 핵심 운영 테이블 행 수. 인증 불요, 가볍게 유지.
DB 이상 시 500 스택트레이스 대신 503 + db:false 로 응답.

fcmanager 는 SECURE_SSL_REDIRECT 를 Django 에서 켜지 않지만(HTTPS 는 앞단 nginx 담당),
smoke 는 관례대로 `X-Forwarded-Proto: https` 를 실어 로컬(127.0.0.1) 평문 검증한다.
경로 예약: `/healthz` 첫 세그먼트는 TenantMiddleware 의 PLATFORM_SEGMENTS 에 등록돼
클럽 슬러그로 해석되지 않는다.
"""
from django.db import connection
from django.http import JsonResponse

from .version import VERSION


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
        payload["status"] = "error"
        payload["error"] = str(exc)
        return JsonResponse(payload, status=503)

    return JsonResponse(payload)
