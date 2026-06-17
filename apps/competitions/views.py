from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from apps.matches.models import Match, MatchEvent
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


def _years(club):
    """이 클럽이 경기를 가진 대회의 연도 목록(내림차순)."""
    return list(
        Competition.objects.filter(matches__club=club)
        .values_list("year", flat=True).distinct().order_by("-year")
    )


def standings(request):
    """대회 조별(부문별) 순위표.

    우리 팀(FC Sky) 경기 기록만 보유하므로, 각 부문(= 우리 팀)별로 우리 팀과 그
    상대팀들의 전적을 '우리 경기 기준'으로 집계한다(상대팀 간 경기는 미반영).
    리그·토너먼트 모두 동일하게 동작. 승점 = 승*3 + 무*1.
    """
    comps = Competition.objects.filter(matches__club=request.club).distinct()

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
        # 순위표는 조별리그만 집계(녹아웃은 대진표로 표시). 부문(division)별로 참가팀(entry)
        # 전적을 home/away 기준으로 모은다 — 우리 경기·상대팀 간 경기 모두 같은 Match.
        matches = Match.objects.filter(
            competition=competition,
            club=request.club,
            stage=Match.Stage.GROUP,
            status=Match.Status.FINISHED,
            home_score__isnull=False,
            away_score__isnull=False,
            division__isnull=False,
        ).select_related(
            "division", "home_entry__team", "home_entry__opponent",
            "away_entry__team", "away_entry__opponent",
        )

        def _blank(entry):
            is_ours = entry.team_id is not None
            url = entry.team.get_absolute_url() if is_ours else None
            return {"name": entry.name, "url": url, "is_ours": is_ours,
                    "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}

        by_div = {}
        for m in matches:
            if m.home_entry_id is None or m.away_entry_id is None:
                continue
            g = by_div.setdefault(m.division_id, {"division": m.division, "rows": {}})
            rows = g["rows"]
            hr = rows.setdefault(m.home_entry_id, _blank(m.home_entry))
            ar = rows.setdefault(m.away_entry_id, _blank(m.away_entry))
            hr["p"] += 1; hr["gf"] += m.home_score; hr["ga"] += m.away_score
            ar["p"] += 1; ar["gf"] += m.away_score; ar["ga"] += m.home_score
            if m.home_score > m.away_score:
                hr["w"] += 1; ar["l"] += 1
            elif m.home_score < m.away_score:
                hr["l"] += 1; ar["w"] += 1
            else:
                hr["d"] += 1; ar["d"] += 1

        for g in by_div.values():
            table = list(g["rows"].values())
            for row in table:
                row["gd"] = row["gf"] - row["ga"]
                row["pts"] = row["w"] * 3 + row["d"]
            table.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["name"]))
            groups.append({"division": g["division"], "table": table})

        _DIV_ORDER = {"2030": 0, "40": 1, "50": 2, "OPEN": 3}
        groups.sort(key=lambda x: _DIV_ORDER.get(
            x["division"].age_group if x["division"] else "", 9))

    context = {
        "competition": competition,
        "competitions": comps,
        "groups": groups,
        "selected": {"competition": comp_slug},
    }
    return render(request, "competitions/standings.html", context)


def awards(request):
    """명예의 전당: 입상 내역을 대회별로 정리(연도 필터)."""
    qs = Award.objects.filter(club=request.club).select_related(
        "competition", "team", "player"
    ).order_by("-competition__year", "competition__name", "rank")

    year = request.GET.get("year") or ""
    if year.isdigit():
        qs = qs.filter(competition__year=year)

    context = {
        "awards": qs,
        "years": _years(request.club),
        "selected": {"year": year},
    }
    return render(request, "competitions/awards.html", context)


