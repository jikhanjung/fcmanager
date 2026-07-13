#!/bin/bash
# deploy/remote-prod.sh — (빌드 호스트 m710q 전용) 운영 서버에 원격 배포하는 얇은 래퍼.
# 운영 서버의 /srv/fcmanager/deploy-prod.sh 를 SSH 로 실행할 뿐 — `ssh dolfinid '/srv/fcmanager/deploy-prod.sh …'`
# 한 줄을 손으로 치는 것과 동일하다. 실제 배포 로직은 전부 운영 서버 쪽(이미지에서 self-heal).
#
# Usage: ./deploy/remote-prod.sh X.Y.Z
# Env:
#   PROD_HOST   원격 SSH 대상 (기본 dolfinid — m710q SSH config alias, 키 인증)
#   PROD_DEPLOY 원격 배포 스크립트 경로 (기본 /srv/fcmanager/deploy-prod.sh)
set -euo pipefail

VERSION=${1:-}
if [ -z "$VERSION" ]; then
    echo "Usage: $0 X.Y.Z" >&2
    exit 1
fi

PROD_HOST=${PROD_HOST:-dolfinid}
PROD_DEPLOY=${PROD_DEPLOY:-/srv/fcmanager/deploy-prod.sh}

echo "=== remote deploy → ${PROD_HOST}:${PROD_DEPLOY} $* ==="
# ssh 가 인자를 공백으로 이어 원격 셸에 전달(버전은 단순 토큰이라 인용 이슈 없음).
exec ssh "$PROD_HOST" "$PROD_DEPLOY" "$@"
