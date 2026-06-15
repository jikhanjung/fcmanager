from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.competitions.models import Competition, Season
from apps.teams.models import Player, Team

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
    # 득점·도움 선수 선택지는 해당 경기 팀에 등록된 선수로 제한.
    team_players = (
        Player.objects.filter(memberships__team=match.our_team)
        .distinct().order_by("name")
    )
    ASSIST = MatchEvent.EventType.ASSIST
    GOAL = MatchEvent.EventType.GOAL
    # 도움(ASSIST)은 득점 행에서 함께 관리하므로 별도 행으로는 표시하지 않는다.
    fs_kwargs = {
        "form_kwargs": {"team_players": team_players},
        "queryset": MatchEvent.objects.exclude(event_type=ASSIST),
    }
    if request.method == "POST":
        form = MatchResultForm(request.POST, instance=match)
        formset = MatchEventFormSet(request.POST, instance=match, **fs_kwargs)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            # 도움 재동기화: 기존 도움 전부 제거 후 득점 행의 '도움 선수'로 재생성.
            match.events.filter(event_type=ASSIST).delete()
            for f in formset.forms:
                cd = getattr(f, "cleaned_data", None)
                if not cd or cd.get("DELETE"):
                    continue
                goal, assist_player = f.instance, cd.get("assist_player")
                if goal.pk and goal.event_type == GOAL and assist_player:
                    MatchEvent.objects.create(
                        match=match, event_type=ASSIST, side=goal.side,
                        player=assist_player, minute=goal.minute, goal=goal,
                    )
            messages.success(request, "경기 결과를 저장했습니다.")
            return redirect("matches:detail", pk=match.pk)
    else:
        form = MatchResultForm(instance=match)
        formset = MatchEventFormSet(instance=match, **fs_kwargs)
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
    """타임라인 항목 구성. 득점과 그 도움을 한 줄로 묶는다.

    각 항목은 {"event": 주 이벤트, "assist": 도움 이벤트 또는 None}.
    도움은 명시적 링크(MatchEvent.goal)로 해당 득점에 정확히 연결한다.
    링크가 없는 과거 데이터는 같은 팀·같은 '분(분이 있을 때만)'으로만 보수적으로 페어링한다.
    """
    GOAL = MatchEvent.EventType.GOAL
    ASSIST = MatchEvent.EventType.ASSIST
    assist_by_goal = {e.goal_id: e for e in events if e.event_type == ASSIST and e.goal_id}
    used = set()
    timeline = []
    for e in events:
        if e.id in used:
            continue
        if e.event_type == GOAL:
            assist = assist_by_goal.get(e.id)
            if assist is None:  # 레거시(링크 없는 과거 데이터) 폴백: 같은 팀 도움을 순서대로 소비
                assist = next(
                    (a for a in events
                     if a.event_type == ASSIST and not a.goal_id and a.id not in used
                     and a.side == e.side),
                    None,
                )
            if assist:
                used.add(assist.id)
            timeline.append({"event": e, "assist": assist})
        elif e.event_type == ASSIST:
            if e.goal_id:        # 자기 득점과 함께 표시 → 단독으로 내지 않음
                used.add(e.id)
                continue
            timeline.append({"event": e, "assist": None})  # 링크 없는 단독 도움
        else:
            timeline.append({"event": e, "assist": None})
        used.add(e.id)
    return timeline


def scorers(request):
    """선수 순위: 우리 팀 골·도움·공격포인트 집계 + 팀·대회·시즌 필터."""
    ET = MatchEvent.EventType
    events = MatchEvent.objects.filter(
        side=MatchEvent.Side.OUR,
        player__isnull=False,
        event_type__in=[ET.GOAL, ET.ASSIST],
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

    # points = goals + assists (events 가 GOAL/ASSIST 만이므로 전체 개수)
    ranking = (
        events.values("player_id", "player__name")
        .annotate(
            goals=Count("id", filter=Q(event_type=ET.GOAL)),
            assists=Count("id", filter=Q(event_type=ET.ASSIST)),
            points=Count("id"),
        )
        .order_by("-points", "-goals", "player__name")
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
