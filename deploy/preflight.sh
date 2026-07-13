#!/bin/bash
# deploy/preflight.sh — 배포 전 위험 표면 점검(배포·데이터 계약 = preflight 동사). 빌드 호스트(m710q) 전용.
# 기억 의존 0: git diff 로 위험 표면을 **항상** 표면화 + seed 냄새 lint + DEPLOY.md 델타 출력.
# 뻔한 부분을 결정론적으로 고정하고, go/no-go 판단은 사람/에이전트에 남긴다.
#
# Usage: deploy/preflight.sh [<since-ref>]    기본 since = 마지막 "Bump version" 커밋(직전 릴리스 경계).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

SINCE="${1:-}"
if [ -z "$SINCE" ]; then
    SINCE=$(git log --grep='^Bump version' -n 1 --format='%H' 2>/dev/null || true)
fi

if [ -n "$SINCE" ]; then
    echo "=== preflight: 변경 표면 ${SINCE:0:9}..HEAD (+ working tree) ==="
    CHANGED=$( { git diff --name-only "$SINCE" HEAD; git status --porcelain | awk '{print $2}'; } | sort -u | sed '/^$/d')
else
    echo "=== preflight: working tree (버전 bump 커밋 없음) ==="
    CHANGED=$(git status --porcelain | awk '{print $2}' | sort -u | sed '/^$/d')
fi

hits() { echo "$CHANGED" | grep -qE "$1"; }

echo "--- 위험 표면 ---"
RISK=0
hits '(^|/)migrations/'                       && { echo "  🔴 migrations/ 변경 → migrate 자동 적용(entrypoint). 배포 전 pre_deploy 스냅샷 확인(prod)."; RISK=1; } || true
hits '\.env'                                  && { echo "  🔴 .env 관련 변경 → /srv/fcmanager/.env 반영 확인(IMAGE_TAG·HOST_PORT·SECRET·SUPERUSER)."; RISK=1; } || true
hits '(docker-compose|Dockerfile|docker-entrypoint)' && { echo "  🟡 컨테이너/compose 변경 → git-free 배포가 이미지에서 자동 추출(별도 sync 불요), 단 재확인."; RISK=1; } || true
hits '(^|/)deploy/host/'                       && { echo "  🟡 host 스크립트 변경 → 이미지에 실려 다음 배포에서 자기 치유(self-heal). 부트스트랩 래퍼(deploy-prod/_extract) 바뀌었으면 sync_to_srv.sh 1회."; RISK=1; } || true
hits '(^|/)scripts/backup_db\.py'              && { echo "  🟡 backup_db.py 변경 → 이미지 추출로 다음 배포 시 호스트 cron 스크립트 갱신됨."; RISK=1; } || true
[ "$RISK" = "0" ] && echo "  🟢 위험 표면 변경 없음(코드/템플릿 전용 추정)."

echo "--- seed 냄새 lint (운영 데이터가 seed/배포 파이프라인으로 새는가) ---"
# fcmanager 는 시스템 시드 레인이 없다(has_seed=false, deploy.toml) — 전 모델이 운영 데이터.
# 따라서 (a) 무가드 .all().delete() 는 전부 냄새(allowlist 없음),
#        (b) seed_* 명령의 존재 자체가 레인 위반 냄새(운영 데이터가 리포 경유 — 계약 §판별 기준).
SMELL=""
while IFS= read -r f; do
    [ -z "$f" ] && continue
    SMELL="${SMELL}${f}\n"
done < <(grep -rlE '\.all\(\)\.delete\(\)|objects\.all\(\)\.delete' \
            apps/*/management/commands 2>/dev/null || true)
if [ -n "$SMELL" ]; then
    echo "  🔴 무가드 전체 삭제가 있는 관리 명령(운영 데이터 전멸 footgun):"
    printf "%b" "$SMELL" | sed 's/^/     /'
else
    echo "  🟢 무가드 .all().delete() 관리 명령 없음."
fi
SEEDS=$(ls apps/*/management/commands/seed_*.py 2>/dev/null || true)
if [ -n "$SEEDS" ]; then
    echo "  🟡 seed_* 명령 존재 — fcmanager 는 시스템 시드 레인이 없으므로 운영 데이터가 리포를 경유 중(은퇴 대상, Track B):"
    echo "$SEEDS" | sed 's/^/     /'
else
    echo "  🟢 seed_* 명령 없음(레인 위반 없음)."
fi

echo "--- DEPLOY.md (권위 운영 델타 노트) ---"
if [ -f DEPLOY.md ]; then
    sed -n '/^## 릴리스별 운영 델타/,$p' DEPLOY.md | sed 's/^/  /' | head -24
else
    echo "  🟡 DEPLOY.md 없음 — 릴리스별 운영 델타 노트를 두는 게 계약 권고."
fi

echo "=== preflight 끝 — go/no-go 는 사람/에이전트 판단 ==="
