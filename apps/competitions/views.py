from django.shortcuts import render

from apps.matches.models import Match

from .models import Award, Competition, Season


def standings(request):
    """리그 순위표: 선택한 리그의 우리 팀 전적(승점/득실) 자동 집계.

    상대팀 간 경기는 기록하지 않으므로, 우리 FC Sky 팀들의 리그 전적만 산출한다.
    승점 = 승*3 + 무*1.
    """
    leagues = Competition.objects.filter(kind=Competition.Kind.LEAGUE)

    comp_slug = request.GET.get("competition") or ""
    season = request.GET.get("season") or ""

    competition = None
    if comp_slug:
        competition = leagues.filter(slug=comp_slug).first()
    if competition is None:
        competition = leagues.first()

    rows = []
    if competition is not None:
        matches = Match.objects.filter(
            competition=competition,
            status=Match.Status.FINISHED,
            our_score__isnull=False,
            opponent_score__isnull=False,
        ).select_related("our_team")
        if season.isdigit():
            matches = matches.filter(season_id=season)

        table = {}
        for m in matches:
            row = table.setdefault(
                m.our_team_id,
                {"team": m.our_team, "p": 0, "w": 0, "d": 0, "l": 0,
                 "gf": 0, "ga": 0},
            )
            row["p"] += 1
            row["gf"] += m.our_score
            row["ga"] += m.opponent_score
            result = m.result
            if result == "W":
                row["w"] += 1
            elif result == "D":
                row["d"] += 1
            else:
                row["l"] += 1

        for row in table.values():
            row["gd"] = row["gf"] - row["ga"]
            row["pts"] = row["w"] * 3 + row["d"]

        rows = sorted(
            table.values(),
            key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"].name),
        )

    context = {
        "competition": competition,
        "leagues": leagues,
        "seasons": Season.objects.all(),
        "rows": rows,
        "selected": {"competition": comp_slug, "season": season},
    }
    return render(request, "competitions/standings.html", context)


def awards(request):
    """명예의 전당: 입상 내역을 시즌별로 정리."""
    qs = Award.objects.select_related(
        "competition", "season", "team", "player"
    ).order_by("-season__year", "competition__name", "rank")

    season = request.GET.get("season") or ""
    if season.isdigit():
        qs = qs.filter(season_id=season)

    context = {
        "awards": qs,
        "seasons": Season.objects.all(),
        "selected": {"season": season},
    }
    return render(request, "competitions/awards.html", context)
