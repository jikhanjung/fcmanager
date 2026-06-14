from django.contrib import admin

from .models import Season, Competition, CompetitionEntry, Award


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["name", "year", "is_current", "start_date", "end_date"]
    list_filter = ["is_current"]
    search_fields = ["name", "year"]


class CompetitionEntryInline(admin.TabularInline):
    model = CompetitionEntry
    extra = 1
    autocomplete_fields = ["team", "season"]


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "organizer"]
    list_filter = ["kind"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CompetitionEntryInline]


@admin.register(CompetitionEntry)
class CompetitionEntryAdmin(admin.ModelAdmin):
    list_display = ["team", "competition", "season"]
    list_filter = ["competition", "season", "team"]
    autocomplete_fields = ["team", "competition", "season"]


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ["title", "competition", "season", "team", "player", "rank", "date_awarded"]
    list_filter = ["competition", "season", "team"]
    search_fields = ["title"]
    autocomplete_fields = ["competition", "season", "team", "player"]
