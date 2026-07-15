"""scripts/backup_db.py — hourly 백업 무결성 게이트 테스트 (0.6.24, devlog 094).

계약(§백업 레인)이 지키라는 것을 테스트가 못 박는다:
  - 깨진 스냅샷은 **채택하지 않는다**(로테이션 오염 방지)
  - 새 스냅샷을 못 만들었으면 **prune 하지 않는다**(성한 과거 보존)
  - 스냅샷은 **일관된 단일 파일**(-wal/-shm 형제 없음)

BACKUP_DIR/SOURCES 등 모듈 상수는 운영 절대경로라 테스트마다 tmp 로 patch 한다.
`manage.py test` 로 함께 돈다(Django 불요 — 순수 unittest).
"""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import backup_db

PAGE_SIZE = 4096


SESSION_KEY = 'zz9tokenzz9tokenzz9tokenzz9token42'   # 파일 바이트에서 찾기 쉬운 표식


def make_db(path: Path, rows: int = 500, wal: bool = False, sessions: int = 3,
            expired_sessions: int = 0, writer_secure_delete: str = 'ON'):
    """실제 sqlite DB 를 만든다. wal=True 면 운영과 같은 WAL 모드(-wal/-shm 형제 생성).

    운영 스키마를 흉내내 `django_session` 도 만든다 — 반출 위생의 대상.

    `expired_sessions` 는 **과거에 지워진 세션**을 재현한다(로그아웃·만료 정리·로그인 시 회전).
    이게 운영 DB 의 실제 모양이고 **위생의 진짜 대상**이다 — 그 잔류는 free page 에 남고
    `backup()` 이 페이지 단위로 스냅샷에 옮기므로, 이미 행이 아니라서 `DELETE` 가 못 닿는다.
    `writer_secure_delete='OFF'` 면 그 잔류가 바이트로 남는다(= VACUUM 없이는 반출된다).

    ⚠️ 이 두 인자가 없던 초판 픽스처는 세션을 만들고 **그 자리에서** 지우는 경로만 밟아
    "DELETE 만으로도 지워진다"는 오진을 낳았다(devlog 095 §4 정정 / 096 §2). 픽스처가
    재현하지 않는 조건은 테스트가 반증도 입증도 못 한다.
    """
    conn = sqlite3.connect(str(path))
    conn.execute(f'PRAGMA secure_delete={writer_secure_delete}')
    if wal:
        conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)')
    conn.executemany('INSERT INTO t (v) VALUES (?)', [(f'row-{i}' * 20,) for i in range(rows)])
    if sessions or expired_sessions:
        conn.execute('CREATE TABLE django_session (session_key TEXT PRIMARY KEY, '
                     'session_data TEXT, expire_date TEXT)')
    if expired_sessions:
        # 과거 세대: 넣었다가 지운다 → 잔류가 free page 로 간다(라이브 DB 의 실제 이력).
        conn.executemany(
            'INSERT INTO django_session VALUES (?, ?, ?)',
            [(f'{SESSION_KEY}old{i}', 'z' * 200, '2020-01-01') for i in range(expired_sessions)],
        )
        conn.commit()
        conn.execute('DELETE FROM django_session')
        conn.commit()
    if sessions:
        # session_data 에 부피를 준다: 소량이면 한 페이지에 들어가 DELETE 해도 페이지가
        # 해제되지 않아(루트 페이지는 테이블에 남는다) freelist 단언이 공허해진다(실측).
        conn.executemany(
            'INSERT INTO django_session VALUES (?, ?, ?)',
            [(f'{SESSION_KEY}{i}', 'x' * 200, '2099-01-01') for i in range(sessions)],
        )
    conn.commit()
    conn.close()


