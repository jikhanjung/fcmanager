# CLAUDE.md

FCManager 웹사이트. Django + Bootstrap. 선수단·대회·일정·결과·입상 내역을
관리/공개하고, 장기적으로 실시간 중계까지 확장하는 것이 목표.

## 환경 / 실행

- **가상환경은 반드시 `~/venv/fcmanager` 사용** (프로젝트 로컬 `.venv` 만들지 말 것).
  ```bash
  source ~/venv/fcmanager/bin/activate
  ```
- 의존성: `pip install -r requirements.txt` (Django 5.1, Pillow)
- DB: SQLite(개발). `db.sqlite3`는 git 제외.
- 자주 쓰는 명령:
  ```bash
  python manage.py runserver        # 개발 서버 (http://127.0.0.1:8000/)
  python manage.py makemigrations && python manage.py migrate
  python manage.py check
  ```
- 개발용 관리자 계정: 사용자명 `admin`. 비밀번호는 `deploy/.env` 의
  `DJANGO_SUPERUSER_PASSWORD` 로 주입하거나 `python manage.py createsuperuser` 로 생성한다.
  (비밀번호 평문 커밋 금지. 운영 비번은 2026-06-17 교체 완료.)

### 테스트 서버 (운영 데이터로 확인할 때)

**m710q 도커 테스트 target 하나로 일원화**(0.6.24 — 종전 `~/dev_data` + `run-testserver.sh` 런처는
은퇴). 운영과 동일 레이아웃(`/srv/fcmanager`, HOST_PORT=**8005**)으로 돌고, DB 는 **daily 백업이 매일
05시 운영 스냅샷으로 갱신**한다(`scripts/backup-fcmanager.sh` step 8). 폰 등 LAN 접근도 `:8005` 로.

```bash
/srv/fcmanager/deploy-dev.sh X.Y.Z    # 테스트 배포(스냅샷 없음, DB 폐기 가능). 매니페스트 [targets.test]
```

- 미러가 하나뿐이라 드리프트가 없다 — 배포 파이프라인 시험과 "운영 데이터로 확인"이 같은 곳에서 된다.
- ⚠️ **테스트 DB 를 손으로 갈아끼울 땐 반드시 컨테이너를 먼저 내린다**: 컨테이너가 DB 를 WAL 로 쥔 채
  파일을 갈면 btree 가 깨진다(cdGTS devlog 149 에서 실제 발생). `cd /srv/fcmanager && docker compose down`
  → 교체 + `rm -f db/db.sqlite3-wal db/db.sqlite3-shm` → `docker compose up -d`. **서비스명은 쓰지 말 것**
  (사이드카가 생기면 그것만 남는다). daily 백업이 바로 이 순서를 지킨다.
- 그냥 `runserver` 는 repo 기본 DB(스크래치)를 쓴다 — 운영 데이터와 무관.
- `DATABASE_PATH`/`MEDIA_ROOT` env 미설정 시 settings 는 기본(`BASE_DIR`) 유지 → 운영 컨테이너 무영향.

## 구조

```
config/              프로젝트 설정 (settings.py, urls.py)
apps/clubs/          Club, ClubMembership + 테넌트 라우팅 미들웨어·권한·홈
apps/teams/          Team, Player, TeamMembership + 홈/팀 뷰·URL
apps/competitions/   Competition, Division(부문), CompetitionEntry, Award
apps/matches/        Opponent, Match, MatchEvent, MatchLineup, MatchVideo + 중계
apps/notices/        Notice(공지)
apps/gallery/        GalleryItem(갤러리)
templates/           base.html + 앱별 템플릿 (Bootstrap 5, CDN)
static/img/          사이트 로고 등 브랜딩 자산
```

- 앱은 `apps/` 하위에 두며, `AppConfig.name`과 `INSTALLED_APPS`는 `apps.<app>` 형식.

## 도메인 모델 핵심

