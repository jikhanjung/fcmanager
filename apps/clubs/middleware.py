"""테넌트(클럽) 해석 미들웨어 — SaaS Phase B1.

경로 첫 세그먼트 `/<club-slug>/` 로 클럽을 정한다.
- 클럽이면: request.club 설정 + 슬러그를 path_info 에서 제거 + script prefix 설정 +
  request.urlconf 를 테넌트 URLconf 로. → 기존 뷰·템플릿·reverse 한 줄도 안 바뀐다.
  (현 URL_PREFIX 정적 래핑의 요청별 동적 버전)
- 플랫폼 세그먼트(admin/accounts/static/media)와 루트('')는 통과(플랫폼 URLconf).
- 알 수 없는 첫 세그먼트는 404.
"""
from django.http import Http404
from django.urls import set_script_prefix

from .models import Club

# 클럽 슬러그로 쓸 수 없는 예약 세그먼트(플랫폼 레벨).
PLATFORM_SEGMENTS = {"admin", "accounts", "static", "media", "clubs"}


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.club = None
        first, _, rest = request.path_info.lstrip("/").partition("/")

        if first and first not in PLATFORM_SEGMENTS:
            club = Club.objects.filter(slug=first, is_active=True).first()
            if club is None:
                raise Http404(f"알 수 없는 클럽: {first}")
            request.club = club
            request.urlconf = "config.urls_tenant"
            set_script_prefix(f"/{first}/")
            request.path_info = "/" + rest

        return self.get_response(request)
