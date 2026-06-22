from django.db import models
from django.urls import reverse


class Competition(models.Model):
    """대회/리그 (구청장기·협회장기·K7리그·시민리그 등)."""

    class Kind(models.TextChoices):
        LEAGUE = "LEAGUE", "리그"
        TOURNAMENT = "TOURNAMENT", "토너먼트"
        CUP = "CUP", "컵 대회"

    name = models.CharField("대회명", max_length=120)
    slug = models.SlugField("URL 슬러그", max_length=140, unique=True)
    kind = models.CharField("종류", max_length=12, choices=Kind.choices)
    year = models.PositiveIntegerField("연도", default=2026)
    organizer = models.CharField("주최", max_length=120, blank=True)
    description = models.TextField("설명", blank=True)
    # 전후반 한 쪽 길이(분). 중계 콘솔 시계·후반 시작점 기준. 부문(Division)에서 덮어쓸 수 있다.
    half_length_minutes = models.PositiveIntegerField("전후반 길이(분)", default=45)
    # 연장 한 쪽 길이(분). 녹아웃 동점 시 연장 시계 기준.
    extra_half_minutes = models.PositiveIntegerField("연장 길이(분)", default=15)
    # 연장을 단일(중간 휴식 없음)로 진행할지. 기본은 전·후반(2개 하프).
    extra_time_single = models.BooleanField(
        "연장 단일 진행", default=False,
        help_text="체크하면 연장을 전·후반 없이 한 번에 진행(휴식 없음).",
    )

    class Meta:
        verbose_name = "대회"
        verbose_name_plural = "대회"
        ordering = ["-year", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("competitions:competition_detail", kwargs={"slug": self.slug})


class Division(models.Model):
    """대회 안의 연령 부문(20-30대/40대/50대/오픈). 부문이 없는 대회(리그 등)도 있다.

    나이 자격: 부문의 최소 나이 이상이면 출전 가능. 따라서 나이 많은 선수는
    더 낮은 연령 부문에서 뛸 수 있으나(50대→40대부문 OK), 그 반대는 불가.
    """

    class AgeGroup(models.TextChoices):
        U30 = "2030", "20-30대"
        FORTIES = "40", "40대"
        FIFTIES = "50", "50대"
        OPEN = "OPEN", "오픈"

    # 부문별 최소 나이(자격 판정용). 20-30대·오픈은 하한 없음.
    MIN_AGE = {"40": 40, "50": 50}

    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="divisions",
        verbose_name="대회",
    )
    age_group = models.CharField("연령 부문", max_length=8, choices=AgeGroup.choices)
    name = models.CharField(
        "부문명", max_length=60, blank=True,
        help_text="비우면 연령 부문 표시명을 사용(예: 40대부문).",
    )
    # 부문별 전후반 길이. 비우면 대회(Competition) 기본값을 사용한다.
    half_length_minutes = models.PositiveIntegerField(
        "전후반 길이(분)", null=True, blank=True,
        help_text="비우면 대회 기본값 사용.",
    )
    # 부문별 연장 길이/형식 오버라이드. 비우면 대회 기본값을 사용한다.
    extra_half_minutes = models.PositiveIntegerField(
        "연장 길이(분)", null=True, blank=True,
        help_text="비우면 대회 기본값 사용.",
    )
    extra_time_single = models.BooleanField(
        "연장 단일 진행", null=True, blank=True,
        help_text="비우면 대회 기본값 사용.",
    )

    class Meta:
        verbose_name = "부문"
        verbose_name_plural = "부문"
        ordering = ["competition", "age_group"]
        unique_together = [("competition", "age_group")]

    def __str__(self):
        return f"{self.competition.name} {self.label}"

    @property
    def label(self):
        return self.name or f"{self.get_age_group_display()}부문"

    @property
    def min_age(self):
        """이 부문 출전 최소 나이. 하한이 없으면 None."""
        return self.MIN_AGE.get(self.age_group)

    def is_eligible(self, player):
        """선수가 이 부문 나이 자격을 만족하는지. 생년 미상이면 True(차단하지 않음)."""
        if self.min_age is None or not player.birth_year:
            return True
        return (self.competition.year - player.birth_year) >= self.min_age


class CompetitionEntry(models.Model):
    """대회/부문 참가팀. 우리 팀(team) 또는 외부팀(opponent) 중 정확히 하나.

    경기(Match)는 이 참가팀(entry) 둘을 home/away 로 참조한다.
    """

    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="entries",
        verbose_name="대회",
    )
    division = models.ForeignKey(
        "Division", on_delete=models.SET_NULL, related_name="entries",
        verbose_name="부문", null=True, blank=True,
    )
    # 참가팀 정체성: team(우리 클럽 팀) XOR opponent(외부팀). 정확히 하나.
    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="entries",
        verbose_name="우리 팀", null=True, blank=True,
    )
    opponent = models.ForeignKey(
        "matches.Opponent", on_delete=models.CASCADE, related_name="entries",
        verbose_name="외부팀", null=True, blank=True,
    )
    note = models.CharField("비고", max_length=200, blank=True)

    class Meta:
        verbose_name = "대회 참가팀"
        verbose_name_plural = "대회 참가팀"
        ordering = ["-competition__year", "competition"]
        unique_together = [
            ("competition", "division", "team"),
            ("competition", "division", "opponent"),
        ]

    @property
    def name(self):
        if self.team_id:
            return self.team.name
        if self.opponent_id:
            return self.opponent.name
        return "?"

    @property
    def club_id(self):
        """우리 팀 entry 면 소속 클럽 id, 외부팀이면 None."""
        return self.team.club_id if self.team_id else None

    def __str__(self):
        return f"{self.name} - {self.competition}"


class Award(models.Model):
    """입상/수상 내역 (팀 또는 선수 단위)."""

    club = models.ForeignKey(
        "clubs.Club", on_delete=models.CASCADE, related_name="awards",
        verbose_name="클럽",
    )
    title = models.CharField("수상명", max_length=120, help_text="예: 우승, 준우승, 득점왕")
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="awards",
        verbose_name="대회",
    )
    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="awards",
        verbose_name="팀", null=True, blank=True,
    )
    player = models.ForeignKey(
        "teams.Player", on_delete=models.CASCADE, related_name="awards",
        verbose_name="선수", null=True, blank=True,
    )
    rank = models.PositiveIntegerField("순위", null=True, blank=True)
    date_awarded = models.DateField("수상일", null=True, blank=True)
    description = models.TextField("설명", blank=True)

    class Meta:
        verbose_name = "입상 내역"
        verbose_name_plural = "입상 내역"
        ordering = ["-date_awarded", "-competition__year"]

    def __str__(self):
        who = self.team or self.player or "?"
        return f"{who} - {self.competition} {self.title}"
