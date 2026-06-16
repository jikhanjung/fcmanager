from django.urls import path

from . import views

app_name = "competitions"

urlpatterns = [
    path("standings/", views.standings, name="standings"),
    path("awards/", views.awards, name="awards"),
    path("years/", views.year_index, name="year_index"),
    path("years/<int:year>/", views.year_detail, name="year_detail"),
]
