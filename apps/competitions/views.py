from django.db.models import Count, Q
from django.shortcuts import render

from apps.matches.models import Match, MatchEvent, OpponentMatch
from apps.matches.services import (
    club_record,
    event_ranking,
    finished_matches,
    our_events,
)

from .models import Award, Competition


_AGE_ORDER = {"K7": 0, "40": 1, "50": 2}


def _years():
    """대회가 존재하는 연도 목록(내림차순)."""
    return list(
        Competition.objects.values_list("year", flat=True).distinct().order_by("-year")
    )


def standings(request):
    """대회 조별(부문별) 순위표.

    우리 팀(FC Sky) 경기 기록만 보유하므로, 각 부문(= 우리 팀)별로 우리 팀과 그
    상대팀들의 전적을 '우리 경기 기준'으로 집계한다(상대팀 간 경기는 미반영).
    리그·토너먼트 모두 동일하게 동작. 승점 = 승*3 + 무*1.
    """
    comps = Competition.objects.filter(matches__isnull=False).distinct()

    comp_slug = request.GET.get("competition") or ""

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
        "groups": groups,
        "selected": {"competition": comp_slug},
    }
    return render(request, "competitions/standings.html", context)


def awards(request):
    """명예의 전당: 입상 내역을 대회별로 정리(연도 필터)."""
    qs = Award.objects.select_related(
        "competition", "team", "player"
    ).order_by("-competition__year", "competition__name", "rank")

    year = request.GET.get("year") or ""
    if year.isdigit():
        qs = qs.filter(competition__year=year)

    context = {
        "awards": qs,
        "years": _years(),
        "selected": {"year": year},
    }
    return render(request, "competitions/awards.html", context)


def year_index(request):
    """연도별 아카이브 목록: 연도마다 종료 경기 수·대회 수·입상 수 요약."""
    rows = []
    for year in _years():
        comps = Competition.objects.filter(year=year)
        rows.append({
            "year": year,
            "competition_count": comps.count(),
            "finished": Match.objects.filter(
                competition__year=year, status=Match.Status.FINISHED).count(),
            "award_count": Award.objects.filter(competition__year=year).count(),
        })
    return render(request, "competitions/year_index.html", {"years": rows})


def year_detail(request, year):
    """연도 종합 아카이브: 클럽 요약 + 출전 대회·입상 + 득점/도움 TOP + 최근 경기."""
    teams, club = club_record(finished_matches(year))

    ev = our_events(year)
    scorers = event_ranking(ev, MatchEvent.EventType.GOAL, limit=10)
    assisters = event_ranking(ev, MatchEvent.EventType.ASSIST, limit=10)

    competitions = (
        Competition.objects.filter(year=year).order_by("name")
    )
    awards = (
        Award.objects.filter(competition__year=year)
        .select_related("competition", "team", "player")
        .order_by("competition__name", "rank")
    )
    recent = (
        Match.objects.filter(competition__year=year, status=Match.Status.FINISHED)
        .select_related("our_team", "opponent", "competition")
        .order_by("-kickoff")[:10]
    )

    context = {
        "year": year,
        "teams": teams,
        "club": club,
        "scorers": scorers,
        "assisters": assisters,
        "competitions": competitions,
        "awards": awards,
        "recent": recent,
    }
    return render(request, "competitions/year_detail.html", context)
