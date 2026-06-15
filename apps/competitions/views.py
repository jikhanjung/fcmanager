from django.shortcuts import render

from apps.matches.models import Match, OpponentMatch

from .models import Award, Competition, Season


_AGE_ORDER = {"K7": 0, "40": 1, "50": 2}


def standings(request):
    """대회 조별(부문별) 순위표.

    우리 팀(FC Sky) 경기 기록만 보유하므로, 각 부문(= 우리 팀)별로 우리 팀과 그
    상대팀들의 전적을 '우리 경기 기준'으로 집계한다(상대팀 간 경기는 미반영).
    리그·토너먼트 모두 동일하게 동작. 승점 = 승*3 + 무*1.
    """
    comps = Competition.objects.filter(matches__isnull=False).distinct()

    comp_slug = request.GET.get("competition") or ""
    season = request.GET.get("season") or ""

    competition = None
    if comp_slug:
        competition = comps.filter(slug=comp_slug).first()
    if competition is None:
        competition = (
            comps.filter(matches__status=Match.Status.FINISHED).distinct().first()
            or comps.first()
        )

    groups = []
    if competition is not None:
        matches = Match.objects.filter(
            competition=competition,
            status=Match.Status.FINISHED,
            our_score__isnull=False,
            opponent_score__isnull=False,
        ).select_related("our_team", "opponent")
        if season.isdigit():
            matches = matches.filter(season_id=season)

        def _blank(name, url, is_ours):
            return {"name": name, "url": url, "is_ours": is_ours,
                    "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}

        by_group = {}
        for m in matches:
            g = by_group.setdefault(m.our_team_id, {"team": m.our_team, "rows": {}})
            rows = g["rows"]
            ours = rows.setdefault(
                ("T", m.our_team_id),
                _blank(m.our_team.name, m.our_team.get_absolute_url(), True))
            opp = rows.setdefault(
                ("O", m.opponent_id), _blank(m.opponent.name, None, False))

            ours["p"] += 1
            ours["gf"] += m.our_score
            ours["ga"] += m.opponent_score
            opp["p"] += 1
            opp["gf"] += m.opponent_score
            opp["ga"] += m.our_score

            result = m.result
            if result == "W":
                ours["w"] += 1
                opp["l"] += 1
            elif result == "L":
                ours["l"] += 1
                opp["w"] += 1
            else:
                ours["d"] += 1
                opp["d"] += 1

        # 상대팀 간 경기(있으면) 같은 부문 조에 반영해 순위 보정.
        group_by_age = {g["team"].age_group: g for g in by_group.values()}
        om_qs = OpponentMatch.objects.filter(
            competition=competition,
            home_score__isnull=False,
            away_score__isnull=False,
        ).select_related("home", "away")
        if season.isdigit():
            om_qs = om_qs.filter(season_id=season)
        for om in om_qs:
            g = group_by_age.get(om.age_group)
            if g is None:
                continue
            rows = g["rows"]
            h = rows.setdefault(("O", om.home_id), _blank(om.home.name, None, False))
            a = rows.setdefault(("O", om.away_id), _blank(om.away.name, None, False))
            h["p"] += 1
            h["gf"] += om.home_score
            h["ga"] += om.away_score
            a["p"] += 1
            a["gf"] += om.away_score
            a["ga"] += om.home_score
            if om.home_score > om.away_score:
                h["w"] += 1
                a["l"] += 1
            elif om.home_score < om.away_score:
                h["l"] += 1
                a["w"] += 1
            else:
                h["d"] += 1
                a["d"] += 1

        for g in by_group.values():
            table = list(g["rows"].values())
            for row in table:
                row["gd"] = row["gf"] - row["ga"]
                row["pts"] = row["w"] * 3 + row["d"]
            table.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["name"]))
            groups.append({"team": g["team"], "table": table})

        groups.sort(key=lambda x: _AGE_ORDER.get(x["team"].age_group, 9))

    context = {
        "competition": competition,
        "competitions": comps,
        "seasons": Season.objects.all(),
        "groups": groups,
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
