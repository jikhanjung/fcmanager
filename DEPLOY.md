# DEPLOY.md — fcmanager 배포·데이터 계약

> 표준 규약: `../devdocs/wiki/deploy-data-contract.md` (cross-project Deploy/Data Contract).
> 이 파일은 그 계약을 fcmanager 에 구체화한 것. **배포 전 pre-flight 권위 소스** — devlog 는
> 더 깊은 맥락이 필요할 때만 참조하는 2차 소스. 배포 caveat 는 커밋 메시지·devlog 가 아니라
> **여기 릴리스별 델타 노트**에 한두 줄로 적는다.

배포 매니페스트(선언층)는 `deploy/deploy.toml`. 전체 파일 구성·흐름은 `deploy/README.md`.
이 문서는 **데이터 안전 경계**와 **릴리스별 운영 주의점**을 다룬다.

## 배포 흐름 (git-free, cdGTS·fsis2026 정렬)

**빌드 호스트 (m710q):**
```
./deploy/preflight.sh          # (선택) 위험 표면 diff + seed 냄새 lint + 이 문서 델타
./deploy/build.sh X.Y.Z        # test + bump + build + push
```
**운영 배포 — 빌드 호스트에서 원격 원터치 (dolfinid 에 git pull/sync 불요):**
```
./deploy/remote-prod.sh X.Y.Z          # = ssh dolfinid '/srv/fcmanager/deploy-prod.sh X.Y.Z'
                                       #   (이미지에서 host 파일 추출 → 스냅샷 → 스왑 → migrate → DB게이트 → smoke)
# 문제 시: ssh dolfinid '/srv/fcmanager/rollback.sh <이전 X.Y.Z> [--db=keep|restore]'
#          기본 --db=keep = 이미지만 전환(운영 데이터 보존). DB 복원은 --db=restore 명시적 opt-in.
```
모든 host 파일은 이미지 `/app/deploy/host/*`(`COPY . .`)에 실려 배포 시 추출되고 부트스트랩 파일까지
self-heal → **운영 서버에 repo 불필요**. 최초 1회만 `deploy/sync_to_srv.sh`(또는 이미지에서 docker cp).

---

## 불변식 (Invariant)

> **fcmanager 에는 시스템 시드 레인이 없다(`has_seed=false`) — 전 모델이 운영 데이터다.
> 운영 데이터(클럽·팀·선수·대회·경기·이벤트·공지·갤러리)는 in-app 입력으로만 들어오고,
> hourly SQLite 백업 + 배포 직전 스냅샷 + m710q daily 미러가 항상 잡는다.
> 배포 파이프라인은 운영 데이터를 나르지 않는다** (`docker-entrypoint.sh` 는
> `migrate` + superuser 보증만, seed 없음).

이 불변식이 서면 "재배포하면 내 경기 결과 날아가나?" 를 매번 고민할 필요가 없다.

---

## 데이터 레인 경계

| 레인 | 해당 모델 | 입구 |
|---|---|---|
| 시스템 시드 | **(없음)** | — |
| 운영 데이터 | Club·ClubMembership / Team·Player·TeamMembership / Competition·Division·CompetitionEntry·Award / Opponent·Match·MatchEvent·MatchLineup·MatchVideo / Notice / GalleryItem — **전부** | 운영진 웹 화면(`@staff_required`) + admin(백업 경로) |

판별 근거(계약 §판별 기준 = 출처): fcmanager 의 모든 데이터는 운영자가 실제로 입력한
프로덕션 데이터다. cdGTS 의 ICC 경계나 fsis 의 지질 참조표 같은 "개발자가 저작한 시스템
정의 데이터"가 없다.

### 레인 위반 냄새 (은퇴 대상 — Track B)

운영 데이터가 리포/관리 명령을 경유 중인 임시 우회(crutch). in-app 입력 UI 가 갭을 메우면 은퇴한다.
`preflight` 가 기계적으로 계속 표면화한다.

- ~~`seed_seocho_k7`~~ — **은퇴 완료(2026-07-13, devlog 083)**. 실제 팀·실경기 결과·이벤트·명단을
  리포에 커밋해 밀어넣던 계약 문서 명시 냄새(devlog 078·080·081). 데이터가 운영 DB 에 반영된 것을
  확인(v0.6.11, 공개 페이지)한 뒤 명령 삭제 — 코드는 git 이력에, 일정 원본은 `docs/seocho-k7-schedule.md` 에
  보존. 이후 경기 결과·이벤트·명단은 in-app(경기 편집·중계 콘솔)으로만 입력.
- `apps/teams/management/commands/import_roster.py` · `import_player_photos.py` — 명단/사진
  일괄 입력 도구(수동 1회성, 배포 파이프라인 밖). in-app 배치 입력 완성 시 함께 은퇴.
- `apps/teams/management/commands/dedupe_members.py` — 병합 정리 도구(충돌 시 중단 안전장치
  있음). 시드 아님 — footgun lint 대상이지만 유지.

## 백업 지도 (안전망 = 파이프라인이 아니라 백업/복원)

