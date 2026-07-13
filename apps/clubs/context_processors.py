"""템플릿에 현재 클럽·클럽 운영진/소유자 여부를 제공."""
from .permissions import is_club_owner, is_club_staff


def club(request):
    current = getattr(request, "club", None)
    user = getattr(request, "user", None)
    return {
        "current_club": current,
        "is_club_staff": is_club_staff(user, current),
        "is_club_owner": is_club_owner(user, current),
    }
