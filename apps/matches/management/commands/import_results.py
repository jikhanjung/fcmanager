"""경기 결과 `.md`(경기당 1파일) → DB 반영 관리 명령 (devlog P06 §4).

    python manage.py import_results <file.md> [<file2.md> …] [--apply] [--create]

- 기본 = dry-run: 파싱·매칭·계획된 변경(before→after)만 출력, 쓰기 없음.
- --apply : transaction.atomic 안에서 반영.
- --create: 매칭 실패(0건) 시 참가팀 name 으로 entry 해석 후 픽스처(Match) 생성 허용.

`.md` 포맷: 프론트매터(competition/date/kickoff/venue/home/away/score/half_minutes/
status/stage) + 선택적 `## 이벤트` 표(| 분 | 팀 | 유형 | 선수 | 도움 |).
이벤트 섹션이 있으면 그 경기의 기록성 이벤트(득점/도움/자책/경고/퇴장/교체)의
**단일 소스**가 되어 삭제 후 재구성(멱등). 섹션이 없으면 스코어만 만진다.
"""
from dataclasses import dataclass, field
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.competitions.models import Competition
from apps.matches.models import Match, MatchEvent

# 파일 유형(한글) → EventType. 재구성 대상(기록성) 이벤트만 다룬다(PSO 제외).
_TYPE_MAP = {
    "득점": MatchEvent.EventType.GOAL,
    "도움": MatchEvent.EventType.ASSIST,
    "자책골": MatchEvent.EventType.OWN_GOAL,
    "경고": MatchEvent.EventType.YELLOW,
    "퇴장": MatchEvent.EventType.RED,
    "교체IN": MatchEvent.EventType.SUB_IN,
    "교체OUT": MatchEvent.EventType.SUB_OUT,
}
# 이벤트 섹션이 재구성(삭제 후 재생성)하는 대상 유형. 승부차기(PSO)는 건드리지 않는다.
_MANAGED_TYPES = set(_TYPE_MAP.values())
# 득점자 이름이 미상/공란일 때로 취급할 토큰.
_UNKNOWN_NAMES = {"", "-", "(미상)", "미상"}


@dataclass
class ParsedEvent:
    minute: int | None
    team: str          # 파일에 적힌 팀명(home/away 중 하나)
    etype: str         # EventType 값
    name: str          # 선수명(미상/공란이면 "")
    assist_name: str   # 도움 선수명(없으면 "")
    raw_type: str      # 원문 유형(오류 메시지용)


@dataclass
class ParsedFile:
    path: str
    meta: dict
    events: list = field(default_factory=list)   # ParsedEvent
    has_event_section: bool = False


def _strip_comment(value):
    """YAML 인라인 주석(' #...') 제거 + 양끝 따옴표 제거."""
    # 공백+# 이후를 주석으로 절단(값 안의 #(예: 색상)은 흔치 않으므로 단순 규칙).
    idx = value.find(" #")
    if idx != -1:
        value = value[:idx]
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def _parse_minute(cell):
    digits = "".join(ch for ch in cell if ch.isdigit())
    return int(digits) if digits else None


