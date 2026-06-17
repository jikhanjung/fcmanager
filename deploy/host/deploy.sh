#!/bin/bash
# /srv/FcSky/deploy.sh X.Y.Z — FcSky 버전 스왑 배포 (운영 호스트 dolfinid 에서 실행)
#
# 전제: deploy/sync_to_srv.sh 로 이 파일과 docker-compose.yml·scripts/backup_db.py 가
#       /srv/FcSky/ 에 이미 복사돼 있어야 한다. (개발 소스 /home/... 를 런타임으로 쓰지 않음)
#
# 흐름: 이미지 pull → .env IMAGE_TAG 갱신 → 컨테이너 down → pre-deploy DB 스냅샷 → up → 헬스체크
# 점검 페이지: down~up 사이 짧은 시간 nginx 가 502 → maintenance.html 자동 노출(devlog 023).
set -euo pipefail

VERSION=${1:-}
if [ -z "$VERSION" ]; then
    echo "Usage: $0 X.Y.Z"
    exit 1
fi

cd /srv/FcSky
IMAGE="honestjung/fcsky:${VERSION}"

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
SNAP_DIR=/srv/FcSky/backup/pre_deploy
mkdir -p "$SNAP_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
SNAP="$SNAP_DIR/fcsky_pre_deploy_${VERSION}_${TS}.sqlite3"
cp -p /srv/FcSky/db.sqlite3 "$SNAP"
[ -f /srv/FcSky/db.sqlite3-wal ] && cp -p /srv/FcSky/db.sqlite3-wal "${SNAP}-wal" || true
[ -f /srv/FcSky/db.sqlite3-shm ] && cp -p /srv/FcSky/db.sqlite3-shm "${SNAP}-shm" || true
echo "  snapshot: $SNAP ($(du -h "$SNAP" | cut -f1))"
# retention: 최근 10개만 (hourly 12개·m710q daily 와 별개 트랙)
ls -1tr "$SNAP_DIR"/fcsky_pre_deploy_*.sqlite3 2>/dev/null \
    | head -n -10 \
    | while read -r f; do rm -f "$f" "$f-wal" "$f-shm"; done

echo ""
echo "=== [5/6] Start new container ==="
docker compose up -d

echo ""
echo "=== [6/6] 헬스체크 (백엔드 기동 대기) ==="
for i in $(seq 1 60); do
    if curl -fsS -o /dev/null -m 2 http://127.0.0.1:8003/FcSky/admin/login/ ; then
        echo "  backend up after ${i}s"
        break
    fi
    sleep 1
done

echo ""
echo "=== Done: fcsky -> ${VERSION} ==="
docker compose ps
