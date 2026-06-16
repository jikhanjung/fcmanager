from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.competitions.models import Competition
from apps.teams.models import Player, Team

from .forms import (
    MatchEventFormSet, MatchResultForm, MatchVideoFormSet, OpponentMatchResultForm,
)
from .models import Match, MatchEvent, MatchLineup, OpponentMatch
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
        "years": list(Competition.objects.values_list("year", flat=True)
                       .distinct().order_by("-year")),
    }


def schedule(request):
    """일정 & 결과: 전체 경기 목록 + 대회·팀·연도·상태 필터."""
    matches = Match.objects.select_related(
        "our_team", "opponent", "competition", "division"
    )

    team = request.GET.get("team") or ""
    competition = request.GET.get("competition") or ""
    year = request.GET.get("year") or ""
    show = request.GET.get("show") or ""

    if team:
        matches = matches.filter(our_team__slug=team)
    if competition:
        matches = matches.filter(competition__slug=competition)
    if year.isdigit():
        matches = matches.filter(competition__year=year)
    if show == "upcoming":
        matches = matches.filter(status=Match.Status.SCHEDULED)
    elif show == "finished":
        matches = matches.filter(status=Match.Status.FINISHED)

    context = {
        "matches": matches,
        "selected": {
            "team": team,
            "competition": competition,
            "year": year,
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


@staff_required
def opponent_match_edit(request, pk):
    """상대팀 간 경기(반대편 준결승 등) 결과 입력. 저장 시 연결된 결승 상대가 자동 갱신."""
    om = get_object_or_404(
        OpponentMatch.objects.select_related("competition", "home", "away"), pk=pk)
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = OpponentMatchResultForm(request.POST, instance=om)
        if form.is_valid():
            form.save()  # post_save 시그널이 연결된 결승 상대를 자동 기입
            messages.success(request, "경기 결과를 저장했습니다.")
            return redirect(next_url or om.competition.get_absolute_url())
    else:
        form = OpponentMatchResultForm(instance=om)
    return render(request, "matches/opponent_match_edit.html",
                  {"om": om, "form": form, "next": next_url})


def match_detail(request, pk):
    """경기 상세: 스코어 + 득점·카드·교체 타임라인."""
    match = get_object_or_404(
        Match.objects.select_related(
            "our_team", "opponent", "competition", "division"
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


def _elapsed_seconds(match):
    """콘솔 자동 타이머의 경과 초.

    기준은 'LIVE 시작'을 누른 실제 시각(``live_started_at``) — 예정 킥오프와 무관.
    아직 시작 전이면 예정 킥오프로 폴백(시작 전 카운트다운 표시용), 둘 다 없으면 None.
    """
    base = match.live_started_at or match.kickoff
    if not base:
        return None
    return int((timezone.now() - base).total_seconds())


def _live_payload(match):
    """공개 폴링·콘솔 AJAX 응답이 공유하는 경기 상태 dict."""
    return {
        "status": match.status,
        "status_display": match.get_status_display(),
        "is_live": match.status == Match.Status.LIVE,
        "our_score": match.our_score,
        "opponent_score": match.opponent_score,
        "result": match.result,
        "timeline": serialize_timeline(match),
        "elapsed_seconds": _elapsed_seconds(match),
        "updated_at": match.updated_at.isoformat(),
    }


def match_live_json(request, pk):
    """공개 폴링 엔드포인트: LIVE 경기의 스코어·상태·타임라인을 JSON으로."""
    match = get_object_or_404(
        Match.objects.select_related("our_team", "opponent"), pk=pk
    )
    return JsonResponse(_live_payload(match))


# 중계 콘솔에서 빠르게 추가할 수 있는 이벤트 종류(득점·도움은 별도 처리).
_LIVE_SIMPLE_EVENTS = {
    MatchEvent.EventType.OWN_GOAL,
    MatchEvent.EventType.YELLOW,
    MatchEvent.EventType.RED,
    MatchEvent.EventType.SUB_IN,
    MatchEvent.EventType.SUB_OUT,
}


def _build_roster(match):
    """중계 콘솔 선수 타일용 로스터.

    경기 출전 명단(MatchLineup)이 있으면 그것을 쓰고(선발 먼저·벤치 뒤),
    없으면 팀 전체 소속 선수로 폴백한다. 각 항목: id·name·number·captain·bench.
    """
    lineup = list(match.lineup.select_related("player").all())
    if lineup:
        order = {MatchLineup.Role.STARTER: 0, MatchLineup.Role.BENCH: 1}
        lineup.sort(key=lambda l: (
            order.get(l.role, 2), l.jersey_number is None,
            l.jersey_number or 0, l.player.name,
        ))
        return [{
            "id": l.player_id, "name": l.player.name,
            "number": l.jersey_number, "captain": l.is_captain,
            "bench": l.role == MatchLineup.Role.BENCH,
        } for l in lineup]

    # 폴백: 팀 전체 소속(선수 단위로 합치고 등번호 있는 행 우선).
    from apps.teams.models import TeamMembership
    seen = {}
    for mm in (TeamMembership.objects.filter(team=match.our_team)
               .select_related("player")):
        p = mm.player
        cur = seen.get(p.id)
        if cur is None or (cur["number"] is None and mm.jersey_number is not None):
            seen[p.id] = {
                "id": p.id, "name": p.name, "number": mm.jersey_number,
                "captain": mm.is_captain, "bench": False,
            }
    roster = list(seen.values())
    roster.sort(key=lambda r: (r["number"] is None, r["number"] or 0, r["name"]))
    return roster


@staff_required
def match_lineup(request, pk):
    """경기 출전 명단 편집(모바일): 선발/벤치/주장 지정. 우리 팀 한정."""
    match = get_object_or_404(
        Match.objects.select_related("our_team", "opponent"), pk=pk
    )
    from apps.teams.models import TeamMembership
    # 팀 등번호(소속에서). 저장 시 라인업 등번호 기본값으로 사용.
    numbers = {}
    for mm in TeamMembership.objects.filter(team=match.our_team):
        if mm.jersey_number is not None:
            numbers.setdefault(mm.player_id, mm.jersey_number)

    if request.method == "POST":
        captain_id = request.POST.get("captain") or ""
        match.lineup.all().delete()
        team_player_ids = set(
            Player.objects.filter(memberships__team=match.our_team)
            .values_list("id", flat=True)
        )
        created = 0
        for pid in team_player_ids:
            role = request.POST.get(f"role_{pid}") or ""
            if role in (MatchLineup.Role.STARTER, MatchLineup.Role.BENCH):
                MatchLineup.objects.create(
                    match=match, player_id=pid, role=role,
                    jersey_number=numbers.get(pid),
                    is_captain=(str(pid) == captain_id),
                )
                created += 1
        messages.success(request, f"출전 명단을 저장했습니다. (선발·벤치 {created}명)")
        return redirect("matches:live_console", pk=match.pk)

    existing = {l.player_id: l for l in match.lineup.all()}
    players = (
        Player.objects.filter(memberships__team=match.our_team)
        .distinct().order_by("name")
    )
    rows = []
    for p in players:
        l = existing.get(p.id)
        rows.append({
            "id": p.id, "name": p.name,
            "position": p.get_position_display() if p.position else "",
            "number": numbers.get(p.id),
            "role": l.role if l else "",
            "captain": bool(l and l.is_captain),
        })
    return render(request, "matches/match_lineup.html", {"match": match, "rows": rows})


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
        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse(_live_payload(match))
        return redirect("matches:live_console", pk=match.pk)

    return render(request, "matches/match_live.html", {
        "match": match,
        "roster": _build_roster(match),
        "timeline": serialize_timeline(match),
        # 자동 타이머 기준: 킥오프 이후 경과 초(킥오프 미설정 시 None).
        "elapsed_seconds": _elapsed_seconds(match),
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
        # 'LIVE 시작'을 누른 시각을 자동 시계 기준으로 고정(킥오프와 무관).
        # 이미 기록돼 있으면 보존(종료 후 재개 시 시계 연속성 유지).
        fields = ["status", "updated_at"]
        if match.live_started_at is None:
            match.live_started_at = timezone.now()
            fields.append("live_started_at")
        match.save(update_fields=fields)
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
    elif action == "sub":
        # 교체: 나간 선수(SUB_OUT) + 들어온 선수(SUB_IN)를 함께 기록(우리 팀).
        out_p = team_players.filter(pk=request.POST.get("player_out") or 0).first()
        in_p = team_players.filter(pk=request.POST.get("player_in") or 0).first()
        OUR = MatchEvent.Side.OUR
        if out_p:
            MatchEvent.objects.create(match=match, event_type=MatchEvent.EventType.SUB_OUT,
                                      side=OUR, player=out_p, minute=minute)
        if in_p:
            MatchEvent.objects.create(match=match, event_type=MatchEvent.EventType.SUB_IN,
                                      side=OUR, player=in_p, minute=minute)
        if out_p or in_p:
            messages.success(request, "교체를 기록했습니다.")
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
    year = request.GET.get("year") or ""

    if team:
        events = events.filter(match__our_team__slug=team)
    if competition:
        events = events.filter(match__competition__slug=competition)
    if year.isdigit():
        events = events.filter(match__competition__year=year)

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
        "selected": {"team": team, "competition": competition, "year": year},
        **_common_filters(),
    }
    return render(request, "matches/scorers.html", context)


def stats(request):
    """통계 대시보드: 클럽/팀별 전적 요약 + 득점·도움 TOP + 경고·퇴장."""
    year = request.GET.get("year") or ""

    # 팀별 전적 + 클럽 합계
    teams, club = club_record(finished_matches(year))

    # 득점/도움/카드 (우리 팀 이벤트)
    ev = our_events(year)
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
        "year": year,
        "years": list(Competition.objects.values_list("year", flat=True)
                      .distinct().order_by("-year")),
        "teams": teams,
        "club": club,
        "scorers": scorers,
        "assisters": assisters,
        "cards": cards,
    }
    return render(request, "matches/stats.html", context)
