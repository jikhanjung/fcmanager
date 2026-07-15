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
| pre-deploy 스냅샷 | dolfinid `/srv/fcmanager/backup/pre_deploy/` (deploy.sh 가 down 직후) | 최근 20개 (3-repo 공통, 2026-07-14 통일) |
| daily 미러 | m710q `~/backups/fcmanager/` + `~/dev_data/fcmanager/` (backup-fcmanager.sh, 05시) | 스크립트 참조 |

복원은 **컨테이너 정지 후**(SQLite WAL torn-copy 방지) — `rollback.sh --db=restore` 가 표준 경로.
`rollback.sh` 기본은 `--db=keep`(코드만 롤백) — 복원이 배포 후 운영 입력분까지 지우면 rollback
자신이 위 불변식을 깨기 때문. 직전 배포에 migration 이 있었으면 keep 가드가 차단(스냅샷 `.mig`
사이드카 vs 현재 적용 수 비교 — `--db=restore` 또는 수동 판단 후 `--force`).

---

## 릴리스별 운영 델타 노트 (append-only)

> 형식: `버전: 운영에 필요한 것 한두 줄`. 없으면 안 적는다(코드/템플릿 전용).

- `0.6.24`: **hourly 백업 무결성 게이트 + `/healthz` degraded**(cdGTS 0.1.68 포팅, devlog 094).
  마이그레이션 없음. 조치 불요 — 배포하면 `scripts/backup_db.py` 가 self-heal 추출로 갱신된다.
  **배포 후기(2026-07-15)**: 7/7 완주·smoke PASS. self-heal 갱신 확인 + 운영 라이브 DB 실행 =
  integrity ok·tar ok·**스냅샷 journal_mode=delete**·부산물 0. 센티넬 배선도 운영에서 직접 태워
  확인(degraded 200 → smoke FAIL exit 1 → 자기해제 → ok).
  - **`smoke` 가 실패할 새 사유가 생겼다**: `status=degraded`(HTTP **200**) = hourly 백업이 운영 DB
    손상을 발견해 `db/INTEGRITY_FAIL` 센티넬을 올린 상태. **배포 문제가 아니고, 반사적 롤백은 답이
    아닐 수 있다** — `--db=keep` 은 손상을 그대로 두고, `--db=restore` 는 스냅샷이 성한지 사람이
    판단해야 한다. 배포를 멈추고 `backup/` 의 과거 스냅샷·`backup/fcmanager_INTEGRITY_FAIL.corrupt`
    (증거 사본)를 먼저 볼 것. 해제는 자동(다음 정시 검사 통과 시) 또는 `rm db/INTEGRITY_FAIL`.
  - `/healthz` 의 실패 `status` 값이 `error` → **`unhealthy`** 로 바뀜(계약 3종 이름 정렬). 소비자는
    smoke 뿐이고 판정은 `== "ok"` 라 무영향.
  - 요건: cron 사용자(honestjung)가 `db/` 에 쓸 수 있어야 센티넬이 선다(현재 `ubuntu:ubuntu` g+w +
    honestjung 이 ubuntu 그룹 → 성립, 2026-07-15 실측). 못 써도 **로테이션 보존은 동작**하고 degraded
    경로만 죽는다.
- `0.6.24`: **m710q daily 미러 정합성**(repo 밖 `~/scripts/backup-fcmanager.sh` — **호스트에 복사해야
  반영됨**, self-heal 없음. 2026-07-15 설치·실행 검증 완료).
  - 라이브 DB scp(torn copy 위험) → **운영 hourly 스냅샷 pull + 로컬 integrity 재검증**. 검증 실패 시
    30일/90일 계층 정리를 건너뛴다. 최신 스냅샷이 **2h 초과로 낡으면 실패 + telegram** (= hourly 중단
    또는 무결성 게이트가 채택 차단 중 → 운영 DB 손상 신호. **배포와 무관하게 매일 도는 탐지 경로**).
  - **`~/dev_data` 은퇴** — daily step 8 이 m710q 테스트 타깃 `/srv/fcmanager/db` 를 직접 갱신
    (`run-testserver.sh` 삭제, 테스트는 `:8005` 도커 타깃으로 일원화). ⚠️ 테스트 컨테이너가 DB 를 WAL 로
    쥐므로 **`docker compose down`(서비스명 없이) → 교체 + `-wal`/`-shm` 제거 → `up -d`** 로 직렬화하고
    정지 실패 시 교체하지 않는다(라이브 교체 = btree 손상, cdGTS devlog 149).
