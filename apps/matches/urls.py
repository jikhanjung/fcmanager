from django.urls import path

from . import views

app_name = "matches"

urlpatterns = [
    path("matches/", views.schedule, name="list"),
    path("matches/scorers/", views.scorers, name="scorers"),
    path("matches/<int:pk>/edit/", views.match_edit, name="edit"),
    path("matches/<int:pk>/live/", views.match_live_console, name="live_console"),
    path("matches/<int:pk>/live.json", views.match_live_json, name="live_json"),
    path("matches/<int:pk>/", views.match_detail, name="detail"),
    path("stats/", views.stats, name="stats"),
]
