from django.http import HttpResponse
from django.shortcuts import redirect

from .models import Club


def platform_home(request):
    """플랫폼 랜딩(테넌트 밖). 지금은 활성 클럽으로 보낸다.

    (추후 클럽 목록·가입 랜딩으로 확장 — Phase C/D)
    """
    club = Club.objects.filter(is_active=True).order_by("id").first()
    if club:
        return redirect(f"/{club.slug}/")
    return HttpResponse("등록된 클럽이 없습니다.", content_type="text/plain; charset=utf-8")
