# HANDOFF — 리포 현재 상태

> **목적**: 세션/작업자 간 인수인계용 "지금 상태" 스냅샷. 다음에 할 일은
> [TODOs.md](TODOs.md), 작업 이력은 [devlog/](devlog/), 운영 절차는
> [docs/operation_manual/](docs/operation_manual/) 참고.
> **갱신 규칙**: 의미 있는 상태 변화(배포·브랜치·미해결 이슈)가 생기면 이 파일을 갱신.

_최종 갱신: 2026-07-15_

---

## 한 줄 요약

Phase 1~4 + SaaS + **배포·데이터 계약 완전 정렬**(devlog 082~089): git-free self-heal 배포에
외부 검토분(rollback `--db=keep|restore`+keep 가드·`.mig` 사이드카·`contract_version`·추출
안전망)까지 운영 착지, **m710q 도커 테스트 target** 신설, **DB 디렉터리 마운트**(fsis2026 패턴)
+ **gosu 권한 드롭**(마운트 소유 uid 런타임 감지 — 소유권 함정 근본 해소) 전환.
**운영(dolfinid) 0.6.24 배포 완료**(2026-07-15, smoke PASS) — 0.6.24 는 **백업 레인**:
채택 전 integrity 검증·실패 시 prune 금지(로테이션 오염 방지), `/healthz` degraded(200)→smoke,
daily 미러는 검증된 hourly 스냅샷 pull + 신선도 2h telegram 게이트, dev_data 은퇴(devlog 094).
상시 배포 =
`./deploy/build.sh X.Y.Z` + `./deploy/remote-prod.sh X.Y.Z` 두 줄, 테스트 확인은
`/srv/fcmanager/deploy-dev.sh X.Y.Z`(m710q, :8005).

## 코드 / 브랜치

- 브랜치: `main` (배포도 main 직접 — feature 브랜치 안 씀)
- 최신 흐름(2026-07-14, devlog 086~089): `87232ba` 외부검토분 정렬 → `0feaf06` 테스트
  target → `1b41c90` compose 파라미터화 → `fb1c0a4` DB 디렉터리 마운트 → `3437c00` 쓰기
  프로브 → `77b76f9` gosu 권한 드롭 → `fb51d05` 프로브 uid 보정
- 작업 트리: clean

## 배포 상태

| 위치 | 버전 | 상태 |
|------|------|------|
| Docker Hub `honestjung/fcmanager` | **0.6.24** + `latest` | push 완료 |
| 운영 dolfinid `/srv/fcmanager` | **0.6.24** | 배포 완료(2026-07-15, 7/7). DB게이트+쓰기프로브 OK·smoke PASS(`club=1, match=28`). 백업 무결성 게이트 운영 실행 검증(스냅샷 delete 모드·부산물 0·센티넬→degraded→smoke FAIL→자기해제 전 구간) |
| 테스트 m710q `/srv/fcmanager` | **0.6.23** | 도커 테스트 target(devlog 087) — `:8005`, DB=운영 스냅샷 미러(daily 05시 갱신), 랜딩(:80) 카드 |

- **배포 방식 = git-free 원격 원터치**(계약 정렬, devlog 082·085): m710q 에서
  `./deploy/remote-prod.sh X.Y.Z` → dolfinid 가 이미지에서 host 파일 추출(self-heal, bash -n
  안전망) → 스냅샷(+`.mig`) → 스왑 → migrate(entrypoint, gosu 드롭 후) → DB 게이트+쓰기
  프로브 → smoke(`/healthz`). 롤백: `ssh dolfinid '/srv/fcmanager/rollback.sh <이전>
  [--db=keep|restore]'`(기본 keep=이미지만, migration 시 keep 가드). 배포 caveat 는
  **`DEPLOY.md`** 릴리스 델타 노트가 권위 소스, 배포 전 `./deploy/preflight.sh`.
- 0.6.12~0.6.18 은 마이그레이션 없음. 운영 포트 `.env HOST_PORT=8004`, 테스트 8005.
- **DB 는 디렉터리 마운트**(`/srv/fcmanager/db` → `/app/hostdb`, devlog 088) — 저널 형제
  파일 호스트 공유. 컨테이너는 root 시작 → 마운트 소유 uid 로 gosu 드롭(devlog 089).
- 배포 중 다운타임(수 초)은 nginx 점검 페이지(502→503 재기술)로 안내(devlog 084).
- **레거시 리다이렉트(호스트 nginx, repo 비추적)**: `/2026biennale/`·`biennale.nopeoplestime.info`
  →`biennale.app` (devlog 068). `/FcSky/` 리다이렉트는 **제거됨**(2026-06-22, devlog 072 —
  `sites-available/2026biennale` 에서 블록 삭제, 백업 `.bak-fcsky-removed-20260622`. 이제 404).
  레거시 fcsky 컨테이너(8003)는 **폐기 완료**(2026-06-22, stop+rm — 포트 해제). `/srv/FcSky`
  데이터·`honestjung/fcsky:0.5.7` 이미지는 콜드백업용 보존(복구 필요 시 재기동 가능).
