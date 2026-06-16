from django.db import models


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

    class Meta:
        verbose_name = "대회"
        verbose_name_plural = "대회"
        ordering = ["-year", "name"]

    def __str__(self):
        return self.name


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
    """팀의 대회 출전 (시즌별)."""

    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="entries",
        verbose_name="팀",
    )
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="entries",
        verbose_name="대회",
    )
    division = models.ForeignKey(
        "Division", on_delete=models.SET_NULL, related_name="entries",
        verbose_name="부문", null=True, blank=True,
    )
    note = models.CharField("비고", max_length=200, blank=True)

    class Meta:
        verbose_name = "대회 출전"
        verbose_name_plural = "대회 출전"
        ordering = ["-competition__year", "competition"]
        unique_together = [("team", "competition", "division")]

    def __str__(self):
        return f"{self.team} - {self.competition}"


class Award(models.Model):
    """입상/수상 내역 (팀 또는 선수 단위)."""

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
