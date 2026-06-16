"""중복 선수(Player) 레코드 병합 — 멤버(사람) 마스터 정규화 (멱등).

같은 사람이 여러 팀에 등록되며 별도 Player로 중복 생성된 경우가 있어
(예: K7 명단의 선수를 40대 명단에 다시 새로 만든 케이스), 이름이 같은
Player들을 **하나의 정본(canonical)으로 병합**해 Player 테이블을 "멤버 마스터"로
정규화한다. 이후 팀원 추가는 정본 Player를 골라 TeamMembership만 추가하면 된다.

병합 규칙(이름이 정확히 같은 Player 묶음마다):
  - 정본 = pk가 가장 작은 레코드(대개 먼저 만든, 더 완전한 레코드).
  - 스칼라 필드(birth_year/position/squad/photo/bio): 정본이 비어 있으면 중복에서 채움(union).
  - 참조 이동: MatchEvent·MatchLineup·TeamMembership을 정본으로 재지정.
    - TeamMembership·MatchLineup은 (정본, 팀/경기) 중복이면 정본 것 유지하고 중복 것 삭제.
  - 정본·중복의 같은 스칼라 필드가 **서로 다른 값으로 충돌**하면(다른 사람일 수 있음)
    그 묶음은 병합하지 않고 경고만 출력(안전장치).
  - 병합 후 중복 레코드 삭제. 재실행 시 더 병합할 게 없으면 무변경(멱등).

사용:
    python manage.py dedupe_members            # 실제 병합
    python manage.py dedupe_members --dry-run   # 미리보기(저장 안 함)
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.matches.models import MatchEvent, MatchLineup
from apps.teams.models import Player, TeamMembership

# union 대상 스칼라 필드 (이미지/문자/숫자 필드 모두 빈 값 판정 동일하게 처리)
MERGE_FIELDS = ["birth_year", "position", "squad", "photo", "bio"]


def _empty(val):
    return val in (None, "", 0)


class Command(BaseCommand):
    help = "이름이 같은 중복 선수(Player)를 정본 하나로 병합한다(멱등)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="실제 저장 없이 병합 계획만 출력")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        dup_names = list(
            Player.objects.values("name")
            .annotate(n=Count("id")).filter(n__gt=1)
            .order_by("name").values_list("name", flat=True)
        )
        if not dup_names:
            self.stdout.write(self.style.SUCCESS("중복 이름 없음 — 병합할 것이 없습니다."))
            return

        merged = skipped = 0
        with transaction.atomic():
            for name in dup_names:
                group = list(Player.objects.filter(name=name).order_by("pk"))
                canon, dups = group[0], group[1:]

                conflict = self._conflict_field(canon, dups)
                if conflict:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(
                        f"  [건너뜀] '{name}' — 필드 '{conflict}' 값 충돌(다른 사람일 수 있음). "
                        f"수동 확인 필요. pk={[p.pk for p in group]}"))
                    continue

                for dup in dups:
                    dup_pk = dup.pk
                    self._merge_into(canon, dup)
                    merged += 1
                    self.stdout.write(
                        f"  [병합] '{name}' #{dup_pk} → #{canon.pk}")
                canon.save()

            if dry:
                self.stdout.write(self.style.WARNING("\n--dry-run: 변경사항을 롤백합니다."))
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"완료: {merged}건 병합 / {skipped}개 묶음 건너뜀. "
            f"남은 Player {Player.objects.count()}명."))

    def _conflict_field(self, canon, dups):
        """정본과 중복이 같은 스칼라 필드를 서로 다른 비어있지않은 값으로 가지면 그 필드명 반환."""
        for f in MERGE_FIELDS:
            cv = getattr(canon, f)
            if _empty(cv):
                continue
            for dup in dups:
                dv = getattr(dup, f)
                if not _empty(dv) and str(dv) != str(cv):
                    return f
        return None

    def _merge_into(self, canon, dup):
        # 1) 정본이 비어있는 필드를 중복 값으로 채움(union).
        for f in MERGE_FIELDS:
            if _empty(getattr(canon, f)) and not _empty(getattr(dup, f)):
                setattr(canon, f, getattr(dup, f))

        # 2) 경기 이벤트/라인업/소속을 정본으로 이동.
        MatchEvent.objects.filter(player=dup).update(player=canon)

        for ln in MatchLineup.objects.filter(player=dup):
            if MatchLineup.objects.filter(match=ln.match, player=canon).exists():
                ln.delete()            # 정본이 이미 그 경기 명단에 있음 → 중복 제거
            else:
                ln.player = canon
                ln.save(update_fields=["player"])

        for m in TeamMembership.objects.filter(player=dup):
            exists = TeamMembership.objects.filter(
                player=canon, team=m.team, competition=m.competition).first()
            if exists:
                # (정본,팀,대회) 중복: 정본 소속에 등번호가 비었으면 중복 것에서 채움.
                if exists.jersey_number is None and m.jersey_number is not None:
                    exists.jersey_number = m.jersey_number
                    exists.save(update_fields=["jersey_number"])
                m.delete()
            else:
                m.player = canon
                m.save(update_fields=["player"])

        # 3) 중복 레코드 삭제.
        dup.delete()