- `0.6.23`: **`MatchEvent.side` OUR/OPPONENT → HOME/AWAY 데이터 마이그레이션**(0019 alter + 0020
  RunPython, reverse 제공) — entrypoint `migrate` 가 자동 적용, 스왑 직전 스냅샷이 안전망.
  변환은 경기별 우리 entry 홈/원정 기준(0020 은 historical 모델이라 `CompetitionEntry.club_id`
  프로퍼티 대신 team FK 로 계산 — 0.6.22 에서 이 함정으로 migrate crash, 0.6.23 에서 수정).
  **운영 후속 작업(1회)**: 경기 결과 `.md`(리포 밖 `data/results/`, gitignore) 를 컨테이너에
  넣어 `import_results *.md --dry-run`→`--apply`. **2026-07-14 실행 완료** — 2026-07-12 K7 서초
  3경기(#15/#16/#22) 스코어·득점자 반영, `.md` 이벤트 섹션이 그 경기 이벤트의 단일 소스(삭제 후
  재구성·멱등)라 #15 기존 콘솔 2골은 파일이 포함(14'/21' 로 시간 갱신). `import_results` 는
  seed 아님(명시 파일 기반 멱등 import) — has_seed=false 불변식과 무관.
- `0.6.21`: **gosu 드롭 시 `HOME=/tmp`(+`MPLCONFIGDIR`) 명시**(entrypoint, fsis 0.5.82 동형 — 3-repo
  수렴). 미등록 numeric uid 의 HOME 이 비쓰기 경로로 남아 HOME 쓰기 라이브러리 추가 시 잠복 크래시하는 함정의
  선제 차단. 동작 무변화(현 코드는 HOME 미사용), 마이그레이션 없음. 운영 배포 완료(2026-07-14,
  드롭 후 `HOME=/tmp` 실측 — PID 1 environ 은 setuid 로 non-dumpable 이라 one-off `compose run` 으로 확인).
- `0.6.19`: **SQLite WAL 전환**(settings OPTIONS `init_command: PRAGMA journal_mode=WAL` +
  `timeout=20`·`transaction_mode=IMMEDIATE`, cdGTS 동형) — reader 가 writer 에 안 막힘.
  `-wal`/`-shm` 형제 파일은 디렉터리 마운트(0.6.16)로 호스트 공유, hourly 백업은 online
  backup API 라 WAL-안전, 스냅샷·rollback·daily 미러는 이미 wal/shm 동반 복사. 마이그레이션 없음.
  WAL 은 DB 파일에 영속 — 이후 구버전으로 롤백해도 WAL 유지(구버전 sqlite 도 읽기 호환).
- `0.6.18`: **gosu 권한 드롭 도입** — 컨테이너가 root 로 시작해 `/app/hostdb` 마운트의 **소유
  uid 를 런타임 감지** 후 `exec gosu <uid:gid>` 로 드롭, gunicorn 은 비-root 로 돎(cdGTS 동형).
  Dockerfile `USER appuser`(uid 1000 고정) 제거 — **0.6.16 소유권 함정의 근본 해소**(호스트별
  uid 매핑 무관, chown 불요. "db/ 는 uid 1000 소유" 요건 소멸 — 임의 비-root 소유면 됨).
  entrypoint 가 이전 실행이 남긴 DB 형제 파일 소유도 멱등 정리. 마이그레이션 없음.
- `0.6.16`: **DB 파일 마운트 → 디렉터리 마운트**(`/srv/fcmanager/db` → `/app/hostdb`,
  `DATABASE_PATH=/app/hostdb/db.sqlite3` compose 고정 — fsis2026 패턴, WAL 형제 파일 호스트 공유).
  구 레이아웃(루트 `db.sqlite3`)은 **deploy.sh 가 down 직후 1회 자동 이행**(db/ 로 mv, wal/shm 포함).
  hourly `backup_db.py` 는 새 경로 + legacy fallback. **m710q daily 미러(`~/scripts/backup-fcmanager.sh`,
  repo 밖)는 별도 수정 필요**(scp 경로 `db/db.sqlite3` — 2026-07-14 수정 완료). DB 게이트 기대값
  `/app/hostdb/db.sqlite3` 로 변경. 마이그레이션 없음(스키마 무변).
  **⚠️ 배포 후기**: dolfinid 에서 **쓰기 readonly 장애** — 컨테이너 uid 1000(=ubuntu)이 deploy 가
  만든 `db/`(honestjung 소유) 디렉터리에 쓰기 불가 → `-journal` 생성 실패. 파일 마운트 시절엔
  저널이 컨테이너 내부 `/app` 에 생겨 안 걸리던 조건. `sudo chown -R 1000:1000 /srv/fcmanager/db`
  로 복구(2026-07-14). **디렉터리 마운트 요건: `db/` 는 uid 1000 소유(또는 쓰기 가능)여야 함.**
  → **0.6.18 에서 요건 소멸**(gosu 가 소유 uid 를 감지해 그 uid 로 드롭 — 위 델타 노트).
- `0.6.17`: DB 게이트에 **쓰기 프로브** 추가 — 경로 검증(읽기)만으로 못 잡는 위 소유권 함정을
  배포 시점에 기계적으로 적발(CREATE/DROP probe 테이블, readonly 면 배포 실패).
- `0.6.15`: compose `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` 파라미터화
  (`${VAR:-운영기본값}` — 운영 .env 미설정이면 종전과 동일, 테스트 호스트만 .env 로 override).
  **m710q 테스트 배포 검증 후 운영 배포 완료(2026-07-14)** — 이 배포로 0.6.14 의 계약
  정렬분(rollback `--db` 분리·`.mig`·추출 안전망)이 운영에 self-heal 착지.
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
