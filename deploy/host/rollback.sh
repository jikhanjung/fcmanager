#!/bin/bash
# /srv/fcmanager/rollback.sh — 롤백 동사(계약). **코드 롤백과 DB 롤백을 분리한다.**
# Usage: /srv/fcmanager/rollback.sh <이전 X.Y.Z> [--db=keep|restore] [--force]
#   --db=keep    (기본) 이전 이미지 태그로만 전환. 현재 DB 유지(운영 데이터 보존) — 삭제 아니라 전환.
#   --db=restore pre_deploy 스냅샷 무결성 검사 → 서비스 정지 → 이전 이미지 전환 → 스냅샷 복원.
#                후보가 손상됐으면 라이브·서비스를 건드리기 전에 중단. 그 배포 창의 운영 쓰기는 유실.
#   --force      keep 가드(직전 배포에 migration 있으면 keep 차단)를 무시하고 강행.
#
# 기본이 keep 인 이유: rollback 이 배포 후 운영자 입력분까지 스냅샷 복원으로 지우면 rollback 자신이
# 불변식("파이프라인은 운영 데이터를 나르지도 지우지도 않는다")을 깬다. DB 복원은 명시적 opt-in.
# 기본값은 deploy.toml `rollback_db="keep"` 선언과 일치.
#
# keep 가드: 직전 배포가 migration 을 적용했으면 이전 코드가 새 스키마와 비호환일 수 있어 keep 을 막고
# restore/수동 판단으로 승격한다. 판정 = 최신 pre_deploy 스냅샷의 `.mig` 사이드카(배포 전 적용 migration
# 수, deploy.sh 가 기록) vs 현재 컨테이너의 적용 수 비교. 사이드카가 없으면(구 스냅샷) 미상으로 두고 진행.
# 다단계 롤백은 스냅샷 파일을 명시해 수동 복원. down~up 사이 nginx 502 → maintenance.html.
set -euo pipefail

ROOT=/srv/fcmanager
cd "$ROOT"

PREV=""
DB_MODE=keep            # deploy.toml rollback_db 기본값과 일치
FORCE=0
for a in "$@"; do
    case "$a" in
        --db=keep)    DB_MODE=keep ;;
        --db=restore) DB_MODE=restore ;;
        --force)      FORCE=1 ;;
        --*)          echo "unknown flag: $a" >&2; exit 1 ;;
        *)            PREV="$a" ;;
    esac
done
if [ -z "$PREV" ]; then
    echo "Usage: $0 <이전 X.Y.Z> [--db=keep|restore] [--force]" >&2; exit 1
fi

echo "=== rollback → ${PREV} (db=${DB_MODE}) ==="

# 최신 pre_deploy 스냅샷 = 직전 배포 1단계 되돌리기용(다단계는 스냅샷 명시).
SNAP=$(ls -1t "$ROOT"/backup/pre_deploy/fcmanager_pre_deploy_*.sqlite3 2>/dev/null | head -n1 || true)

# 스냅샷(+WAL/SHM 사이드카)을 임시 사본에 펼쳐 PRAGMA integrity_check → ok 면 0, 손상이면 1.
# rw 로 여는 이유: 스냅샷은 compose down 직후의 raw cp 라 WAL 사이드카가 딸릴 수 있고(deploy.sh),
#   실제 복원은 그 WAL 까지 라이브로 옮긴다 → WAL 을 반영한 상태를 검사해야 옳다. 사본이라 원본 불변.
# python3 을 쓰는 이유: backup_db.py·hourly cron 이 이미 상시 쓰는 도구라 두 호스트 모두 보장된다.
_snapshot_integrity_ok() {
    local snap="$1" tmpdir rc
    tmpdir=$(mktemp -d)
    cp -p "$snap" "$tmpdir/db.sqlite3"
    [ -f "${snap}-wal" ] && cp -p "${snap}-wal" "$tmpdir/db.sqlite3-wal" || true
    [ -f "${snap}-shm" ] && cp -p "${snap}-shm" "$tmpdir/db.sqlite3-shm" || true
    if python3 - "$tmpdir/db.sqlite3" <<'PY'
import sqlite3, sys
try:
    conn = sqlite3.connect(sys.argv[1])
    rows = conn.execute('PRAGMA integrity_check').fetchall()
    conn.close()
except sqlite3.DatabaseError as e:
    print(f'    열기/PRAGMA 실패: {e}', file=sys.stderr); sys.exit(1)
bad = [r[0] for r in rows if r and r[0] != 'ok']
if bad:
    print('    integrity_check: ' + '; '.join(bad[:5]), file=sys.stderr); sys.exit(1)
PY
    then rc=0; else rc=1; fi
    rm -rf "$tmpdir"
    return $rc
}

