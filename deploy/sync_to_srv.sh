#!/bin/bash
# deploy/sync_to_srv.sh — 운영 호스트(dolfinid) 측 sync 진입점
#
# 개발 소스(/home/honestjung/projects/FcSky)는 git 체크아웃일 뿐, 런타임으로 직접 쓰지 않는다.
# 배포 때 운영에 필요한 파일만 골라 /srv/FcSky 로 복사한다.
#
# 사용 (dolfinid 에서 git pull 직후):
#   cd ~/projects/FcSky
#   git pull
#   ./deploy/sync_to_srv.sh
#   /srv/FcSky/deploy.sh X.Y.Z          # 이어서 컨테이너 교체
#
# 복사 대상:
#   scripts/backup_db.py        → /srv/FcSky/scripts/   (호스트 hourly cron 이 실행)
#   deploy/host/docker-compose.yml → /srv/FcSky/        (런타임 compose)
#   deploy/host/deploy.sh       → /srv/FcSky/           (버전 스왑 스크립트)
#
# .env 는 비밀값이라 동기화하지 않는다(운영 /srv/FcSky/.env 에서 호스트가 직접 관리).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOST_DEST="${HOST_DEST:-/srv/FcSky}"

if [ ! -d "$HOST_DEST" ]; then
    echo "ERROR: $HOST_DEST 없음 — 이 스크립트는 운영 호스트(dolfinid)에서만 실행." >&2
    exit 1
fi

echo "=== [1/2] scripts/backup_db.py → $HOST_DEST/scripts/ ==="
mkdir -p "$HOST_DEST/scripts"
cp -p "$PROJECT_DIR"/scripts/backup_db.py "$HOST_DEST/scripts/"
echo "  1 file synced."

echo ""
echo "=== [2/2] deploy/host/* → $HOST_DEST/ ==="
cp -p "$PROJECT_DIR"/deploy/host/docker-compose.yml "$HOST_DEST/"
cp -p "$PROJECT_DIR"/deploy/host/deploy.sh          "$HOST_DEST/"
chmod +x "$HOST_DEST/deploy.sh"
echo "  2 files synced + deploy.sh executable."

echo ""
echo "=== Done. 다음: /srv/FcSky/deploy.sh X.Y.Z ==="
