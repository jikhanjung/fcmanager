from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.competitions.models import Competition, Season
from apps.teams.models import Player, Team

from .forms import MatchEventFormSet, MatchResultForm, MatchVideoFormSet
from .models import Match, MatchEvent
from .services import (
    AGE_ORDER as _AGE_ORDER,
    build_timeline,
    club_record,
    event_ranking,
    finished_matches,
    our_events,
    recompute_score,
    serialize_timeline,
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
        video_formset = MatchVideoFormSet(request.POST, instance=match)
        if form.is_valid() and formset.is_valid() and video_formset.is_valid():
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
            video_formset.save()
            messages.success(request, "경기 결과를 저장했습니다.")
            return redirect("matches:detail", pk=match.pk)
    else:
        form = MatchResultForm(instance=match)
        formset = MatchEventFormSet(instance=match, **fs_kwargs)
        video_formset = MatchVideoFormSet(instance=match)
    return render(
        request,
        "matches/match_edit.html",
        {"match": match, "form": form, "formset": formset,
         "video_formset": video_formset},
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
    timeline = build_timeline(events)
    videos = match.videos.all()
    return render(
        request,
        "matches/match_detail.html",
        {"match": match, "timeline": timeline, "videos": videos},
    )


def match_live_json(request, pk):
    """공개 폴링 엔드포인트: LIVE 경기의 스코어·상태·타임라인을 JSON으로."""
    match = get_object_or_404(
        Match.objects.select_related("our_team", "opponent"), pk=pk
    )
    return JsonResponse({
        "status": match.status,
        "status_display": match.get_status_display(),
        "is_live": match.status == Match.Status.LIVE,
        "our_score": match.our_score,
        "opponent_score": match.opponent_score,
        "result": match.result,
        "timeline": serialize_timeline(match),
        "updated_at": match.updated_at.isoformat(),
    })


# 중계 콘솔에서 빠르게 추가할 수 있는 이벤트 종류(득점·도움은 별도 처리).
_LIVE_SIMPLE_EVENTS = {
    MatchEvent.EventType.OWN_GOAL,
    MatchEvent.EventType.YELLOW,
    MatchEvent.EventType.RED,
    MatchEvent.EventType.SUB_IN,
    MatchEvent.EventType.SUB_OUT,
}


@staff_required
def match_live_console(request, pk):
    """운영진용 실시간 중계 콘솔(모바일): LIVE 토글 + 빠른 이벤트 입력/삭제."""
    match = get_object_or_404(
        Match.objects.select_related("our_team", "opponent"), pk=pk
    )
    team_players = (
        Player.objects.filter(memberships__team=match.our_team)
        .distinct().order_by("name")
    )

    if request.method == "POST":
        _handle_live_action(request, match, team_players)
        return redirect("matches:live_console", pk=match.pk)

    events = list(match.events.select_related("player").order_by("minute", "id"))
    # 분 자동 채움 제안: LIVE면 킥오프 이후 경과(분), 아니면 비움.
    suggested_minute = ""
    if match.status == Match.Status.LIVE and match.kickoff:
        elapsed = (timezone.now() - match.kickoff).total_seconds() / 60
        if 0 <= elapsed <= 130:
            suggested_minute = int(elapsed)

    return render(request, "matches/match_live.html", {
        "match": match,
        "events": events,
        "team_players": team_players,
        "suggested_minute": suggested_minute,
        "Side": MatchEvent.Side,
        "EventType": MatchEvent.EventType,
    })


def _parse_minute(raw):
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def _handle_live_action(request, match, team_players):
    """중계 콘솔의 POST 액션 처리. 득점 시 점수를 재집계한다."""
    action = request.POST.get("action") or ""
    GOAL = MatchEvent.EventType.GOAL
    ASSIST = MatchEvent.EventType.ASSIST
    minute = _parse_minute(request.POST.get("minute"))
    score_changed = False

    if action == "start":
        match.status = Match.Status.LIVE
        match.save(update_fields=["status", "updated_at"])
        messages.success(request, "경기를 LIVE로 시작했습니다.")
    elif action == "finish":
        match.status = Match.Status.FINISHED
        match.save(update_fields=["status", "updated_at"])
        messages.success(request, "경기를 종료했습니다.")
    elif action == "goal":
        side = request.POST.get("side") or MatchEvent.Side.OUR
        player = team_players.filter(pk=request.POST.get("player") or 0).first()
        goal = MatchEvent.objects.create(
            match=match, event_type=GOAL, side=side,
            player=player if side == MatchEvent.Side.OUR else None, minute=minute,
        )
        assist = team_players.filter(pk=request.POST.get("assist") or 0).first()
        if side == MatchEvent.Side.OUR and assist:
            MatchEvent.objects.create(
                match=match, event_type=ASSIST, side=side,
                player=assist, minute=minute, goal=goal,
            )
        score_changed = True
        messages.success(request, "득점을 기록했습니다.")
    elif action == "event":
        etype = request.POST.get("event_type") or ""
        if etype in _LIVE_SIMPLE_EVENTS:
            side = request.POST.get("side") or MatchEvent.Side.OUR
            player = team_players.filter(pk=request.POST.get("player") or 0).first()
            MatchEvent.objects.create(
                match=match, event_type=etype, side=side,
                player=player if side == MatchEvent.Side.OUR else None, minute=minute,
            )
            score_changed = etype == MatchEvent.EventType.OWN_GOAL
            messages.success(request, "이벤트를 기록했습니다.")
    elif action == "delete":
        ev = match.events.filter(pk=request.POST.get("event_id") or 0).first()
        if ev:
            score_changed = ev.event_type in (GOAL, MatchEvent.EventType.OWN_GOAL)
            ev.delete()  # 연결된 도움(assists)은 CASCADE로 함께 삭제됨
            messages.success(request, "이벤트를 삭제했습니다.")

    if score_changed:
        recompute_score(match)


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
        .order_by("-goals", "-points", "player__name")
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
