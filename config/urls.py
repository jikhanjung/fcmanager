"""플랫폼(테넌트 밖) URLconf — admin·랜딩만.

클럽 페이지(`/<club-slug>/...`)는 TenantMiddleware 가 슬러그를 떼고 `config.urls_tenant`
로 라우팅한다. 정적/미디어와 admin·accounts 는 슬러그 밖의 공유/플랫폼 경로다.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from apps.clubs import views as club_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", club_views.platform_home, name="platform_home"),
]

# 개발 환경 미디어 서빙.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin 사이트 헤더 커스터마이징
admin.site.site_header = "FC Sky 관리자"
admin.site.site_title = "FC Sky 관리자"
admin.site.index_title = "데이터 관리"
