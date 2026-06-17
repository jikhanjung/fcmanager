"""참가팀(Entry) 전면 개편 — Match 를 home/away entry 쌍으로, OpponentMatch 흡수, Opponent 공유화.

한 마이그레이션 안에서 [신규 필드 추가] → [RunPython backfill] → [구 필드/모델 제거] 순으로
수행한다(RunPython 시점엔 신·구 필드와 OpponentMatch 가 모두 존재).
"""
import django.db.models.deletion
from django.db import migrations, models


# Team.AgeGroup → Division.AgeGroup
AGE2DIV = {"K7": "2030", "40": "40", "50": "50"}


def backfill(apps, schema_editor):
    Match = apps.get_model("matches", "Match")
    OpponentMatch = apps.get_model("matches", "OpponentMatch")
    Division = apps.get_model("competitions", "Division")
    Entry = apps.get_model("competitions", "CompetitionEntry")

    def team_entry(comp_id, div_id, team_id):
        return Entry.objects.get_or_create(
            competition_id=comp_id, division_id=div_id, team_id=team_id)[0]

    def opp_entry(comp_id, div_id, opp_id):
        return Entry.objects.get_or_create(
            competition_id=comp_id, division_id=div_id, opponent_id=opp_id)[0]

    # 1) 기존 Match: our_team/opponent → home/away entry (is_home 으로 배정)
    for m in Match.objects.all():
        our = team_entry(m.competition_id, m.division_id, m.our_team_id)
        opp = opp_entry(m.competition_id, m.division_id, m.opponent_id)
        if m.is_home:
            m.home_entry, m.away_entry = our, opp
            m.home_score, m.away_score = m.our_score, m.opponent_score
        else:
            m.home_entry, m.away_entry = opp, our
            m.home_score, m.away_score = m.opponent_score, m.our_score
        m.save(update_fields=["home_entry", "away_entry", "home_score", "away_score"])

    # 2) OpponentMatch → Match (상대팀 간 경기). age_group → division 매핑.
    for om in OpponentMatch.objects.all():
        div = Division.objects.get_or_create(
            competition_id=om.competition_id,
            age_group=AGE2DIV.get(om.age_group, "OPEN"))[0]
        he = opp_entry(om.competition_id, div.id, om.home_id)
        ae = opp_entry(om.competition_id, div.id, om.away_id)
        scored = om.home_score is not None and om.away_score is not None
        Match.objects.create(
            club_id=om.club_id, competition_id=om.competition_id, division_id=div.id,
            home_entry=he, away_entry=ae, home_score=om.home_score, away_score=om.away_score,
            stage=om.stage, kickoff=om.kickoff, venue="",
            status="FINISHED" if scored else "SCHEDULED", note=om.note or "",
        )


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0007_alter_competitionentry_options_and_more'),
        ('matches', '0012_match_club_opponent_club_opponentmatch_club_and_more'),
    ]

    operations = [
        # ── 신규 필드/구조 ──
        migrations.AlterField(
            model_name='match', name='opponent_feeder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='feeds_opponent_of', to='matches.match', verbose_name='상대 진출 경기'),
        ),
        migrations.AlterModelOptions(
            name='opponent',
            options={'ordering': ['name'], 'verbose_name': '외부팀', 'verbose_name_plural': '외부팀'},
        ),
        migrations.AlterUniqueTogether(name='opponent', unique_together=set()),
        migrations.AddField(
            model_name='match', name='home_entry',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='home_matches', to='competitions.competitionentry', verbose_name='홈 참가팀'),
        ),
        migrations.AddField(
            model_name='match', name='away_entry',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='away_matches', to='competitions.competitionentry', verbose_name='원정 참가팀'),
        ),
        migrations.AddField(
            model_name='match', name='home_score',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='홈 득점'),
        ),
        migrations.AddField(
            model_name='match', name='away_score',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='원정 득점'),
        ),
        migrations.AlterField(
            model_name='match', name='kickoff',
            field=models.DateTimeField(blank=True, null=True, verbose_name='경기 일시'),
        ),
        # 구 필드를 잠시 nullable 로(OM→Match 생성 시 our_team/opponent 없이 만들기 위함)
        migrations.AlterField(
            model_name='match', name='our_team',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='matches', to='teams.team', verbose_name='우리 팀'),
        ),
        migrations.AlterField(
            model_name='match', name='opponent',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='matches', to='matches.opponent', verbose_name='상대팀'),
        ),
        migrations.AlterField(
            model_name='opponent', name='name',
            field=models.CharField(max_length=120, unique=True, verbose_name='팀명'),
        ),
        migrations.RemoveField(model_name='opponent', name='club'),

        # ── 데이터 backfill ──
        migrations.RunPython(backfill, migrations.RunPython.noop),

        # ── 구 필드/모델 제거 ──
        migrations.RemoveField(model_name='match', name='is_home'),
        migrations.RemoveField(model_name='match', name='opponent'),
        migrations.RemoveField(model_name='match', name='opponent_score'),
        migrations.RemoveField(model_name='match', name='our_score'),
        migrations.RemoveField(model_name='match', name='our_team'),
        migrations.DeleteModel(name='OpponentMatch'),
    ]
