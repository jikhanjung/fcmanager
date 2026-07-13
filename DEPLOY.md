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
**운영 호스트 (dolfinid) — git pull/sync 불요:**
```
/srv/fcmanager/deploy-prod.sh X.Y.Z    # 이미지에서 host 파일 추출 → 스냅샷 → 스왑 → migrate → DB게이트 → smoke
# 원격 원터치: ssh dolfinid '/srv/fcmanager/deploy-prod.sh X.Y.Z'
# 문제 시:     /srv/fcmanager/rollback.sh <이전 X.Y.Z>
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

- `apps/matches/management/commands/seed_seocho_k7.py` — **실제 팀·실경기 결과·이벤트·명단**을
  리포에 커밋해 배포로 밀어넣음(devlog 078·080·081). 계약 문서가 명시한 그 냄새.
  멱등(get_or_create)이라 삭제 footgun 은 아니지만 경계 위반. 운영 반영은 배포와 별개로
  `docker exec fcmanager python manage.py seed_seocho_k7` 수동 실행.
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

복원은 **컨테이너 정지 후**(SQLite WAL torn-copy 방지) — `rollback.sh` 가 표준 경로.

---

## 릴리스별 운영 델타 노트 (append-only)

> 형식: `버전: 운영에 필요한 것 한두 줄`. 없으면 안 적는다(코드/템플릿 전용).

- `0.6.12(예정)`: **배포 계약 Track A** — /healthz 신설, git-free 배포 전환.
  ① 이 버전을 **구 방식**(`git pull` + `sync_to_srv.sh` + `/srv/fcmanager/deploy.sh 0.6.12`)으로
  마지막 1회 배포하거나, `sync_to_srv.sh` 로 부트스트랩 래퍼(`deploy-prod.sh`·`_extract_and_deploy.sh`)를
  먼저 심을 것. ② 이후부터는 `/srv/fcmanager/deploy-prod.sh X.Y.Z` 한 줄(git-free).
  ③ nginx 변경 불요(healthz 는 로컬 127.0.0.1:8003 검증).
- `0.6.9~0.6.11`: 서초 K7 시드(`seed_seocho_k7`) 릴리스 — 운영 반영은 배포 후
  `docker exec fcmanager python manage.py seed_seocho_k7` 수동 실행(위 레인 위반 냄새 참조).
