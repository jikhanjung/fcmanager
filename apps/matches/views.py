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
from .models import Match, MatchEvent, MatchLineup
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


def _common_filters(club):
    comp_ids = Match.objects.filter(club=club).values_list("competition_id", flat=True)
    comps = Competition.objects.filter(id__in=comp_ids).distinct()
    return {
        "teams": Team.objects.filter(club=club),
        "competitions": comps,
        "years": list(comps.values_list("year", flat=True)
                       .distinct().order_by("-year")),
    }


def schedule(request):
    """일정 & 결과: 전체 경기 목록 + 대회·팀·연도·상태 필터."""
    matches = Match.objects.select_related(
        "home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "competition", "division"
    # 공개 일정은 우리 팀(team entry)이 참가한 경기만(상대팀 간 경기 제외).
    ).filter(club=request.club).filter(Q(home_entry__team__isnull=False) | Q(away_entry__team__isnull=False))

    team = request.GET.get("team") or ""
    competition = request.GET.get("competition") or ""
    year = request.GET.get("year") or ""
    show = request.GET.get("show") or ""

    if team:
        matches = matches.filter(
            Q(home_entry__team__slug=team) | Q(away_entry__team__slug=team))
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
        **_common_filters(request.club),
    }
    return render(request, "matches/match_list.html", context)


from apps.clubs.permissions import club_staff_required as staff_required


@staff_required
def match_edit(request, pk):
    """운영진용 경기 결과 편집 (스코어·상태 + 득점/도움/시간 이벤트). 사이트 내 직접 편집."""
    match = get_object_or_404(
        Match.objects.select_related("home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "competition"), pk=pk, club=request.club
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
def match_delete(request, pk):
    """경기 삭제(확인 페이지). 이벤트·출전 명단·영상도 함께 삭제(CASCADE)."""
    match = get_object_or_404(
        Match.objects.select_related(
            "home_entry__team", "home_entry__opponent",
            "away_entry__team", "away_entry__opponent", "competition"),
        pk=pk, club=request.club)
    if request.method == "POST":
        competition = match.competition
        name = str(match)
        match.delete()
        messages.success(request, f"경기 '{name}'을(를) 삭제했습니다.")
        return redirect(competition.get_absolute_url())
    return render(request, "matches/match_confirm_delete.html", {
        "match": match,
        "event_count": match.events.count(),
        "video_count": match.videos.count(),
    })


@staff_required
def opponent_match_edit(request, pk):
    """상대팀 간 경기(반대편 준결승 등) 결과 입력. 저장 시 연결된 결승 상대가 자동 갱신."""
    om = get_object_or_404(
        Match.objects.select_related(
            "competition", "home_entry__opponent", "away_entry__opponent"), pk=pk, club=request.club)
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
            "home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "competition", "division"
        ),
        pk=pk, club=request.club,
    )
    events = list(match.events.select_related("player").order_by("minute", "id"))
    timeline = build_timeline(events)
    videos = match.videos.all()
    return render(
        request,
        "matches/match_detail.html",
        {"match": match, "timeline": timeline, "videos": videos},
    )


def _current_half(match):
    """현재 진행 단계의 하프 번호(1 전반·2 후반·3 연장전반·4 연장후반). 그 외 None."""
    P = Match.Period
    return {
        P.FIRST: 1, P.HALFTIME: 1,
        P.SECOND: 2,
        P.ET_FIRST: 3, P.ET_HALFTIME: 3,
        P.ET_SECOND: 4,
    }.get(match.period)


