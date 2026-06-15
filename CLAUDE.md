# CLAUDE.md

FC Sky 웹사이트. Django + Bootstrap. 선수단·대회·일정·결과·입상 내역을
관리/공개하고, 장기적으로 실시간 중계까지 확장하는 것이 목표.

## 환경 / 실행

- **가상환경은 반드시 `~/venv/FcSky` 사용** (프로젝트 로컬 `.venv` 만들지 말 것).
  ```bash
  source ~/venv/FcSky/bin/activate
  ```
- 의존성: `pip install -r requirements.txt` (Django 5.1, Pillow)
- DB: SQLite(개발). `db.sqlite3`는 git 제외.
- 자주 쓰는 명령:
  ```bash
  python manage.py runserver        # 개발 서버 (http://127.0.0.1:8000/)
  python manage.py makemigrations && python manage.py migrate
  python manage.py seed             # 멱등 샘플 데이터 (--flush 로 초기화 후 재생성)
  python manage.py check
  ```
- 개발용 관리자 계정: `admin` / `fcsky1234` (운영 전 반드시 교체).

## 구조

```
config/              프로젝트 설정 (settings.py, urls.py)
apps/teams/          Team, Player, TeamMembership + 홈/팀 뷰·URL
apps/competitions/   Season, Competition, CompetitionEntry, Award
apps/matches/        Opponent, Match, MatchEvent
templates/           base.html + 앱별 템플릿 (Bootstrap 5, CDN)
static/img/          사이트 로고 등 브랜딩 자산
```

- 앱은 `apps/` 하위에 두며, `AppConfig.name`과 `INSTALLED_APPS`는 `apps.<app>` 형식.

## 도메인 모델 핵심

- **선수의 팀 소속·등번호·주장은 `TeamMembership`(선수↔팀↔시즌)** 에 둔다. 시즌/팀 이동 표현용.
  등번호를 `Player`에 직접 넣지 말 것.
- **`Match.result`** 프로퍼티가 우리 팀 기준 승(W)/무(D)/패(L)를 자동 판정. 점수 미입력 시 `None`.
- **`MatchEvent`** (side·event_type·minute·player)는 득점/카드/교체 기록이자 **Phase 4 실시간 중계의 기반**.
  새 경기 기능은 이 모델을 활용/확장하는 방향으로.
- 사용자 노출 텍스트·`verbose_name`은 **한글**로.

## 규칙 / 관례

- 데이터 입력은 1차적으로 **Django Admin(`/admin/`)** 으로 한다. 새 모델은 admin에도 등록(검색·필터·autocomplete 포함).
- `autocomplete_fields`를 쓰려면 대상 ModelAdmin에 `search_fields`가 있어야 함.
- 프론트는 Django Template + Bootstrap 5(현재 CDN). 별도 JS 빌드 도입 안 함.
- 업로드 이미지는 `media/`, 브랜딩 정적 자산은 `static/`.

## 작업 기록 관례

- 진행할 작업 목록: **`TODOs.md`**.
- 개발 로그: **`devlog/`**.
  - 계획 문서: `YYYYMMDD_P##_{제목}.md`
  - 작업 기록: `YYYYMMDD_###_{제목}.md`
- 의미 있는 작업 단위마다 devlog를 남기고 커밋한다.

## 현재 상태

- **Phase 1·2 완료** (모델·Admin·기본 페이지·로고·시드 + 일정/결과·경기 상세·순위표·
  득점 순위·명예의 전당·선수 상세 공개 조회 페이지). 다음은 **Phase 3 운영 편의 기능**.
  상세 로드맵은 `TODOs.md` 참고.
