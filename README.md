# FCManager

축구 클럽의 선수단·대회·일정·결과·입상 내역을 관리·공개하고 실시간 중계까지 제공하는
**멀티테넌트 SaaS**(Django). 클럽별로 슬러그 경로(`/<club-slug>/`)로 서비스되며,
첫 클럽은 FC Sky(`/fcsky/`). 운영 도메인은 `fcmanager.app`.

## 기술 스택
- Django 5.1, Python 3.12 / Django Template + Bootstrap 5
- 실시간 중계: Django Channels
- DB: SQLite (개발·운영 — 볼륨 영속화. PostgreSQL 전환은 보류)
- 배포: Docker(`honestjung/fcmanager`) + Gunicorn + nginx. 절차는 `docs/operation_manual/` 참고.

## 프로젝트 구조
```
config/              프로젝트 설정 (settings, urls)
apps/clubs/          테넌트(Club, ClubMembership) + 라우팅 미들웨어·권한
apps/teams/          팀, 선수, 팀 소속(TeamMembership)
apps/competitions/   대회(Competition)·부문(Division)·참가팀(CompetitionEntry)·입상(Award)
apps/matches/        상대팀, 경기(Match), 경기 이벤트(MatchEvent), 중계
apps/notices/        공지
apps/gallery/        갤러리
templates/           Bootstrap 기반 템플릿
```

## 개발 환경 실행
```bash
source ~/venv/fcmanager/bin/activate     # 가상환경
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
- 사이트: http://127.0.0.1:8000/
- 관리자: http://127.0.0.1:8000/admin/  (계정은 `createsuperuser` 또는 `.env` 의 `DJANGO_SUPERUSER_PASSWORD` 로 생성)

## 도메인 구조
- **대회(Competition)** 는 연도·종류(리그/토너먼트/컵)별로 만들고, 그 아래 **부문(Division,
  연령대 20-30대/40대/50대/오픈)** 을 둔다. 경기 시간 등은 부문이 대회 기본값을 오버라이드.
- **참가팀(CompetitionEntry)** 이 대회·부문에 우리 팀(Team) 또는 상대팀(Opponent)을 등록하고,
  **경기(Match)** 는 home/away 양쪽을 참가팀으로 연결한다.
- 선수의 팀 소속·등번호·주장은 **TeamMembership**(선수↔팀↔대회)에 둔다(대회 단위 명단).
- **MatchEvent**(득점/카드/교체)는 경기 기록이자 실시간 중계의 기반.

## 데이터 입력
대부분 **운영진(클럽 staff) 웹 화면**에서 입력한다(`/admin/` 직접 입력은 보조 수단):
- 대회·부문: `/manage/competitions/` (대회 생성·수정 시 부문 체크박스로 함께 구성)
- 팀: `/teams/add/` · 팀 명단(소속·등번호·주장): `/teams/<slug>/players/…`
- 선수 마스터: `/manage/players/` (검색·soft delete·복구)
- 경기 결과·이벤트·영상: `/matches/<pk>/edit/` · 실시간 중계는 별도 콘솔
- 클럽 생성: `/clubs/new/`

아직 **Django 관리자(/admin/)** 로만 입력하는 것: 참가팀(CompetitionEntry)·입상(Award)·
상대팀(Opponent)·출전명단(MatchLineup)·클럽 멤버십(ClubMembership)·부문 시간 오버라이드.

## 로드맵
- [x] **Phase 1** — 모델 + 관리자 입력 + 기본 페이지
- [x] **Phase 2** — 공개 조회 페이지(선수단/일정·결과/순위/명예의 전당)
- [x] **Phase 3** — 회원/권한, 공지·갤러리, 멀티테넌트 SaaS 전환
- [x] **Phase 4** — 실시간 중계(Django Channels — 중계 콘솔·연장전·승부차기·시청자 진행시계)
- [x] **Phase 5** — Docker 배포 (`fcmanager.app` 운영 중. PostgreSQL 전환은 보류)

> 현재 상태·다음 작업은 [HANDOFF.md](HANDOFF.md) / [TODOs.md](TODOs.md), 작업 이력은
> [devlog/](devlog/) 참고.
