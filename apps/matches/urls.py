from django.urls import path

from . import views

app_name = "matches"

urlpatterns = [
    path("matches/", views.schedule, name="list"),
    path("matches/scorers/", views.scorers, name="scorers"),
    path("matches/<int:pk>/", views.match_detail, name="detail"),
]