def corrupt_db(path: Path, page: int = 3):
    """헤더는 살리고 page 번째 페이지를 쓰레기로 덮는다 — "열리지만 깨진" 상태.

    운영에서 실제로 겪은 손상 모양(cdGTS devlog 149: 워커가 DB 를 쥔 채 파일이 갈려 btree 파손).
    """
    with open(path, 'r+b') as f:
        f.seek((page - 1) * PAGE_SIZE)
        f.write(b'\xde\xad\xbe\xef' * (PAGE_SIZE // 4))


class BackupTestCase(unittest.TestCase):
    """tmp 백업 디렉터리 + tmp DB 소스로 모듈 상수를 갈아끼운다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.backup_dir = self.tmp / 'backup'
        self.backup_dir.mkdir()
        self.db_dir = self.tmp / 'db'      # 컨테이너가 보는 디렉터리 = 센티넬 자리
        self.db_dir.mkdir()
        self.src = self.db_dir / 'db.sqlite3'
        patcher = mock.patch.object(backup_db, 'BACKUP_DIR', self.backup_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    @property
    def sentinel(self) -> Path:
        return self.db_dir / backup_db.SENTINEL_NAME

    def snapshots(self) -> list[Path]:
        return sorted(self.backup_dir.glob('fcmanager_*.sqlite3'))


class TestIntegrityCheck(BackupTestCase):
    def test_healthy_db_passes(self):
        make_db(self.src)
        self.assertEqual(backup_db.integrity_check(self.src), [])

    def test_corrupt_db_reports_problems(self):
        make_db(self.src)
        corrupt_db(self.src)
        self.assertTrue(backup_db.integrity_check(self.src))

    def test_non_database_file_is_treated_as_corrupt(self):
        """헤더부터 깨진 경우 — 예외로 죽지 말고 '손상'으로 보고할 것."""
        self.src.write_bytes(b'not a database at all')
        problems = backup_db.integrity_check(self.src)
        self.assertTrue(problems)
        self.assertIn('열기/PRAGMA 실패', problems[0])


class TestBackupOne(BackupTestCase):
    def test_healthy_source_is_adopted(self):
        make_db(self.src)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertIsNotNone(dest)
        self.assertTrue(dest.exists())
        self.assertEqual(backup_db.integrity_check(dest), [])
        self.assertFalse(self.sentinel.exists())

    def test_missing_source_returns_none(self):
        self.assertIsNone(backup_db.backup_one('fcmanager', self.src))

    def test_backup_leaves_no_wal_siblings(self):
        """소스가 WAL 이어도 스냅샷은 **단일 파일**이어야 한다.

        backup() 은 소스의 저널 모드까지 복사하므로 스냅샷도 WAL 로 뜨고, integrity_check 의
        mode=ro 커넥션이 -shm 을 만들어놓고 치울 권한이 없어 매시 고아 2개가 남았다
        (cdGTS 0.1.68 이 테스트서버 실측으로 발견 — 단위 테스트의 합성 DB 가 기본 저널 모드라
        재현 조건이 픽스처에 없었다. 그래서 여기선 소스를 **명시적으로 WAL 로** 올린다).

        단언은 화이트리스트(`*.tmp` 없음)가 아니라 **전수**로 — 상상한 실패만 잡으면 `.tmp-wal` 이
        그대로 통과한다.
        """
        make_db(self.src, wal=True)
        # 저널 모드는 **파일에 영속**한다(-wal 형제는 close 시 체크포인트되며 사라짐) — 그래서
        # backup_one 이 이 소스를 열면 WAL 이 다시 서고 스냅샷도 WAL 로 뜬다. 그게 재현 조건이다.
        probe = sqlite3.connect(str(self.src))
        self.assertEqual(probe.execute('PRAGMA journal_mode').fetchone()[0], 'wal', 'WAL 픽스처 전제')
        probe.close()
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertEqual([p.name for p in self.backup_dir.iterdir()], [dest.name])

    def test_corrupt_source_is_not_promoted(self):
        """§로테이션 오염 방지의 본체 — backup() 은 손상을 예외 없이 충실히 복사한다."""
        make_db(self.src)
        corrupt_db(self.src)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertIsNone(dest)
        self.assertEqual(self.snapshots(), [], '깨진 스냅샷이 로테이션에 들어갔다')
        # 센티넬 + 증거 사본 = 예외 경로가 아니라 무결성 경로를 탔다는 증거
        self.assertTrue(self.sentinel.exists())
        self.assertTrue((self.backup_dir / 'fcmanager_INTEGRITY_FAIL.corrupt').exists())
        self.assertEqual(list(self.backup_dir.glob('*.tmp')), [])

    def test_evidence_copy_is_kept_only_once(self):
        """매시 쌓이면 디스크가 샌다 — 최초 1개만."""
        make_db(self.src)
        corrupt_db(self.src)
        backup_db.backup_one('fcmanager', self.src)
        evidence = self.backup_dir / 'fcmanager_INTEGRITY_FAIL.corrupt'
        first = evidence.stat().st_mtime_ns
        backup_db.backup_one('fcmanager', self.src)
        self.assertEqual(evidence.stat().st_mtime_ns, first, '증거 사본이 덮였다')
        self.assertEqual(len(list(self.backup_dir.glob('*.corrupt'))), 1)
        self.assertEqual(list(self.backup_dir.glob('*.tmp')), [], '두 번째 tmp 가 안 치워졌다')

    def test_sentinel_is_self_clearing(self):
        """손상이 고쳐졌는데 degraded 로 남으면 안 된다(smoke 가 계속 실패)."""
        self.sentinel.write_text('stale\n')
        make_db(self.src)
        self.assertIsNotNone(backup_db.backup_one('fcmanager', self.src))
        self.assertFalse(self.sentinel.exists())

    def test_sentinel_write_failure_does_not_crash(self):
        """센티넬을 못 써도(권한) 로테이션 보존은 계속 동작해야 한다 — 본체는 (1)이다."""
        make_db(self.src)
        corrupt_db(self.src)
        with mock.patch.object(Path, 'write_text', side_effect=OSError('read-only fs')):
            dest = backup_db.backup_one('fcmanager', self.src)
        self.assertIsNone(dest)
        self.assertEqual(self.snapshots(), [])


class TestSanitizeExport(BackupTestCase):
    """반출 위생 — 스냅샷은 호스트를 떠난다(NAS 0777·90일). bearer 토큰을 싣지 않는다."""

    def sessions_in(self, path: Path) -> int:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        n = conn.execute('SELECT count(*) FROM django_session').fetchone()[0]
        conn.close()
        return n

    def test_sessions_are_stripped_from_snapshot(self):
        make_db(self.src, sessions=3)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertEqual(self.sessions_in(dest), 0)

    def test_live_db_is_never_touched(self):
        """★ 라이브 DB 는 읽기만 — 로그인한 사람이 튕기면 안 된다."""
        make_db(self.src, sessions=3)
        backup_db.backup_one('fcmanager', self.src)
        self.assertEqual(self.sessions_in(self.src), 3, '라이브 DB 의 세션이 지워졌다')

    def test_token_bytes_are_gone_from_file(self):
        """행 수 0 은 위생의 증거가 아니다 — 파일을 통째로 grep 해 **우리가 원하는 속성**을 본다.

        ⚠️ 살아있는 세션만 있는 픽스처에선 이 단언이 VACUUM 을 검증하지 **못한다**: 지금 지우는
        행은 `secure_delete`(이 빌드 기본값 1)가 덮어줘 VACUUM 을 빼도 통과한다(변이 테스트로
        확인). 운영 조건을 재현해 VACUUM 을 못 박는 건 아래 `test_..._from_expired_sessions`.
        """
        make_db(self.src, sessions=200)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertNotIn(SESSION_KEY.encode(), dest.read_bytes(), 'free page 에 토큰이 남아 있다')

    def test_token_bytes_are_gone_from_expired_sessions(self):
        """★ 운영의 실제 조건 — **과거에** 지워진 세션의 free page 잔류까지 반출되지 않는가.

        여기가 위생의 진짜 대상이다. 라이브 DB 는 로그아웃·만료·회전으로 세션을 계속 지워왔고,
        그 writer 의 `secure_delete` 가 0 이었으면 잔류가 free page 에 남는다. `backup()` 은
        페이지 단위 복사라 그걸 스냅샷으로 옮기고, **이미 행이 아니므로 `DELETE` 는 물론
        `secure_delete=ON` 도 닿지 못한다** — `VACUUM`(재구축)만이 없앤다.

        그래서 이 단언은 **환경 기본값에 기대지 않는다**: writer 를 `OFF` 로 고정해 잔류를
        *반드시* 만들어 놓고 본다. VACUUM 을 빼면 실패한다(변이 테스트 확인: 442개 잔존).
        실측 근거는 devlog 096 §2.
        """
        make_db(self.src, sessions=3, expired_sessions=200, writer_secure_delete='OFF')
        self.assertIn(SESSION_KEY.encode(), self.src.read_bytes(),
                      '픽스처가 재현 조건을 못 만들었다 — 라이브에 free page 잔류가 있어야 한다')
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertNotIn(SESSION_KEY.encode(), dest.read_bytes(),
                         '과거에 지워진 세션의 잔류가 스냅샷으로 반출됐다 — VACUUM 이 빠졌나')

    def test_snapshot_has_no_free_pages(self):
        """VACUUM 이 실제로 돌았는가 — `freelist_count == 0`(파일이 재작성돼 freed page 가 없다).

        위 두 grep 이 "토큰이 없다"는 *결과*를 본다면, 이건 **수단**(파일 재작성)을 고정한다 —
        토큰 외의 잔류(예: 앞으로 위생 대상에 추가될 테이블)까지 같은 보장을 받게.
        """
        # 페이지를 여러 장 쓸 만큼 실어야 DELETE 가 실제로 free page 를 만든다 — 그래야
        # 이 단언이 VACUUM 을 검증한다(3행짜리 픽스처론 freelist 가 0 이라 공허했다).
        make_db(self.src, sessions=200)
        dest = backup_db.backup_one('fcmanager', self.src)
        conn = sqlite3.connect(f'file:{dest}?mode=ro', uri=True)
        try:
            self.assertEqual(conn.execute('PRAGMA freelist_count').fetchone()[0], 0)
        finally:
            conn.close()

    def test_other_data_survives(self):
        """위생은 세션만 — 도메인 데이터·해시는 백업의 존재 이유다."""
        make_db(self.src, rows=500, sessions=3)
        dest = backup_db.backup_one('fcmanager', self.src)
        conn = sqlite3.connect(f'file:{dest}?mode=ro', uri=True)
        self.assertEqual(conn.execute('SELECT count(*) FROM t').fetchone()[0], 500)
        conn.close()

    def test_missing_session_table_is_not_a_failure(self):
        """지울 토큰이 없는 것은 실패가 아니다 — 백업은 그대로 채택된다."""
        make_db(self.src, sessions=0)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertIsNotNone(dest)
        self.assertTrue(dest.exists())

    def test_hygiene_failure_blocks_adoption(self):
        """위생 못 한 사본은 내보내지 않는다 — 토큰 실린 스냅샷보다 결번이 낫다."""
        make_db(self.src, sessions=3)
        with mock.patch.object(backup_db, 'sanitize_export', return_value=(False, 0)):
            dest = backup_db.backup_one('fcmanager', self.src)
        self.assertIsNone(dest)
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(list(self.backup_dir.glob('*.tmp')), [])

    def test_snapshot_stays_single_file_after_vacuum(self):
        """VACUUM 이 저널 모드를 되돌리지 않는지 — 단일 파일 계약은 유지돼야 한다."""
        make_db(self.src, wal=True, sessions=3)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertEqual([p.name for p in self.backup_dir.iterdir()], [dest.name])
        conn = sqlite3.connect(f'file:{dest}?mode=ro', uri=True)
        self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
        conn.close()

    def test_corrupt_source_reports_corruption_not_hygiene(self):
        """손상이면 '위생 실패'가 아니라 **센티넬(손상 진단)** 로 가야 한다 — 사인이 정확해야."""
        make_db(self.src, sessions=3)
        corrupt_db(self.src)
        dest = backup_db.backup_one('fcmanager', self.src)
        self.assertIsNone(dest)
        self.assertTrue(self.sentinel.exists(), '손상인데 센티넬이 안 떴다')
        self.assertTrue((self.backup_dir / 'fcmanager_INTEGRITY_FAIL.corrupt').exists())


class TestBackupData(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.src_dir = self.tmp / 'sites-available'
        self.src_dir.mkdir()
        (self.src_dir / 'fcmanager.conf').write_text('server { listen 80; }\n')

    def test_healthy_dir_is_archived(self):
        dest = backup_db.backup_data('dolfinid_nginx', self.src_dir)
        self.assertIsNotNone(dest)
        subprocess.run(['tar', '-tzf', str(dest)], check=True, capture_output=True)

    def test_missing_dir_returns_none(self):
        self.assertIsNone(backup_db.backup_data('dolfinid_nginx', self.tmp / 'nope'))

    def test_corrupt_archive_is_not_adopted(self):
        """tar 트랙의 integrity_check 대응물 = `tar -tzf`. 깨진 아카이브는 채택 금지."""
        real_run = subprocess.run

        def fake_run(cmd, *a, **kw):
            if cmd[1] == '-czf':                 # 생성만 가로채 쓰레기를 쓴다
                Path(cmd[2]).write_bytes(b'\x1f\x8b garbage not really gzip')
                return mock.Mock(returncode=0)
            return real_run(cmd, *a, **kw)       # 검증(-tzf)은 진짜 tar 가 판정

        with mock.patch.object(backup_db.subprocess, 'run', side_effect=fake_run):
            dest = backup_db.backup_data('dolfinid_nginx', self.src_dir)
        self.assertIsNone(dest)
        self.assertEqual(list(self.backup_dir.glob('*.tar.gz')), [])
        self.assertEqual(list(self.backup_dir.glob('*.tmp')), [])


class TestPrune(BackupTestCase):
    def _seed(self, count: int, name: str = 'fcmanager', suffix: str = '.sqlite3'):
        made = []
        for hour in range(count):
            f = self.backup_dir / f'{name}_20260715_{hour:02d}{suffix}'
            f.write_text('x')
            made.append(f)
        return made

    def test_keeps_newest_retain_count(self):
        self._seed(5)
        with mock.patch.object(backup_db, 'RETAIN_COUNT', 2):
            backup_db.prune_old('fcmanager')
        self.assertEqual(
            [p.name for p in self.snapshots()],
            ['fcmanager_20260715_03.sqlite3', 'fcmanager_20260715_04.sqlite3'],
        )

    def test_evidence_copy_survives_prune(self):
        """증거 사본은 확장자가 .sqlite3 가 아니라 glob 에 안 걸린다."""
        self._seed(3)
        evidence = self.backup_dir / 'fcmanager_INTEGRITY_FAIL.corrupt'
        evidence.write_text('corrupt')
        with mock.patch.object(backup_db, 'RETAIN_COUNT', 1):
            backup_db.prune_old('fcmanager')
        self.assertTrue(evidence.exists())


class TestMain(BackupTestCase):
    """계약 MUST: 검증·생성 실패 시 로테이션을 prune 하지 않는다."""

    def _run_main(self) -> int:
        with self.assertRaises(SystemExit) as cm:
            backup_db.main()
        return cm.exception.code

    def test_skips_prune_when_integrity_fails(self):
        """오염 로테이션의 반대 증명 — RETAIN_COUNT 를 넘겨도 과거가 전부 산다."""
        make_db(self.src)
        corrupt_db(self.src)
        old = [self.backup_dir / f'fcmanager_20260714_{h:02d}.sqlite3' for h in range(4)]
        for f in old:
            f.write_text('healthy-past')
        with mock.patch.object(backup_db, 'SOURCES', [('fcmanager', self.src)]), \
             mock.patch.object(backup_db, 'DATA_DIRS', []), \
             mock.patch.object(backup_db, 'RETAIN_COUNT', 2):
            rc = self._run_main()
        self.assertEqual(rc, 1)
        self.assertTrue(all(f.exists() for f in old), '백업 실패 + 과거 삭제가 겹쳤다')
        self.assertTrue(self.sentinel.exists())

    def test_skips_prune_when_source_missing(self):
        """손상이 아니어도(소스 부재·IO) 새것 없이 보관 창만 깎이면 안 된다."""
        old = [self.backup_dir / f'fcmanager_20260714_{h:02d}.sqlite3' for h in range(4)]
        for f in old:
            f.write_text('healthy-past')
        with mock.patch.object(backup_db, 'SOURCES', [('fcmanager', self.src)]), \
             mock.patch.object(backup_db, 'DATA_DIRS', []), \
             mock.patch.object(backup_db, 'RETAIN_COUNT', 2):
            rc = self._run_main()
        self.assertEqual(rc, 1)
        self.assertTrue(all(f.exists() for f in old))

    def test_healthy_run_prunes_and_exits_zero(self):
        make_db(self.src)
        old = [self.backup_dir / f'fcmanager_20260714_{h:02d}.sqlite3' for h in range(4)]
        for f in old:
            f.write_text('healthy-past')
        with mock.patch.object(backup_db, 'SOURCES', [('fcmanager', self.src)]), \
             mock.patch.object(backup_db, 'DATA_DIRS', []), \
             mock.patch.object(backup_db, 'RETAIN_COUNT', 2):
            rc = self._run_main()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.snapshots()), 2)

    def test_tar_track_failure_also_skips_prune(self):
        """DB 가 성해도 tar 트랙이 실패하면 그 트랙의 과거는 보존 + exit 1."""
        make_db(self.src)
        old_tars = [self.backup_dir / f'dolfinid_nginx_20260714_{h:02d}.tar.gz' for h in range(4)]
        for f in old_tars:
            f.write_text('past-archive')
        with mock.patch.object(backup_db, 'SOURCES', [('fcmanager', self.src)]), \
             mock.patch.object(backup_db, 'DATA_DIRS', [('dolfinid_nginx', self.tmp / 'nope')]), \
             mock.patch.object(backup_db, 'RETAIN_COUNT', 2):
            rc = self._run_main()
        self.assertEqual(rc, 1)
        self.assertTrue(all(f.exists() for f in old_tars))
        self.assertEqual(len(self.snapshots()), 1, 'DB 트랙은 정상이므로 스냅샷이 채택됐어야')

    def test_disk_full_aborts_before_touching_anything(self):
        make_db(self.src)
        old = self.backup_dir / 'fcmanager_20260714_00.sqlite3'
        old.write_text('healthy-past')
        with mock.patch.object(backup_db, 'MIN_FREE_GB', sys.maxsize), \
             mock.patch.object(backup_db, 'RETAIN_COUNT', 0):
            rc = self._run_main()
        self.assertEqual(rc, 1)
        self.assertTrue(old.exists())


if __name__ == '__main__':
    unittest.main()
