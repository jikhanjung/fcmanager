# 배포·데이터 계약 Track A — 매니페스트·동사·healthz·git-free 전환

날짜: 2026-07-13
근거: `../devdocs/wiki/deploy-data-contract.md` (cross-project 배포·데이터 계약).
cdGTS(P08, devlog 140~143)·fsis2026(devlog 213)에 이어 fcmanager retrofit.
계약 문서가 fcmanager 에 지목한 할 일 중 **(1) 레인 경계 명시**와 배포 계약 전 구간을
이번에 구현(Track A). **(2) in-app 배치 입력 UI 완성 + (3) seed_seocho_k7 은퇴·역할 분리**는
별도 트랙(Track B)으로 남김.

## 레인 경계 판정 (핵심)

fcmanager 는 **시스템 시드 레인이 없다** — Club·Team·Player·Competition·Match·MatchEvent·
Notice·GalleryItem 등 전 모델이 운영자 입력 운영 데이터(출처 기준, 계약 §판별 기준).
따라서 매니페스트 `has_seed=false`, 불변식은 owner 필터가 아니라 **seed 명령 부재/은퇴**로
성립한다. `seed_seocho_k7` 은 계약 문서가 명시한 레인 위반 냄새(운영 데이터가 리포 경유,
devlog 078·080·081) — preflight lint 가 은퇴 전까지 기계적으로 계속 플래그한다.
상세는 `DEPLOY.md` §데이터 레인 경계.

## 구현 내역

- **`/healthz`** (`config/views_health.py` + urls + 테스트 2건): 버전·DB 연결·핵심 행 수
  (club·match). **함정**: TenantMiddleware 가 첫 세그먼트를 클럽 슬러그로 해석 → 404 나는
  문제를 `PLATFORM_SEGMENTS` 에 `healthz` 예약으로 해결.
- **`deploy/deploy.toml`**: 매니페스트(image·db_path·has_seed=false·services=["web"]·
  health·verbs·targets.prod=dolfinid).
- **`deploy/preflight.sh`**: 마지막 Bump version 이후 위험 표면 diff(migrations/.env/
  compose/host 스크립트) + seed 냄새 lint(무가드 `.all().delete()` — allowlist 없음 +
  `seed_*` 존재 자체 플래그) + DEPLOY.md 델타 출력.
- **`DEPLOY.md`** 신설: 불변식·레인 경계 표·냄새 목록(seed_seocho_k7/import_*/dedupe)·
  백업 지도(hourly + pre_deploy + m710q daily)·릴리스별 append-only 델타 노트.
- **호스트 동사** (`deploy/host/`): `deploy.sh` 를 fsis 엔진 형태로 재편(healthz 대기 +
  **DB 바인딩 게이트**(컨테이너 DB=/app/db.sqlite3 exact-match) + smoke 자동 호출, 기존
  pre-deploy 스냅샷·retention 유지), `smoke.sh`(healthz 200+버전 일치+club>0),
  `rollback.sh`(이전 태그 + 최신 pre_deploy 스냅샷 복원, 컨테이너 정지 후) 신설.
- **git-free 전환**: `deploy-prod.sh`(래퍼, exec) + `_extract_and_deploy.sh`(이미지에서
  docker cp 추출 + self-heal: 래퍼는 즉시, 추출기 자신은 원자 rename) 신설.
  `sync_to_srv.sh` 는 최초 1회 부트스트랩 전용으로 재편(상시 배포에서 git pull/sync 제거).
  `Dockerfile.dockerignore` 에서 `scripts/` 제외 해제(backup_db.py 를 이미지에 실어
  self-heal 대상에 포함) + `__pycache__/` → `**/__pycache__/` 교정.
- `build.sh` 안내 문구 git-free 로 갱신, `deploy/README.md` 전면 재작성(URL_PREFIX 시절
  내용 제거), CLAUDE.md 에 계약 포인터 추가.

## 검증

- `manage.py test` 52건 통과(healthz 2건 포함), `manage.py check` 무결.
- 전 스크립트 `bash -n` 통과. preflight 실행 — seed_seocho_k7 을 정확히 플래그.
- 로컬 이미지 빌드로 `/app/deploy/host/*` + `/app/scripts/backup_db.py` 탑재 확인
  (pycache 0), runserver 로 `/healthz` 200 + JSON 응답 실확인.

## 다음 배포(0.6.12) 운영 절차 — DEPLOY.md 델타 노트에도 기록

1. 이번 버전은 부트스트랩 필요: dolfinid 에서 `git pull && ./deploy/sync_to_srv.sh`
   (마지막 git 사용) 후 `/srv/fcmanager/deploy-prod.sh 0.6.12`.
2. 이후 배포부터: `ssh dolfinid '/srv/fcmanager/deploy-prod.sh X.Y.Z'` 한 줄.
3. nginx 변경 불요(healthz 는 로컬 검증). 운영 repo 체크아웃은 이후 삭제 가능.

## 남은 것 (Track B — 별도 트랙)

- 결과·명단 in-app 배치 입력 UI(기록지 기반 이벤트/명단 포함) 완성.
- `seed_seocho_k7`·`import_roster`·`import_player_photos` 은퇴.
- 역할 분리(system admin / 클럽 관리자 / 대회 관리자 — admin 뭉침 해소),
  Award·ClubMembership 웹 관리화.
