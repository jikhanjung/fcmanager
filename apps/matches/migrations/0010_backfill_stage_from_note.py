"""기존 경기의 단계(stage)를 note 텍스트로 백필.

note 형식은 '{대회명} {라운드} — {설명}'. 라운드 판정은 '—' 앞부분만 본다
(결승 note 설명에 '준결승 승자'가 들어 있어 전체 substring 검사 시 오분류됨).
'준결승'은 '결승'을 포함하므로 준결승을 먼저 판정.
"""
from django.db import migrations


def forward(apps, schema_editor):
    Match = apps.get_model("matches", "Match")
    for m in Match.objects.all():
        head = (m.note or "").split("—")[0]
        if "준결승" in head:
            stage = "SF"
        elif "위전" in head:
            stage = "3RD"
        elif "결승" in head:
            stage = "F"
        elif "8강" in head:
            stage = "QF"
        else:
            continue  # GROUP(기본값) 유지
        if m.stage != stage:
            m.stage = stage
            m.save(update_fields=["stage"])


def backward(apps, schema_editor):
    apps.get_model("matches", "Match").objects.update(stage="GROUP")


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0009_match_stage"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
