#!/bin/bash
# /srv/fcmanager/deploy.sh X.Y.Z — FCManager 버전 스왑 배포 (운영 호스트 dolfinid 에서 실행)
#
# 전제: deploy/sync_to_srv.sh 로 이 파일과 docker-compose.yml·scripts/backup_db.py 가
#       /srv/fcmanager/ 에 이미 복사돼 있어야 한다. (개발 소스 /home/... 를 런타임으로 쓰지 않음)
#
# 흐름: 이미지 pull → .env IMAGE_TAG 갱신 → 컨테이너 down → pre-deploy DB 스냅샷 → up → 헬스체크
# 점검 페이지: down~up 사이 짧은 시간 nginx 가 502 → maintenance.html 자동 노출(devlog 023).
set -euo pipefail

VERSION=${1:-}
if [ -z "$VERSION" ]; then
    echo "Usage: $0 X.Y.Z"
    exit 1
fi

cd /srv/fcmanager
IMAGE="honestjung/fcmanager:${VERSION}"

# 헬스체크 포트(.env HOST_PORT, 기본 8003). 병렬 운영 시 8004 등으로 override 가능.
HOST_PORT=$(sed -n 's/^HOST_PORT=//p' .env 2>/dev/null)
HOST_PORT=${HOST_PORT:-8003}

echo "=== [1/6] Pull ${IMAGE} ==="
docker pull "${IMAGE}"

echo ""
echo "=== [2/6] .env IMAGE_TAG=${VERSION} ==="
if grep -q '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${VERSION}/" .env
else
    echo "IMAGE_TAG=${VERSION}" >> .env
fi

echo ""
echo "=== [3/6] Stop old container ==="
docker compose down

echo ""
echo "=== [4/6] Pre-deploy DB 스냅샷 (롤백 안전망) ==="
# compose down 직후 — writer 없어 cp 안전. WAL/SHM 도 함께 보존.
SNAP_DIR=/srv/fcmanager/backup/pre_deploy
mkdir -p "$SNAP_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
SNAP="$SNAP_DIR/fcmanager_pre_deploy_${VERSION}_${TS}.sqlite3"
cp -p /srv/fcmanager/db.sqlite3 "$SNAP"
[ -f /srv/fcmanager/db.sqlite3-wal ] && cp -p /srv/fcmanager/db.sqlite3-wal "${SNAP}-wal" || true
[ -f /srv/fcmanager/db.sqlite3-shm ] && cp -p /srv/fcmanager/db.sqlite3-shm "${SNAP}-shm" || true
echo "  snapshot: $SNAP ($(du -h "$SNAP" | cut -f1))"
# retention: 최근 10개만 (hourly 12개·m710q daily 와 별개 트랙)
ls -1tr "$SNAP_DIR"/fcmanager_pre_deploy_*.sqlite3 2>/dev/null \
    | head -n -10 \
    | while read -r f; do rm -f "$f" "$f-wal" "$f-shm"; done

echo ""
echo "=== [5/6] Start new container ==="
docker compose up -d

echo ""
echo "=== [6/6] 헬스체크 (백엔드 기동 대기) ==="
for i in $(seq 1 60); do
    if curl -fsS -o /dev/null -m 2 "http://127.0.0.1:${HOST_PORT}/admin/login/" ; then
        echo "  backend up after ${i}s"
        break
    fi
    sleep 1
done

echo ""
echo "=== Done: fcmanager -> ${VERSION} (port ${HOST_PORT}) ==="
docker compose ps
