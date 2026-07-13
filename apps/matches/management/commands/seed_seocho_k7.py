"""2026 K7 서초구 디비전 리그 참가팀·경기 시드 명령 (멱등).

docs/seocho-k7-schedule.md 의 참가팀 6팀과 리그 공식 일정 전체(1~15번경기,
싱글 라운드로빈)를 참가팀(CompetitionEntry)·경기(Match)로 생성/갱신한다.
여러 번 실행해도 중복이 생기지 않는다(외부팀은 이름, 경기는 대진+날짜로 매칭).
홈/원정이 뒤집혀 들어간 기존 경기는 발견 시 교정한다(스코어 포함 스왑).

사용 예:
    python manage.py seed_seocho_k7 --dry-run     # 저장 없이 확인
    python manage.py seed_seocho_k7               # repo 기본 DB
    DATABASE_PATH=~/dev_data/fcmanager/db.sqlite3 python manage.py seed_seocho_k7
    # 운영: docker exec <컨테이너> python manage.py seed_seocho_k7
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.clubs.models import Club
from apps.competitions.models import Competition, CompetitionEntry
from apps.matches.models import Match, Opponent
from apps.teams.models import Team

KST = ZoneInfo("Asia/Seoul")

# 참가팀(docs 표). key: 대진표 약칭 / opponent_name: DB의 Opponent 정식 이름(없으면 생성).
# 스카이(우리 팀)는 OUR_TEAM_KEY 로 별도 처리.
OUR_TEAM_KEY = "스카이"
OPPONENTS = [
    # (약칭 key, Opponent.name, 정식 명칭 — entry 비고에 기록)
    ("HUMBLE", "HUMBLEFC", "서울중구 HUMBLE FC"),
    ("오키나와", "FC오키나와", "서울서초구 FC 오키나와"),
    ("시누쓰", "시누쓰", "서울서초구 시누쓰"),
    ("리얼", "리얼FC", "서울서초구 리얼FC"),
    ("ACI", "ACI", "서울서초구 ACI"),
]
OUR_TEAM_FULL_NAME = "서울서초구 FC 스카이축구회"

# 경기: (kickoff KST, 홈 key, 원정 key, 장소, 홈 득점, 원정 득점, 비고).
# 득점은 결과를 아는 경기만(None 이면 미입력). 비고엔 리그 공식 경기 번호.
# 리그 공식 일정 기준(홈/원정 포함) — 스카이는 4번경기(7/12)에서 원정.
MATCHES = [
    # 6/28 (일) 인재개발원
    ("2026-06-28 11:20", "ACI", "오키나와", "인재개발원", 3, 7, "1번경기"),
    ("2026-06-28 12:30", "리얼", "시누쓰", "인재개발원", 1, 1, "2번경기"),
    ("2026-06-28 13:40", "스카이", "HUMBLE", "인재개발원", 1, 1, "3번경기"),
    # 7/12 (일) 인재개발원
    ("2026-07-12 11:20", "시누쓰", "스카이", "인재개발원", 0, 2, "4번경기"),
    ("2026-07-12 12:30", "HUMBLE", "ACI", "인재개발원", None, None, "5번경기"),
    ("2026-07-12 13:40", "오키나와", "리얼", "인재개발원", None, None, "6번경기"),
    # 8/1 (토) 양재근린공원
    ("2026-08-01 13:30", "ACI", "리얼", "양재근린공원", None, None, "7번경기"),
    ("2026-08-01 14:40", "스카이", "오키나와", "양재근린공원", None, None, "8번경기"),
    ("2026-08-01 15:50", "HUMBLE", "시누쓰", "양재근린공원", None, None, "9번경기"),
    # 9/5 (토) 양재근린공원
    ("2026-09-05 13:30", "시누쓰", "오키나와", "양재근린공원", None, None, "10번경기"),
    ("2026-09-05 14:40", "리얼", "HUMBLE", "양재근린공원", None, None, "11번경기"),
    ("2026-09-05 15:30", "스카이", "ACI", "양재근린공원", None, None, "12번경기"),
    # 9/19 (토) 양재근린공원
    ("2026-09-19 13:30", "리얼", "스카이", "양재근린공원", None, None, "13번경기"),
    ("2026-09-19 14:40", "ACI", "시누쓰", "양재근린공원", None, None, "14번경기"),
    ("2026-09-19 15:50", "오키나와", "HUMBLE", "양재근린공원", None, None, "15번경기"),
]


class Command(BaseCommand):
    help = "2026 K7 서초구 리그 참가팀 6팀 + 전체 일정(1~15번경기)을 시드한다(멱등)."

    def add_arguments(self, parser):
        parser.add_argument("--club", default="fcsky", help="클럽 slug (기본 fcsky)")
        parser.add_argument("--team", default="sky-k7", help="우리 팀 slug (기본 sky-k7)")
        parser.add_argument("--competition", default="k7-seocho-2026",
                            help="대회 slug (기본 k7-seocho-2026)")
        parser.add_argument("--dry-run", action="store_true",
                            help="실제 저장 없이 처리 결과만 출력")

    def handle(self, *args, **opts):
        try:
            club = Club.objects.get(slug=opts["club"])
            team = Team.objects.get(slug=opts["team"], club=club)
            comp = Competition.objects.get(slug=opts["competition"])
        except Club.DoesNotExist:
            raise CommandError(f"클럽 slug='{opts['club']}' 없음.")
        except Team.DoesNotExist:
            raise CommandError(f"팀 slug='{opts['team']}' 없음.")
        except Competition.DoesNotExist:
            raise CommandError(f"대회 slug='{opts['competition']}' 없음.")

        with transaction.atomic():
            entries = self._seed_entries(comp, team)
            m_created, m_updated = self._seed_matches(club, comp, entries)
            if opts["dry_run"]:
                transaction.set_rollback(True)

        mode = " (DRY-RUN, 저장 안 함)" if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"완료{mode}: 대회={comp.name} | 참가팀 {len(entries)}팀 확보 | "
            f"경기 신규 {m_created}·갱신 {m_updated}"))
        self.stdout.write(
            "※ 스코어 미확보 지난 경기(7/12 5번 HUMBLE-ACI · 6번 오키나와-리얼)는 "
            "종료 상태에 스코어 비움 — 결과 확인 후 대회 상세의 '편집'에서 입력하세요.")

    # ── 참가팀 ──────────────────────────────────────────────────
    def _seed_entries(self, comp, team):
        """약칭 key → CompetitionEntry 맵을 만들며 없는 참가팀은 생성."""
        entries = {}

        entry, created = CompetitionEntry.objects.get_or_create(
            competition=comp, division=None, team=team,
            defaults={"note": OUR_TEAM_FULL_NAME})
        entries[OUR_TEAM_KEY] = entry
        self._log_entry(team.name, created)

        for key, opp_name, full_name in OPPONENTS:
            opponent, o_created = Opponent.objects.get_or_create(name=opp_name)
            if not opponent.short_name:
                opponent.short_name = key
                opponent.save(update_fields=["short_name"])
            entry, created = CompetitionEntry.objects.get_or_create(
                competition=comp, division=None, opponent=opponent,
                defaults={"note": full_name})
            entries[key] = entry
            self._log_entry(f"{opp_name}{' (외부팀 신규)' if o_created else ''}", created)
        return entries

    def _log_entry(self, name, created):
        self.stdout.write(f"  참가팀 {name}: {'등록' if created else '이미 있음'}")

    # ── 경기 ────────────────────────────────────────────────────
    def _seed_matches(self, club, comp, entries):
        now = timezone.now()
        created_n = updated_n = 0
        for dt_str, home_key, away_key, venue, h_score, a_score, note in MATCHES:
            kickoff = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
            home, away = entries[home_key], entries[away_key]
            # 같은 대진·같은 날짜의 기존 경기와 매칭(시간이 바뀌었어도 중복 생성 방지).
            match = Match.objects.filter(
                club=club, competition=comp,
                home_entry=home, away_entry=away,
                kickoff__date=kickoff.date(),
            ).first()
            # 홈/원정이 뒤집혀 들어간 기존 경기(예: 초기 시드의 7/12 스카이전) 교정 매칭.
            swapped = False
            if match is None:
                match = Match.objects.filter(
                    club=club, competition=comp,
                    home_entry=away, away_entry=home,
                    kickoff__date=kickoff.date(),
                ).first()
                swapped = match is not None
            label = f"{home_key} vs {away_key} {dt_str}"
            if match is None:
                status = (Match.Status.FINISHED if kickoff < now
                          else Match.Status.SCHEDULED)
                Match.objects.create(
                    club=club, competition=comp,
                    home_entry=home, away_entry=away,
                    stage=Match.Stage.GROUP, kickoff=kickoff, venue=venue,
                    status=status, home_score=h_score, away_score=a_score,
                    note=note,
                )
                created_n += 1
                score = f" {h_score}:{a_score}" if h_score is not None else ""
                self.stdout.write(
                    f"  경기 {label}: 생성 ({Match.Status(status).label}{score})")
            else:
                # 일정 정보 갱신 + 빈 스코어·비고 채움(수동 입력된 결과·상태는 건드리지 않음).
                changed = []
                if swapped:
                    # 홈/원정 교정: 참가팀과 기존 스코어를 함께 뒤집는다.
                    match.home_entry, match.away_entry = home, away
                    match.home_score, match.away_score = (
                        match.away_score, match.home_score)
                    changed.append("홈/원정 교정")
                if match.kickoff != kickoff:
                    match.kickoff = kickoff; changed.append("일시")
                if venue and match.venue != venue:
                    match.venue = venue; changed.append("장소")
                if (h_score is not None and match.home_score is None
                        and match.away_score is None):
                    match.home_score, match.away_score = h_score, a_score
                    match.status = Match.Status.FINISHED
                    changed.append(f"스코어 {h_score}:{a_score}")
                if note and not match.note:
                    match.note = note; changed.append("비고")
                if changed:
                    match.save()
                    updated_n += 1
                self.stdout.write(
                    f"  경기 {label}: 이미 있음"
                    f"{' → ' + '·'.join(changed) + ' 갱신' if changed else ''}")
        return created_n, updated_n
