from django.contrib import admin

from .models import Opponent, Match, MatchEvent


@admin.register(Opponent)
class OpponentAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name"]
    search_fields = ["name", "short_name"]


class MatchEventInline(admin.TabularInline):
    model = MatchEvent
    extra = 1
    autocomplete_fields = ["player"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = [
        "kickoff", "our_team", "opponent", "competition",
        "status", "our_score", "opponent_score",
    ]
    list_filter = ["status", "competition", "season", "our_team", "is_home"]
    search_fields = ["opponent__name", "venue"]
    date_hierarchy = "kickoff"
    autocomplete_fields = ["our_team", "opponent", "competition", "season"]
    inlines = [MatchEventInline]


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ["match", "minute", "event_type", "side", "player"]
    list_filter = ["event_type", "side"]
    autocomplete_fields = ["match", "player"]
