"""템플릿 전역 컨텍스트."""
from django.conf import settings


def app_version(request):
    """배포 이미지 버전을 모든 템플릿에서 사용 가능하게 노출."""
    return {"app_version": settings.APP_VERSION}
