"""테넌트(클럽) 스코프 URL — 클럽 멤버십(운영진 구성) 관리. 소유자 전용."""
from django.urls import path

from . import views

app_name = "clubs"

urlpatterns = [
    path("manage/members/", views.member_manage, name="member_manage"),
    path("manage/members/<int:pk>/role/", views.member_role, name="member_role"),
    path("manage/members/<int:pk>/remove/", views.member_remove, name="member_remove"),
]
