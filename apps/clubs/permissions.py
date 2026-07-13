"""클럽별 운영진 권한 — 전역 is_staff 대신 ClubMembership 기반."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import ClubMembership


def is_club_staff(user, club):
    """user 가 club 의 운영진인가. superuser 는 모든 클럽 접근."""
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    if club is None:
        return False
    return ClubMembership.objects.filter(user=user, club=club).exists()


def is_club_owner(user, club):
    """user 가 club 의 소유자(OWNER)인가. superuser 는 모든 클럽 접근.

    역할 분리(배포·데이터 계약 §역할이 입구를 정한다): 소유자만 클럽 멤버십(운영진
    구성)을 관리한다. 일상 데이터 입력은 운영진(STAFF) 권한으로 충분.
    """
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    if club is None:
        return False
    return ClubMembership.objects.filter(
        user=user, club=club, role=ClubMembership.Role.OWNER).exists()


def club_staff_required(view):
    """현재 클럽(request.club)의 운영진만 통과. 비로그인 → 로그인, 권한없음 → 403."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_club_staff(user, getattr(request, "club", None)):
            raise PermissionDenied("이 클럽의 운영진이 아닙니다.")
        return view(request, *args, **kwargs)

    return wrapped


def club_owner_required(view):
    """현재 클럽(request.club)의 소유자만 통과. 비로그인 → 로그인, 권한없음 → 403."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_club_owner(user, getattr(request, "club", None)):
            raise PermissionDenied("이 클럽의 소유자가 아닙니다.")
        return view(request, *args, **kwargs)

    return wrapped
