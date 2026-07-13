#!/bin/bash
# /srv/fcmanager/deploy-prod.sh — 프로덕션 배포(dolfinid, git-free). 배포 전 DB 스냅샷을 뜬다.
# Usage: /srv/fcmanager/deploy-prod.sh X.Y.Z
#
# 운영 서버는 앱 소스(repo/git)가 필요 없다 — 모든 host 파일을 **이미지**(/app/deploy/host/*)에서
# 추출한다(_extract_and_deploy.sh). 부트스트랩 파일도 매 배포 self-heal → 최초 1회 심으면 repo 영영 불필요.
# m710q 에서 원격 원터치도 가능: ssh dolfinid '/srv/fcmanager/deploy-prod.sh X.Y.Z'
set -euo pipefail
DEPLOY_SNAPSHOT=1 exec "$(dirname "$0")/_extract_and_deploy.sh" "$@"
