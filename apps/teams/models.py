from django.db import models
from django.urls import reverse


class Team(models.Model):
    """FC Sky 산하 팀 (K7=20-30대, 40대, 50대)."""

    class AgeGroup(models.TextChoices):
        K7 = "K7", "K7 (20-30대)"
        FORTIES = "40", "40대"
        FIFTIES = "50", "50대"

    name = models.CharField("팀 이름", max_length=100)
    slug = models.SlugField("URL 슬러그", max_length=120, unique=True)
    age_group = models.CharField(
        "연령대", max_length=4, choices=AgeGroup.choices
    )
    founded_date = models.DateField("창단일", null=True, blank=True)
    logo = models.ImageField("로고", upload_to="teams/logos/", blank=True)
    description = models.TextField("소개", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "팀"
        verbose_name_plural = "팀"
        ordering = ["age_group", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("teams:detail", kwargs={"slug": self.slug})


class Player(models.Model):
    """선수 (한 선수가 여러 팀/시즌에 소속될 수 있어 소속은 TeamMembership으로 관리)."""

    class Position(models.TextChoices):
        GK = "GK", "골키퍼"
        DF = "DF", "수비수"
        MF = "MF", "미드필더"
        FW = "FW", "공격수"

    name = models.CharField("이름", max_length=50)
    birth_year = models.PositiveIntegerField("출생 연도", null=True, blank=True)
    position = models.CharField(
        "주 포지션", max_length=2, choices=Position.choices, blank=True
    )
    squad = models.CharField(
        "구분(임시)", max_length=20, blank=True,
        help_text="대회 구분용 임시 필드 (예: 50대초, 50대말). "
                  "추후 대회별·팀별 로스터 모델로 분리 예정.",
    )
    photo = models.ImageField("사진", upload_to="players/", blank=True)
    bio = models.TextField("프로필", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "선수"
        verbose_name_plural = "선수"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("teams:player", kwargs={"pk": self.pk})


class TeamMembership(models.Model):
    """선수의 팀 소속 (시즌별 등번호 포함)."""

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="memberships",
        verbose_name="선수",
    )
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="memberships",
        verbose_name="팀",
    )
    season = models.ForeignKey(
        "competitions.Season", on_delete=models.CASCADE,
        related_name="memberships", verbose_name="시즌",
        null=True, blank=True,
    )
    jersey_number = models.PositiveIntegerField("등번호", null=True, blank=True)
    is_captain = models.BooleanField("주장", default=False)
    joined_date = models.DateField("합류일", null=True, blank=True)
    left_date = models.DateField("탈퇴일", null=True, blank=True)
    is_active = models.BooleanField("현재 활동", default=True)

    class Meta:
        verbose_name = "팀 소속"
        verbose_name_plural = "팀 소속"
        ordering = ["team", "jersey_number"]
        unique_together = [("player", "team", "season")]

    def __str__(self):
        num = f" #{self.jersey_number}" if self.jersey_number else ""
        return f"{self.player} @ {self.team}{num}"
