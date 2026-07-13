"""플랫폼(테넌트 밖) URLconf — admin·랜딩만.

클럽 페이지(`/<club-slug>/...`)는 TenantMiddleware 가 슬러그를 떼고 `config.urls_tenant`
로 라우팅한다. 정적/미디어와 admin·accounts 는 슬러그 밖의 공유/플랫폼 경로다.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.clubs import views as club_views
from config import views_health

urlpatterns = [
    # 배포 계약 smoke 가 찌르는 헬스체크(버전·DB·핵심 행 수). 테넌트 밖 예약 경로.
    path("healthz", views_health.healthz, name="healthz"),
    path("admin/", admin.site.urls),
    # 플랫폼 로그인(테넌트 밖) — 로그인 후 랜딩으로. (클럽 생성·클럽 선택용)
    path("accounts/login/", auth_views.LoginView.as_view(next_page="/"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),
    path("clubs/new/", club_views.club_create, name="club_create"),
    path("", club_views.platform_home, name="platform_home"),
]

# 개발 환경 미디어 서빙.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin 사이트 헤더 커스터마이징
admin.site.site_header = "FCManager 관리자"
admin.site.site_title = "FCManager 관리자"
admin.site.index_title = "데이터 관리"
