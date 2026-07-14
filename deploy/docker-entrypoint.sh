#!/bin/sh
# 컨테이너 시작: (root) 마운트 소유 uid 감지 → gosu 권한 드롭 → migrate(+선택적 관리자 생성) → 본 명령.
set -e
umask 002

HOSTDB=/app/hostdb

# --- 비-root 실행(권한 드롭, cdGTS entrypoint 동형) ---
# DB 는 $HOSTDB 디렉터리 바인드(-wal/-journal 형제 파일을 호스트와 공유). 컨테이너 프로세스가
# 그 디렉터리 소유 uid 로 돌아야 저널 생성이 된다. 호스트마다 소유 uid 가 달라서 Dockerfile 의
# USER 고정으로는 어긋난다(계약 "디렉터리 마운트 소유권 함정", devlog 088 — dolfinid 실측).
# 대신 root 로 시작해 마운트 소유자를 런타임 감지, 그 uid 로 gosu 드롭 — 호스트 무관·chown 불요.
# 마운트가 root 소유면 그대로 root(폴백). collectstatic 은 빌드 타임이라 여기선 불요.
if [ "$(id -u)" = "0" ] && [ -d "$HOSTDB" ]; then
  UID_T=$(stat -c %u "$HOSTDB"); GID_T=$(stat -c %g "$HOSTDB")
  if [ "$UID_T" != "0" ]; then
    # 과거 실행이 남긴 다른 uid 소유 DB 형제 파일이 있으면 드롭 후 못 쓰니 소유 정리(멱등).
    chown "${UID_T}:${GID_T}" "$HOSTDB"/db.sqlite3* 2>/dev/null || true
    echo "[entrypoint] drop -> uid ${UID_T}:${GID_T} (owner of ${HOSTDB})"
    exec gosu "${UID_T}:${GID_T}" "$0" "$@"
  fi
  echo "[entrypoint] ${HOSTDB} is root-owned -> staying root"
fi

# --- 드롭 후(비-root) 또는 root 폴백/마운트 없음(로컬 개발) ---
echo "[entrypoint] migrate..."
python manage.py migrate --noinput

# DJANGO_SUPERUSER_USERNAME/PASSWORD 지정 시 관리자 계정 생성(없을 때만).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "[entrypoint] ensure superuser '$DJANGO_SUPERUSER_USERNAME'..."
  python manage.py createsuperuser --noinput \
    --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" 2>/dev/null \
    || echo "[entrypoint] superuser already exists, skip."
fi

exec "$@"
