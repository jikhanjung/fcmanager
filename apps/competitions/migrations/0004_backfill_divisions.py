"""기존 데이터를 부문(Division) 구조로 백필.

- 여러 연령대 팀이 출전한 대회(예: 구청장기)에만 부문 생성. 단일 연령대 대회(리그 등)는
  부문 없이 둔다.
- 경기·출전·명단(TeamMembership)의 division/competition을 팀 연령대에 맞춰 채운다.
- 명단은 '가장 최근 대회' 중 해당 연령 부문이 있는 대회로 귀속(팀 페이지 표시 기준).
"""
from django.db import migrations

# Team.AgeGroup -> Division.AgeGroup
AGE_MAP = {"K7": "2030", "40": "40", "50": "50"}


def forward(apps, schema_editor):
    Team = apps.get_model("teams", "Team")
    Competition = apps.get_model("competitions", "Competition")
    Division = apps.get_model("competitions", "Division")
    CompetitionEntry = apps.get_model("competitions", "CompetitionEntry")
    TeamMembership = apps.get_model("teams", "TeamMembership")
    Match = apps.get_model("matches", "Match")

    # 1) 다중 연령대 출전 대회에 부문 생성.
    for comp in Competition.objects.all():
        ages = set()
        for e in CompetitionEntry.objects.filter(competition=comp).select_related("team"):
            ages.add(AGE_MAP.get(e.team.age_group, "OPEN"))
        if len(ages) > 1:
            for ag in ages:
                Division.objects.get_or_create(competition=comp, age_group=ag)

    def div_for(comp_id, team_age):
        ag = AGE_MAP.get(team_age, "OPEN")
        return Division.objects.filter(competition_id=comp_id, age_group=ag).first()

    # 2) 출전(Entry) division 백필.
    for e in CompetitionEntry.objects.select_related("team"):
        e.division = div_for(e.competition_id, e.team.age_group)
        e.save(update_fields=["division"])

    # 3) 경기(Match) division 백필.
    for m in Match.objects.select_related("our_team"):
        m.division = div_for(m.competition_id, m.our_team.age_group)
        m.save(update_fields=["division"])

    # 4) 명단(TeamMembership) competition/division 백필.
    #    팀별로 '부문이 있는 최근 대회'를 우선 귀속, 없으면 최근 대회(부문 없음).
    for team in Team.objects.all():
        ag = AGE_MAP.get(team.age_group, "OPEN")
        entries = list(
            CompetitionEntry.objects.filter(team=team)
            .select_related("competition")
            .order_by("-competition__year", "-competition_id")
        )
        target_comp = target_div = None
        for e in entries:
            div = Division.objects.filter(
                competition=e.competition, age_group=ag).first()
            if div:
                target_comp, target_div = e.competition, div
                break
        if target_comp is None and entries:
            target_comp = entries[0].competition
        if target_comp is not None:
            TeamMembership.objects.filter(team=team).update(
                competition=target_comp, division=target_div)


def backward(apps, schema_editor):
    # 부문/연결 데이터 제거(되돌리기).
    apps.get_model("teams", "TeamMembership").objects.update(
        competition=None, division=None)
    apps.get_model("matches", "Match").objects.update(division=None)
    apps.get_model("competitions", "CompetitionEntry").objects.update(division=None)
    apps.get_model("competitions", "Division").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("competitions", "0003_alter_competition_options_and_more"),
        ("matches", "0007_match_division"),
        ("teams", "0004_alter_teammembership_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
