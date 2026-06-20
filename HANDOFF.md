# HANDOFF — 리포 현재 상태

> **목적**: 세션/작업자 간 인수인계용 "지금 상태" 스냅샷. 다음에 할 일은
> [TODOs.md](TODOs.md), 작업 이력은 [devlog/](devlog/), 운영 절차는
> [docs/operation_manual/](docs/operation_manual/) 참고.
> **갱신 규칙**: 의미 있는 상태 변화(배포·브랜치·미해결 이슈)가 생기면 이 파일을 갱신.

_최종 갱신: 2026-06-20_

---

## 한 줄 요약

Phase 1~4 완료. 중계 콘솔 **전후반 구분 + 길이 설정(대회/부문) + 시계 일시정지/재개**
추가, 버전 관리 fsis2026 패턴(`config/version.py`+`deploy/build.sh`) 도입, 운영 쿠키
Secure 보안 설정. 이미지 `0.6.3` 빌드·push 완료. **운영(dolfinid) 0.6.3 배포 완료**(2026-06-20, 사이트 정상).

## 코드 / 브랜치

- 브랜치: `main` (배포도 main 직접 — feature 브랜치 안 씀)
- 최신 커밋: `9c1f398` — Bump version to 0.6.3
  - 직전: `889ccf2` devlog 067(쿠키 Secure), `53345b1` 운영 쿠키 Secure 블록, `2f44e7e` 버전 단일소스
- 작업 트리: clean (단, `db.sqlite3.devbak` 는 추적 안 함 — 아래 "로컬 개발 DB" 참고)

## 배포 상태

| 위치 | 버전 | 상태 |
|------|------|------|
| Docker Hub `honestjung/fcmanager` | **0.6.3** + `latest` | push 완료 (digest `sha256:629349ab…`), 매니페스트 정상 |
| 운영 dolfinid `/srv/fcmanager` | **0.6.3** | 배포 완료(2026-06-20). 컨테이너 `fcmanager` Up, `fcmanager.app` 200, navbar `v0.6.3` |

- 운영 0.6.3 배포 완료 — 미완 배포 작업 없음.
- 0.6.3 은 **마이그레이션 없음**(운영 비 DEBUG 쿠키 Secure 설정만). DEBUG=false 라
  `SESSION_COOKIE_SECURE`·`CSRF_COOKIE_SECURE` 활성(devlog 067).
- (직전) 0.6.2 는 **마이그레이션 3개 포함**(competitions 0009, matches 0015·0016) — entrypoint
  `migrate` 가 적용 완료.
- 버전 단일 소스 = `config/version.py`. 다음 릴리스는 **`./deploy/build.sh X.Y.Z`** 로
  (test → version.py bump/commit → build `:X.Y.Z`·`:latest` → push) 일괄 처리.
- dolfinid 소스 체크아웃(`~/projects/FcSky`)은 GitHub pull 키 없음 → `git pull` 실패할 수 있음.
  단 앱 코드는 이미지에 포함되어 배포에 지장 없음(`sync_to_srv` 는 compose/deploy.sh/백업
  스크립트만 복사).

## 운영 호스트 (요약 — 상세는 메모리/매뉴얼)

- dolfinid `honestjung@34.64.158.160`, 도메인 `fcmanager.app`(루트=플랫폼, `/fcsky/`=클럽).
- 런타임은 `/srv/fcmanager/`(컨테이너 `fcmanager`, 포트 8004). 소스 체크아웃은 런타임 아님.
- 백업 2계층: dolfinid hourly(`backup_db.py`) + m710q daily 04~05시
  (`~/scripts/backup-fcmanager.sh` → `~/backups/fcmanager/`).

## 로컬 개발 (m710q)

- venv: **`~/venv/FcSky`** (CLAUDE.md엔 `FCManager`로 적혀 있으나 실제 디렉터리는 `FcSky` — 불일치).
- **테스트 서버는 운영 백업 미러(`~/dev_data/fcmanager/`)를 바라본다** (fsis2026 dev_data 패턴):
  ```bash
  source ~/venv/FcSky/bin/activate && ./scripts/run-testserver.sh   # 0.0.0.0:8000
  ```
  - `scripts/run-testserver.sh` 가 `DATABASE_PATH`/`MEDIA_ROOT` 를 dev_data 로 지정하고
    `DEBUG=true`, `ALLOWED_HOSTS=*`(LAN 접근용) 로 기동. settings 는 두 env 미설정 시
    기본(BASE_DIR) 유지 → 운영 컨테이너 영향 없음.
  - dev_data 는 **daily 백업이 자동 갱신**: `backup-fcmanager.sh` step 8 이 매일 05시
    `~/backups/fcmanager/current/{db.sqlite3,media}` → `~/dev_data/fcmanager/` 로 cp/rsync.
  - 데이터는 repo 가 아니라 dev_data 에 있으므로 **repo 에 db.sqlite3 두지 않는다**(삭제됨,
    gitignore). 굳이 스크래치 DB 가 필요하면 `python manage.py migrate` 가 빈 repo DB 생성.

## 알려진 정리거리 (급하지 않음)

- **리네임 미완**: repo 디렉터리 `~/projects/FcSky` → `FCManager` 예정. venv 이름,
  CLAUDE.md의 venv 경로 표기도 함께 정리 필요.
- dolfinid 운영 전환 잔여: `/srv/FcSky`→`/srv/fcmanager`, m710q `~/backups/FcSky`→`fcmanager`,
  구 cron `backup-fcsky.sh`(04시) 제거 — `prod-and-backup` 메모리/devlog 참고.
- 행 클릭 스크립트가 템플릿마다 중복 → base.html 공통 JS로 통합 여지.
