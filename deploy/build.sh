#!/bin/bash
# build.sh — 테스트 + 버전 bump + docker build/push. (개발기 m710q 전용)
# Usage: ./deploy/build.sh X.Y.Z
#
# 책임 분리:
#   - 본 스크립트: 개발기에서 test + bump(config/version.py) + docker build + push(버전·latest)
#   - 운영 호스트(dolfinid) 측은 git-free: deploy-prod.sh 가 이미지에서 host 파일을 추출.
#     최초 1회 부트스트랩만 deploy/sync_to_srv.sh (DEPLOY.md 참조).
set -e

VERSION=$1
if [ -z "$VERSION" ]; then
    echo "Usage: $0 X.Y.Z"
    exit 1
fi

VENV="${VENV:-$HOME/venv/fcmanager/bin/activate}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE=honestjung/fcmanager

cd "$PROJECT_DIR"

echo "=== [1/4] Running tests ==="
source "$VENV"
python manage.py test
echo "All tests passed."

echo ""
echo "=== [2/4] Bumping version to $VERSION ==="
echo "VERSION = '$VERSION'" > config/version.py
git add config/version.py
if git diff --cached --quiet; then
    echo "(version already at $VERSION, no commit)"
else
    git commit -m "Bump version to $VERSION"
fi

echo ""
echo "=== [3/4] Building image $IMAGE:$VERSION ==="
docker build -f deploy/Dockerfile --build-arg APP_VERSION="$VERSION" \
    -t "$IMAGE:$VERSION" -t "$IMAGE:latest" .

echo ""
echo "=== [4/4] Pushing image ==="
docker push "$IMAGE:$VERSION"
docker push "$IMAGE:latest"

echo ""
echo "=== Done: $IMAGE:$VERSION ==="
echo ""
echo "다음 단계 (git-free — dolfinid 에 repo/git pull 불요):"
echo "  ssh dolfinid '/srv/fcmanager/deploy-prod.sh $VERSION'   # 추출→스냅샷→스왑→smoke"
echo "  (최초 1회만 부트스트랩: deploy/sync_to_srv.sh — DEPLOY.md 참조)"
