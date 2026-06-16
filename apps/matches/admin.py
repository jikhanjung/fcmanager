from django.contrib import admin

from .models import (
    Match, MatchEvent, MatchLineup, MatchVideo, Opponent, OpponentMatch,
)


@admin.register(Opponent)
class OpponentAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name"]
    search_fields = ["name", "short_name"]


@admin.register(OpponentMatch)
class OpponentMatchAdmin(admin.ModelAdmin):
    list_display = [
        "competition", "age_group", "home", "home_score",
        "away_score", "away",
    ]
    list_filter = ["competition", "age_group", "season"]
    autocomplete_fields = ["competition", "season", "home", "away"]


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
    search_fields = ["title", "url", "match__opponent__name"]
    autocomplete_fields = ["match"]


class MatchEventInline(admin.TabularInline):
    """경기 이벤트 인라인 (득점자·어시스트·시간 입력용).

    득점=GOAL, 어시스트=ASSIST 를 각각 한 줄로 추가한다.
    우리 팀 이벤트는 선수를 지정(side=우리 팀), 상대 득점은 side=상대팀 + 선수 비움.
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
        "kickoff", "our_team", "opponent", "competition", "division",
        "status", "score_display", "result_badge",
    ]
    list_filter = ["status", "competition", "division", "season", "our_team", "is_home"]
    search_fields = ["opponent__name", "venue"]
    date_hierarchy = "kickoff"
    autocomplete_fields = ["our_team", "opponent", "competition", "division", "season"]
    inlines = [MatchLineupInline, MatchEventInline, MatchVideoInline]
    fieldsets = (
        ("경기 정보", {
            "fields": (
                ("our_team", "opponent"),
                ("competition", "division"),
                ("kickoff", "venue"),
                ("is_home", "status"),
            ),
        }),
        ("결과", {
            "fields": (("our_score", "opponent_score"),),
            "description": (
                "최종 스코어를 입력하고, 아래 <b>경기 이벤트</b>에 "
                "득점자·어시스트와 득점 시간(분)을 추가하세요. "
                "상대팀 득점은 ‘팀 구분’을 상대팀으로 두고 선수는 비웁니다."
            ),
        }),
        ("비고", {"fields": ("note",), "classes": ("collapse",)}),
    )

    @admin.display(description="스코어", ordering="our_score")
    def score_display(self, obj):
        if obj.our_score is None or obj.opponent_score is None:
            return "—"
        return f"{obj.our_score} : {obj.opponent_score}"

    @admin.display(description="결과")
    def result_badge(self, obj):
        return {"W": "승", "D": "무", "L": "패"}.get(obj.result, "—")


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ["match", "minute", "event_type", "side", "player"]
    list_filter = ["event_type", "side"]
    autocomplete_fields = ["match", "player"]
