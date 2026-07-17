# 20260717_097 — rollback restore 복원 직전 무결성 게이트

> 성격: **백업 레인 부채 마무리.** [094](20260715_094_백업_무결성게이트_daily미러_정합성.md) 이
> 남긴 미해결 1건(“채택 전 검증 MUST 가 복원 경로엔 미적용”)을 닫는다.
> 계기: 사용자 — *"테스트 서버도 버전 업데이트 해줘"* · *"rollback restore 스냅샷 무결성 검사 추가 해줘"*
> 릴리스: 코드(정본 `deploy/host/rollback.sh`) 변경 — **다음 이미지 빌드·배포 때 self-heal 로 운영 반영**.

## 1. 한 줄

`rollback.sh --db=restore` 가 복원할 pre_deploy 스냅샷을 **복원 직전에** `PRAGMA integrity_check`
하고, 손상이면 **`docker compose down` 전에** 중단한다(라이브 DB·서비스 불변).

## 2. 배경 — 게이트가 지키던 것과 못 지키던 것

0.6.24(devlog 094)의 채택 게이트는 **hourly backup_db.py 가 방금 만든 '새' 스냅샷**만 검사한다:
integrity 통과해야 채택하고, 실패면 prune 도 막아 로테이션 오염을 방지한다.

그런데 `rollback.sh --db=restore` 는 로테이션에 **이미 있는** 최신 pre_deploy 스냅샷을 고른다.
그 후보가

- 채택 게이트가 생기기 **이전**에 들어왔거나,
- 사람이 **수동으로** 갖다 놓았거나,

하면 **무검증으로 라이브에 오른다** = 손상을 되살릴 마지막 경로. "채택 전 검증 MUST" 가 복원
경로엔 구멍이 나 있었다.

## 3. 처방

restore 분기에 복원 후보 무결성 검사를 넣었다. 핵심 3가지:

1. **검사 시점 = `docker compose down` 전.** 후보가 못 쓸 것이면 서비스를 내리지도, 라이브 DB 를
   건드리지도 않고 멈춘다. 실패 모드가 "서비스 내려간 채 손상 DB" 가 아니라 "아무것도 안 바뀜".
2. **WAL 까지 반영해서 검사.** pre_deploy 스냅샷은 `compose down` 직후 raw `cp` 라 `-wal`/`-shm`
   사이드카가 딸릴 수 있고(deploy.sh), 실제 복원은 그 WAL 도 라이브로 옮긴다. 그래서 스냅샷(+사이드카)을
   **임시 사본에 펼쳐 rw 로 열어** `integrity_check` — WAL 이 반영된 최종 상태를 검사한다. 원본 스냅샷 불변.
3. **자동으로 다른 스냅샷을 고르지 않는다.** 손상 감지 시 중단만 하고 다른 후보·수동 복원 절차를
   **안내**한다. "손상 감지 시 자동 롤백/자동 대체"는 계약이 반려한다 — 사람에게 넘긴다.

검사기는 `python3`(sqlite3 모듈)을 쓴다 — backup_db.py·hourly cron 이 이미 상시 쓰는 도구라
운영/테스트 두 호스트 모두 보장된다(호스트 `sqlite3` CLI 유무에 의존하지 않음).

## 4. 검증

- `bash -n` 문법 통과.
- **함수 격리 테스트**: 정상 DB → 통과, 랜덤 헤더 손상 → 차단, sqlite 아님 → 차단, WAL 모드 DB → 통과.
- **end-to-end(테스트 서버 :8005)**: 손상 스냅샷을 최신 mtime 으로 주입 → `rollback.sh 0.6.24
  --db=restore` → `열기/PRAGMA 실패: file is not a database` 로 **exit 1**, 컨테이너는 0.6.25 로
  **여전히 up**(down 미실행 확인). 이후 손상 후보 제거.
- 실제 pre_deploy_0.6.14 스냅샷 → `integrity_check` **ok**(false-positive 없음).

## 5. 반영 경계 → 배포 완료

정본은 **repo `deploy/host/rollback.sh`** 이고, 운영/테스트 `/srv/fcmanager/rollback.sh` 는 배포 때
이미지에서 self-heal 추출된다. **0.6.26 으로 빌드(`build.sh 0.6.26`, 112 tests OK)+운영 배포
완료**(2026-07-17): remote-prod.sh → dolfinid 7/7·smoke PASS(`club=1, match=28`), 운영 host
`rollback.sh` 에 `_snapshot_integrity_ok` 함수 존재 확인. 테스트 서버(:8005)도 0.6.26 라인에 정렬됨.

## 6. 곁다리 — 테스트 서버 0.6.23 → 0.6.25

같은 세션에서 테스트 target(m710q)을 운영과 동일한 0.6.25 로 올렸다(`deploy-dev.sh 0.6.25`,
smoke PASS `club=1, match=28`). 미러 하나 원칙(0.6.24)에 맞춰 운영과 버전 정렬.

## 7. 남은 것

- 계약 [기록 §롤아웃](../../devdocs/wiki/deploy-data-contract-record.md#롤아웃) 추적 항목(5-repo 공통)은
  **devdocs 세션 소관** — 여기서 건드리지 않는다(공유 워킹트리, 사용자 조율).
- 이 변경을 운영에 태우려면 다음 릴리스 빌드가 필요(§5).
