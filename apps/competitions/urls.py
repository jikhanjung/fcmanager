from django.urls import path

from . import views

app_name = "competitions"

urlpatterns = [
    path("standings/", views.standings, name="standings"),
    path("awards/", views.awards, name="awards"),
]
