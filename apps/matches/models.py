import re

from django.db import models
from django.urls import reverse

from apps.teams.models import Team

# 다양한 유튜브 링크 형식에서 11자 영상 ID 추출.
_YOUTUBE_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|v/|live/))([\w-]{11})"
)


def extract_youtube_id(url):
    """유튜브 URL(또는 ID)에서 영상 ID를 뽑는다. 없으면 빈 문자열."""
    s = (url or "").strip()
    m = _YOUTUBE_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[\w-]{11}", s):  # 순수 ID
        return s
    return ""


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


class OpponentMatch(models.Model):
    """상대팀 간 경기 (우리 팀이 끼지 않은 경기).

    조 순위표를 완성하기 위한 보정용. 부문(age_group)으로 어느 조에 속하는지 구분한다.
    """

    competition = models.ForeignKey(
        "competitions.Competition", on_delete=models.CASCADE,
        related_name="opponent_matches", verbose_name="대회",
    )
    season = models.ForeignKey(
        "competitions.Season", on_delete=models.PROTECT,
        related_name="opponent_matches", verbose_name="시즌",
        null=True, blank=True,
    )
    age_group = models.CharField(
        "부문", max_length=4, choices=Team.AgeGroup.choices,
        help_text="어느 부문(조)의 경기인지",
    )
    home = models.ForeignKey(
        Opponent, on_delete=models.PROTECT, related_name="home_opponent_matches",
        verbose_name="홈팀",
    )
    away = models.ForeignKey(
        Opponent, on_delete=models.PROTECT, related_name="away_opponent_matches",
        verbose_name="원정팀",
    )
    home_score = models.PositiveIntegerField("홈 득점", null=True, blank=True)
    away_score = models.PositiveIntegerField("원정 득점", null=True, blank=True)
    kickoff = models.DateTimeField("경기 일시", null=True, blank=True)
    note = models.CharField("비고", max_length=200, blank=True)

    class Meta:
        verbose_name = "상대팀 간 경기"
        verbose_name_plural = "상대팀 간 경기"
        ordering = ["competition", "age_group", "id"]

    def __str__(self):
        s = ""
        if self.home_score is not None and self.away_score is not None:
            s = f" {self.home_score}:{self.away_score}"
        return f"[{self.get_age_group_display()}] {self.home} vs {self.away}{s}"


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
    # 도움(ASSIST) 이벤트가 어느 득점(GOAL)에 연결되는지 명시적으로 가리킨다.
    # (분 미입력 시 분 기준 추정이 불가능하므로 직접 연결로 정확히 짝짓는다.)
    goal = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="assists", verbose_name="연결된 득점",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "경기 이벤트"
        verbose_name_plural = "경기 이벤트"
        ordering = ["match", "minute", "id"]

    def __str__(self):
        m = f"{self.minute}'" if self.minute is not None else ""
        return f"{m} {self.get_event_type_display()} - {self.player or self.get_side_display()}"


class MatchLineup(models.Model):
    """경기별 출전 명단 (선발/벤치 + 주장). 우리 팀 한정.

    중계 콘솔의 선수 타일·교체 입력이 이 명단을 기준으로 동작한다.
    명단이 없으면 콘솔은 팀 전체 소속 선수로 폴백한다.
    """

    class Role(models.TextChoices):
        STARTER = "STARTER", "선발"
        BENCH = "BENCH", "벤치"

    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="lineup", verbose_name="경기",
    )
    player = models.ForeignKey(
        "teams.Player", on_delete=models.CASCADE, related_name="lineups",
        verbose_name="선수",
    )
    role = models.CharField(
        "역할", max_length=8, choices=Role.choices, default=Role.STARTER,
    )
    # 경기 시점 등번호(소속 등번호에서 채워 넣되 경기별로 다를 수 있음).
    jersey_number = models.PositiveIntegerField("등번호", null=True, blank=True)
    is_captain = models.BooleanField("주장", default=False)

    class Meta:
        verbose_name = "출전 명단"
        verbose_name_plural = "출전 명단"
        ordering = ["match", "role", "jersey_number", "player__name"]
        unique_together = [("match", "player")]

    def __str__(self):
        c = " (C)" if self.is_captain else ""
        n = f"{self.jersey_number} " if self.jersey_number is not None else ""
        return f"{n}{self.player}{c} - {self.get_role_display()}"


class MatchVideo(models.Model):
    """경기 영상 (유튜브 임베드). 경기당 여러 개 가능."""

    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="videos", verbose_name="경기",
    )
    url = models.CharField(
        "유튜브 링크", max_length=300,
        help_text="유튜브 영상 URL (watch/youtu.be/shorts/embed 모두 가능)",
    )
    title = models.CharField("제목", max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "경기 영상"
        verbose_name_plural = "경기 영상"
        ordering = ["id"]

    def __str__(self):
        return self.title or self.url

    @property
    def youtube_id(self):
        return extract_youtube_id(self.url)

    @property
    def embed_url(self):
        vid = self.youtube_id
        return f"https://www.youtube.com/embed/{vid}" if vid else ""

    @property
    def watch_url(self):
        vid = self.youtube_id
        return f"https://www.youtube.com/watch?v={vid}" if vid else self.url
