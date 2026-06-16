from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.competitions.models import Season
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
    team = get_object_or_404(Team, slug=slug)
    memberships = (
        team.memberships.filter(is_active=True)
        .select_related("player")
        .order_by("jersey_number")
    )
    return render(
        request,
        "teams/team_detail.html",
        {"team": team, "memberships": memberships},
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
    """기존 Player(멤버 마스터)에서 선택해 팀 소속을 추가. 새 Player는 만들지 않는다."""
    team = get_object_or_404(Team, slug=slug)
    season = Season.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = MembershipAddForm(request.POST, team=team, season=season)
        if form.is_valid():
            m = form.save(commit=False)
            m.team = team
            m.season = season
            m.is_active = True
            m.save()
            messages.success(request, f"'{m.player.name}'을(를) {team.name}에 추가했습니다.")
            return redirect(team.get_absolute_url())
    else:
        form = MembershipAddForm(team=team, season=season)
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
