from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from apps.matches.models import Match, MatchEvent, OpponentMatch
from apps.matches.services import (
    club_record,
    event_ranking,
    finished_matches,
    our_events,
)

from .forms import CompetitionForm
from .models import Award, Competition


_AGE_ORDER = {"K7": 0, "40": 1, "50": 2}

staff_required = user_passes_test(lambda u: u.is_staff, login_url="login")


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
        # 순위표는 조별리그만 집계(녹아웃은 대진표로 표시).
        matches = Match.objects.filter(
            competition=competition,
            stage=Match.Stage.GROUP,
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


# ── 대회 목록 · 상세 (공개 조회: 누구나) ──

def competition_list(request):
    """모든 대회 목록(연도 내림차순). 누구나 조회 가능."""
    competitions = (
        Competition.objects.annotate(
            division_count=Count("divisions", distinct=True),
            match_count=Count("matches", distinct=True),
        ).prefetch_related("divisions").order_by("-year", "name")
    )
    return render(request, "competitions/competition_list.html",
                  {"competitions": competitions})


def competition_detail(request, slug):
    """대회 상세: 부문·출전팀 + 조별리그 경기 + 녹아웃 대진표. 누구나 조회 가능."""
    competition = get_object_or_404(Competition, slug=slug)
    divisions = list(competition.divisions.all())
    entries = (
        competition.entries.select_related("team", "division").order_by("team__name")
    )
    matches = list(
        competition.matches.select_related("our_team", "opponent", "division")
        .order_by("kickoff")
    )

    group_matches = [m for m in matches if not m.is_knockout]
    knockout = [m for m in matches if m.is_knockout]

    # 부문(Division.age_group) -> 상대팀 간 경기(OpponentMatch.age_group) 매핑.
    div_to_team_age = {"2030": "K7", "40": "40", "50": "50"}
    opp_sfs = list(
        competition.opponent_matches.filter(stage=Match.Stage.SEMI)
        .select_related("home", "away")
    )

    # 녹아웃 대진표: 부문별 → 단계별(준결승→결승) 열. 준결승 열에는 반대편 준결승도 포함.
    brackets = []
    div_order = {d.id: i for i, d in enumerate(divisions)}
    by_div = {}
    for m in knockout:
        by_div.setdefault(m.division_id, []).append(m)
    for div_id, ms in sorted(by_div.items(), key=lambda kv: div_order.get(kv[0], 99)):
        division = next((d for d in divisions if d.id == div_id), None)
        team_age = div_to_team_age.get(division.age_group) if division else None
        rev_sfs = [o for o in opp_sfs if o.age_group == team_age]
        stages = {}
        for m in ms:
            stages.setdefault(m.stage, []).append(m)
        # 반대편 준결승은 준결승(SF) 열에 함께 표시(녹아웃이 있는 부문에 한함).
        if rev_sfs:
            stages.setdefault(Match.Stage.SEMI, [])
        columns = []
        for st in sorted(stages, key=lambda s: Match.STAGE_ORDER.get(s, 0)):
            columns.append({
                "label": dict(Match.Stage.choices)[st],
                "matches": stages[st],
                "opps": rev_sfs if st == Match.Stage.SEMI else [],
            })
        brackets.append({"division": division, "columns": columns})

    return render(request, "competitions/competition_detail.html", {
        "competition": competition,
        "divisions": divisions,
        "entries": entries,
        "group_matches": group_matches,
        "brackets": brackets,
    })


# ── 대회 관리 (staff 전용) ──

@staff_required
def competition_manage(request):
    """대회 관리 목록: 생성·수정·삭제 진입."""
    competitions = (
        Competition.objects.annotate(
            division_count=Count("divisions", distinct=True),
            match_count=Count("matches", distinct=True),
        ).order_by("-year", "name")
    )
    return render(request, "competitions/competition_manage.html",
                  {"competitions": competitions})


@staff_required
def competition_create(request):
    if request.method == "POST":
        form = CompetitionForm(request.POST)
        if form.is_valid():
            comp = form.save()
            messages.success(request, f"대회 '{comp.name}'을(를) 추가했습니다.")
            return redirect("competitions:competition_manage")
    else:
        form = CompetitionForm()
    return render(request, "competitions/competition_form.html",
                  {"form": form, "is_create": True})


@staff_required
def competition_edit(request, slug):
    competition = get_object_or_404(Competition, slug=slug)
    if request.method == "POST":
        form = CompetitionForm(request.POST, instance=competition)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{competition.name}' 정보를 저장했습니다.")
            return redirect("competitions:competition_manage")
    else:
        form = CompetitionForm(instance=competition)
    return render(request, "competitions/competition_form.html",
                  {"form": form, "competition": competition, "is_create": False})


@staff_required
def competition_delete(request, slug):
    """대회 삭제. 경기가 연결돼 있으면(PROTECT) 막고 안내."""
    competition = get_object_or_404(Competition, slug=slug)
    if request.method == "POST":
        try:
            name = competition.name
            competition.delete()
            messages.success(request, f"대회 '{name}'을(를) 삭제했습니다.")
            return redirect("competitions:competition_manage")
        except ProtectedError:
            messages.error(
                request,
                "이 대회에 연결된 경기가 있어 삭제할 수 없습니다. 경기를 먼저 정리하세요.")
            return redirect("competitions:competition_manage")
    return render(request, "competitions/competition_confirm_delete.html", {
        "competition": competition,
        "match_count": competition.matches.count(),
        "entry_count": competition.entries.count(),
    })