def _elapsed_seconds(match):
    """콘솔 자동 타이머의 경과 초(전후반 연속 표기).

    전반: now - 전반 시작시각. 하프타임: 전후반 길이에서 정지.
    후반: 전후반 길이 + (now - 후반 시작시각) — 전반 길이부터 이어서 흐른다.
    종료: 후반까지 했으면 풀타임(길이×2), 아니면 길이. 시작 전엔 킥오프 카운트다운 폴백.
    일시정지 중이면 멈춘 시각 기준으로, 현재 하프 누적 정지 시간(paused_seconds)을 뺀다.
    """
    P = Match.Period
    half = match.half_length_seconds
    ehalf = match.extra_half_seconds
    reg = half * 2            # 정규 풀타임(연장 시작점)
    # 정지 중이면 멈춘 시각을, 아니면 현재 시각을 기준으로 한다.
    ref = match.paused_at or timezone.now()

    def running(base_offset, started_at):
        if not started_at:
            return base_offset
        return base_offset + int((ref - started_at).total_seconds()) - match.paused_seconds

    if match.period == P.FIRST:
        if not match.live_started_at:
            return None
        return running(0, match.live_started_at)
    if match.period == P.HALFTIME:
        return half
    if match.period == P.SECOND:
        return running(half, match.second_half_started_at)
    if match.period == P.ET_FIRST:
        return running(reg, match.et_first_started_at)
    if match.period == P.ET_HALFTIME:
        return reg + ehalf
    if match.period == P.ET_SECOND:
        return running(reg + ehalf, match.et_second_started_at)
    if match.period == P.PENALTIES:
        return reg + ehalf * 2 if match.et_first_started_at else reg
    if match.period == P.FINISHED:
        if match.et_first_started_at:
            return reg + ehalf * 2     # 연장까지 진행
        return reg if match.second_half_started_at else half
    # 시작 전(SCHEDULED): 킥오프가 있으면 카운트다운용 경과(음수 가능), 없으면 None.
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
        "period": match.period,
        "period_display": match.get_period_display(),
        "paused": match.paused_at is not None,
        "half_length": match.half_length_minutes,
        # 홈/원정 기준 스코어(공개 상세 페이지 표시용).
        "home_score": match.home_score,
        "away_score": match.away_score,
        # 우리 팀 관점(중계 콘솔용 — 콘솔은 우리 팀 기준으로 동작).
        "our_score": match.our_score,
        "opponent_score": match.opponent_score,
        "result": match.result,
        # 녹아웃 연장/승부차기 정보(콘솔 단계 흐름·시청자 표시용).
        "is_knockout": match.is_knockout,
        "extra_time_single": match.extra_time_single,
        "our_pso": match.our_pso_score,
        "opponent_pso": match.opponent_pso_score,
        "decided_by_penalties": match.decided_by_penalties,
        "timeline": serialize_timeline(match),
        "elapsed_seconds": _elapsed_seconds(match),
        "updated_at": match.updated_at.isoformat(),
    }


