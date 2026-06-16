from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.competitions.models import Competition, Division, Season

# Team.AgeGroup -> Division.AgeGroup
_AGE_TO_DIVISION = {"K7": "2030", "40": "40", "50": "50"}


def _latest_competition(team):
    """팀의 명단/출전 기준 가장 최근 대회(연도·id 내림차순). 없으면 None."""
    return (
        Competition.objects.filter(memberships__team=team).order_by("-year", "-id").first()
        or Competition.objects.filter(entries__team=team).order_by("-year", "-id").first()
    )


def _division_for(competition, team):
    """대회 안에서 팀 연령대에 해당하는 부문. 부문 없는 대회면 None."""
    if competition is None:
        return None
    ag = _AGE_TO_DIVISION.get(team.age_group, "OPEN")
    return Division.objects.filter(competition=competition, age_group=ag).first()
from apps.matches.models import Match, MatchEvent
from apps.notices.models import Notice

from .forms import MembershipAddForm, MembershipForm, PlayerForm, TeamForm
from .models import Player, Team, TeamMembership

staff_required = user_passes_test(lambda u: u.is_staff, login_url="login")


def home(request):
    """홈: 다음 경기 / 최근 결과 / 팀 목록."""
    now = timezone.now()
    upcoming = (
        Match.objects.filter(kickoff__gte=now)
        .exclude(status=Match.Status.CANCELLED)
        .select_related("our_team", "opponent", "competition")
        .order_by("kickoff")[:5]
    )
    recent = (
        Match.objects.filter(status=Match.Status.FINISHED)
        .select_related("our_team", "opponent", "competition")
        .order_by("-kickoff")[:5]
    )
    teams = Team.objects.all()
    notices = Notice.objects.filter(is_published=True)[:5]
    return render(
        request,
        "teams/home.html",
        {"upcoming": upcoming, "recent": recent, "teams": teams,
         "notices": notices},
    )


def team_list(request):
    teams = Team.objects.all()
    return render(request, "teams/team_list.html", {"teams": teams})


def team_detail(request, slug):
    """팀 상세 — 명단은 '가장 최근 대회' 기준(명단은 대회 단위로 꾸려짐)."""
    team = get_object_or_404(Team, slug=slug)
    latest = _latest_competition(team)
    memberships = team.memberships.filter(
        is_active=True, player__deleted_at__isnull=True)
    if latest is not None:
        memberships = memberships.filter(competition=latest)
    memberships = (
        memberships.select_related("player", "division").order_by("jersey_number")
    )
    return render(
        request,
        "teams/team_detail.html",
        {"team": team, "memberships": memberships, "latest_competition": latest},
    )


def player_detail(request, pk):
    """선수 상세: 프로필 + 소속 이력 + 득점/도움/카드 기록 + 수상."""
    player = get_object_or_404(Player, pk=pk)
    memberships = (
        player.memberships.select_related("team", "season")
        .order_by("-season__year", "team")
    )

    ET = MatchEvent.EventType
    counts = player.match_events.aggregate(
        goals=Count("id", filter=Q(event_type=ET.GOAL)),
        assists=Count("id", filter=Q(event_type=ET.ASSIST)),
        yellows=Count("id", filter=Q(event_type=ET.YELLOW)),
        reds=Count("id", filter=Q(event_type=ET.RED)),
    )

    goal_events = (
        player.match_events.filter(event_type=ET.GOAL)
        .select_related("match", "match__opponent", "match__competition")
        .order_by("-match__kickoff")
    )
    awards = player.awards.select_related("competition", "season")

    return render(
        request,
        "teams/player_detail.html",
        {
            "player": player,
            "memberships": memberships,
            "counts": counts,
            "goal_events": goal_events,
            "awards": awards,
        },
    )


# ── 운영진 편집 (사이트 내 관리) ─────────────────────────────────────────

@staff_required
def team_create(request):
    if request.method == "POST":
        form = TeamForm(request.POST, request.FILES)
        if form.is_valid():
            team = form.save()
            messages.success(request, f"팀 '{team.name}'을(를) 추가했습니다.")
            return redirect(team.get_absolute_url())
    else:
        form = TeamForm()
    return render(request, "teams/team_form.html", {"form": form, "is_create": True})


@staff_required
def team_edit(request, slug):
    team = get_object_or_404(Team, slug=slug)
    if request.method == "POST":
        form = TeamForm(request.POST, request.FILES, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, "팀 정보를 저장했습니다.")
            return redirect(team.get_absolute_url())
    else:
        form = TeamForm(instance=team)
    return render(request, "teams/team_form.html",
                  {"form": form, "team": team, "is_create": False})


def _get_membership(team, player_pk):
    """팀-선수의 소속 레코드(가장 최근 시즌)."""
    m = (TeamMembership.objects.filter(team=team, player_id=player_pk)
         .order_by("-season__year", "-id").first())
    if m is None:
        from django.http import Http404
        raise Http404("이 팀에 속한 선수가 아닙니다.")
    return m


