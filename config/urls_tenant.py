"""테넌트(클럽) URLconf — TenantMiddleware 가 슬러그를 떼고 이 URLconf 로 보낸다.

여기 경로들은 `/<club-slug>/...` 하위에서 서비스된다(미들웨어가 script prefix 처리).
"""
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.clubs.urls")),
    path("", include("apps.teams.urls")),
    path("", include("apps.matches.urls")),
    path("", include("apps.competitions.urls")),
    path("", include("apps.notices.urls")),
    path("", include("apps.gallery.urls")),
]
