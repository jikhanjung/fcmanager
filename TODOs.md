# FCManager 웹사이트 — TODO

> 전체 로드맵은 [devlog/20260614_P01_프로젝트_계획.md](devlog/20260614_P01_프로젝트_계획.md) 참고.
> 진행 상황 표기: `[ ]` 예정 · `[~]` 진행 중 · `[x]` 완료

## ✅ Phase 1 — 기반 + 데이터 입력 (완료)

- [x] Django 프로젝트/앱(teams·competitions·matches) 셋업
- [x] 도메인 모델 정의 + 마이그레이션
- [x] Django Admin 전 모델 등록 (인라인·autocomplete·필터)
- [x] 홈/팀 목록/팀 상세 페이지 + Bootstrap base 템플릿
- [x] 한글 로케일·미디어/스태틱 설정
- [x] 사이트 엠블럼(로고) 적용
- [x] 샘플 데이터 시드 명령 (`python manage.py seed`)

## ✅ Phase 2 — 공개 조회 페이지 (완료)

- [x] **일정 & 결과 페이지** — 전체 경기 리스트, 대회별·팀별·연도별 필터, 예정/종료 구분
- [x] **경기 상세 페이지** — 스코어, 득점·카드·교체 타임라인(MatchEvent)
- [x] **리그 순위표** — 리그별 승점/득실 자동 계산 (승 3·무 1·패 0)
- [x] **득점 순위** — MatchEvent(GOAL) 집계, 팀/대회/연도 필터
- [x] **명예의 전당** — 입상 내역(Award) 연도·대회별 정리
- [x] **선수 상세 페이지** — 프로필 + 소속 이력 + 득점/도움/카드 + 수상
- [x] 네비게이션에 위 메뉴 추가

## 🗂️ Phase 3 — 운영 편의 기능

- [x] 회원/권한 (운영진 로그인/로그아웃, 방문자 구분, 조건부 관리 링크)
- [x] 공지사항(Notice) 모델 + 페이지 (목록·상세·홈 노출·admin)
- [x] 갤러리 (사진/영상 링크 — /gallery/)
- [x] 통계 자동 집계 (득점왕·도움·팀별 승무패·승률 — `/stats/`)
- [x] 연도별 아카이브 화면 (`/years/` 목록 + `/years/<year>/` 종합 — 클럽 요약·입상·득점/도움 TOP·경기 결과)

## 📡 Phase 4 — 실시간 중계

- [x] **경기 LIVE 상태 + MatchEvent 실시간 입력(운영진 모바일 콘솔 `/matches/<pk>/live/`)**
- [x] **라이브 스코어보드 / 타임라인 자동 갱신 — 폴링(`live.json`, 3초 주기)**
  - WebSocket/Redis 미도입(단일 컨테이너·WSGI 유지). 데이터 계약은 추후 WS 교체 가능.
- [x] **출전 명단(MatchLineup) + 중계 콘솔 무새로고침(fetch)** — 콘솔 액션 fetch 기반,
      선수 타일·교체 IN/OUT 명단 연동(`/matches/<pk>/lineup/`)
- [x] **전후반 구분 + 길이 설정 + 시계 일시정지** (v0.6.2, devlog 066)
  - 단계 진행(전반→하프타임→후반→종료), 후반 이어가기 시계, 이벤트 전/후반 태깅
  - 전후반 길이: 대회(Competition) 기본값 + 부문(Division) 오버라이드, 대회 편집 폼에서 설정
  - 시계 일시정지/재개(하프 유지한 채 동결, 누적 정지 보정)
- [x] **연장전 + 승부차기 (녹아웃)** (v0.6.4, devlog 069)
  - 연장 전·후반 또는 단일 연장(대회/부문 override), 시계는 정규 풀타임부터 이어서
  - 연장 길이: `extra_half_minutes`(대회 기본 15 + 부문 오버라이드), 대회 편집 폼에서 설정
  - 승부차기 킥별 기록(성공/실패) → 성공 수 집계, 동점 시 승자 판정(`winner_entry`)
  - 콘솔 '다음 단계' 시트(연장/승부차기/종료) — 연장 없이 바로 승부차기 가능
- [x] **시청자 페이지 진행시계·갱신 카운트다운·LIVE 깜박임** (v0.6.4, devlog 069)
  - 콘솔과 동일 시계(연장 이어가기·일시정지 반영), 단계 라벨, `🔄 N초 후 갱신`