- 버전 단일 소스 = `config/version.py`. 릴리스는 **`./deploy/build.sh X.Y.Z`** 로
  (test → version.py bump/commit → build `:X.Y.Z`·`:latest` → push) 일괄 처리.
- dolfinid 소스 체크아웃(`~/projects/fcmanager`)은 **배포 경로에서 완전 이탈** —
  git-free 전환으로 운영 서버 상시 파일은 `.env` + DB + 백업뿐, 체크아웃은 삭제 가능.

## 운영 호스트 (요약 — 상세는 메모리/매뉴얼)

- dolfinid `honestjung@34.64.158.160`, 도메인 `fcmanager.app`(루트=플랫폼, `/fcsky/`=클럽).
- 런타임은 `/srv/fcmanager/`(컨테이너 `fcmanager`, 포트 8004). 소스 체크아웃은 런타임 아님.
- 백업 2계층: dolfinid hourly(`/srv/fcmanager/scripts/backup_db.py` — 트랙 `fcmanager`+`dolfinid_nginx`,
  **채택 전 integrity 검증·실패 시 prune 금지**, 0.6.24) + m710q daily 05시(`~/scripts/backup-fcmanager.sh`
  → `~/backups/fcmanager/` + NAS 90일). daily 는 라이브 DB 가 아니라 **검증된 hourly 스냅샷을 pull**
  하고, 스냅샷이 2시간 넘게 낡으면(= hourly 중단/무결성 차단) telegram 으로 알린다.
  레거시 fcsky 백업(dolfinid hourly `/srv/FcSky/...` cron, m710q `backup-fcsky.sh` 04시)은
  모두 폐기 완료(2026-06-22, devlog 072).

## 로컬 개발 (m710q)

- venv: **`~/venv/fcmanager`** (디렉터리 재생성 완료, 구 `~/venv/FcSky` 제거됨).
- **테스트는 도커 테스트 target 하나로 일원화**(0.6.24 — `~/dev_data` + `scripts/run-testserver.sh`
  런처는 은퇴. 미러가 둘이면 드리프트만 늘고, 실제로 드리프트했다):
  `/srv/fcmanager/deploy-dev.sh X.Y.Z` — 운영 동일 레이아웃, `:8005`, m710q 랜딩(:80) 카드로 접근.
  - DB 는 **daily 백업이 매일 05시 운영 스냅샷으로 자동 갱신**(`backup-fcmanager.sh` step 8 —
    integrity 검증된 hourly 스냅샷 → 컨테이너 정지 → 교체 → 재기동). "운영 데이터로 확인"과
    "배포 파이프라인 시험"이 같은 곳에서 된다.
  - ⚠️ **손으로 DB 를 갈아끼울 땐 컨테이너를 먼저 내린다** — WAL 로 쥔 채 파일을 갈면 btree 가
    깨진다(cdGTS devlog 149). `docker compose down`(서비스명 없이) → 교체 + `rm -f db/db.sqlite3-{wal,shm}`
    → `up -d`.
  - **repo 에 db.sqlite3 두지 않는다**(gitignore). 스크래치 DB 가 필요하면 `python manage.py migrate`
    가 빈 repo DB 를 만든다 — 운영 데이터와 무관.

## 알려진 정리거리 (급하지 않음)

- **리네임 완료** (FcSky → `fcmanager`, 전부 소문자):
  - [x] 코드 참조 → `~/venv/fcmanager`·`~/projects/fcmanager` (build.sh VENV·CLAUDE.md·run-testserver, 커밋 반영)
  - [x] GitHub repo 리네임 `jikhanjung/FcSky` → `jikhanjung/fcmanager` (웹)
  - [x] `git remote set-url origin git@github.com:jikhanjung/fcmanager.git` (m710q 반영, fetch/push 정상)
  - [x] 로컬 디렉터리 `~/projects/fcmanager` 로 이동 완료 (m710q)
  - [x] venv 재생성 완료 — `~/venv/fcmanager` 사용, 구 `~/venv/FcSky` 제거됨
  - [x] `deploy/Dockerfile` OCI `image.source` 라벨 → `github.com/jikhanjung/fcmanager` 로 정정
  - 참고: `/srv`·백업·dev_data·이미지·도메인은 이미 `fcmanager`. devlog 의 `/srv/FcSky`·`/FcSky/`
    는 과거 기록이라 불변, 레거시 `/FcSky/` 301 리다이렉트(devlog 068)·클럽 슬러그 `fcsky` 도 유지.
  - [x] dolfinid(운영) 소스 체크아웃도 `~/projects/fcmanager` 로 리네임·remote 갱신 완료(2026-06-22).
    → FcSky → fcmanager 리네임은 m710q·dolfinid 양쪽 모두 완료.
- [x] m710q 구 cron `backup-fcsky.sh`(04시) → 신규 `backup-fcmanager.sh`(05시)로 대체·정리 완료.
  레거시 fcsky 폐기(devlog 072)로 fcsky 백업은 더 이상 불필요. `/srv/FcSky` 는 콜드백업으로만 보존.
- 행 클릭 스크립트가 템플릿마다 중복 → base.html 공통 JS로 통합 여지.
