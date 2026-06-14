from django.urls import path

from . import views

app_name = "teams"

urlpatterns = [
    path("", views.home, name="home"),
    path("teams/", views.team_list, name="list"),
    path("teams/<slug:slug>/", views.team_detail, name="detail"),
]
