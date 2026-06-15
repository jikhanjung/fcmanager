"""선수 명단(로스터) 일괄 입력 명령.

CSV 파일을 읽어 선수(Player)와 팀 소속(TeamMembership)을 멱등하게 생성/갱신한다.
이름으로 기존 선수를 매칭하므로 여러 번 실행해도 중복이 생기지 않는다.

CSV 컬럼 (헤더 필수):
    name      선수 이름            (필수)
    jersey    등번호               (선택, 정수)
    squad     구분/스쿼드          (선택, 예: 50대초 / 50대말)  → Player.squad
    position  포지션               (선택, GK/DF/MF/FW 또는 골키퍼/수비/미드필더/공격, 키퍼=GK)
    note      비고                 (선택)  → Player.bio

사용 예:
    python manage.py import_roster data/roster_sky50.csv --team sky-50 --season 2026
    # 팀이 없으면 생성:
    python manage.py import_roster roster.csv --team sky-50 --create-team \\
        --team-name "스카이 50대" --age-group 50
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.competitions.models import Season
from apps.teams.models import Player, Team, TeamMembership

POSITION_ALIASES = {
    "GK": "GK", "골키퍼": "GK", "키퍼": "GK",
    "DF": "DF", "수비": "DF", "수비수": "DF",
    "MF": "MF", "미드필더": "MF", "미들": "MF",
    "FW": "FW", "공격": "FW", "공격수": "FW",
}


class Command(BaseCommand):
    help = "CSV 선수 명단을 읽어 선수·팀 소속을 일괄 생성/갱신(멱등)한다."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="로스터 CSV 파일 경로")
        parser.add_argument("--team", required=True, help="대상 팀 slug")
        parser.add_argument("--season", help="시즌 연도(예: 2026). 생략 시 현재 시즌 사용")
        parser.add_argument("--create-team", action="store_true",
                            help="대상 팀이 없으면 생성")
        parser.add_argument("--team-name", help="--create-team 시 팀 이름")
        parser.add_argument("--age-group", choices=[c[0] for c in Team.AgeGroup.choices],
                            help="--create-team 시 연령대(K7/40/50)")
        parser.add_argument("--dry-run", action="store_true",
                            help="실제 저장 없이 처리 결과만 출력")

    def handle(self, *args, **opts):
        team = self._resolve_team(opts)
        season = self._resolve_season(opts.get("season"))
        rows = self._read_csv(opts["csv_path"])

        created_p = updated_p = created_m = updated_m = 0
        with transaction.atomic():
            for i, row in enumerate(rows, 1):
                name = (row.get("name") or "").strip()
                if not name:
                    self.stderr.write(f"  [{i}행] 이름 없음 → 건너뜀")
                    continue
                jersey = self._to_int(row.get("jersey"))
                squad = (row.get("squad") or "").strip()
                position = self._norm_position(row.get("position"))
                note = (row.get("note") or "").strip()

                player, p_created = Player.objects.get_or_create(name=name)
                changed = False
                if squad and player.squad != squad:
                    player.squad = squad; changed = True
                if position and player.position != position:
                    player.position = position; changed = True
                if note and player.bio != note:
                    player.bio = note; changed = True
                if not opts["dry_run"] and (p_created or changed):
                    player.save()
                created_p += int(p_created)
                updated_p += int(changed and not p_created)

                m, m_created = (
                    TeamMembership.objects.get_or_create(
                        player=player, team=team, season=season
                    )
                    if not opts["dry_run"]
                    else (TeamMembership(player=player, team=team, season=season), True)
                )
                m_changed = False
                if jersey is not None and m.jersey_number != jersey:
                    m.jersey_number = jersey; m_changed = True
                if not m.is_active:
                    m.is_active = True; m_changed = True
                if not opts["dry_run"] and (m_created or m_changed):
                    m.save()
                created_m += int(m_created)
                updated_m += int(m_changed and not m_created)

                tag = "신규" if p_created else "갱신"
                self.stdout.write(
                    f"  [{i:>2}] {name} #{jersey if jersey is not None else '-'} "
                    f"[{squad or '-'}] {position or '-'} ({tag})"
                )

            if opts["dry_run"]:
                transaction.set_rollback(True)

        mode = " (DRY-RUN, 저장 안 함)" if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"완료{mode}: 팀={team.name}, 시즌={season or '없음'} | "
            f"선수 신규 {created_p}·갱신 {updated_p} / 소속 신규 {created_m}·갱신 {updated_m}"
        ))

    # ── helpers ──────────────────────────────────────────────────
    def _resolve_team(self, opts):
        slug = opts["team"]
        try:
            return Team.objects.get(slug=slug)
        except Team.DoesNotExist:
            if not opts["create_team"]:
                raise CommandError(
                    f"팀 slug='{slug}' 없음. --create-team --team-name ... --age-group ... 로 생성하세요."
                )
            if not opts.get("team_name") or not opts.get("age_group"):
                raise CommandError("--create-team 에는 --team-name 과 --age-group 이 필요합니다.")
            team = Team.objects.create(
                slug=slug, name=opts["team_name"], age_group=opts["age_group"]
            )
            self.stdout.write(self.style.WARNING(f"팀 생성: {team.name} ({slug})"))
            return team

    def _resolve_season(self, year):
        if year:
            season, _ = Season.objects.get_or_create(
                year=int(year), defaults={"name": str(year)}
            )
            return season
        return Season.objects.filter(is_current=True).first()

    def _read_csv(self, path):
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            raise CommandError(f"파일 없음: {path}")
        if not rows:
            raise CommandError("CSV 에 데이터 행이 없습니다.")
        if "name" not in rows[0]:
            raise CommandError("CSV 헤더에 'name' 컬럼이 필요합니다.")
        return rows

    @staticmethod
    def _to_int(v):
        v = (v or "").strip()
        return int(v) if v.isdigit() else None

    @staticmethod
    def _norm_position(v):
        return POSITION_ALIASES.get((v or "").strip(), "")
