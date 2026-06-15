from django.contrib import admin

from .models import Team, Player, TeamMembership


class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 1
    autocomplete_fields = ["player", "season"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "age_group", "founded_date"]
    list_filter = ["age_group"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TeamMembershipInline]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "squad", "position", "birth_year"]
    list_filter = ["squad", "position"]
    search_fields = ["name"]
    inlines = [TeamMembershipInline]


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ["player", "team", "season", "jersey_number", "is_captain", "is_active"]
    list_filter = ["team", "season", "is_active"]
    search_fields = ["player__name"]
    autocomplete_fields = ["player", "team", "season"]
