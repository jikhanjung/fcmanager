# 배포 (Docker) — 배포·데이터 계약 구현

fcmanager 의 빌드/배포 파일 구성. 계약 선언층은 [`deploy.toml`](deploy.toml),
데이터 안전 경계·릴리스 델타 노트는 루트 [`DEPLOY.md`](../DEPLOY.md),
표준 규약은 `../devdocs/wiki/deploy-data-contract.md` 참조.

## 파일 구성

```
deploy/
  deploy.toml            배포 매니페스트(선언층) — contract_version·image·target·db_path·has_seed·rollback_db·verbs
  preflight.sh           [동사] 배포 전 위험 표면 diff + seed 냄새 lint (빌드 호스트)
  build.sh               [동사] test + 버전 bump + docker build/push (빌드 호스트 m710q)
  remote-prod.sh         빌드 호스트: ssh dolfinid '/srv/fcmanager/deploy-prod.sh …' 얇은 래퍼
                         (원격 prod 배포). PROD_HOST/PROD_DEPLOY env 로 대상 변경
  sync_to_srv.sh         최초 1회 부트스트랩(host/* → /srv/fcmanager). 상시 배포엔 불필요
  Dockerfile             이미지 정의. COPY . . 로 deploy/host/*·scripts/backup_db.py 도 탑재(git-free 재료)
  Dockerfile.dockerignore
  docker-entrypoint.sh   컨테이너 기동 시 migrate + superuser 보증 (seed 없음 — DEPLOY.md 불변식)
  docker-compose.yml     로컬/개발용 compose (build: 포함)
  host/                  운영 호스트(dolfinid) 파일 — 배포 시 이미지에서 추출(self-heal)
    deploy-prod.sh         [동사 deploy 진입점] git-free 래퍼 (DEPLOY_SNAPSHOT=1)
    _extract_and_deploy.sh 이미지에서 host 파일 추출 → deploy.sh 위임 (부트스트랩 파일도 self-heal;
                           스크립트는 bash -n 통과 시에만 교체, 이전본은 .previous 보존)
    deploy.sh              배포 엔진: pull → down → 스냅샷(+.mig 사이드카) → up → healthz 대기 → DB게이트 → smoke
    smoke.sh               [동사] /healthz 200 + 버전 일치 + club>0
    rollback.sh            [동사] 코드/DB 분리 — --db=keep(기본, 이미지만 전환)|restore(스냅샷 복원).
                           keep 가드: 직전 배포에 migration 있으면 차단(.mig vs 현재 비교)
    docker-compose.yml     운영 compose (pull 전용, IMAGE_TAG는 .env)
    nginx-fcmanager.conf.example
```

## 배포 흐름

**빌드 호스트 (m710q):**
```bash
./deploy/preflight.sh          # (선택) 위험 표면 + seed 냄새 + DEPLOY.md 델타
./deploy/build.sh X.Y.Z        # test + bump(config/version.py) + build + push
```

**운영 배포 — 빌드 호스트에서 원격 원터치 (dolfinid 에 repo/git pull 불요):**
```bash
./deploy/remote-prod.sh X.Y.Z           # = ssh dolfinid '/srv/fcmanager/deploy-prod.sh X.Y.Z'
# (운영 호스트에서 직접 실행해도 동일: /srv/fcmanager/deploy-prod.sh X.Y.Z)
# 문제 시: ssh dolfinid '/srv/fcmanager/rollback.sh <이전 X.Y.Z> [--db=keep|restore]'  (기본 keep=이미지만)
```

최초 도입 1회만: repo 있는 머신에서 `./deploy/sync_to_srv.sh`, 또는 repo 없이
이미지에서 직접 `docker cp`(스크립트 머리말 참조). 이후는 매 배포가 self-heal.

## 로컬 실행

```bash
docker compose -f deploy/docker-compose.yml up --build
# → http://localhost:8003/
```

## 환경변수 (운영 /srv/fcmanager/.env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DJANGO_SECRET_KEY` | (개발용 키) | 운영에선 반드시 지정 |
| `IMAGE_TAG` | `latest` | deploy.sh/rollback.sh 가 갱신 — 손대지 말 것 |
| `HOST_PORT` | `8003` | 호스트 노출 포트(8000은 portainer 점유). 병렬 운영 시 override |
| `DJANGO_DEBUG` | `false` | |
| `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` | compose 에 지정 | fcmanager.app |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | (없음) | 지정 시 관리자 계정 보증(없을 때만 생성) |
| `DATABASE_PATH` | (미설정 = `/app/db.sqlite3`) | 설정 시 반드시 `/app/db.sqlite3` — deploy.sh DB 게이트가 검증 |

## 주의

- DB 는 SQLite 파일 마운트(`/srv/fcmanager/db.sqlite3` → `/app/db.sqlite3`). 미디어는
  `/srv/fcmanager/media`. 백업 트랙 3종은 `DEPLOY.md` 백업 지도 참조.
- HTTPS 리다이렉트는 앞단 nginx 담당 — Django `SECURE_SSL_REDIRECT` 를 켜지 말 것
  (로컬 healthz/smoke 평문 검증과 충돌, settings.py 주석 참조).
