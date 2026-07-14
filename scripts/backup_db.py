#!/usr/bin/env python3
"""FCManager 운영(dolfinid) hourly 백업 — DB(sqlite3 online backup) + nginx conf(tar.gz).

fsis2026 의 backup_db.py 를 FCManager 규모에 맞게 단순화한 것.
  - DB: sqlite3 online backup API (컨테이너가 쓰는 중에도 안전)
  - nginx: /etc/nginx/sites-available/ tar.gz (전체 호스트 복원용, 권한 없으면 skip)
  - 소스별 최근 RETAIN_COUNT 개만 유지(오래된 것부터 삭제)
  - cron 으로 매시 정각 실행 (dolfinid devops crontab):
      0 * * * * /usr/bin/python3 /srv/fcmanager/scripts/backup_db.py >> /srv/fcmanager/backup/backup.log 2>&1

fsis 와 달리 ghdb·data JSON 트랙 없음. DB 가 작아(<5MB) 부담 없음.
"""
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path('/srv/fcmanager/backup')
# 디렉터리 마운트 레이아웃(0.6.16): 정본 = /srv/fcmanager/db/db.sqlite3.
# 구 레이아웃(루트 파일)은 deploy.sh 가 1회 이행하지만, 이행 전 cron 이 돌 수 있어 fallback 유지.
_DB_NEW = Path('/srv/fcmanager/db/db.sqlite3')
_DB_LEGACY = Path('/srv/fcmanager/db.sqlite3')
SOURCES = [
    ('fcmanager', _DB_NEW if _DB_NEW.exists() else _DB_LEGACY),
]
DATA_DIRS = [
    ('dolfinid_nginx', Path('/etc/nginx/sites-available')),
]
RETAIN_COUNT = 12      # 매시 1개 → 최근 12시간 유지
MIN_FREE_GB = 2        # 백업 디렉토리 여유가 이 미만이면 abort (디스크 풀 방지)


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def backup_one(name: str, src: Path) -> Path | None:
    if not src.exists():
        log(f'{name}: source not found ({src}) — skip')
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H')
    dest = BACKUP_DIR / f'{name}_{stamp}.sqlite3'
    tmp = dest.with_suffix('.sqlite3.tmp')
    try:
        with sqlite3.connect(str(src)) as source_conn, sqlite3.connect(str(tmp)) as dest_conn:
            source_conn.backup(dest_conn)
        tmp.replace(dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        log(f'{name}: backup OK ({dest.name}, {size_mb:.1f} MB)')
        return dest
    except Exception as e:
        log(f'{name}: ERROR {e}')
        if tmp.exists():
            try: tmp.unlink()
            except OSError: pass
        return None


def backup_data(name: str, src_dir: Path) -> Path | None:
    """data 디렉토리 tar.gz. DB 와 동일 retention 트랙."""
    if not src_dir.is_dir():
        log(f'{name}: source dir not found ({src_dir}) — skip')
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H')
    dest = BACKUP_DIR / f'{name}_{stamp}.tar.gz'
    tmp = dest.with_suffix('.tar.gz.tmp')
    try:
        subprocess.run(
            ['tar', '-czf', str(tmp), '-C', str(src_dir.parent), src_dir.name],
            check=True, capture_output=True,
        )
        tmp.replace(dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        log(f'{name}: backup OK ({dest.name}, {size_mb:.1f} MB)')
        return dest
    except Exception as e:
        log(f'{name}: ERROR {e}')
        if tmp.exists():
            try: tmp.unlink()
            except OSError: pass
        return None


def prune_old(name: str, suffix: str = '.sqlite3'):
    """RETAIN_COUNT 개 최신만 남기고 나머지 삭제."""
    snapshots = []
    for f in BACKUP_DIR.glob(f'{name}_*{suffix}'):
        stem = f.name[:-len(suffix)] if f.name.endswith(suffix) else f.stem
        parts = stem.split('_')
        if len(parts) < 3:
            continue
        try:
            dt = datetime.strptime(f'{parts[-2]}_{parts[-1]}', '%Y%m%d_%H')
        except ValueError:
            continue
        snapshots.append((dt, f))
    snapshots.sort(key=lambda x: x[0], reverse=True)
    deleted = 0
    for _, f in snapshots[RETAIN_COUNT:]:
        try:
            f.unlink()
            deleted += 1
        except OSError:
            pass
    if deleted:
        log(f'{name}: pruned {deleted} old snapshot(s)')


def check_disk_space() -> bool:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(BACKUP_DIR).free / (1024 ** 3)
    if free_gb < MIN_FREE_GB:
        msg = f'ABORT: free disk {free_gb:.2f} GB < {MIN_FREE_GB} GB threshold — skipping backup'
        log(msg)
        print(f'ERROR: {msg}', file=sys.stderr)
        return False
    return True


def main():
    if not check_disk_space():
        sys.exit(1)
    for name, src in SOURCES:
        backup_one(name, src)
        prune_old(name)
    for name, src_dir in DATA_DIRS:
        backup_data(name, src_dir)
        prune_old(name, suffix='.tar.gz')


if __name__ == '__main__':
    main()
