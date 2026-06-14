from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from apps.competitions.models import Competition, Season
from apps.teams.models import Team

from .models import Match, MatchEvent


def _common_filters():
    return {
        "teams": Team.objects.all(),
        "competitions": Competition.objects.all(),
        "seasons": Season.objects.all(),
    }


def schedule(request):
    """일정 & 결과: 전체 경기 목록 + 대회·팀·시즌·상태 필터."""
    matches = Match.objects.select_related(
        "our_team", "opponent", "competition", "season"
    )

    team = request.GET.get("team") or ""
    competition = request.GET.get("competition") or ""
    season = request.GET.get("season") or ""
    show = request.GET.get("show") or ""

    if team:
        matches = matches.filter(our_team__slug=team)
    if competition:
        matches = matches.filter(competition__slug=competition)
    if season.isdigit():
        matches = matches.filter(season_id=season)
    if show == "upcoming":
        matches = matches.filter(status=Match.Status.SCHEDULED)
    elif show == "finished":
        matches = matches.filter(status=Match.Status.FINISHED)

    context = {
        "matches": matches,
        "selected": {
            "team": team,
            "competition": competition,
            "season": season,
            "show": show,
        },
        **_common_filters(),
    }
    return render(request, "matches/match_list.html", context)


def match_detail(request, pk):
    """경기 상세: 스코어 + 득점·카드·교체 타임라인."""
    match = get_object_or_404(
        Match.objects.select_related(
            "our_team", "opponent", "competition", "season"
        ),
        pk=pk,
    )
    events = match.events.select_related("player").order_by("minute", "id")
    return render(
        request,
        "matches/match_detail.html",
        {"match": match, "events": events},
    )


def scorers(request):
    """득점 순위: 우리 팀 GOAL 이벤트 집계 + 팀·대회·시즌 필터."""
    events = MatchEvent.objects.filter(
        event_type=MatchEvent.EventType.GOAL,
        side=MatchEvent.Side.OUR,
        player__isnull=False,
    )

    team = request.GET.get("team") or ""
    competition = request.GET.get("competition") or ""
    season = request.GET.get("season") or ""

    if team:
        events = events.filter(match__our_team__slug=team)
    if competition:
        events = events.filter(match__competition__slug=competition)
    if season.isdigit():
        events = events.filter(match__season_id=season)

    ranking = (
        events.values("player_id", "player__name")
        .annotate(goals=Count("id"))
        .order_by("-goals", "player__name")
    )

    context = {
        "ranking": ranking,
        "selected": {"team": team, "competition": competition, "season": season},
        **_common_filters(),
    }
    return render(request, "matches/scorers.html", context)
