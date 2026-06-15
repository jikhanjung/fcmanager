"""URL configuration for the FC Sky site."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.teams.urls")),
    path("", include("apps.matches.urls")),
    path("", include("apps.competitions.urls")),
    path("", include("apps.notices.urls")),
    path("", include("apps.gallery.urls")),
]

# 서브패스 배포(DJANGO_URL_PREFIX 지정 시): 전체 URL을 접두사 하위로 묶는다.
# 모든 내부 링크가 reverse()/{% url %}/{% static %} 기반이라 접두사가 자동 반영된다.
if settings.URL_PREFIX:
    urlpatterns = [path(f"{settings.URL_PREFIX}/", include(urlpatterns))]

# 개발 환경 미디어 서빙. MEDIA_URL이 이미 접두사를 포함하므로 래핑 뒤에 추가한다.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin 사이트 헤더 커스터마이징
admin.site.site_header = "FC Sky 관리자"
admin.site.site_title = "FC Sky 관리자"
admin.site.index_title = "데이터 관리"
