#!/bin/bash
# /srv/fcmanager/deploy.sh — fcmanager 버전 스왑 배포 (공통 엔진).
# 직접 부르지 말고 git-free 래퍼로 호출(이미지에서 host 파일 추출 후 이 엔진에 위임):
#   /srv/fcmanager/deploy-prod.sh X.Y.Z    (DEPLOY_SNAPSHOT=1 — 배포 전 DB 스냅샷)
# 미설정 시 DEPLOY_SNAPSHOT 기본=1 (dolfinid 는 prod 단일 호스트라 안전측 기본).
#
# 흐름: pull → .env IMAGE_TAG → down → pre-deploy DB 스냅샷 → up(전 서비스) → healthz 대기
#       → DB 바인딩 게이트 → smoke. down~up 사이 nginx 가 502 → maintenance.html 자동 노출(devlog 023).
# Usage: DEPLOY_SNAPSHOT=0|1 /srv/fcmanager/deploy.sh X.Y.Z
set -euo pipefail

VERSION=${1:-}
if [ -z "$VERSION" ]; then
    echo "Usage: $0 X.Y.Z"
    exit 1
fi

ROOT=/srv/fcmanager
cd "$ROOT"

IMAGE="honestjung/fcmanager:${VERSION}"

# 헬스체크 포트(.env HOST_PORT, 기본 8003). 병렬 운영 시 8004 등으로 override 가능.
HOST_PORT=$(sed -n 's/^HOST_PORT=//p' .env 2>/dev/null)
HOST_PORT=${HOST_PORT:-8003}

echo "=== [1/7] Pull ${IMAGE} ==="
docker pull "${IMAGE}"

echo ""
echo "=== [2/7] .env IMAGE_TAG=${VERSION} ==="
if grep -q '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${VERSION}/" .env
else
    echo "IMAGE_TAG=${VERSION}" >> .env
fi

echo ""
echo "=== [3/7] Stop old container ==="
# rollback keep 가드용: 배포 전(새 이미지의 migrate 실행 전) 적용된 migration 수를 기록.
# 컨테이너 정지 전에 조회(정지 후엔 exec 불가) — [4/7] 스냅샷의 .mig 사이드카로 저장,
# rollback.sh 가 현재 적용 수와 비교해 keep 가부를 판정한다.
PRE_MIG=""
if [ "${DEPLOY_SNAPSHOT:-1}" = "1" ]; then
    PRE_MIG=$(docker compose exec -T web python manage.py showmigrations --plan 2>/dev/null | grep -c '\[X\]' || echo "")
fi
docker compose down

# 파일→디렉터리 마운트 전환(0.6.16) 1회 자동 이행 — down 직후(writer 없음) 루트 DB 를 db/ 로 이동.
# compose 가 /srv/fcmanager/db 디렉터리를 /app/hostdb 로 마운트하므로 이 위치가 유일한 정본.
if [ -f "$ROOT/db.sqlite3" ] && [ ! -f "$ROOT/db/db.sqlite3" ]; then
    echo "  (레이아웃 이행) $ROOT/db.sqlite3 → $ROOT/db/ (파일→디렉터리 마운트, WAL 형제 포함)"
    mkdir -p "$ROOT/db"
    mv "$ROOT/db.sqlite3" "$ROOT/db/db.sqlite3"
    [ -f "$ROOT/db.sqlite3-wal" ] && mv "$ROOT/db.sqlite3-wal" "$ROOT/db/db.sqlite3-wal" || true
    [ -f "$ROOT/db.sqlite3-shm" ] && mv "$ROOT/db.sqlite3-shm" "$ROOT/db/db.sqlite3-shm" || true
fi
mkdir -p "$ROOT/db"    # 신규 호스트(빈 DB 부트스트랩)도 마운트 대상 디렉터리는 있어야 함

echo ""
echo "=== [4/7] (prod) Pre-deploy DB 스냅샷 (롤백 안전망) ==="
# compose down 직후 — writer 없어 cp 안전. WAL/SHM 도 함께 보존.
if [ "${DEPLOY_SNAPSHOT:-1}" = "1" ] && [ -f "$ROOT/db/db.sqlite3" ]; then
    SNAP_DIR="$ROOT/backup/pre_deploy"
    mkdir -p "$SNAP_DIR"
    TS=$(date -u +%Y%m%d_%H%M%S)
    SNAP="$SNAP_DIR/fcmanager_pre_deploy_${VERSION}_${TS}.sqlite3"
    cp -p "$ROOT/db/db.sqlite3" "$SNAP"
    [ -f "$ROOT/db/db.sqlite3-wal" ] && cp -p "$ROOT/db/db.sqlite3-wal" "${SNAP}-wal" || true
    [ -f "$ROOT/db/db.sqlite3-shm" ] && cp -p "$ROOT/db/db.sqlite3-shm" "${SNAP}-shm" || true
    [ -n "$PRE_MIG" ] && printf '%s\n' "$PRE_MIG" > "${SNAP}.mig" || true
    echo "  snapshot: $SNAP ($(du -h "$SNAP" | cut -f1), pre-migration count: ${PRE_MIG:-미상})"
    # retention: 최근 20개만 (3-repo 공통 수치, 2026-07-14 통일. hourly 12개·m710q daily 와 별개 트랙, .mig 사이드카 포함)
    ls -1tr "$SNAP_DIR"/fcmanager_pre_deploy_*.sqlite3 2>/dev/null \
        | head -n -20 \
        | while read -r f; do rm -f "$f" "$f-wal" "$f-shm" "$f.mig"; done