- **멀티테넌트**: 모든 루트 모델은 `Club` FK 를 가지며, 요청은 슬러그 경로(`/<club-slug>/`)로
  스코핑된다(`apps.clubs.middleware.TenantMiddleware`). 새 모델도 `club` FK 를 둘 것.
- **대회 구조**: `Competition`(연도·종류) 아래 `Division`(부문, 연령대)을 두고, `CompetitionEntry`가
  대회·부문에 팀(Team) 또는 상대팀(Opponent)을 등록. `Match`는 home/away 를 참가팀으로 연결.
- **선수의 팀 소속·등번호·주장은 `TeamMembership`(선수↔팀↔대회)** 에 둔다. 대회 단위 명단·팀 이동 표현용.
  등번호를 `Player`에 직접 넣지 말 것.
- **`Match.result`** 프로퍼티가 우리 팀 기준 승(W)/무(D)/패(L)를 자동 판정. 점수 미입력 시 `None`.
- **`MatchEvent`** (side·event_type·minute·player)는 득점/카드/교체 기록이자 **실시간 중계의 기반**.
  새 경기 기능은 이 모델을 활용/확장하는 방향으로.
- 사용자 노출 텍스트·`verbose_name`은 **한글**로.

## 규칙 / 관례

- 데이터 입력은 **운영진(클럽 staff) 웹 화면**(`/manage/`·`/teams/`·`/matches/` 등,
  `@staff_required`)에서 한다. 참가팀(CompetitionEntry)·경기 추가/삭제는 대회 상세에서,
  입상(Award)·부문 시간 오버라이드·클럽 운영진(ClubMembership)도 웹 관리 가능(devlog 083).
  admin 은 백업/보조 경로 + 사용자 계정 생성만.
- **역할 분리**: 소유자(OWNER)만 클럽 운영진 구성을 관리(`club_owner_required`),
  운영진(STAFF)은 데이터 입력. 마지막 소유자는 강등/제거 불가.
- 새 모델은 **admin에도 등록**(검색·필터·autocomplete 포함) — 백업/보조 입력 경로.
- `autocomplete_fields`를 쓰려면 대상 ModelAdmin에 `search_fields`가 있어야 함.
- 프론트는 Django Template + Bootstrap 5(현재 CDN). 별도 JS 빌드 도입 안 함.
- 업로드 이미지는 `media/`, 브랜딩 정적 자산은 `static/`.
- **배포는 배포·데이터 계약을 따른다** (`../devdocs/wiki/deploy-data-contract.md`):
  매니페스트 `deploy/deploy.toml` + 동사(preflight/build/deploy/smoke/rollback), git-free
  (운영 서버 repo 불요), 배포 caveat 는 **`DEPLOY.md`** 릴리스 델타 노트에. fcmanager 는
  시스템 시드 레인 없음(`has_seed=false`) — **운영 데이터를 seed 명령으로 리포에 넣지 말 것**
  (기존 `seed_seocho_k7` 은 은퇴 대상 냄새, DEPLOY.md 레인 경계 참조).

## 작업 기록 관례

- 진행할 작업 목록: **`TODOs.md`**.
- 개발 로그: **`devlog/`**.
  - 계획 문서: `YYYYMMDD_P##_{제목}.md`
  - 작업 기록: `YYYYMMDD_###_{제목}.md`
- 의미 있는 작업 단위마다 devlog를 남기고 커밋한다.

## 현재 상태

- **Phase 1~4 완료** + 멀티테넌트 SaaS 전환 + Docker 배포(`fcmanager.app` 운영):
  공개 조회 페이지(일정/결과·경기 상세·순위표·득점 순위·명예의 전당·선수 상세), 운영진 웹 입력,
  공지·갤러리, 실시간 중계 콘솔(연장전·승부차기·시청자 진행시계)까지 가동 중.
- PostgreSQL 전환은 보류(SQLite 볼륨 영속). 현재 상태/다음 작업은 `HANDOFF.md`·`TODOs.md` 참고.
