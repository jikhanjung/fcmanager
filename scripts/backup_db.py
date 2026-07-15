#!/usr/bin/env python3
"""FCManager 운영(dolfinid) hourly 백업 — DB(sqlite3 online backup) + nginx conf(tar.gz).

fsis2026 의 backup_db.py 를 FCManager 규모에 맞게 단순화한 것.
  - DB: sqlite3 online backup API (컨테이너가 쓰는 중에도 안전)
  - 스냅샷마다 PRAGMA integrity_check → **실패하면 채택도 prune 도 하지 않는다**(아래 참조)
  - **반출 위생**: 스냅샷에서 `django_session`(bearer 토큰) 제거 + VACUUM — 이 파일은 호스트를
    떠난다(daily 미러 → NAS 0777·90일 · 테스트 컨테이너). 라이브 DB 는 안 건드린다(§EXPORT_STRIP_TABLES).
  - nginx: /etc/nginx/sites-available/ tar.gz (전체 호스트 복원용). 채택 전 `tar -tzf` 로 검증.
  - 소스별 최근 RETAIN_COUNT 개만 유지(24 = daily 오프사이트 간격을 덮는 유도값)
  - pre_deploy 스냅샷 retention 은 deploy.sh 가 단독 관리(20개) — 여기서 건드리지 않는다
    (fsis 에서 두 곳이 다른 수치로 같은 디렉터리를 prune 하던 충돌 교훈, 2026-07-14).
  - 배포 시 이미지에서 self-heal 추출(deploy/host/_extract_and_deploy.sh).
  - cron 으로 매시 정각 실행 (dolfinid honestjung crontab):
      0 * * * * /usr/bin/python3 /srv/fcmanager/scripts/backup_db.py >> /srv/fcmanager/backup/backup.log 2>&1

fsis 와 달리 ghdb·data JSON 트랙 없음. DB 가 작아(<5MB) 부담 없음.

무결성 검사를 왜 여기 두나 (0.6.24, devlog 094 — cdGTS 0.1.68/devlog 150 포팅)
--------------------------------------------------------------------------------
목적은 **탐지가 아니라 로테이션 오염 방지**다. `backup()` 은 소스 페이지를 충실히 복사하므로 소스가
깨져 있으면 스냅샷도 조용히 깨진 채 만들어지고, 매시 로테이션이라 **RETAIN_COUNT 시간이면 성한 스냅샷이
전부 prune 된다.** 손상을 늦게 알아차리는 것보다 이쪽이 훨씬 위험하다 — 복구 대상 자체가 사라지므로.
그래서 규칙은 두 줄이다:

  1. 스냅샷이 검사에 걸리면 **채택하지 않는다**(로테이션에 안 들어감) + **prune 을 건너뛴다**(과거 성한 것 보존).
  2. DB 디렉터리에 센티넬 파일을 남긴다 → /healthz 가 stat 만 해서 degraded 반환 → **배포마다 도는 smoke 가 잡는다.**

(1) 이 본체다 — 아무도 안 보고 있어도 자동으로 성한 스냅샷을 지킨다. (2) 는 사람에게 닿는 경로.
dolfinid crontab 에 **MAILTO 가 없어** cron 실패는 backup/backup.log 에만 남고 아무도 안 읽는다.
읽히지 않는 검사는 연극이라, 사람이 이미 보는 경로(배포마다 도는 smoke)에 물린다.

센티넬이 backup/ 아닌 db/ 에 있는 이유: 컨테이너가 보는 건 `/srv/fcmanager/db` → `/app/hostdb` 뿐이다
(0.6.16 디렉터리 마운트 — .env·backup 은 blast radius 축소를 위해 의도적으로 비노출). 마운트를 되돌리지
않고, 의미상으로도 "DB 가 깨졌다" 플래그는 DB 옆이 맞다.
⚠️ cron 사용자(honestjung)가 db/ 에 쓸 수 있어야 한다 — 현 운영은 db/ 가 `ubuntu:ubuntu` drwxrwxr-x 이고
honestjung 이 ubuntu 그룹 소속이라 성립(2026-07-15 실측). 못 쓰면 (1)은 그대로 동작하고 (2)만 로그 경고.
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
# ⚠️ 구 레이아웃으로 폴백하면 센티넬이 /srv/fcmanager/ 에 떨어져 컨테이너가 못 본다(healthz 는
#    /app/hostdb 만 본다) — prune 보존은 유효하나 degraded 경로는 죽는다. 이행 완료된 운영은 해당 없음.
_DB_NEW = Path('/srv/fcmanager/db/db.sqlite3')
_DB_LEGACY = Path('/srv/fcmanager/db.sqlite3')
SOURCES = [
    ('fcmanager', _DB_NEW if _DB_NEW.exists() else _DB_LEGACY),
]
DATA_DIRS = [
    ('dolfinid_nginx', Path('/etc/nginx/sites-available')),
]
# 매시 1개 → 최근 24시간 유지. **튜닝값이 아니라 유도값**(계약 §백업 레인 "창을 덮는다", 0.6.25):
# 세밀 트랙(hourly)의 창이 성긴 트랙(daily 오프사이트, 05시)의 간격을 덮어야 한다 —
#   RETAIN_COUNT × 주기 ≥ 오프사이트 간격 → 12×1h = 12h < 24h ✗ / 24×1h = 24h ≥ 24h ✓
# 12 이면 05시 daily 와 그 12시간 뒤(17시) 사이에 **granularity 갭**이 생겨, 하루의 절반은
# 시간 단위 복원이 안 되고 어제치 daily 로만 돌아간다. 디스크는 0.45MB × 24 ≈ 11MB.
RETAIN_COUNT = 24
MIN_FREE_GB = 2        # 백업 디렉토리 여유가 이 미만이면 abort (디스크 풀 방지)

# DB 디렉터리(= 컨테이너의 /app/hostdb)에 놓는 손상 플래그. config/views_health.py 가 stat 한다.
SENTINEL_NAME = 'INTEGRITY_FAIL'

# --- 반출 위생 (0.6.25, 계약 §규범 MUST — cdGTS devlog 151 동형) ---
# 이 스냅샷은 호스트를 떠난다(daily 미러 → m710q 30일 · NAS 90일 **0777** · 테스트 컨테이너).
# `django_session.session_key` 는 **쿠키에 담기는 값 그 자체(bearer 토큰)** 다 — 사본을 읽은 사람이
# 그걸 **운영에** 되제시하면 운영이 자기 DB 에서 행을 찾아 자기 SECRET_KEY 로 디코드해 그 사용자로
# 로그인된다. ⚠️ **SECRET_KEY 가 달라도 못 막는다**: 키 차이는 "받는 쪽이 session_data 를 해독하는 것"만
# 막고, 이 공격은 해독을 하지 않는다. 해시는 뚫어야 쓰지만 세션 키는 그냥 쓰면 된다.
# 대칭적으로 그 세션은 테스트에선 무용지물(서명 검증 실패) = **테스트엔 쓸모없고 운영엔 위험한 순수 손해**.
#
# 왜 여기(hourly)인가 — cdGTS 는 sync 스크립트에 넣었는데(그쪽은 sync 가 자기 스냅샷을 직접 뜬다),
# fcmanager 의 daily 는 **이 스냅샷을 소비**한다(0.6.24). 그래서 초크포인트가 상류로 옮겨왔다:
# 여기서 지우면 daily·NAS·테스트 타깃·수동 scp 까지 **전부 구조적으로** 깨끗해진다.
# ★ 라이브 운영 DB 는 읽기만 한다 — 로그인한 사람은 영향 없다(백업 API 는 소스를 안 건드린다).
# 복원 시 세션이 없어 재로그인이 필요하지만, rollback 경로는 pre_deploy 스냅샷(정지 후 cp, 호스트를
# 떠나지 않음)이라 그쪽은 세션이 온전하다. hourly 는 재해 복구용 = 재로그인은 무시할 만한 비용.
# 해시(auth_user.password)는 **남긴다** — 강하고(pbkdf2), 지우면 테스트 로그인이 막힌다(성질이 다르다).
EXPORT_STRIP_TABLES = ['django_session']


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def integrity_check(path: Path) -> list[str]:
    """PRAGMA integrity_check — 통과면 [], 실패면 문제 문자열 목록(빈 목록이 아니면 손상).

    읽기 전용 URI 로 연다: 검사 대상은 방금 만든 스냅샷이지 라이브 DB 가 아니다.
    라이브 소스 대신 스냅샷을 검사하는 이유 — (a) 소스가 깨졌으면 backup() 이 그대로 복사하므로
    스냅샷 손상 ⇒ 소스 손상이 성립하고, (b) 라이브 DB 에 긴 read 트랜잭션을 걸지 않는다.
    """
    conn = None
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        rows = conn.execute('PRAGMA integrity_check').fetchall()
    except sqlite3.DatabaseError as e:
        return [f'열기/PRAGMA 실패: {e}']      # 헤더부터 깨진 경우 — 손상으로 취급
    finally:
        if conn is not None:
            conn.close()
    return [r[0] for r in rows if r and r[0] != 'ok']


def sanitize_export(path: Path) -> tuple[bool, int]:
    """스냅샷에서 bearer 토큰을 지운다 — **사본만**, 라이브 DB 는 절대 안 건드린다.

    반환 `(ok, removed)`. ok=False 면 호출자가 **채택을 중단**한다(위생 못 한 사본을 내보내느니
    이번 시각 백업을 거르는 게 낫다 — 계약의 "검증 실패면 채택 안 함"과 같은 모양).
    테이블이 없으면 지울 토큰도 없으므로 ok(0).
    """
    removed = 0
    conn = None
    try:
        conn = sqlite3.connect(str(path))
        for table in EXPORT_STRIP_TABLES:
            try:
                n = conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
            except sqlite3.OperationalError:
                log(f'반출 위생: {table} 테이블 없음 — 지울 토큰 없음')
                continue
            conn.execute(f'DELETE FROM {table}')
            removed += n
        conn.commit()
        # VACUUM 으로 파일을 재작성한다. ⚠️ 흔히 "DELETE 만으론 free page 에 토큰이 남는다"고
        # 하지만 **그건 빌드에 달렸다** — dolfinid·m710q 둘 다 `PRAGMA secure_delete` 컴파일
        # 기본값이 **1** 이라 DELETE 만으로도 바이트가 지워진다(2026-07-15 실측, sqlite 3.45/3.46).
        # 즉 지금 VACUUM 을 빼도 토큰은 안 남는다. 그래도 두는 이유: 그건 **주변 환경의 기본값에
        # 기댄 것이지 계약이 아니다** — `secure_delete=0` 빌드에선 DELETE 만 하면 토큰 문자열이
        # free page 에 그대로 남는 것을 실측으로 확인했다(OFF 로 두고 grep). VACUUM 은 그 기본값과
        # 무관하게 free page 자체를 없앤다(+ 부수적으로 파일 축소). VACUUM 은 트랜잭션 안에서 못 도니 commit 후.
        conn.execute('VACUUM')
        return True, removed
    except sqlite3.DatabaseError as e:
        # 손상 소스면 여기서 죽는다 — 호출자는 이걸 무시하고 integrity_check 로 넘어가
        # 센티넬 경로를 타게 한다(손상 진단이 위생 실패보다 정확한 사인이다).
        log(f'반출 위생 실패: {e}')
        return False, removed
    finally:
        if conn is not None:
            conn.close()


def raise_sentinel(db_dir: Path, problems: list[str]):
    """DB 디렉터리에 손상 플래그를 남긴다 → /healthz degraded → smoke 실패(사람이 본다)."""
    body = [
        f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} backup_db.py: PRAGMA integrity_check 실패.',
        '이 파일이 있는 한 /healthz 는 degraded 이고 smoke 는 실패한다.',
        '백업 로테이션 prune 은 중단됐다 — backup/ 의 과거 스냅샷이 복구 후보다.',
        '조치 후(예: rollback.sh --db=restore) 다음 정시 검사가 통과하면 자동으로 지워진다.',
        '',
        *problems[:20],
    ]
    try:
        (db_dir / SENTINEL_NAME).write_text('\n'.join(body) + '\n')
    except OSError as e:
        log(f'경고: 센티넬 기록 실패 ({db_dir / SENTINEL_NAME}: {e}) — smoke 가 못 잡는다')


def clear_sentinel(db_dir: Path):
    """검사 통과 시 자기 해제. 손상이 고쳐졌는데 degraded 로 남아 있으면 안 된다."""
    sentinel = db_dir / SENTINEL_NAME
    if sentinel.exists():
        try:
            sentinel.unlink()
            log(f'integrity OK — 센티넬 해제({sentinel})')
        except OSError as e:
            log(f'경고: 센티넬 해제 실패 ({sentinel}: {e})')


def backup_one(name: str, src: Path) -> Path | None:
    if not src.exists():
        log(f'{name}: source not found ({src}) — skip')
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H')
    dest = BACKUP_DIR / f'{name}_{stamp}.sqlite3'
    tmp = dest.with_suffix('.sqlite3.tmp')
    try:
        # `with sqlite3.connect(...)` 를 쓰지 않는다 — 그건 **트랜잭션** 컨텍스트지 close 가 아니다
        # (파이썬 sqlite3 의 고전적 함정). 종전 코드는 이 관용구를 썼지만 cron 단명 프로세스라
        # 종료 시 GC 가 닫아주며 체크포인트했다 → 실해는 없었다(cdGTS 가 prod backup/ 실측으로 확인).
        # 그래도 명시적으로 닫는다: GC 타이밍에 기대는 정합성은 계약이 아니고, 아래 integrity_check 가
        # 정적인 파일을 봐야 하기 때문.
        source_conn = dest_conn = None
        try:
            source_conn = sqlite3.connect(str(src))
            dest_conn = sqlite3.connect(str(tmp))
            source_conn.backup(dest_conn)       # online backup API — writer 상주해도 일관 스냅샷
            # backup 은 소스의 저널 모드까지 복사 → 스냅샷이 WAL 로 뜬다(운영 settings.py 가
            # init_command 로 WAL). **아카이브는 WAL 일 이유가 없다**(동시 writer 가 없다).
            # DELETE 로 내려 -wal/-shm 이 아예 존재하지 않게 만든다:
            #   (a) 아래 integrity_check 는 mode=ro 로 여는데 **읽기 전용 커넥션은 WAL DB 의 -shm 을
            #       만들어놓고 치울 권한이 없다** → DELETE 가 아니면 검사가 매시 고아 2개를 남기고,
            #       prune 의 glob `*.sqlite3` 에 안 걸려 영구 누적된다(cdGTS 0.1.68 테스트서버 실측).
            #   (b) 본체만 rename 하면 -wal 에 있던 내용이 스냅샷에서 조용히 누락된다.
            # "스냅샷 = 일관된 단일 파일" 은 daily 미러(backup-fcmanager.sh)가 이미 전제하는 계약이다.
            dest_conn.execute('PRAGMA journal_mode=DELETE')
        finally:
            for conn in (dest_conn, source_conn):
                if conn is not None:
                    conn.close()

        # 반출 위생을 **integrity_check 앞**에 둔다 — 그래야 검사가 *실제로 채택할 산출물*(VACUUM 후)을
        # 본다. 손상 소스면 여기서 DatabaseError 로 실패하지만 그냥 흘려보내고 아래 게이트가 판정하게
        # 한다: "손상"이 "위생 실패"보다 정확한 진단이고, 센티넬 경로도 그쪽에 달려 있다.
        hygiene_ok, removed = sanitize_export(tmp)

        # 채택 전 게이트 — 깨진 스냅샷은 로테이션에 들어가지 않는다(docstring "로테이션 오염 방지").
        problems = integrity_check(tmp)
        if problems:
            log(f'{name}: !! INTEGRITY FAIL — 스냅샷 미채택. 라이브 DB({src}) 손상으로 간주.')
            for p in problems[:5]:
                log(f'{name}:    {p}')
            # 증거는 하나만 남긴다: 최초 손상이 가장 정보가 많고, 매시 쌓이면 디스크가 샌다.
            # 확장자가 .sqlite3 가 아니므로 prune_old() 의 glob 에도 안 걸린다.
            evidence = BACKUP_DIR / f'{name}_INTEGRITY_FAIL.corrupt'
            if evidence.exists():
                tmp.unlink()
                log(f'{name}: 증거 사본 이미 있음({evidence.name}) — 이번 것은 버림')
            else:
                tmp.replace(evidence)
                log(f'{name}: 증거 사본 보존 → {evidence.name}')
            raise_sentinel(src.parent, problems)
            return None

        # 소스는 성한데 위생만 실패한 경우 — 위생 못 한 사본은 내보내지 않는다. 이 스냅샷이
        # daily 미러를 거쳐 NAS(0777·90일)와 테스트 컨테이너로 나가기 때문(계약 §규범 MUST).
        if not hygiene_ok:
            log(f'{name}: !! 반출 위생 실패 — 스냅샷 미채택(토큰 실린 사본을 내보내지 않는다)')
            tmp.unlink()
            return None

        tmp.replace(dest)
        clear_sentinel(src.parent)
        size_mb = dest.stat().st_size / (1024 * 1024)
        log(f'{name}: backup OK ({dest.name}, {size_mb:.1f} MB, integrity ok, 세션 {removed}행 제거)')
        return dest
    except Exception as e:
        log(f'{name}: ERROR {e}')
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return None


def backup_data(name: str, src_dir: Path) -> Path | None:
    """data 디렉토리 tar.gz. DB 와 동일 retention 트랙.

    DB 와 같은 원칙으로 **채택 전에 검증한다.** tar 트랙에서 integrity_check 의 대응물은 `tar -tzf`
    (gzip CRC + 아카이브 구조 확인) — 깨진 아카이브를 로테이션에 넣어 성한 과거를 밀어내지 않는다.
    센티넬은 올리지 않는다: nginx conf 아카이브 손상은 앱 서빙 상태(degraded)와 무관하다.
    """
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
        subprocess.run(['tar', '-tzf', str(tmp)], check=True, capture_output=True)
        tmp.replace(dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        log(f'{name}: backup OK ({dest.name}, {size_mb:.1f} MB, tar ok)')
        return dest
    except Exception as e:
        log(f'{name}: ERROR {e}')
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
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
    failed = False
    # 새 스냅샷을 못 만들었으면(디스크/IO/무결성) **prune 하지 않는다** — 새것 없이 과거를 지우면
    # 보관 창이 소리 없이 줄어든다. 종전 코드는 backup_*() 의 반환값을 버리고 무조건 prune 했다
    # (계약 §백업 레인 — 5개 프로젝트 공통 결함이었다).
    for name, src in SOURCES:
        if backup_one(name, src) is None:
            failed = True
            log(f'{name}: prune 건너뜀(스냅샷 미채택) — 과거 스냅샷 보존')
            continue
        prune_old(name)
    for name, src_dir in DATA_DIRS:
        if backup_data(name, src_dir) is None:
            failed = True
            log(f'{name}: prune 건너뜀(아카이브 미채택) — 과거 아카이브 보존')
            continue
        prune_old(name, suffix='.tar.gz')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