def match_live_json(request, pk):
    """공개 폴링 엔드포인트: LIVE 경기의 스코어·상태·타임라인을 JSON으로."""
    match = get_object_or_404(
        Match.objects.select_related("home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "competition", "division"), pk=pk, club=request.club
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
        Match.objects.select_related("home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent"), pk=pk, club=request.club
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
    """운영진용 실시간 중계 콘솔(모바일): 전후반 진행 + 빠른 이벤트 입력/삭제."""
    match = get_object_or_404(
        Match.objects.select_related("home_entry__team", "home_entry__opponent", "away_entry__team", "away_entry__opponent", "competition", "division"), pk=pk, club=request.club
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
        # 자동 타이머 기준: 진행 단계별 경과 초(시작 전·킥오프 미설정 시 None).
        "elapsed_seconds": _elapsed_seconds(match),
        # 전후반 길이(분) — 후반 시작점·하프타임 정지 표시 기준.
        "half_length": match.half_length_minutes,
        # 녹아웃 연장/승부차기 단계 흐름용 설정.
        "is_knockout": match.is_knockout,
        "extra_half_length": match.extra_half_minutes,
        "extra_time_single": match.extra_time_single,
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
    half = _current_half(match)
    score_changed = False

    # 콘솔 UI 는 "우리/상대"(POST side=OUR/OPPONENT) UX 를 유지하고, 저장 시 절대 기준
    # (MatchEvent.side=HOME/AWAY)으로 번역한다. 선수 링크는 우리 쪽에만 세팅.
    our_is_home = (match.our_entry is not None
                   and match.our_entry.id == match.home_entry_id)

    def ui_is_our(ui_side):
        return (ui_side or "OUR") != "OPPONENT"

    def to_side(ui_side):
        is_our = ui_is_our(ui_side)
        if is_our:
            return MatchEvent.Side.HOME if our_is_home else MatchEvent.Side.AWAY
        return MatchEvent.Side.AWAY if our_is_home else MatchEvent.Side.HOME

    if action in ("start_first", "start"):
        # 전반 시작: 누른 시각을 기준으로 전반 시계가 0:00에서 흐른다(킥오프와 무관).
        match.status = Match.Status.LIVE
        match.period = Match.Period.FIRST
        match.live_started_at = timezone.now()
        match.second_half_started_at = None
        match.paused_at = None
        match.paused_seconds = 0
        match.save(update_fields=["status", "period", "live_started_at",
                                  "second_half_started_at", "paused_at",
                                  "paused_seconds", "updated_at"])
        messages.success(request, "전반을 시작했습니다.")
    elif action == "halftime":
        match.period = Match.Period.HALFTIME
        match.paused_at = None
        match.save(update_fields=["period", "paused_at", "updated_at"])
        messages.success(request, "하프타임입니다.")
    elif action == "start_second":
        # 후반 시작: 후반 시계 = 전후반 길이 + (now - 이 시각). 전반 길이부터 이어서 흐른다.
        match.status = Match.Status.LIVE
        match.period = Match.Period.SECOND
        match.second_half_started_at = timezone.now()
        match.paused_at = None
        match.paused_seconds = 0
        match.save(update_fields=["status", "period", "second_half_started_at",
                                  "paused_at", "paused_seconds", "updated_at"])
        messages.success(request, "후반을 시작했습니다.")
    elif action == "start_et":
        # 연장 전반 시작: 시계는 정규 풀타임부터 이어서 흐른다.
        match.status = Match.Status.LIVE
        match.period = Match.Period.ET_FIRST
        match.et_first_started_at = timezone.now()
        match.et_second_started_at = None
        match.paused_at = None
        match.paused_seconds = 0
        match.save(update_fields=["status", "period", "et_first_started_at",
                                  "et_second_started_at", "paused_at",
                                  "paused_seconds", "updated_at"])
        messages.success(request, "연장 전반을 시작했습니다.")
    elif action == "et_halftime":
        match.period = Match.Period.ET_HALFTIME
        match.paused_at = None
        match.save(update_fields=["period", "paused_at", "updated_at"])
        messages.success(request, "연장 휴식입니다.")
    elif action == "et_start_second":
        match.status = Match.Status.LIVE
        match.period = Match.Period.ET_SECOND
        match.et_second_started_at = timezone.now()
        match.paused_at = None
        match.paused_seconds = 0
        match.save(update_fields=["status", "period", "et_second_started_at",
                                  "paused_at", "paused_seconds", "updated_at"])
        messages.success(request, "연장 후반을 시작했습니다.")
    elif action == "penalties":
        # 승부차기 시작: 시계는 정지(킥 기록 모드).
        match.status = Match.Status.LIVE
        match.period = Match.Period.PENALTIES
        match.paused_at = None
        match.save(update_fields=["status", "period", "paused_at", "updated_at"])
        messages.success(request, "승부차기를 시작했습니다.")
    elif action == "pause":
        # 일시정지: 전·후반·연장 진행 중일 때만. 멈춘 시각을 기록해 시계를 동결.
        _RUN = (Match.Period.FIRST, Match.Period.SECOND,
                Match.Period.ET_FIRST, Match.Period.ET_SECOND)
        if match.period in _RUN and not match.paused_at:
            match.paused_at = timezone.now()
            match.save(update_fields=["paused_at", "updated_at"])
            messages.success(request, "시계를 일시정지했습니다.")
    elif action == "resume":
        # 재개: 멈춰 있던 시간을 누적 정지에 더하고 시계를 다시 흐르게 한다.
        if match.paused_at:
            match.paused_seconds += int((timezone.now() - match.paused_at).total_seconds())
            match.paused_at = None
            match.save(update_fields=["paused_at", "paused_seconds", "updated_at"])
            messages.success(request, "시계를 재개했습니다.")
    elif action == "finish":
        match.status = Match.Status.FINISHED
        match.period = Match.Period.FINISHED
        match.paused_at = None
        match.save(update_fields=["status", "period", "paused_at", "updated_at"])
        messages.success(request, "경기를 종료했습니다.")
    elif action == "goal":
        ui_side = request.POST.get("side") or "OUR"
        is_our = ui_is_our(ui_side)
        side = to_side(ui_side)
        player = team_players.filter(pk=request.POST.get("player") or 0).first()
        goal = MatchEvent.objects.create(
            match=match, event_type=GOAL, side=side,
            player=player if is_our else None,
            minute=minute, half=half,
        )
        assist = team_players.filter(pk=request.POST.get("assist") or 0).first()
        if is_our and assist:
            MatchEvent.objects.create(
                match=match, event_type=ASSIST, side=side,
                player=assist, minute=minute, half=half, goal=goal,
            )
        score_changed = True
        messages.success(request, "득점을 기록했습니다.")
    elif action == "event":
        etype = request.POST.get("event_type") or ""
        if etype in _LIVE_SIMPLE_EVENTS:
            ui_side = request.POST.get("side") or "OUR"
            is_our = ui_is_our(ui_side)
            side = to_side(ui_side)
            player = team_players.filter(pk=request.POST.get("player") or 0).first()
            MatchEvent.objects.create(
                match=match, event_type=etype, side=side,
                player=player if is_our else None,
                minute=minute, half=half,
            )
            score_changed = etype == MatchEvent.EventType.OWN_GOAL
            messages.success(request, "이벤트를 기록했습니다.")
    elif action == "sub":
        # 교체: 나간 선수(SUB_OUT) + 들어온 선수(SUB_IN)를 함께 기록(우리 팀).
        out_p = team_players.filter(pk=request.POST.get("player_out") or 0).first()
        in_p = team_players.filter(pk=request.POST.get("player_in") or 0).first()
        our_side = to_side("OUR")
        if out_p:
            MatchEvent.objects.create(match=match, event_type=MatchEvent.EventType.SUB_OUT,
                                      side=our_side, player=out_p, minute=minute, half=half)
        if in_p:
            MatchEvent.objects.create(match=match, event_type=MatchEvent.EventType.SUB_IN,
                                      side=our_side, player=in_p, minute=minute, half=half)
        if out_p or in_p:
            messages.success(request, "교체를 기록했습니다.")
    elif action in ("pso_goal", "pso_miss"):
        # 승부차기 킥: 성공(PSO_GOAL)/실패(PSO_MISS)를 팀별로 기록. 빠른 입력 위해 선수 미지정.
        side = to_side(request.POST.get("side") or "OUR")
        etype = (MatchEvent.EventType.PSO_GOAL if action == "pso_goal"
                 else MatchEvent.EventType.PSO_MISS)
        MatchEvent.objects.create(match=match, event_type=etype, side=side)
        score_changed = True   # 승부차기 성공 수 재집계
        messages.success(request, "승부차기를 기록했습니다.")
    elif action == "delete":
        ev = match.events.filter(pk=request.POST.get("event_id") or 0).first()
        if ev:
            score_changed = ev.event_type in (
                GOAL, MatchEvent.EventType.OWN_GOAL,
                MatchEvent.EventType.PSO_GOAL, MatchEvent.EventType.PSO_MISS)
            ev.delete()  # 연결된 도움(assists)은 CASCADE로 함께 삭제됨
            messages.success(request, "이벤트를 삭제했습니다.")

    if score_changed:
        recompute_score(match)


def scorers(request):
    """선수 순위: 우리 팀 골·도움·공격포인트 집계 + 팀·대회·시즌 필터."""
    ET = MatchEvent.EventType
    # side 는 HOME/AWAY(절대 기준)라 우리 팀 식별에 못 쓴다. player FK 는 우리 클럽
    # 선수에만 링크되므로 player__isnull=False 로 우리 팀 이벤트를 식별한다.
    events = MatchEvent.objects.filter(
        match__club=request.club,
        player__isnull=False,
        event_type__in=[ET.GOAL, ET.ASSIST],
    )

    team = request.GET.get("team") or ""
    competition = request.GET.get("competition") or ""
    year = request.GET.get("year") or ""

    if team:
        events = events.filter(
            Q(match__home_entry__team__slug=team) | Q(match__away_entry__team__slug=team))
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
        **_common_filters(request.club),
    }
    return render(request, "matches/scorers.html", context)


def stats(request):
    """통계 대시보드: 클럽/팀별 전적 요약 + 득점·도움 TOP + 경고·퇴장."""
    year = request.GET.get("year") or ""

    # 팀별 전적 + 클럽 합계
    teams, club = club_record(finished_matches(year, request.club))

    # 득점/도움/카드 (우리 팀 이벤트)
    ev = our_events(year, request.club)
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
