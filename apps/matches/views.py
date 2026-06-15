from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.competitions.models import Competition, Season
from apps.teams.models import Team

from .forms import MatchEventFormSet, MatchResultForm
from .models import Match, MatchEvent
from .services import (
    AGE_ORDER as _AGE_ORDER,
    club_record,
    event_ranking,
    finished_matches,
    our_events,
)


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


staff_required = user_passes_test(lambda u: u.is_staff, login_url="login")


@staff_required
def match_edit(request, pk):
    """운영진용 경기 결과 편집 (스코어·상태 + 득점/도움/시간 이벤트). 사이트 내 직접 편집."""
    match = get_object_or_404(
        Match.objects.select_related("our_team", "opponent", "competition"), pk=pk
    )
    if request.method == "POST":
        form = MatchResultForm(request.POST, instance=match)
        formset = MatchEventFormSet(request.POST, instance=match)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "경기 결과를 저장했습니다.")
            return redirect("matches:detail", pk=match.pk)
    else:
        form = MatchResultForm(instance=match)
        formset = MatchEventFormSet(instance=match)
    return render(
        request,
        "matches/match_edit.html",
        {"match": match, "form": form, "formset": formset},
    )


def match_detail(request, pk):
    """경기 상세: 스코어 + 득점·카드·교체 타임라인."""
    match = get_object_or_404(
        Match.objects.select_related(
            "our_team", "opponent", "competition", "season"
        ),
        pk=pk,
    )
    events = list(match.events.select_related("player").order_by("minute", "id"))
    timeline = _build_timeline(events)
    return render(
        request,
        "matches/match_detail.html",
        {"match": match, "timeline": timeline},
    )


def _build_timeline(events):
    """타임라인 항목 구성. 같은 팀·같은 분의 득점-도움을 한 줄로 묶는다.

    각 항목은 {"event": 주 이벤트, "assist": 도움 이벤트 또는 None}.
    득점에는 짝이 되는 도움을, 짝 없는 도움/그 외 이벤트는 단독으로 둔다.
    """
    GOAL = MatchEvent.EventType.GOAL
    ASSIST = MatchEvent.EventType.ASSIST
    used = set()
    timeline = []
    for e in events:
        if e.id in used:
            continue
        if e.event_type in (GOAL, ASSIST):
            want = ASSIST if e.event_type == GOAL else GOAL
            mate = next(
                (m for m in events
                 if m.id not in used and m.id != e.id
                 and m.event_type == want and m.side == e.side
                 and m.minute == e.minute),
                None,
            )
            if mate:
                used.add(mate.id)
            goal = e if e.event_type == GOAL else mate
            assist = mate if e.event_type == GOAL else e
            # 짝이 없으면 e 단독(득점이든 도움이든)
            timeline.append({"event": goal or e, "assist": assist if goal else None})
        else:
            timeline.append({"event": e, "assist": None})
        used.add(e.id)
    return timeline


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

    # 팀별 전적 + 클럽 합계
    teams, club = club_record(finished_matches(season))

    # 득점/도움/카드 (우리 팀 이벤트)
    ev = our_events(season)
    scorers = event_ranking(ev, MatchEvent.EventType.GOAL, limit=10)
    assisters = event_ranking(ev, MatchEvent.EventType.ASSIST, limit=10)

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
