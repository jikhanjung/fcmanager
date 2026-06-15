from django.urls import path

from . import views

app_name = "notices"

urlpatterns = [
    path("notices/", views.notice_list, name="list"),
    path("notices/<int:pk>/", views.notice_detail, name="detail"),
]
