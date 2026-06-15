from django.urls import path

from . import views

app_name = "teams"

urlpatterns = [
    path("", views.home, name="home"),
    path("teams/", views.team_list, name="list"),
    path("teams/add/", views.team_create, name="team_add"),
    path("teams/<slug:slug>/edit/", views.team_edit, name="team_edit"),
    path("teams/<slug:slug>/players/add/", views.player_add, name="player_add"),
    path("teams/<slug:slug>/players/<int:pk>/edit/", views.player_edit, name="player_edit"),
    path("teams/<slug:slug>/players/<int:pk>/remove/", views.player_remove, name="player_remove"),
    path("teams/<slug:slug>/", views.team_detail, name="detail"),
    path("players/<int:pk>/", views.player_detail, name="player"),
]
