from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ClubForm
from .models import Club, ClubMembership


def platform_home(request):
    """플랫폼 랜딩(테넌트 밖): 클럽 목록 + 로그인/클럽 만들기."""
    clubs = Club.objects.filter(is_active=True).order_by("name")
    my_clubs = []
    if request.user.is_authenticated:
        my_clubs = list(
            Club.objects.filter(memberships__user=request.user).distinct().order_by("name")
        )
    return render(request, "clubs/landing.html",
                  {"clubs": clubs, "my_clubs": my_clubs})


@login_required
def club_create(request):
    """클럽 생성 — 만든 사용자가 소유자(OWNER) 멤버십을 받는다."""
    if request.method == "POST":
        form = ClubForm(request.POST, request.FILES)
        if form.is_valid():
            club = form.save()
            ClubMembership.objects.create(
                user=request.user, club=club, role=ClubMembership.Role.OWNER)
            messages.success(request, f"'{club.name}' 클럽을 만들었습니다.")
            return redirect(f"/{club.slug}/")
    else:
        form = ClubForm()
    return render(request, "clubs/club_form.html", {"form": form})
