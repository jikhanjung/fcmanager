from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ClubForm
from .models import Club, ClubMembership
from .permissions import club_owner_required


def platform_home(request):
    """플랫폼 랜딩(테넌트 밖): 클럽 목록 + 로그인/클럽 만들기."""
    clubs = Club.objects.filter(is_active=True).order_by("name")
    my_clubs = []
    if request.user.is_authenticated:
        my_clubs = list(
            Club.objects.filter(memberships__user=request.user).distinct().order_by("name")
        )
    return render(request, "clubs/landing.html",
                  {"clubs": clubs, "my_clubs": my_clubs})


@login_required
def club_create(request):
    """클럽 생성 — 만든 사용자가 소유자(OWNER) 멤버십을 받는다."""
    if request.method == "POST":
        form = ClubForm(request.POST, request.FILES)
        if form.is_valid():
            club = form.save()
            ClubMembership.objects.create(
                user=request.user, club=club, role=ClubMembership.Role.OWNER)
            messages.success(request, f"'{club.name}' 클럽을 만들었습니다.")
            return redirect(f"/{club.slug}/")
    else:
        form = ClubForm()
    return render(request, "clubs/club_form.html", {"form": form})


# ---- 클럽 멤버십(운영진 구성) 관리 — 소유자(OWNER) 전용 ----
# 역할 분리: 운영진(STAFF)은 데이터 입력, 소유자는 "누가 운영진인가"를 정한다.
# 사용자 계정 생성 자체는 여전히 시스템 관리자(admin) 몫 — 여기서는 기존 계정을 연결만 한다.

def _owner_count(club):
    return ClubMembership.objects.filter(club=club, role=ClubMembership.Role.OWNER).count()


@club_owner_required
def member_manage(request):
    """클럽 운영진 목록 + 사용자명으로 추가."""
    club = request.club
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        role = request.POST.get("role")
        if role not in ClubMembership.Role.values:
            role = ClubMembership.Role.STAFF
        user = get_user_model().objects.filter(username=username).first()
        if not username:
            messages.error(request, "사용자명을 입력하세요.")
        elif user is None:
            messages.error(
                request,
                f"사용자 '{username}' 계정이 없습니다. 계정 생성은 시스템 관리자에게 요청하세요.")
        elif ClubMembership.objects.filter(user=user, club=club).exists():
            messages.warning(request, f"'{username}' 은(는) 이미 이 클럽의 운영진입니다.")
        else:
            m = ClubMembership.objects.create(user=user, club=club, role=role)
            messages.success(request, f"'{username}' 을(를) {m.get_role_display()}(으)로 추가했습니다.")
        return redirect("clubs:member_manage")

    members = club.memberships.select_related("user").order_by("role", "user__username")
    return render(request, "clubs/member_manage.html",
                  {"members": members, "roles": ClubMembership.Role.choices})


@club_owner_required
def member_role(request, pk):
    """역할 변경(소유자 ⇄ 운영진). 마지막 소유자는 강등 불가."""
    club = request.club
    m = get_object_or_404(ClubMembership, pk=pk, club=club)
    if request.method == "POST":
        role = request.POST.get("role")
        if role not in ClubMembership.Role.values:
            messages.error(request, "알 수 없는 역할입니다.")
        elif (m.role == ClubMembership.Role.OWNER and role != ClubMembership.Role.OWNER
              and _owner_count(club) <= 1):
            messages.error(request, "마지막 소유자는 강등할 수 없습니다. 먼저 다른 소유자를 지정하세요.")
        else:
            m.role = role
            m.save(update_fields=["role"])
            messages.success(request, f"'{m.user.username}' 역할을 {m.get_role_display()}(으)로 변경했습니다.")
    return redirect("clubs:member_manage")


@club_owner_required
def member_remove(request, pk):
    """운영진 제거(확인 페이지). 마지막 소유자는 제거 불가."""
    club = request.club
    m = get_object_or_404(ClubMembership, pk=pk, club=club)
    last_owner = (m.role == ClubMembership.Role.OWNER and _owner_count(club) <= 1)
    if request.method == "POST":
        if last_owner:
            messages.error(request, "마지막 소유자는 제거할 수 없습니다. 먼저 다른 소유자를 지정하세요.")
            return redirect("clubs:member_manage")
        username = m.user.username
        m.delete()
        messages.success(request, f"'{username}' 을(를) 운영진에서 제거했습니다.")
        return redirect("clubs:member_manage")
    return render(request, "clubs/member_confirm_remove.html",
                  {"membership": m, "last_owner": last_owner})