| 트랙 | 위치 | 주기·보존 |
|---|---|---|
| hourly 온라인 백업 | dolfinid `/srv/fcmanager/backup/` (`scripts/backup_db.py`, cron 매시) | 최근 12개 |
| pre-deploy 스냅샷 | dolfinid `/srv/fcmanager/backup/pre_deploy/` (deploy.sh 가 down 직후) | 최근 10개 |
| daily 미러 | m710q `~/backups/fcmanager/` + `~/dev_data/fcmanager/` (backup-fcmanager.sh, 05시) | 스크립트 참조 |

복원은 **컨테이너 정지 후**(SQLite WAL torn-copy 방지) — `rollback.sh --db=restore` 가 표준 경로.
`rollback.sh` 기본은 `--db=keep`(코드만 롤백) — 복원이 배포 후 운영 입력분까지 지우면 rollback
자신이 위 불변식을 깨기 때문. 직전 배포에 migration 이 있었으면 keep 가드가 차단(스냅샷 `.mig`
사이드카 vs 현재 적용 수 비교 — `--db=restore` 또는 수동 판단 후 `--force`).

---

## 릴리스별 운영 델타 노트 (append-only)

> 형식: `버전: 운영에 필요한 것 한두 줄`. 없으면 안 적는다(코드/템플릿 전용).

- `0.6.16`: **DB 파일 마운트 → 디렉터리 마운트**(`/srv/fcmanager/db` → `/app/hostdb`,
  `DATABASE_PATH=/app/hostdb/db.sqlite3` compose 고정 — fsis2026 패턴, WAL 형제 파일 호스트 공유).
  구 레이아웃(루트 `db.sqlite3`)은 **deploy.sh 가 down 직후 1회 자동 이행**(db/ 로 mv, wal/shm 포함).
  hourly `backup_db.py` 는 새 경로 + legacy fallback. **m710q daily 미러(`~/scripts/backup-fcmanager.sh`,
  repo 밖)는 별도 수정 필요**(scp 경로 `db/db.sqlite3` — 2026-07-14 수정 완료). DB 게이트 기대값
  `/app/hostdb/db.sqlite3` 로 변경. 마이그레이션 없음(스키마 무변).
- `0.6.15`: compose `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` 파라미터화
  (`${VAR:-운영기본값}` — 운영 .env 미설정이면 종전과 동일, 테스트 호스트만 .env 로 override).
  **m710q 테스트 배포 검증 완료(2026-07-14)** — 추출 compose 파라미터화 확인, tailnet 접속 200,
  smoke PASS. 운영(dolfinid) 반영 대기 — 0.6.14 의 계약 정렬분과 함께 이 버전 prod 배포로 착지.
- `0.6.14`: **계약 외부 검토분 정렬(2026-07-14, cdGTS 0.1.61 동형)** — rollback `--db=keep|restore`
  분리(기본 keep + migration 시 keep 가드), pre-deploy 스냅샷 `.mig` 사이드카, 매니페스트
  `contract_version`/`rollback_db`, self-heal 추출 안전망(`bash -n`+`.previous`). 마이그레이션 없음.
  + **m710q 테스트 target 신설**(`deploy-dev.sh`, HOST_PORT=8005, DB=dev_data 미러 복사본) —
  전 구간(추출 안전망·`.mig` 61 기록·rollback keep 가드 61=61 통과·smoke)을 테스트 배포로 검증(devlog 087).
  ⚠️ 운영(dolfinid) 반영은 이 버전 prod 배포 시 self-heal 추출로 — 그 전까지 운영 `rollback.sh` 는
  구계약(이미지+DB 복원 묶음)이므로, 배포 전에 롤백이 필요하면 그 점을 감안할 것.
- `0.6.12 배포 후기(2026-07-13)`: 배포 성공(smoke PASS, club=1·match=28). 단 **[6/7] DB 게이트가
  false-fail 로 중단**(컨테이너에 `DJANGO_SETTINGS_MODULE` 없음 → 순수 `python -c` 가
  ImproperlyConfigured) — `manage.py shell -c` 로 수정, 다음 배포부터 self-heal 반영.
  운영 `.env` 는 `HOST_PORT=8004`(매니페스트 8003 표기 교정).
- `0.6.12(예정)`: **데이터 레인 Track B** — `seed_seocho_k7` 은퇴(이미지에 명령 없음 — 운영
  데이터는 이미 운영 DB 에, 이후 입력은 in-app 만). 입상·부문 오버라이드·클럽 운영진 웹 관리화,
  소유자/운영진 역할 분리. 마이그레이션 없음.
- `0.6.12(예정)`: **배포 계약 Track A** — /healthz 신설, git-free 배포 전환.
  ① 이 버전을 **구 방식**(`git pull` + `sync_to_srv.sh` + `/srv/fcmanager/deploy.sh 0.6.12`)으로
  마지막 1회 배포하거나, `sync_to_srv.sh` 로 부트스트랩 래퍼(`deploy-prod.sh`·`_extract_and_deploy.sh`)를
  먼저 심을 것. ② 이후부터는 빌드 호스트에서 `./deploy/remote-prod.sh X.Y.Z` 한 줄(git-free).
  ③ nginx 변경 불요(healthz 는 로컬 127.0.0.1:8003 검증).
- `0.6.9~0.6.11`: 서초 K7 시드(`seed_seocho_k7`) 릴리스 — 운영 반영은 배포 후
  `docker exec fcmanager python manage.py seed_seocho_k7` 수동 실행(위 레인 위반 냄새 참조).
