#!/bin/bash
# /srv/fcmanager/deploy-dev.sh — 개발/테스트 배포(git-free, m710q test target). 스냅샷 없음
# (DB = 운영 백업 미러 복사본, 폐기 가능 — dev_data 패턴). Usage: /srv/fcmanager/deploy-dev.sh X.Y.Z
# host 운영 파일은 이미지에서 추출(_extract_and_deploy.sh) — 테스트 호스트도 repo/git pull 불필요.
set -euo pipefail
DEPLOY_SNAPSHOT=0 exec "$(dirname "$0")/_extract_and_deploy.sh" "$@"
