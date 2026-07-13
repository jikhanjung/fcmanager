from django.urls import path

from . import views

app_name = "competitions"

urlpatterns = [
    path("standings/", views.standings, name="standings"),
    path("awards/", views.awards, name="awards"),
    path("years/", views.year_index, name="year_index"),
    path("years/<int:year>/", views.year_detail, name="year_detail"),
    # 대회 관리(staff) — <slug> 경로보다 먼저 둔다.
    path("manage/competitions/", views.competition_manage, name="competition_manage"),
    path("manage/competitions/add/", views.competition_create, name="competition_create"),
    path("manage/competitions/<slug:slug>/edit/", views.competition_edit, name="competition_edit"),
    path("manage/competitions/<slug:slug>/delete/", views.competition_delete, name="competition_delete"),
    # 참가팀·경기 관리(staff)
    path("manage/competitions/<slug:slug>/entries/add/", views.entry_add, name="entry_add"),
    path("manage/competitions/<slug:slug>/entries/<int:pk>/edit/", views.entry_edit, name="entry_edit"),
    path("manage/competitions/<slug:slug>/entries/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("manage/competitions/<slug:slug>/matches/add/", views.match_add, name="match_add"),
    path("manage/competitions/<slug:slug>/divisions/<int:pk>/edit/",
         views.division_edit, name="division_edit"),
    # 입상 관리(staff)
    path("manage/awards/add/", views.award_add, name="award_add"),
    path("manage/awards/<int:pk>/edit/", views.award_edit, name="award_edit"),
    path("manage/awards/<int:pk>/delete/", views.award_delete, name="award_delete"),
    # 대회 목록·상세 (공개)
    path("competitions/", views.competition_list, name="competition_list"),
    path("competitions/<slug:slug>/", views.competition_detail, name="competition_detail"),
]
