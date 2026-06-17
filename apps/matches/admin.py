from django.contrib import admin

from .models import Match, MatchEvent, MatchLineup, MatchVideo, Opponent


@admin.register(Opponent)
class OpponentAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name"]
    search_fields = ["name", "short_name"]


class MatchVideoInline(admin.TabularInline):
    model = MatchVideo
    extra = 1
    fields = ["url", "title"]


class MatchLineupInline(admin.TabularInline):
    """경기 출전 명단 인라인 (선발/벤치 + 등번호 + 주장)."""

    model = MatchLineup
    extra = 0
    fields = ["player", "role", "jersey_number", "is_captain"]
    autocomplete_fields = ["player"]
    ordering = ["role", "jersey_number", "player__name"]


@admin.register(MatchVideo)
class MatchVideoAdmin(admin.ModelAdmin):
    list_display = ["match", "title", "url"]
    search_fields = ["title", "url"]
    autocomplete_fields = ["match"]


class MatchEventInline(admin.TabularInline):
    """경기 이벤트 인라인 (득점자·어시스트·시간 입력용).

    side(OUR/OPPONENT)는 우리 entry 기준. 우리 팀 이벤트는 선수 지정, 상대 득점은
    side=상대팀 + 선수 비움.
    """

    model = MatchEvent
    extra = 2
    fields = ["event_type", "side", "player", "minute", "description"]
    autocomplete_fields = ["player"]
    ordering = ["minute", "id"]
    verbose_name = "경기 이벤트"
    verbose_name_plural = "경기 이벤트 (득점자 · 어시스트 · 시간)"


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = [
        "kickoff", "home_entry", "away_entry", "competition", "division", "stage",
        "status", "score_display",
    ]
    list_filter = ["status", "stage", "competition", "division", "club"]
    search_fields = ["venue", "home_entry__opponent__name", "away_entry__opponent__name",
                     "home_entry__team__name", "away_entry__team__name"]
    date_hierarchy = "kickoff"
    autocomplete_fields = ["competition", "division", "opponent_feeder", "advance_feeder"]
    inlines = [MatchLineupInline, MatchEventInline, MatchVideoInline]
    fieldsets = (
        ("경기 정보", {
            "fields": (
                ("club",),
                ("home_entry", "away_entry"),
                ("competition", "division"),
                ("stage", "kickoff"),
                ("venue", "status"),
            ),
        }),
        ("대진 자동 진행(녹아웃)", {
            "classes": ("collapse",),
            "fields": ("opponent_feeder", "advance_feeder"),
            "description": "결승 상대(away_entry) = 상대 진출 경기(반대편 준결승) 승자. "
                           "우리 진출 경기에서 지면 자동으로 '취소'.",
        }),
        ("결과", {
            "fields": (("home_score", "away_score"),),
            "description": "최종 스코어 입력 후 아래 <b>경기 이벤트</b>에 득점자·시간을 추가하세요.",
        }),
        ("비고", {"fields": ("note",), "classes": ("collapse",)}),
    )

    @admin.display(description="스코어", ordering="home_score")
    def score_display(self, obj):
        if obj.home_score is None or obj.away_score is None:
            return "—"
        return f"{obj.home_score} : {obj.away_score}"


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ["match", "minute", "event_type", "side", "player"]
    list_filter = ["event_type", "side"]
    autocomplete_fields = ["match", "player"]