- [ ] (확장) Django Channels + Redis → WebSocket 푸시 전환

## 🚀 Phase 5 — 배포 & 운영

- [x] Docker 이미지화 (`deploy/`, `honestjung/fcsky:0.1.0`, Gunicorn)
- [x] 정적 파일 운영 설정 (WhiteNoise) — 미디어/S3는 추후
- [x] `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` 환경변수 분리 (운영 키 지정은 배포 시)
- [ ] ~~PostgreSQL 전환~~ — 당분간 보류. SQLite DB는 호스트 파일(볼륨)로 영속화되어 유실 위험 없음.
- [x] 미디어 파일 — `media/` 디렉토리 유지 + 백업으로 보호 (볼륨/S3 전환은 보류)
- [x] **백업 체계** — 운영 hourly(`backup_db.py`) + m710q daily pull(`backup-fcmanager.sh`).
      DB·media·nginx tar 포함. 매뉴얼: `docs/operation_manual/backup.md`.
  - [x] `.env` 백업 — `/srv/fcmanager/.env`에서 pull, m710q 백업 검증 완료(2026-06-17).
  - [x] NAS 3계층화 — `/nas/JikhanJung/fcmanager_backup/`(90일) 매일 미러,
        2026-06-17부터 가동 중(backup.log "NAS 백업 완료" 매일). dev_data 갱신은 0.6.24 에서 은퇴,
        `~/dev_data/fcmanager` 디렉터리도 삭제 완료(2026-07-15, devlog 095 §9).
  - [x] **백업 유효성 = 계약**(0.6.24, devlog 094 — cdGTS 0.1.68 포팅): hourly 채택 전
        `integrity_check`(+ nginx tar 는 `tar -tzf`), 실패 시 prune 금지 → 로테이션 오염 방지.
        센티넬 → `/healthz` degraded → smoke. daily 는 라이브 scp(torn) 대신 검증된 hourly 스냅샷
        pull + 신선도 2h 게이트(telegram). dev_data 은퇴 → 테스트 타깃 직접 갱신.
  - [x] **`rollback.sh --db=restore` 복원 직전 스냅샷 무결성 검사**(2026-07-17, devlog 097) —
        후보 스냅샷(+WAL/SHM)을 임시 사본에 펼쳐 `PRAGMA integrity_check`, 손상이면 **`docker compose
        down` 전에 중단**(라이브 DB·서비스 불변). 0.6.24 채택 게이트가 **새** 스냅샷만 지키던 빈틈
        (restore 는 로테이션의 **기존** 것을 고름 → 게이트 이전·수동 후보 무검증)을 막는다.
        ⚠️ "손상 감지 시 자동 롤백"은 아님 — 자동으로 다른 스냅샷 고르지 않고 중단만(계약: 사람에게 넘김).
        정본 `deploy/host/rollback.sh` — 다음 이미지 빌드·배포 때 self-heal 로 운영 반영.
        계약 [기록 §롤아웃](../devdocs/wiki/deploy-data-contract-record.md#롤아웃) 추적 항목은
        devdocs 세션 소관(5-repo 공통, 사용자 조율).
  - [ ] `backup-fcmanager.sh` self-heal 부재 — 실행본 `~/scripts/` vs 정본 repo 가 실제로
        드리프트했다(0.6.24 에서 흡수). m710q 는 이미지 소비 호스트가 아니라 구조가 다름 — 별도 설계.
- [x] 배포 구조 분리 — 개발 소스 ↔ 운영 런타임 `/srv/fcmanager` (devlog 050, 매뉴얼 `deploy.md`)
  - [x] dolfinid 1회 마이그레이션 실행 — `fcsky` 컨테이너 `/srv` 런타임 기동, `.env` 이전 완료(2026-06-17)
- [x] 리버스 프록시(Nginx) + HTTPS + 도메인 연결 — `fcmanager.app` 병렬 배포(포트 8004,
      `/srv/fcmanager`), certbot HTTPS + HTTP→HTTPS 301 + HSTS, fcsky 레거시 유지 (devlog 063)
  - [x] 신규 인스턴스 백업 — dolfinid hourly cron + m710q daily pull(`backup-fcmanager.sh`) 모두 적용 완료(2026-06-17).
  - [x] 레거시 fcsky 폐기 (2026-06-22, devlog 072)
    - [x] nginx `/FcSky/` 301 리다이렉트 제거 — 이제 404
    - [x] 레거시 fcsky 컨테이너(8003) stop+rm — 포트 해제. `/srv/FcSky` 데이터·`honestjung/fcsky:0.5.7` 이미지는 콜드백업용 보존
    - [x] m710q 구 cron `backup-fcsky.sh`(04시) 제거·스크립트 retired (`backup-fcmanager.sh` 05시로 단일화)
- [x] repo 리네임 FcSky → `fcmanager` (m710q·dolfinid 양쪽 디렉터리·remote, GitHub `jikhanjung/fcmanager`,
      Dockerfile OCI 라벨) + 프로젝트 문서 현행화(README·CLAUDE.md) (2026-06-22, devlog 070·072·073)
      · 콜드백업·클럽 슬러그 `fcsky` 는 의도적 유지, 에셋 파일명은 후속 CI 작업 때 정리
- [x] 관리자 계정 비밀번호 교체 (2026-06-17, 운영 `admin` 비번 변경 완료)
- [x] 버전 관리 단일소스화 (fsis2026 패턴) — `config/version.py` + `deploy/build.sh X.Y.Z`
      (test→bump/commit→build `:X.Y.Z`·`:latest`→push). 0.6.2부터 적용 (devlog 066)

## ✅ Phase 6 — 멀티테넌트 SaaS 전환 (A~D 완료)

> 단일 클럽(FCManager) → 여러 클럽 SaaS. 최소 전환 계획: `devlog/20260617_P03_SaaS_멀티테넌트_전환계획.md`.

- [x] A. 테넌트 모델 + backfill (`Club`·`ClubMembership`, 8개 모델 `club` FK, fcsky backfill — devlog 053)
      · Competition/Division 은 공유(참가는 CompetitionEntry), Opponent 는 클럽별
- [x] B. 라우팅 + 스코핑 (P04) — B1 라우팅·B2 스코핑·B3 쓰기주입/폼제한·B4 격리테스트·B5 club non-null 완료
- [x] C. 권한 + 온보딩 — ClubMembership 기반 권한·플랫폼 랜딩/로그인·클럽 생성(devlog 059)
- [x] D. 브랜딩 분리 — current_club 기반 로고·이름·타이틀(devlog 060)
- 비범위(후속): 결제·요금제, 커스텀 도메인/서브도메인, schema/DB-per-tenant, Postgres 전환

## 📦 배포·데이터 계약 (../devdocs/wiki/deploy-data-contract.md)

- [x] **Track A — 배포 계약 retrofit** (2026-07-13, devlog 082): `deploy/deploy.toml` 매니페스트,
      동사(preflight/smoke/rollback), `/healthz`, `DEPLOY.md`(레인 경계 + 릴리스 델타 노트),
      git-free 배포(운영 repo 불요, self-heal). 다음 배포 시 최초 1회 부트스트랩 — DEPLOY.md 참조.
- [~] **Track B — 데이터 레인 정리** (계약 문서가 지목한 fcmanager 할 일, devlog 083):
  - [ ] 결과·명단 in-app 배치 입력 UI (일정 일괄 입력, 기록지 기반 이벤트/출전명단 배치 입력) — 보류
  - [x] `seed_seocho_k7` 은퇴 (2026-07-13 — 운영 반영 확인 후 삭제, git 이력 보존)
    - [ ] `import_roster`·`import_player_photos` 은퇴는 배치 입력 UI 완성 후
  - [x] 역할 분리 — 소유자(OWNER)/운영진(STAFF) 권한 계층(`club_owner_required`),
        마지막 소유자 보호. Award·부문 오버라이드(staff)·ClubMembership(owner) 웹 관리화.
        계정 생성만 admin 에 남음. (대회 관리 권한 세분화 — 공유 Competition 편집권 — 은 후속 메모)

## 🧹 기술 부채 / 개선 메모

- [~] 테스트 코드 작성 (모델·뷰) — 기본 스모크/단위 테스트 완료, 커버리지 확대 필요
- [x] 운영 설정 분리 — **환경변수 방식** 채택(단일 `settings.py` + `DJANGO_*` 주입,
      파일 분리 불필요). 운영(비 DEBUG) 보안 블록 추가: `SESSION_COOKIE_SECURE`·
      `CSRF_COOKIE_SECURE`. HTTPS 리다이렉트·HSTS 는 nginx 담당(devlog 063)이라 Django 측 비설정.
- [ ] 로고 투명 배경 PNG 버전 확보 시 교체
