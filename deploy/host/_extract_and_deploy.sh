#!/bin/bash
# /srv/fcmanager/_extract_and_deploy.sh — git-free 배포 코어. deploy-prod.sh 가 호출.
# 이미지에서 host 파일을 추출한 뒤 그 (갓 추출한) deploy.sh 로 위임한다. **운영 서버 repo/git pull 불필요.**
#
# 자기 치유(self-heal): 부트스트랩 파일(deploy-prod.sh · 이 스크립트)도 이미지에서 매 배포 갱신.
#   - deploy-prod.sh: 이미 exec 로 넘어와 프로세스가 사라졌으니 덮어써도 안전(즉시 반영).
#   - 이 스크립트 자신: 임시파일 → 원자 rename. 실행 중 bash 는 옛 inode 를 계속 읽고, 새 버전은 다음 배포부터.
# → 최초 1회만 부트스트랩(sync_to_srv.sh 또는 이미지에서 docker cp)하면, 이후 모든 파일이
#   이미지에서 자기 치유 → git 영영 불필요.
#
# 호출: DEPLOY_SNAPSHOT=0|1 /srv/fcmanager/_extract_and_deploy.sh X.Y.Z
# 상시 존재해야 하는 호스트 파일 = 이 스크립트 + deploy-prod.sh + .env.
set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then echo "Usage: DEPLOY_SNAPSHOT=0|1 $0 X.Y.Z"; exit 1; fi

ROOT=/srv/fcmanager
IMAGE="honestjung/fcmanager:${VERSION}"

echo "=== [0/7] Pull + extract host files from ${IMAGE} (git-free) ==="
docker pull "$IMAGE"

CID=$(docker create "$IMAGE")
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

# 운영 파일 — 매 배포마다 이미지에서 새로 추출.
for f in docker-compose.yml deploy.sh smoke.sh rollback.sh; do
    if docker cp "${CID}:/app/deploy/host/${f}" "${ROOT}/${f}" 2>/dev/null; then
        echo "  extracted ${f}"
    else
        echo "  (이미지에 ${f} 없음 — 구버전, 건너뜀)"
    fi
done
# backup_db.py 는 호스트 cron 이 쓰는 유일한 스크립트 — 이미지에서 함께 갱신.
mkdir -p "${ROOT}/scripts"
docker cp "${CID}:/app/scripts/backup_db.py" "${ROOT}/scripts/backup_db.py" 2>/dev/null \
    && echo "  extracted scripts/backup_db.py" || true

# 부트스트랩 래퍼 — exec 로 넘어와 안전. 즉시 반영.
docker cp "${CID}:/app/deploy/host/deploy-prod.sh" "${ROOT}/deploy-prod.sh" 2>/dev/null \
    && echo "  self-heal deploy-prod.sh" || true
# 이 스크립트 자신 — 임시파일 후 원자 rename(옛 inode 로 계속 실행, 새 버전은 다음 배포부터).
if docker cp "${CID}:/app/deploy/host/_extract_and_deploy.sh" "${ROOT}/.ead.new" 2>/dev/null; then
    chmod +x "${ROOT}/.ead.new"; mv -f "${ROOT}/.ead.new" "${ROOT}/_extract_and_deploy.sh"
    echo "  self-heal _extract_and_deploy.sh (다음 배포부터 반영)"
fi

docker rm -f "$CID" >/dev/null; trap - EXIT
chmod +x "${ROOT}/deploy.sh" "${ROOT}/smoke.sh" "${ROOT}/rollback.sh" "${ROOT}/deploy-prod.sh" 2>/dev/null || true

echo ""
exec "${ROOT}/deploy.sh" "$@"        # 버전 그대로 전달
