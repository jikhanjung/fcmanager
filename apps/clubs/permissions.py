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
