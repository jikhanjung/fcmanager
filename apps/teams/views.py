from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.matches.models import Match, MatchEvent
from apps.notices.models import Notice

from .models import Player, Team


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
    notices = Notice.objects.filter(is_published=True)[:5]
    return render(
        request,
        "teams/home.html",
        {"upcoming": upcoming, "recent": recent, "teams": teams,
         "notices": notices},
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


def player_detail(request, pk):
    """선수 상세: 프로필 + 소속 이력 + 득점/도움/카드 기록 + 수상."""
    player = get_object_or_404(Player, pk=pk)
    memberships = (
        player.memberships.select_related("team", "season")
        .order_by("-season__year", "team")
    )

    ET = MatchEvent.EventType
    counts = player.match_events.aggregate(
        goals=Count("id", filter=Q(event_type=ET.GOAL)),
        assists=Count("id", filter=Q(event_type=ET.ASSIST)),
        yellows=Count("id", filter=Q(event_type=ET.YELLOW)),
        reds=Count("id", filter=Q(event_type=ET.RED)),
    )

    goal_events = (
        player.match_events.filter(event_type=ET.GOAL)
        .select_related("match", "match__opponent", "match__competition")
        .order_by("-match__kickoff")
    )
    awards = player.awards.select_related("competition", "season")

    return render(
        request,
        "teams/player_detail.html",
        {
            "player": player,
            "memberships": memberships,
            "counts": counts,
            "goal_events": goal_events,
            "awards": awards,
        },
    )