# --- keep 가드 ---
if [ "$DB_MODE" = keep ]; then
    CUR_MIG=$(docker compose exec -T web python manage.py showmigrations --plan 2>/dev/null | grep -c '\[X\]' || echo "")
    PRE_MIG=""
    [ -n "$SNAP" ] && [ -f "${SNAP}.mig" ] && PRE_MIG=$(cat "${SNAP}.mig" 2>/dev/null || echo "")
    if [ -n "$CUR_MIG" ] && [ -n "$PRE_MIG" ] && [ "$CUR_MIG" -gt "$PRE_MIG" ]; then
        echo "  ⚠ 직전 배포가 migration 을 적용함(적용 ${PRE_MIG}→${CUR_MIG})."
        echo "    이전 이미지(${PREV}) 코드가 새 스키마와 비호환일 수 있어 keep 은 위험 →"
        if [ "$FORCE" = 1 ]; then
            echo "    (--force 지정 — 강행)"
        else
            echo "    --db=restore (스냅샷으로 스키마째 되돌림) 또는 수동 판단 후 --force." >&2
            exit 1
        fi
    elif [ -z "$PRE_MIG" ]; then
        echo "  (migration 상태 미상 — .mig 사이드카 없음/구 스냅샷. 대부분 무migration 이라 keep 진행. 의심되면 --db=restore.)"
    else
        echo "  keep 안전(직전 배포 migration 없음: ${PRE_MIG}=${CUR_MIG})."
    fi
fi

# --- DB ---
if [ "$DB_MODE" = restore ]; then
    if [ -z "$SNAP" ]; then
        echo "  (pre_deploy 스냅샷 없음 — DB 복원 건너뜀; 최초 배포?)"
        docker compose down
    else
        # 복원 직전 무결성 검사(계약 §롤아웃): 채택 게이트(backup_db.py)는 '새' 스냅샷만 지킨다.
        # restore 는 로테이션의 '이미 있는' 것을 고르므로 게이트 이전·수동으로 놓인 후보는 무검증이었다
        # = 손상을 라이브로 되살릴 마지막 경로. 여기서 막는다. 서비스 정지 '전'에 검사해, 후보가 못 쓸
        # 것이면 라이브 DB·서비스를 건드리지 않고 멈춘다.
        # ⚠ 손상 감지 시 자동으로 다른 스냅샷을 고르지 않는다 — 계약이 반려한다(사람에게 넘김). 중단만.
        echo "  복원 후보 무결성 검사: ${SNAP}"
        if _snapshot_integrity_ok "$SNAP"; then
            echo "  ✓ integrity_check ok"
        else
            echo "  ✗ 스냅샷 손상 — 복원 중단(라이브 DB·서비스 불변)." >&2
            echo "    이 후보는 채택 게이트 이전이거나 수동으로 놓인 것일 수 있다." >&2
            echo "    다른 후보 확인: ls -1t $ROOT/backup/pre_deploy/fcmanager_pre_deploy_*.sqlite3" >&2
            echo "    특정 스냅샷 복원: docker compose down → 손으로 검사 → cp <스냅샷> $ROOT/db/db.sqlite3 → up -d" >&2
            exit 1
        fi
        docker compose down
        echo "  restore DB ← ${SNAP} (컨테이너 정지 후 — SQLite WAL torn-copy 방지)"
        mkdir -p "$ROOT/db"    # 디렉터리 마운트 레이아웃(0.6.16) — 스냅샷 출처와 무관하게 정본 위치는 db/
        cp -p "$SNAP" "$ROOT/db/db.sqlite3"
        [ -f "${SNAP}-wal" ] && cp -p "${SNAP}-wal" "$ROOT/db/db.sqlite3-wal" || rm -f "$ROOT/db/db.sqlite3-wal"
        [ -f "${SNAP}-shm" ] && cp -p "${SNAP}-shm" "$ROOT/db/db.sqlite3-shm" || rm -f "$ROOT/db/db.sqlite3-shm"
    fi
else
    echo "  db=keep — 현재 DB 유지(운영 데이터 보존). 이미지 태그만 전환."
fi

# --- 이미지 전환 ---
echo "  IMAGE_TAG → ${PREV}"
if grep -q '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${PREV}/" .env
else
    echo "IMAGE_TAG=${PREV}" >> .env
fi
docker pull "honestjung/fcmanager:${PREV}"
docker compose up -d       # 전 서비스 — 서비스명 지정 없이(사이드카 추가 시 누락 방지).

echo "=== rolled back to ${PREV} (db=${DB_MODE}) — /srv/fcmanager/smoke.sh ${PREV} 로 확인 권장 ==="
