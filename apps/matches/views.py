from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from apps.competitions.models import Competition, Season
from apps.teams.models import Team

from .models import Match, MatchEvent

_AGE_ORDER = {"K7": 0, "40": 1, "50": 2}


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


def stats(request):
    """통계 대시보드: 클럽/팀별 전적 요약 + 득점·도움 TOP + 경고·퇴장."""
    season = request.GET.get("season") or ""

    fin = Match.objects.filter(
        status=Match.Status.FINISHED,
        our_score__isnull=False,
        opponent_score__isnull=False,
    )
    if season.isdigit():
        fin = fin.filter(season_id=season)

    # 팀별 전적 + 클럽 합계
    team_rows = {}
    for m in fin.select_related("our_team"):
        r = team_rows.setdefault(
            m.our_team_id,
            {"team": m.our_team, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0},
        )
        r["p"] += 1
        r["gf"] += m.our_score
        r["ga"] += m.opponent_score
        result = m.result
        if result == "W":
            r["w"] += 1
        elif result == "L":
            r["l"] += 1
        else:
            r["d"] += 1

    club = {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}
    teams = []
    for r in team_rows.values():
        r["gd"] = r["gf"] - r["ga"]
        r["pts"] = r["w"] * 3 + r["d"]
        r["winrate"] = round(r["w"] / r["p"] * 100) if r["p"] else 0
        for k in ("p", "w", "d", "l", "gf", "ga"):
            club[k] += r[k]
        teams.append(r)
    teams.sort(key=lambda x: _AGE_ORDER.get(x["team"].age_group, 9))
    club["gd"] = club["gf"] - club["ga"]
    club["winrate"] = round(club["w"] / club["p"] * 100) if club["p"] else 0

    # 득점/도움/카드 (우리 팀 이벤트)
    ev = MatchEvent.objects.filter(side=MatchEvent.Side.OUR, player__isnull=False)
    if season.isdigit():
        ev = ev.filter(match__season_id=season)

    def _rank(event_type):
        return list(
            ev.filter(event_type=event_type)
            .values("player_id", "player__name")
            .annotate(n=Count("id"))
            .order_by("-n", "player__name")[:10]
        )

    scorers = _rank(MatchEvent.EventType.GOAL)
    assisters = _rank(MatchEvent.EventType.ASSIST)

    cards = list(
        ev.filter(event_type__in=[MatchEvent.EventType.YELLOW,
                                  MatchEvent.EventType.RED])
        .values("player_id", "player__name")
        .annotate(
            yellow=Count("id", filter=Q(event_type=MatchEvent.EventType.YELLOW)),
            red=Count("id", filter=Q(event_type=MatchEvent.EventType.RED)),
        )
        .order_by("-red", "-yellow", "player__name")
    )

    context = {
        "season": season,
        "seasons": Season.objects.all(),
        "teams": teams,
        "club": club,
        "scorers": scorers,
        "assisters": assisters,
        "cards": cards,
    }
    return render(request, "matches/stats.html", context)