@staff_required
def player_add(request, slug):
    """기존 Player(멤버 마스터)에서 선택해 팀 소속을 추가. 새 Player는 만들지 않는다.

    명단은 '가장 최근 대회'에 귀속(팀 페이지 표시 기준과 일치). 그 대회에 팀 연령
    부문이 있으면 division도 함께 지정한다.
    """
    team = get_object_or_404(Team, slug=slug)
    competition = _latest_competition(team)
    division = _division_for(competition, team)
    if request.method == "POST":
        form = MembershipAddForm(request.POST, team=team,
                                 competition=competition, division=division)
        if form.is_valid():
            m = form.save(commit=False)
            m.team = team
            m.competition = competition
            m.division = division
            m.is_active = True
            m.save()
            messages.success(request, f"'{m.player.name}'을(를) {team.name}에 추가했습니다.")
            return redirect(team.get_absolute_url())
    else:
        form = MembershipAddForm(team=team, competition=competition, division=division)
    return render(request, "teams/player_add.html", {"form": form, "team": team})


@staff_required
def player_edit(request, slug, pk):
    team = get_object_or_404(Team, slug=slug)
    player = get_object_or_404(Player, pk=pk)
    membership = _get_membership(team, pk)
    if request.method == "POST":
        pform = PlayerForm(request.POST, request.FILES, instance=player)
        mform = MembershipForm(request.POST, instance=membership)
        if pform.is_valid() and mform.is_valid():
            pform.save()
            mform.save()
            messages.success(request, f"'{player.name}' 정보를 저장했습니다.")
            return redirect(team.get_absolute_url())
    else:
        pform = PlayerForm(instance=player)
        mform = MembershipForm(instance=membership)
    return render(request, "teams/player_form.html",
                  {"pform": pform, "mform": mform, "team": team,
                   "player": player, "is_create": False})


@staff_required
def player_remove(request, slug, pk):
    """선수를 팀에서 제외(소속 삭제). 선수 레코드·기록은 보존."""
    team = get_object_or_404(Team, slug=slug)
    player = get_object_or_404(Player, pk=pk)
    membership = _get_membership(team, pk)
    if request.method == "POST":
        membership.delete()
        messages.success(request, f"'{player.name}'을(를) {team.name}에서 제외했습니다.")
        return redirect(team.get_absolute_url())
    return render(request, "teams/player_confirm_remove.html",
                  {"team": team, "player": player})


# ── Player(멤버 마스터) 전체 관리 — 팀과 무관한 선수 레코드 CRUD ──

@staff_required
def player_manage(request):
    """모든 Player를 한 화면에서 관리(검색·생성·수정·삭제 진입).

    기본은 활동 선수만. ?deleted=1 이면 삭제(soft delete)된 선수 목록(복구용).
    """
    q = (request.GET.get("q") or "").strip()
    show_deleted = request.GET.get("deleted") == "1"
    players = (
        Player.objects.annotate(team_count=Count("memberships__team", distinct=True))
        .prefetch_related("memberships__team").order_by("name")
    )
    players = players.filter(deleted_at__isnull=not show_deleted)
    if q:
        players = players.filter(name__icontains=q)
    return render(request, "teams/player_manage.html", {
        "players": players, "q": q, "show_deleted": show_deleted,
        "active_total": Player.objects.filter(deleted_at__isnull=True).count(),
        "deleted_total": Player.objects.filter(deleted_at__isnull=False).count(),
    })


@staff_required
def player_create(request):
    """새 Player 레코드 생성(팀 소속과 무관). 소속은 팀 페이지에서 별도 추가."""
    if request.method == "POST":
        form = PlayerForm(request.POST, request.FILES)
        if form.is_valid():
            player = form.save()
            messages.success(request, f"선수 '{player.name}'을(를) 등록했습니다.")
            return redirect("teams:player_manage")
    else:
        form = PlayerForm()
    return render(request, "teams/player_master_form.html",
                  {"form": form, "is_create": True})


@staff_required
def player_master_edit(request, pk):
    """Player 레코드 정보 수정(팀 소속·등번호와 무관)."""
    player = get_object_or_404(Player, pk=pk)
    if request.method == "POST":
        form = PlayerForm(request.POST, request.FILES, instance=player)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{player.name}' 정보를 저장했습니다.")
            return redirect("teams:player_manage")
    else:
        form = PlayerForm(instance=player)
    return render(request, "teams/player_master_form.html",
                  {"form": form, "player": player, "is_create": False})


@staff_required
def player_master_delete(request, pk):
    """Player를 soft delete(삭제 표시). 레코드·소속·기록은 보존, 목록·로스터에서만 숨김."""
    player = get_object_or_404(Player, pk=pk, deleted_at__isnull=True)
    if request.method == "POST":
        player.deleted_at = timezone.now()
        player.save(update_fields=["deleted_at", "updated_at"])
        messages.success(request, f"선수 '{player.name}'을(를) 삭제했습니다. (복구 가능)")
        return redirect("teams:player_manage")
    return render(request, "teams/player_master_confirm_delete.html", {
        "player": player,
        "membership_count": player.memberships.count(),
        "team_names": list(player.memberships.values_list("team__name", flat=True).distinct()),
    })


@staff_required
def player_restore(request, pk):
    """soft delete된 Player를 복구."""
    player = get_object_or_404(Player, pk=pk, deleted_at__isnull=False)
    if request.method == "POST":
        player.deleted_at = None
        player.save(update_fields=["deleted_at", "updated_at"])
        messages.success(request, f"선수 '{player.name}'을(를) 복구했습니다.")
    return redirect(f"{reverse('teams:player_manage')}?deleted=1")
