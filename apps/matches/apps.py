from django.apps import AppConfig


class MatchesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.matches'

    def ready(self):
        from . import signals  # noqa: F401  (대진 자동 진행 시그널 등록)
