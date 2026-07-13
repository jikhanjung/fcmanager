#!/bin/bash
# /srv/fcmanager/rollback.sh — 이전 이미지 태그로 되돌리고 pre_deploy DB 스냅샷 복원 (계약 rollback 동사).
# Usage: /srv/fcmanager/rollback.sh <이전 X.Y.Z>
#
# DB 복원은 backup/pre_deploy 의 **최신** 스냅샷을 쓴다 — deploy.sh 가 방금(문제의) 배포 직전에
# 뜬 것이라 롤백 목표 상태와 일치. 그 배포 창에서 쌓인 운영 쓰기는 유실된다(스냅샷 롤백의 본질).
# 다단계 롤백은 스냅샷 파일을 명시해 수동 복원. 스냅샷이 없으면(최초) 이미지만 되돌린다.
# 복원은 컨테이너 정지 후(SQLite torn-copy 방지). down~up 사이 nginx 502 → maintenance.html.
set -euo pipefail

ROOT=/srv/fcmanager
cd "$ROOT"

PREV="${1:-}"
if [ -z "$PREV" ]; then echo "Usage: $0 <이전 X.Y.Z>"; exit 1; fi

echo "=== rollback → ${PREV} ==="
docker compose down

SNAP=$(ls -1t "$ROOT"/backup/pre_deploy/fcmanager_pre_deploy_*.sqlite3 2>/dev/null | head -n1 || true)
if [ -n "$SNAP" ]; then
    echo "  restore DB ← ${SNAP}"
    cp -p "$SNAP" "$ROOT/db.sqlite3"
    [ -f "${SNAP}-wal" ] && cp -p "${SNAP}-wal" "$ROOT/db.sqlite3-wal" || rm -f "$ROOT/db.sqlite3-wal"
    [ -f "${SNAP}-shm" ] && cp -p "${SNAP}-shm" "$ROOT/db.sqlite3-shm" || rm -f "$ROOT/db.sqlite3-shm"
else
    echo "  (pre_deploy 스냅샷 없음 — DB 복원 건너뜀; 최초 배포?)"
fi

echo "  IMAGE_TAG → ${PREV}"
if grep -q '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${PREV}/" .env
else
    echo "IMAGE_TAG=${PREV}" >> .env
fi
docker pull "honestjung/fcmanager:${PREV}"
docker compose up -d

echo "=== rolled back to ${PREV} — /srv/fcmanager/smoke.sh ${PREV} 로 확인 권장 ==="
