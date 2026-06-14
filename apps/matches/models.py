from django.db import models
from django.urls import reverse


class Opponent(models.Model):
    """상대팀 (외부 팀)."""

    name = models.CharField("팀명", max_length=120, unique=True)
    short_name = models.CharField("약칭", max_length=40, blank=True)
    logo = models.ImageField("로고", upload_to="opponents/logos/", blank=True)

    class Meta:
        verbose_name = "상대팀"
        verbose_name_plural = "상대팀"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Match(models.Model):
    """경기 (일정 + 결과)."""

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "예정"
        LIVE = "LIVE", "진행 중"
        FINISHED = "FINISHED", "종료"
        POSTPONED = "POSTPONED", "연기"
        CANCELLED = "CANCELLED", "취소"

    our_team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="matches",
        verbose_name="우리 팀",
    )
    opponent = models.ForeignKey(
        Opponent, on_delete=models.PROTECT, related_name="matches",
        verbose_name="상대팀",
    )
    competition = models.ForeignKey(
        "competitions.Competition", on_delete=models.PROTECT,
        related_name="matches", verbose_name="대회",
    )
    season = models.ForeignKey(
        "competitions.Season", on_delete=models.PROTECT,
        related_name="matches", verbose_name="시즌",
        null=True, blank=True,
    )
    is_home = models.BooleanField("홈 경기", default=True)
    kickoff = models.DateTimeField("경기 일시")
    venue = models.CharField("장소", max_length=200, blank=True)
    status = models.CharField(
        "상태", max_length=12, choices=Status.choices, default=Status.SCHEDULED
    )
    our_score = models.PositiveIntegerField("우리 득점", null=True, blank=True)
    opponent_score = models.PositiveIntegerField("상대 득점", null=True, blank=True)
    note = models.TextField("비고", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "경기"
        verbose_name_plural = "경기"
        ordering = ["-kickoff"]

    def __str__(self):
        return f"{self.our_team} vs {self.opponent} ({self.kickoff:%Y-%m-%d})"

    def get_absolute_url(self):
        return reverse("matches:detail", kwargs={"pk": self.pk})

    @property
    def result(self):
        """우리 팀 기준 승/무/패 (W/D/L). 점수 미입력 시 None."""
        if self.our_score is None or self.opponent_score is None:
            return None
        if self.our_score > self.opponent_score:
            return "W"
        if self.our_score < self.opponent_score:
            return "L"
        return "D"


class MatchEvent(models.Model):
    """경기 이벤트 (득점·도움·경고·교체 등). 실시간 중계의 기반."""

    class EventType(models.TextChoices):
        GOAL = "GOAL", "득점"
        ASSIST = "ASSIST", "도움"
        OWN_GOAL = "OWN_GOAL", "자책골"
        YELLOW = "YELLOW", "경고"
        RED = "RED", "퇴장"
        SUB_IN = "SUB_IN", "교체 IN"
        SUB_OUT = "SUB_OUT", "교체 OUT"

    class Side(models.TextChoices):
        OUR = "OUR", "우리 팀"
        OPPONENT = "OPPONENT", "상대팀"

    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="events",
        verbose_name="경기",
    )
    side = models.CharField(
        "팀 구분", max_length=8, choices=Side.choices, default=Side.OUR
    )
    player = models.ForeignKey(
        "teams.Player", on_delete=models.SET_NULL, related_name="match_events",
        verbose_name="선수", null=True, blank=True,
        help_text="우리 팀 이벤트일 때 선택",
    )
    event_type = models.CharField("이벤트", max_length=10, choices=EventType.choices)
    minute = models.PositiveIntegerField("분", null=True, blank=True)
    description = models.CharField("설명", max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "경기 이벤트"
        verbose_name_plural = "경기 이벤트"
        ordering = ["match", "minute", "id"]

    def __str__(self):
        m = f"{self.minute}'" if self.minute is not None else ""
        return f"{m} {self.get_event_type_display()} - {self.player or self.get_side_display()}"