def parse_md(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.splitlines()

    # ── 프론트매터: 첫 '---' ~ 다음 '---' ──
    if not lines or lines[0].strip() != "---":
        raise CommandError(f"{path}: 프론트매터(---)로 시작해야 합니다.")
    meta = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = _strip_comment(val)
    if i >= len(lines):
        raise CommandError(f"{path}: 프론트매터 종료(---)가 없습니다.")
    i += 1  # 닫는 '---' 다음으로

    pf = ParsedFile(path=path, meta=meta)

    # ── 이벤트 섹션: '## 이벤트' 이후의 마크다운 표 ──
    in_events = False
    for line in lines[i:]:
        stripped = line.strip()
        if stripped.startswith("##"):
            in_events = stripped.replace(" ", "").startswith("##이벤트")
            if in_events:
                pf.has_event_section = True
            continue
        if not in_events:
            continue
        if not stripped.startswith("|"):
            if stripped == "":
                continue
            break  # 표 종료
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        joined = "".join(cells)
        if set(joined) <= set("-: "):     # 구분선 |---|
            continue
        if "분" in cells and "유형" in cells:   # 헤더행
            continue
        if len(cells) < 3:
            continue
        minute = _parse_minute(cells[0])
        team = cells[1]
        raw_type = cells[2].replace(" ", "")
        name = cells[3] if len(cells) > 3 else ""
        assist_name = cells[4] if len(cells) > 4 else ""
        if name in _UNKNOWN_NAMES:
            name = ""
        if assist_name in _UNKNOWN_NAMES:
            assist_name = ""
        pf.events.append(ParsedEvent(
            minute=minute, team=team, etype=_TYPE_MAP.get(raw_type),
            name=name, assist_name=assist_name, raw_type=cells[2],
        ))
    return pf


class Command(BaseCommand):
    help = "경기 결과 .md 파일(경기당 1개)을 파싱·매칭해 스코어·이벤트를 반영한다."

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+", help="경기 결과 .md 파일 경로들")
        parser.add_argument("--apply", action="store_true",
                            help="실제 반영(기본은 dry-run)")
        parser.add_argument("--create", action="store_true",
                            help="매칭 실패 시 참가팀 name 으로 픽스처(Match) 생성 허용")

    def handle(self, *args, **opts):
        self.apply = opts["apply"]
        self.create = opts["create"]
        files = opts["files"]

        mode = "APPLY" if self.apply else "DRY-RUN"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"import_results [{mode}] — {len(files)}개 파일"))

        if self.apply:
            with transaction.atomic():
                for path in files:
                    self._process(path)
        else:
            for path in files:
                self._process(path)

        if not self.apply:
            self.stdout.write(self.style.WARNING(
                "\n※ dry-run 입니다. 실제 반영하려면 --apply 를 붙이세요."))

    # ── 파일 1개 처리 ──
    def _process(self, path):
        self.stdout.write(f"\n── {path}")
        pf = parse_md(path)
        m = pf.meta
        for req in ("competition", "date", "home", "away", "score"):
            if not m.get(req):
                raise CommandError(f"{path}: 필수 프론트매터 '{req}' 누락")

        comp = self._resolve_competition(m["competition"], path)
        date = self._parse_date(m["date"], path)
        match = self._match_or_create(comp, date, m, path)

        self._apply_score(match, m, path)
        if pf.has_event_section:
            self._sync_events(match, pf)
        else:
            self.stdout.write("  이벤트 섹션 없음 → 이벤트는 손대지 않음(스코어만).")

    def _resolve_competition(self, slug, path):
        qs = list(Competition.objects.filter(slug=slug))
        if not qs:
            raise CommandError(f"{path}: 대회 슬러그 '{slug}' 없음")
        if len(qs) > 1:
            raise CommandError(f"{path}: 대회 슬러그 '{slug}' 가 {len(qs)}건(모호)")
        return qs[0]

    def _parse_date(self, raw, path):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"{path}: date '{raw}' 형식 오류(YYYY-MM-DD)")

    def _kickoff_dt(self, date, kickoff_str):
        """date(+kickoff 'HH:MM')를 KST aware datetime 으로. kickoff 없으면 None."""
        if not kickoff_str:
            return None
        try:
            t = datetime.strptime(kickoff_str, "%H:%M").time()
        except ValueError:
            return None
        naive = datetime.combine(date, t)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def _match_or_create(self, comp, date, m, path):
        home, away = m["home"], m["away"]
        candidates = []
        qs = Match.objects.filter(competition=comp).select_related(
            "home_entry__team", "home_entry__opponent",
            "away_entry__team", "away_entry__opponent", "club")
        for mt in qs:
            if not mt.kickoff:
                continue
            if timezone.localtime(mt.kickoff).date() != date:
                continue
            if mt.home_entry and mt.away_entry \
                    and mt.home_entry.name == home and mt.away_entry.name == away:
                candidates.append(mt)
        if len(candidates) == 1:
            self.stdout.write(f"  매칭: Match #{candidates[0].pk} ({home} vs {away})")
            return candidates[0]
        if len(candidates) > 1:
            raise CommandError(
                f"{path}: {date} {home} vs {away} 매칭 {len(candidates)}건(수동 확인)")
        # 0건
        if not self.create:
            raise CommandError(
                f"{path}: {date} {home} vs {away} 매칭 실패. "
                f"픽스처 생성하려면 --create")
        return self._create_match(comp, date, m, path)

    def _create_match(self, comp, date, m, path):
        home_e = self._resolve_entry(comp, m["home"], path)
        away_e = self._resolve_entry(comp, m["away"], path)
        club_id = home_e.club_id or away_e.club_id  # 우리 entry 쪽에서 유도
        if club_id is None:
            raise CommandError(
                f"{path}: --create 상대팀 간 경기의 club 을 유도할 수 없음")
        kickoff = self._kickoff_dt(date, m.get("kickoff")) \
            or timezone.make_aware(datetime.combine(date, datetime.min.time()))
        match = Match(
            club_id=club_id, competition=comp,
            home_entry=home_e, away_entry=away_e, kickoff=kickoff,
        )
        self.stdout.write(self.style.SUCCESS(
            f"  [생성] Match {m['home']} vs {m['away']} @ {date}"))
        if self.apply:
            match.save()
        return match

    def _resolve_entry(self, comp, name, path):
        for e in comp.entries.select_related("team", "opponent").all():
            if e.name == name:
                return e
        raise CommandError(f"{path}: 대회에 참가팀 '{name}' entry 없음(--create 대상 아님)")

    def _apply_score(self, match, m, path):
        try:
            hs, _, as_ = m["score"].partition("-")
            home_score, away_score = int(hs.strip()), int(as_.strip())
        except (ValueError, AttributeError):
            raise CommandError(f"{path}: score '{m.get('score')}' 형식 오류(예: 4-2)")

        before = (match.home_score, match.away_score, match.status)
        match.home_score = home_score
        match.away_score = away_score
        match.status = m.get("status") or Match.Status.FINISHED
        if m.get("stage"):
            match.stage = m["stage"]
        if m.get("venue"):
            match.venue = m["venue"]
        kickoff = self._kickoff_dt(self._parse_date(m["date"], path), m.get("kickoff"))
        if kickoff:
            match.kickoff = kickoff
        after = (match.home_score, match.away_score, match.status)
        self.stdout.write(
            f"  스코어: {before[0]}-{before[1]}({before[2]}) → "
            f"{after[0]}-{after[1]}({after[2]})")
        if self.apply:
            match.save()

    def _sync_events(self, match, pf):
        our_entry = match.our_entry
        our_name = our_entry.name if our_entry else None
        home_name = match.home_entry.name
        away_name = match.away_entry.name
        roster = self._roster(match) if our_entry else {}

        # 기존 기록성 이벤트 수(삭제 대상).
        old_n = match.events.filter(event_type__in=_MANAGED_TYPES).count()

        planned = []      # (ParsedEvent, side, is_our)
        warnings = []
        for ev in pf.events:
            if ev.etype is None:
                raise CommandError(
                    f"{pf.path}: 알 수 없는 이벤트 유형 '{ev.raw_type}'")
            if ev.team == home_name:
                side = MatchEvent.Side.HOME
            elif ev.team == away_name:
                side = MatchEvent.Side.AWAY
            else:
                raise CommandError(
                    f"{pf.path}: 이벤트 팀 '{ev.team}' 이 home/away 와 불일치")
            is_our = our_name is not None and ev.team == our_name
            if is_our and ev.name and ev.name not in roster:
                warnings.append(f"미해결 선수 '{ev.name}'({ev.team}) → player=null")
            if is_our and ev.assist_name and ev.assist_name not in roster:
                warnings.append(
                    f"미해결 도움 선수 '{ev.assist_name}'({ev.team}) → player=null")
            planned.append((ev, side, is_our))

        # 결정적 정렬(멱등): 분(없으면 큰 값) → side → 유형 → 이름.
        planned.sort(key=lambda t: (
            t[0].minute if t[0].minute is not None else 9999,
            t[1], t[0].etype, t[0].name))

        self.stdout.write(
            f"  이벤트: 기존 {old_n}건 삭제 → {len(planned)}건 재구성")
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"    ⚠ {w}"))

        if not self.apply:
            return

        match.events.filter(event_type__in=_MANAGED_TYPES).delete()
        half_minutes = _parse_minute(pf.meta.get("half_minutes", "")) or None
        for ev, side, is_our in planned:
            half = None
            if ev.minute is not None and half_minutes:
                half = 1 if ev.minute <= half_minutes else 2
            player = roster.get(ev.name) if is_our else None
            description = "" if player else ev.name
            obj = MatchEvent.objects.create(
                match=match, event_type=ev.etype, side=side,
                player=player, minute=ev.minute, half=half,
                description=description,
            )
            # 득점 행에 도움이 있으면 ASSIST 이벤트를 연결 생성.
            if ev.etype == MatchEvent.EventType.GOAL and ev.assist_name:
                a_player = roster.get(ev.assist_name) if is_our else None
                MatchEvent.objects.create(
                    match=match, event_type=MatchEvent.EventType.ASSIST,
                    side=side, player=a_player, minute=ev.minute, half=half,
                    description="" if a_player else ev.assist_name, goal=obj,
                )

    def _roster(self, match):
        """우리 팀 로스터: {선수명: Player}. 동명이인은 먼저 조회된 것."""
        from apps.teams.models import Player
        players = Player.objects.filter(memberships__team=match.our_team).distinct()
        roster = {}
        for p in players:
            roster.setdefault(p.name, p)
        return roster