def year_index(request):
    """연도별 아카이브 목록: 연도마다 종료 경기 수·대회 수·입상 수 요약."""
    rows = []
    for year in _years(request.club):
        comps = Competition.objects.filter(
            year=year, matches__club=request.club).distinct()
        rows.append({
            "year": year,
            "competition_count": comps.count(),
            "finished": Match.objects.filter(
                club=request.club, competition__year=year,
                status=Match.Status.FINISHED).count(),
            "award_count": Award.objects.filter(
                club=request.club, competition__year=year).count(),
        })
    return render(request, "competitions/year_index.html", {"years": rows})


def year_detail(request, year):
    """연도 종합 아카이브: 클럽 요약 + 출전 대회·입상 + 득점/도움 TOP + 최근 경기."""
    teams, club = club_record(finished_matches(year, request.club))

    ev = our_events(year, request.club)
    scorers = event_ranking(ev, MatchEvent.EventType.GOAL, limit=10)
    assisters = event_ranking(ev, MatchEvent.EventType.ASSIST, limit=10)

    competitions = (
        Competition.objects.filter(year=year, matches__club=request.club)
        .distinct().order_by("name")
    )
    awards = (
        Award.objects.filter(club=request.club, competition__year=year)
        .select_related("competition", "team", "player")
        .order_by("competition__name", "rank")
    )
    recent = (
        Match.objects.filter(club=request.club, competition__year=year, status=Match.Status.FINISHED)
        .select_related("home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "competition")
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
        Competition.objects.filter(matches__club=request.club)
        .annotate(
            division_count=Count("divisions", distinct=True),
            match_count=Count("matches", filter=Q(matches__club=request.club), distinct=True),
        ).prefetch_related("divisions").distinct().order_by("-year", "name")
    )
    return render(request, "competitions/competition_list.html",
                  {"competitions": competitions})


def _bracket_for(matches, division):
    """한 부문의 녹아웃 대진(준결승 → 결승) 구조. 녹아웃 없으면 None.

    참가팀 개편 후 반대편 준결승도 일반 Match(우리 팀 entry 없음)라 모두 같이 다룬다.
    """
    knockout = [m for m in matches if m.is_knockout]
    if not knockout:
        return None
    semis = [{"kind": "match", "obj": m} for m in knockout if m.stage == Match.Stage.SEMI]
    finals = [m for m in knockout if m.stage == Match.Stage.FINAL]
    return {"semis": semis, "final": finals[0] if finals else None}


def competition_detail(request, slug):
    """대회 상세: 부문이 있으면 부문 탭으로(각 탭에 출전팀·대진표·조별리그). 누구나 조회."""
    competition = get_object_or_404(Competition, slug=slug)
    divisions = list(competition.divisions.all())
    entries = list(
        competition.entries.filter(Q(team__isnull=True) | Q(team__club=request.club)).select_related("team", "opponent", "division").order_by("team__name")
    )
    matches = list(
        competition.matches.filter(club=request.club).select_related("home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "division")
        .order_by("kickoff")
    )
    def make_panel(division, ms, es, key, label):
        return {
            "key": key,
            "label": label,
            "division": division,
            "entries": es,
            "group_matches": [m for m in ms if not m.is_knockout],
            "bracket": _bracket_for(ms, division),
        }

    panels = []
    if divisions:
        for i, d in enumerate(divisions):
            d_ms = [m for m in matches if m.division_id == d.id]
            d_es = [e for e in entries if e.division_id == d.id]
            panels.append(make_panel(d, d_ms, d_es, f"div{d.id}", d.label))
        # 부문 미지정 경기/출전이 있으면 '기타' 탭.
        misc_ms = [m for m in matches if m.division_id is None]
        misc_es = [e for e in entries if e.division_id is None]
        if misc_ms or misc_es:
            panels.append(make_panel(None, misc_ms, misc_es, "misc", "기타"))
    else:
        panels.append(make_panel(None, matches, entries, "all", "전체"))

    return render(request, "competitions/competition_detail.html", {
        "competition": competition,
        "divisions": divisions,
        "panels": panels,
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
