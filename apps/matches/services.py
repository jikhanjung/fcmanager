"""경기 집계 헬퍼.

통계 대시보드(stats)와 연도 아카이브(year_detail)가 공유하는 집계 로직을 모은다.
연도(Competition.year) 필터를 인자로 받아 동일한 결과 구조를 반환한다.
"""

from django.db.models import Count

from .models import Match, MatchEvent

# 부문(연령대) 표시 순서.
AGE_ORDER = {"K7": 0, "40": 1, "50": 2}


_MATCH_ENTRY_SELECT = (
    "club", "competition",
    "home_entry__team", "home_entry__opponent",
    "away_entry__team", "away_entry__opponent",
)


def finished_matches(year=None, club=None):
    """점수가 입력된 종료 경기 쿼리셋. year·club 으로 한정 가능."""
    qs = Match.objects.filter(
        status=Match.Status.FINISHED,
        home_score__isnull=False,
        away_score__isnull=False,
    )
    if club is not None:
        qs = qs.filter(club=club)
    if year and str(year).isdigit():
        qs = qs.filter(competition__year=year)
    return qs.select_related(*_MATCH_ENTRY_SELECT)


def club_record(matches):
    """팀별 전적 리스트와 클럽 합계 dict를 반환(우리 팀이 참가한 경기만).

    반환: (teams, club)
      teams — 부문 순으로 정렬된 팀별 전적 dict 리스트
      club  — 전 팀 합산 전적 dict
    """
    team_rows = {}
    for m in matches:
        team = m.our_team  # 호환 프로퍼티: 우리 팀 entry 의 Team (없으면 None=상대팀 간 경기)
        if team is None:
            continue
        r = team_rows.setdefault(
            team.id,
            {"team": team, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0},
        )
        r["p"] += 1
        r["gf"] += m.our_score
        r["ga"] += m.opponent_score
        result = m.result
        if result == "W":
            r["w"] += 1
        elif result == "L":
            r["l"] += 1
        else:
            r["d"] += 1

    club = {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}
    teams = []
    for r in team_rows.values():
        r["gd"] = r["gf"] - r["ga"]
        r["pts"] = r["w"] * 3 + r["d"]
        r["winrate"] = round(r["w"] / r["p"] * 100) if r["p"] else 0
        for k in ("p", "w", "d", "l", "gf", "ga"):
            club[k] += r[k]
        teams.append(r)
    teams.sort(key=lambda x: AGE_ORDER.get(x["team"].age_group, 9))
    club["gd"] = club["gf"] - club["ga"]
    club["winrate"] = round(club["w"] / club["p"] * 100) if club["p"] else 0
    return teams, club


def our_events(year=None, club=None):
    """우리 팀(선수 지정) 이벤트 쿼리셋. year·club 으로 한정 가능."""
    ev = MatchEvent.objects.filter(
        side=MatchEvent.Side.OUR, player__isnull=False
    )
    if club is not None:
        ev = ev.filter(match__club=club)
    if year and str(year).isdigit():
        ev = ev.filter(match__competition__year=year)
    return ev


def event_ranking(events, event_type, limit=None):
    """이벤트 종류별 선수 순위 리스트(player_id·player__name·n). limit이 있으면 상위 N명."""
    qs = (
        events.filter(event_type=event_type)
        .values("player_id", "player__name")
        .annotate(n=Count("id"))
        .order_by("-n", "player__name")
    )
    if limit:
        qs = qs[:limit]
    return list(qs)


def build_timeline(events):
    """타임라인 항목 구성. 득점과 그 도움을 한 줄로 묶는다.

    각 항목은 {"event": 주 이벤트, "assist": 도움 이벤트 또는 None}.
    도움은 명시적 링크(MatchEvent.goal)로 해당 득점에 정확히 연결한다.
    링크가 없는 과거 데이터는 같은 팀의 도움을 순서대로 보수적으로 페어링한다.
    """
    GOAL = MatchEvent.EventType.GOAL
    ASSIST = MatchEvent.EventType.ASSIST
    assist_by_goal = {e.goal_id: e for e in events if e.event_type == ASSIST and e.goal_id}
    used = set()
    timeline = []
    for e in events:
        if e.id in used:
            continue
        if e.event_type == GOAL:
            assist = assist_by_goal.get(e.id)
            if assist is None:  # 레거시(링크 없는 과거 데이터) 폴백: 같은 팀 도움을 순서대로 소비
                assist = next(
                    (a for a in events
                     if a.event_type == ASSIST and not a.goal_id and a.id not in used
                     and a.side == e.side),
                    None,
                )
            if assist:
                used.add(assist.id)
            timeline.append({"event": e, "assist": assist})
        elif e.event_type == ASSIST:
            if e.goal_id:        # 자기 득점과 함께 표시 → 단독으로 내지 않음
                used.add(e.id)
                continue
            timeline.append({"event": e, "assist": None})  # 링크 없는 단독 도움
        else:
            timeline.append({"event": e, "assist": None})
        used.add(e.id)
    return timeline


def recompute_score(match):
    """이벤트 집계로 경기 점수를 재계산해 저장한다(중계 콘솔 전용).

    우리 점수 = 우리팀 GOAL + 상대팀 OWN_GOAL,
    상대 점수 = 상대팀 GOAL + 우리팀 OWN_GOAL.
    """
    GOAL = MatchEvent.EventType.GOAL
    OWN_GOAL = MatchEvent.EventType.OWN_GOAL
    OUR = MatchEvent.Side.OUR
    OPP = MatchEvent.Side.OPPONENT
    evs = list(match.events.values("event_type", "side"))

    def count(etype, side):
        return sum(1 for e in evs if e["event_type"] == etype and e["side"] == side)

    our_score = count(GOAL, OUR) + count(OWN_GOAL, OPP)
    opp_score = count(GOAL, OPP) + count(OWN_GOAL, OUR)
    our = match.our_entry
    if our is None:  # 우리 팀 경기가 아니면 이벤트 기반 재집계 불가
        return
    if our.id == match.home_entry_id:
        match.home_score, match.away_score = our_score, opp_score
    else:
        match.home_score, match.away_score = opp_score, our_score
    match.save(update_fields=["home_score", "away_score", "updated_at"])


def serialize_timeline(match):
    """공개 폴링용 타임라인 직렬화. build_timeline 결과를 단순 dict 리스트로."""
    events = list(match.events.select_related("player").order_by("minute", "id"))
    items = []
    for item in build_timeline(events):
        e = item["event"]
        assist = item["assist"]
        items.append({
            "id": e.id,
            "minute": e.minute,
            "half": e.half,
            "side": e.side,
            "type": e.event_type,
            "type_display": e.get_event_type_display(),
            "player": e.player.name if e.player else "",
            "side_display": e.get_side_display(),
            "assist": (assist.player.name if assist and assist.player else
                       (assist.get_side_display() if assist else "")),
            "description": e.description,
        })
    return items
