#!/usr/bin/env bash
# 테스트(개발) 서버 — 운영 백업 미러(dev_data)를 바라보고 기동.
#
# 데이터는 repo 의 db.sqlite3/media 가 아니라 ~/dev_data/fcmanager 를 사용한다.
# 이 디렉토리는 daily 백업(backup-fcmanager.sh step 8)이 매일 운영 미러로 갱신한다.
# (fsis2026 의 dev_data 패턴과 동일 — 서버는 repo 에서 돌고, 데이터만 분리)
#
# 사용: source ~/venv/FcSky/bin/activate && ./scripts/run-testserver.sh [PORT]
set -euo pipefail

DEV_DATA_DIR="${DEV_DATA_DIR:-/home/jikhanjung/dev_data/fcmanager}"
PORT="${1:-8000}"
cd "$(dirname "$0")/.."

if [ ! -f "${DEV_DATA_DIR}/db.sqlite3" ]; then
  echo "ERROR: ${DEV_DATA_DIR}/db.sqlite3 없음. 먼저 backup-fcmanager.sh 가 dev_data 를 채워야 함." >&2
  echo "       (수동: cp ~/backups/fcmanager/current/db.sqlite3 ${DEV_DATA_DIR}/)" >&2
  exit 1
fi

export DATABASE_PATH="${DEV_DATA_DIR}/db.sqlite3"
export MEDIA_ROOT="${DEV_DATA_DIR}/media"
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS='*'   # LAN/타 기기 접근용 — 개발 한정

echo "테스트 서버: DB=${DATABASE_PATH} (운영 백업 미러)"
exec python manage.py runserver "0.0.0.0:${PORT}"
