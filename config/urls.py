"""URL configuration for the FC Sky site."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.teams.urls")),
    path("", include("apps.matches.urls")),
    path("", include("apps.competitions.urls")),
    path("", include("apps.notices.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin 사이트 헤더 커스터마이징
admin.site.site_header = "FC Sky 관리자"
admin.site.site_title = "FC Sky 관리자"
admin.site.index_title = "데이터 관리"
