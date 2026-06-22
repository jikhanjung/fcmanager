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
    """외부팀 (비-플랫폼 팀). 대회 참가팀(CompetitionEntry)으로 공유된다(클럽 무관)."""

    name = models.CharField("팀명", max_length=120, unique=True)
    short_name = models.CharField("약칭", max_length=40, blank=True)
    logo = models.ImageField("로고", upload_to="opponents/logos/", blank=True)

    class Meta:
        verbose_name = "외부팀"
        verbose_name_plural = "외부팀"
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

    class Period(models.TextChoices):
        """중계 진행 단계(상태 LIVE 내부의 전·후반·연장·승부차기 구분)."""
        SCHEDULED = "SCHEDULED", "시작 전"
        FIRST = "FIRST", "전반"
        HALFTIME = "HALFTIME", "하프타임"
        SECOND = "SECOND", "후반"
        ET_FIRST = "ET_FIRST", "연장 전반"
        ET_HALFTIME = "ET_HALFTIME", "연장 휴식"
        ET_SECOND = "ET_SECOND", "연장 후반"
        PENALTIES = "PENALTIES", "승부차기"
        FINISHED = "FINISHED", "종료"

    class Stage(models.TextChoices):
        GROUP = "GROUP", "조별리그"
        RO16 = "RO16", "16강"
        QUARTER = "QF", "8강"
        SEMI = "SF", "준결승"
        THIRD = "3RD", "3·4위전"
        FINAL = "F", "결승"

    # 대진표 정렬 순서(작을수록 앞 단계). 조별리그가 가장 앞.
    STAGE_ORDER = {"GROUP": 0, "RO16": 1, "QF": 2, "SF": 3, "3RD": 4, "F": 5}
    KNOCKOUT_STAGES = {"RO16", "QF", "SF", "3RD", "F"}

    club = models.ForeignKey(
        "clubs.Club", on_delete=models.CASCADE, related_name="matches",
        verbose_name="클럽",
    )
    # 두 참가팀(entry). 우리 팀일 수도 외부팀일 수도 있다(대칭).
    home_entry = models.ForeignKey(
        "competitions.CompetitionEntry", on_delete=models.CASCADE,
        related_name="home_matches", verbose_name="홈 참가팀",
        null=True, blank=True,
    )
    away_entry = models.ForeignKey(
        "competitions.CompetitionEntry", on_delete=models.CASCADE,
        related_name="away_matches", verbose_name="원정 참가팀",
        null=True, blank=True,
    )
    competition = models.ForeignKey(
        "competitions.Competition", on_delete=models.PROTECT,
        related_name="matches", verbose_name="대회",
    )
    division = models.ForeignKey(
        "competitions.Division", on_delete=models.SET_NULL,
        related_name="matches", verbose_name="부문",
        null=True, blank=True,
    )
    stage = models.CharField(
        "단계", max_length=6, choices=Stage.choices, default=Stage.GROUP,
        help_text="조별리그 / 녹아웃(8강·준결승·결승 등)",
    )
    # 대진 자동 진행(feeder): 결승 상대 = opponent_feeder(반대편 준결승) 승자.
    # advance_feeder(우리 준결승)에서 우리가 지면 이 경기는 '진출 실패' 처리.
    opponent_feeder = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="feeds_opponent_of", verbose_name="상대 진출 경기",
        help_text="이 경기의 상대(away_entry) = 선택한 경기의 승자(예: 반대편 준결승).",
    )
    advance_feeder = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="advances_to", verbose_name="우리 진출 경기",
        help_text="우리가 선택한 경기(예: 우리 준결승)에서 이겨야 이 경기에 진출.",
    )
    kickoff = models.DateTimeField("경기 일시", null=True, blank=True)
    venue = models.CharField("장소", max_length=200, blank=True)
    status = models.CharField(
        "상태", max_length=12, choices=Status.choices, default=Status.SCHEDULED
    )
    home_score = models.PositiveIntegerField("홈 득점", null=True, blank=True)
    away_score = models.PositiveIntegerField("원정 득점", null=True, blank=True)
    note = models.TextField("비고", blank=True)

    # 중계 진행 단계(전반/하프타임/후반/종료). 상태(status)는 공개 페이지용으로 유지하고,
    # 콘솔의 전후반 전환은 이 필드로 추적한다.
    period = models.CharField(
        "진행 단계", max_length=12, choices=Period.choices, default=Period.SCHEDULED,
    )
    # 중계 콘솔 자동 시계의 기준점. '전반 시작'을 누른 실제 시각으로,
    # 예정 킥오프와 무관하게 이 시각부터 전반 시계가 0:00에서 흐른다.
    live_started_at = models.DateTimeField("전반 시작 시각", null=True, blank=True)
    # '후반 시작'을 누른 실제 시각. 후반 시계 = 전후반 길이 + (now - 이 시각).
    second_half_started_at = models.DateTimeField("후반 시작 시각", null=True, blank=True)
    # 연장 전·후반 시작 시각(녹아웃 동점 시). 시계는 정규 풀타임부터 이어서 흐른다.
    et_first_started_at = models.DateTimeField("연장 전반 시작 시각", null=True, blank=True)
    et_second_started_at = models.DateTimeField("연장 후반 시작 시각", null=True, blank=True)
    # 연장전 진행 여부. 최종 스코어(home/away_score)는 연장 골까지 합산한 값이며,
    # 이 플래그로 '연장 접전'을 공개 페이지에 표시한다(승부차기와 별개로 켤 수 있음).
    went_to_extra_time = models.BooleanField("연장전 진행", default=False)
    # 승부차기 최종 스코어(킥 이벤트 집계). 본점수 동점일 때 승자 판정에 쓰인다.
    home_pso_score = models.PositiveIntegerField("홈 승부차기", null=True, blank=True)
    away_pso_score = models.PositiveIntegerField("원정 승부차기", null=True, blank=True)
    # 시계 일시정지: 멈춘 시각(정지 중이면 not-null) + 현재 구간에서 누적 정지 초.
    # 구간 시계에서 paused_seconds 를 빼서 정지 시간만큼 시계가 멈춘 듯 보이게 한다.
    paused_at = models.DateTimeField("일시정지 시각", null=True, blank=True)
    paused_seconds = models.PositiveIntegerField("누적 정지(초)", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "경기"
        verbose_name_plural = "경기"
        ordering = ["-kickoff"]

    def __str__(self):
        h = self.home_entry.name if self.home_entry_id else "?"
        a = self.away_entry.name if self.away_entry_id else "?"
        return f"{h} vs {a}"

    def get_absolute_url(self):
        return reverse("matches:detail", kwargs={"pk": self.pk})

    # ── 우리 팀 관점 호환 프로퍼티 ──
    # (기존 our_team/opponent/our_score/opponent_score/is_home/result 를 home/away entry 에서 도출)
    @property
    def our_entry(self):
        """home/away 중 이 경기 클럽(club) 소속 팀의 entry. 없으면 None(상대팀 간 경기)."""
        for e in (self.home_entry, self.away_entry):
            if e and e.club_id is not None and e.club_id == self.club_id:
                return e
        return None

    @property
    def opponent_entry(self):
        our = self.our_entry
        if our is None:
            return None
        return self.away_entry if our.id == self.home_entry_id else self.home_entry

    @property
    def is_our_match(self):
        return self.our_entry is not None

    @property
    def our_team(self):
        e = self.our_entry
        return e.team if e else None

    @property
    def opponent(self):
        """상대(호환): 외부팀이면 Opponent, 플랫폼 팀이면 Team. str→이름."""
        oe = self.opponent_entry
        if oe is None:
            return None
        return oe.opponent or oe.team

    @property
    def is_home(self):
        our = self.our_entry
        return our is not None and our.id == self.home_entry_id

    @property
    def our_score(self):
        our = self.our_entry
        if our is None:
            return None
        return self.home_score if our.id == self.home_entry_id else self.away_score

    @property
    def opponent_score(self):
        our = self.our_entry
        if our is None:
            return None
        return self.away_score if our.id == self.home_entry_id else self.home_score

    @property
    def result(self):
        """우리 팀 기준 승/무/패 (W/D/L). 점수 미입력/상대팀 간 경기면 None."""
        os, ops = self.our_score, self.opponent_score
        if os is None or ops is None:
            return None
        return "W" if os > ops else ("L" if os < ops else "D")

    @property
    def winner_entry(self):
        """승자 entry. 본점수 우선, 동점이면 승부차기로 판정(둘 다 없으면 None)."""
        if self.home_score is None or self.away_score is None:
            return None
        if self.home_score > self.away_score:
            return self.home_entry
        if self.away_score > self.home_score:
            return self.away_entry
        # 본점수 동점 → 승부차기 승자.
        hp, ap = self.home_pso_score, self.away_pso_score
        if hp is not None and ap is not None and hp != ap:
            return self.home_entry if hp > ap else self.away_entry
        return None

    @property
    def decided_by_penalties(self):
        """본점수 동점인데 승부차기로 승부가 갈렸는지."""
        return (self.home_score is not None and self.home_score == self.away_score
                and self.home_pso_score is not None and self.away_pso_score is not None
                and self.home_pso_score != self.away_pso_score)

    @property
    def our_pso_score(self):
        our = self.our_entry
        if our is None or self.home_pso_score is None:
            return None
        return self.home_pso_score if our.id == self.home_entry_id else self.away_pso_score

    @property
    def opponent_pso_score(self):
        our = self.our_entry
        if our is None or self.home_pso_score is None:
            return None
        return self.away_pso_score if our.id == self.home_entry_id else self.home_pso_score

    @property
    def half_length_minutes(self):
        """이 경기의 전후반 한 쪽 길이(분). 부문 오버라이드 → 대회 기본값 순."""
        if self.division_id and self.division.half_length_minutes:
            return self.division.half_length_minutes
        return self.competition.half_length_minutes

    @property
    def half_length_seconds(self):
        return self.half_length_minutes * 60

    @property
    def extra_half_minutes(self):
        """연장 한 쪽 길이(분). 부문 오버라이드 → 대회 기본값 순."""
        if self.division_id and self.division.extra_half_minutes:
            return self.division.extra_half_minutes
        return self.competition.extra_half_minutes

    @property
    def extra_half_seconds(self):
        return self.extra_half_minutes * 60

    @property
    def extra_time_total_seconds(self):
        """연장 전체 길이(초). 단일/전후반 모두 한 쪽 길이의 2배."""
        return self.extra_half_seconds * 2

    @property
    def extra_time_single(self):
        """연장을 단일(중간 휴식 없음)으로 진행할지. 부문 오버라이드 → 대회 기본값 순."""
        if self.division_id and self.division.extra_time_single is not None:
            return self.division.extra_time_single
        return self.competition.extra_time_single

    @property
    def is_knockout(self):
        return self.stage in self.KNOCKOUT_STAGES

    @property
    def stage_order(self):
        return self.STAGE_ORDER.get(self.stage, 0)


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
        PSO_GOAL = "PSO_GOAL", "승부차기 성공"
        PSO_MISS = "PSO_MISS", "승부차기 실패"

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
    # 이벤트가 일어난 전·후반 구분(1=전반, 2=후반). 콘솔 기록 시 진행 단계에서 채운다.
    half = models.PositiveSmallIntegerField("전/후반", null=True, blank=True)
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
