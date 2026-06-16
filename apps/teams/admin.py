from django.contrib import admin

from .models import Team, Player, TeamMembership


class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 1
    autocomplete_fields = ["player", "competition", "division"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "age_group", "founded_date"]
    list_filter = ["age_group"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TeamMembershipInline]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    """선수(=멤버) 마스터. 모든 사람의 union이며, 팀 소속은 아래 인라인으로 붙인다.

    새 팀원은 여기서 만든 선수를 팀/소속 화면의 autocomplete로 선택해 추가한다
    (Player를 중복 생성하지 말 것). 중복이 생기면 `manage.py dedupe_members`로 병합.
    """

    list_display = ["name", "teams_display", "position", "birth_year"]
    list_filter = ["squad", "position", "memberships__team"]
    search_fields = ["name"]
    inlines = [TeamMembershipInline]

    @admin.display(description="소속 팀")
    def teams_display(self, obj):
        names = list(obj.memberships.values_list("team__name", flat=True).distinct())
        return ", ".join(names) or "—"


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ["player", "team", "competition", "division",
                    "jersey_number", "is_captain", "is_active"]
    list_filter = ["team", "competition", "division", "is_active"]
    search_fields = ["player__name"]
    autocomplete_fields = ["player", "team", "competition", "division"]
