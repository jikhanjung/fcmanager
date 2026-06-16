from django.contrib import admin

from .models import Competition, Division, CompetitionEntry, Award


class DivisionInline(admin.TabularInline):
    model = Division
    extra = 0


class CompetitionEntryInline(admin.TabularInline):
    model = CompetitionEntry
    extra = 1
    autocomplete_fields = ["team", "division"]


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "year", "organizer"]
    list_filter = ["kind", "year"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [DivisionInline, CompetitionEntryInline]


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ["competition", "age_group", "label"]
    list_filter = ["competition", "age_group"]
    search_fields = ["competition__name", "name"]
    autocomplete_fields = ["competition"]


@admin.register(CompetitionEntry)
class CompetitionEntryAdmin(admin.ModelAdmin):
    list_display = ["team", "competition", "division"]
    list_filter = ["competition", "division", "team"]
    autocomplete_fields = ["team", "competition", "division"]


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ["title", "competition", "team", "player", "rank", "date_awarded"]
    list_filter = ["competition", "team"]
    search_fields = ["title"]
    autocomplete_fields = ["competition", "team", "player"]
