from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.matches.models import Match

from .models import Team


def home(request):
    """홈: 다음 경기 / 최근 결과 / 팀 목록."""
    now = timezone.now()
    upcoming = (
        Match.objects.filter(kickoff__gte=now)
        .exclude(status=Match.Status.CANCELLED)
        .select_related("our_team", "opponent", "competition")
        .order_by("kickoff")[:5]
    )
    recent = (
        Match.objects.filter(status=Match.Status.FINISHED)
        .select_related("our_team", "opponent", "competition")
        .order_by("-kickoff")[:5]
    )
    teams = Team.objects.all()
    return render(
        request,
        "teams/home.html",
        {"upcoming": upcoming, "recent": recent, "teams": teams},
    )


def team_list(request):
    teams = Team.objects.all()
    return render(request, "teams/team_list.html", {"teams": teams})


def team_detail(request, slug):
    team = get_object_or_404(Team, slug=slug)
    memberships = (
        team.memberships.filter(is_active=True)
        .select_related("player")
        .order_by("jersey_number")
    )
    return render(
        request,
        "teams/team_detail.html",
        {"team": team, "memberships": memberships},
    )