else
    echo "  (DEPLOY_SNAPSHOT=${DEPLOY_SNAPSHOT:-1} 또는 DB 없음 — 스냅샷 건너뜀)"
fi

echo ""
echo "=== [5/7] Start new container (전 서비스) + wait for backend (/healthz) ==="
# up -d (서비스명 미지정) = compose 전 서비스. 현재 web 단일이나, 사이드카 추가 시 누락 방지(cdGTS 교훈).
docker compose up -d
# liveness: /healthz 200 대기. HTTPS 리다이렉트는 nginx 담당(Django SECURE_SSL_REDIRECT 미사용)이지만
# 관례대로 X-Forwarded-Proto 를 실어 로컬 평문 검증(추후 설정 변경에도 안전).
for i in $(seq 1 60); do
    if curl -fsS -o /dev/null -m 2 \
        -H "X-Forwarded-Proto: https" \
        "http://127.0.0.1:${HOST_PORT}/healthz" ; then
        echo "  backend up after ${i}s"
        break
    fi
    sleep 1
done

echo ""
echo "=== [6/7] Verify DB binding (host bind mount, not ephemeral image DB) ==="
# compose 는 host 디렉터리 $ROOT/db 를 /app/hostdb 로 바인드하고 DATABASE_PATH 를
# environment 로 고정한다(docker-compose.yml). 이 값이 어긋나면 컨테이너가 이미지 내부
# 빈 DB 로 폴백 → 사이트가 빈 데이터로 뜬다(실데이터는 $ROOT/db/db.sqlite3 에 안전).
EXPECT_DB=/app/hostdb/db.sqlite3
# manage.py shell 경유 — 컨테이너에 DJANGO_SETTINGS_MODULE env 가 없어 순수 python -c 는
# ImproperlyConfigured 로 죽는다(0.6.12 배포에서 false-fail 로 드러남).
DB_NAME=$(docker compose exec -T web \
    python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['NAME'])" \
    2>/dev/null | tr -d '\r' | tail -n1)
if [ "$DB_NAME" = "$EXPECT_DB" ]; then
    echo "  OK: container DB = ${DB_NAME} (host bind mount)"
    # 쓰기 프로브 — 서비스 프로세스 uid 가 db/ 디렉터리에 -journal 을 만들 수 있어야 한다.
    # 파일 마운트에선 안 걸리던 조건이라 경로 검증만으론 못 잡는다(0.6.16 dolfinid readonly 장애).
    # 0.6.18 gosu 이후 exec 기본 유저는 root 라, entrypoint 와 같은 규칙(마운트 소유 uid)으로
    # 명시해 서비스 프로세스와 동일 권한으로 프로브한다.
    PROBE_UID=$(stat -c %u "$ROOT/db" 2>/dev/null || echo 0)
    WRITE_OK=$(docker compose exec -T -u "${PROBE_UID}" web python manage.py shell -c "
from django.db import connection
c = connection.cursor()
c.execute('CREATE TABLE IF NOT EXISTS _deploy_write_probe(x INTEGER)')
c.execute('DROP TABLE _deploy_write_probe')
print('ok')" 2>/dev/null | tr -d '\r' | tail -n1)
    if [ "$WRITE_OK" = "ok" ]; then
        echo "  OK: DB write probe (journal 생성 가능)"
    else
        echo "  ✗ FATAL: DB 쓰기 프로브 실패 — 읽기는 되나 쓰기가 readonly 로 죽는 상태."
        echo "    원인(전형): 컨테이너 uid 1000 에 ${ROOT}/db 디렉터리 쓰기 권한 없음(-journal 생성 불가)."
        echo "    고치기: sudo chown -R 1000:1000 ${ROOT}/db 후 이 스크립트 재실행."
        exit 1
    fi
else
    echo "  ✗ FATAL: container DB = '${DB_NAME:-<empty>}' — 기대 ${EXPECT_DB} 아님."
    echo "    컨테이너가 마운트되지 않은 이미지 내부 DB 를 쓰고 있다 → 사이트가 빈 데이터로 뜬다."
    echo "    실데이터는 ${ROOT}/db/db.sqlite3 에 안전. compose 의 environment DATABASE_PATH 가"
    # 서비스명을 쓰지 않는다 — 안내문을 그대로 따른 사람이 사이드카를 빠뜨리면 그것만 낡은
    # DATABASE_PATH 로 남는다. 단일-서비스 가정은 실행 코드뿐 아니라 **조언에도** 박히면 버그다
    # (cdGTS 0.1.68 이 회수한 마지막 잔재 — 계약 §규범 MUST).
    echo "    ${EXPECT_DB} 인지(구 compose 로 덮였는지) 확인 후 (cd ${ROOT} && docker compose up -d --force-recreate)"
    exit 1
fi

echo ""
echo "=== [7/7] Smoke (healthz + 버전 일치 + 핵심 행 수) ==="
# smoke.sh 는 이미지에서 함께 추출됨(_extract_and_deploy.sh). 없으면 구버전 — 경고만.
if [ -x "$ROOT/smoke.sh" ]; then
    if ! "$ROOT/smoke.sh" "$VERSION"; then
        echo ""
        echo "!!! smoke 실패 — 컨테이너는 떴으나 검증 불일치(버전/DB/행수)."
        echo "!!! 조사 후 필요시 롤백: $ROOT/rollback.sh <이전 X.Y.Z> [--db=keep|restore] (기본 keep=이미지만)"
        exit 1
    fi
else
    echo "  (smoke.sh 없음 — 이미지 추출 실패? 건너뜀.)"
fi

echo ""
echo "=== Done: fcmanager -> ${VERSION} (port ${HOST_PORT}, smoke OK) ==="
docker compose ps
