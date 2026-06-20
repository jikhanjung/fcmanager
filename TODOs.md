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

- [x] **일정 & 결과 페이지** — 전체 경기 리스트, 대회별·팀별·시즌별 필터, 예정/종료 구분
- [x] **경기 상세 페이지** — 스코어, 득점·카드·교체 타임라인(MatchEvent)
- [x] **리그 순위표** — 리그별 승점/득실 자동 계산 (승 3·무 1·패 0)
- [x] **득점 순위** — MatchEvent(GOAL) 집계, 팀/대회/시즌 필터
- [x] **명예의 전당** — 입상 내역(Award) 시즌·대회별 정리
- [x] **선수 상세 페이지** — 프로필 + 소속 이력 + 득점/도움/카드 + 수상
- [x] 네비게이션에 위 메뉴 추가

## 🗂️ Phase 3 — 운영 편의 기능

- [x] 회원/권한 (운영진 로그인/로그아웃, 방문자 구분, 조건부 관리 링크)
- [x] 공지사항(Notice) 모델 + 페이지 (목록·상세·홈 노출·admin)
- [x] 갤러리 (사진/영상 링크 — /gallery/)
- [x] 통계 자동 집계 (득점왕·도움·팀별 승무패·승률 — `/stats/`)
- [x] 시즌별 아카이브 화면 (`/seasons/` 목록 + `/seasons/<id>/` 종합 — 클럽 요약·입상·득점/도움 TOP·경기 결과)

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
- [ ] (확장) Django Channels + Redis → WebSocket 푸시 전환

## 🚀 Phase 5 — 배포 & 운영

- [x] Docker 이미지화 (`deploy/`, `honestjung/fcsky:0.1.0`, Gunicorn)
- [x] 정적 파일 운영 설정 (WhiteNoise) — 미디어/S3는 추후
- [x] `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` 환경변수 분리 (운영 키 지정은 배포 시)
- [ ] ~~PostgreSQL 전환~~ — 당분간 보류. SQLite DB는 호스트 파일(볼륨)로 영속화되어 유실 위험 없음.
- [x] 미디어 파일 — `media/` 디렉토리 유지 + 백업으로 보호 (볼륨/S3 전환은 보류)
- [x] **백업 체계** — 운영 hourly(`backup_db.py`) + m710q daily pull(`backup-fcsky.sh`).
      DB·media·nginx tar 포함. 매뉴얼: `docs/operation_manual/backup.md`.
  - [x] `.env` 백업 — `/srv/fcmanager/.env`에서 pull, m710q 백업 검증 완료(2026-06-17).
  - [x] NAS 3계층화 — `/nas/JikhanJung/fcmanager_backup/`(90일) 매일 미러 + dev_data 갱신,
        2026-06-17부터 가동 중(backup.log "NAS 백업 완료" 매일)
- [x] 배포 구조 분리 — 개발 소스 ↔ 운영 런타임 `/srv/fcmanager` (devlog 050, 매뉴얼 `deploy.md`)
  - [x] dolfinid 1회 마이그레이션 실행 — `fcsky` 컨테이너 `/srv` 런타임 기동, `.env` 이전 완료(2026-06-17)
- [x] 리버스 프록시(Nginx) + HTTPS + 도메인 연결 — `fcmanager.app` 병렬 배포(포트 8004,
      `/srv/fcmanager`), certbot HTTPS + HTTP→HTTPS 301 + HSTS, fcsky 레거시 유지 (devlog 063)
  - [x] 신규 인스턴스 백업 — dolfinid hourly cron + m710q daily pull(`backup-fcmanager.sh`) 모두 적용 완료(2026-06-17).
  - [ ] 레거시 fcsky 폐기 시점·절차 결정
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

## 🧹 기술 부채 / 개선 메모

- [~] 테스트 코드 작성 (모델·뷰) — 기본 스모크/단위 테스트 완료, 커버리지 확대 필요
- [ ] 운영 설정 분리 (`settings/base.py`, `dev.py`, `prod.py` 또는 환경변수)
- [ ] 로고 투명 배경 PNG 버전 확보 시 교체
