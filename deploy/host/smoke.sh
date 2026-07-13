#!/bin/bash
# /srv/fcmanager/smoke.sh — 배포 계약 `smoke` 동사
# Usage: /srv/fcmanager/smoke.sh X.Y.Z
#
# /healthz 200 + 버전 일치 + DB 연결 + 핵심 행 수(club>0) 를 결정론적으로 검증.
# 가볍게 유지 — 스테이크 낮으니 무거운 모니터링은 만들지 않는다.
#
# HTTPS 리다이렉트는 nginx 담당(Django SECURE_SSL_REDIRECT 미사용)이라 fsis 의
# prod 리다이렉트 함정에 해당 없지만, 관례대로 X-Forwarded-Proto: https 를 실어
# 추후 설정 변경에도 안전하게 로컬(127.0.0.1) 평문 검증한다.
set -euo pipefail

EXPECT_VERSION=${1:-}
if [ -z "$EXPECT_VERSION" ]; then
    echo "Usage: $0 X.Y.Z"
    exit 1
fi

# deploy.sh 와 동일하게 .env HOST_PORT(기본 8003) 사용.
HOST_PORT=$(sed -n 's/^HOST_PORT=//p' /srv/fcmanager/.env 2>/dev/null || true)
HOST_PORT=${HOST_PORT:-8003}
URL="${SMOKE_URL:-http://127.0.0.1:${HOST_PORT}/healthz}"

echo "=== smoke: GET $URL (expect $EXPECT_VERSION) ==="

BODY=$(curl -fsS -m 5 \
    -H "X-Forwarded-Proto: https" \
    "$URL") || { echo "FAIL: /healthz 요청 실패 (연결/타임아웃/HTTP 오류)"; exit 1; }

echo "  response: $BODY"

# stdlib python3 로 JSON 검증 (호스트에 jq 의존 안 함)
EXPECT_VERSION="$EXPECT_VERSION" python3 - "$BODY" <<'PY'
import json, os, sys
body = sys.argv[1]
expect = os.environ["EXPECT_VERSION"]
try:
    d = json.loads(body)
except Exception as e:
    print(f"FAIL: JSON 파싱 불가 — {e}")
    sys.exit(1)

errs = []
if d.get("status") != "ok":
    errs.append(f"status={d.get('status')!r} (기대 'ok', error={d.get('error')!r})")
if d.get("db") is not True:
    errs.append(f"db={d.get('db')!r} (기대 True)")
if d.get("version") != expect:
    errs.append(f"version={d.get('version')!r} (기대 {expect!r})")
# 도메인 불변식 1개: 클럽 행 수>0 (운영엔 항상 최소 1개 클럽 존재)
club = (d.get("counts") or {}).get("club")
if not isinstance(club, int) or club <= 0:
    errs.append(f"counts.club={club!r} (기대 정수>0)")

if errs:
    print("FAIL:")
    for e in errs:
        print(f"  - {e}")
    sys.exit(1)
print(f"PASS: version={expect}, db=ok, club={club}, match={(d.get('counts') or {}).get('match')}")
PY

echo "=== smoke OK ==="
