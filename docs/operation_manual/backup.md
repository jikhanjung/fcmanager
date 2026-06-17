# FCManager 백업 운영 매뉴얼

> **대상**: 운영자 (dolfinid 호스트 + m710q 백업 호스트)
> **원형**: fsis2026 3계층 백업을 FCManager 규모로 단순화(단일 SQLite + media).
> **관련 스크립트**: `scripts/backup_db.py`(운영 hourly), `scripts/backup-fcmanager.sh`(m710q daily pull)

데이터 손실 시 1시간~1년 전 상태로 복구할 수 있도록 2~3계층 백업을 둔다.
fsis2026 대비 단순화: ghdb·분류 JSON 트랙 없음, DB 가 작아(<5MB) 부담이 미미하다.

---

## 1. 구조 한눈에

```
┌──────────── 운영 (dolfinid) ─────────────┐
│  /srv/fcmanager/backup/  (hourly, 12 rolling) │
│  ├─ fcmanager_YYYYMMDD_HH.sqlite3            │
│  └─ dolfinid_nginx_YYYYMMDD_HH.tar.gz    │
└───────────────────────────────────────────┘
            │ 매일 04:00 SSH pull
            ▼
┌──────────── 백업 (m710q) ─────────────────┐
│  /home/jikhanjung/backups/fcmanager/          │
│  ├─ current/    (db.sqlite3 + media/ + .env)│
│  ├─ db_history/ (30일 매일 → 월초 → 12월 영구)│
│  ├─ tar_history/(nginx tar, 동일 정책)     │
│  └─ media_snapshots/                       │
│     ├─ monthly/YYYYMM_full/ (link-dest 체인)│
│     └─ daily/YYYYMMDD/                     │
└───────────────────────────────────────────┘
            │ (NAS 마운트 시) 매 백업 끝에 미러 (-H)
            ▼
┌──────────── NAS (선택) ───────────────────┐
│  /nas/JikhanJung/fcmanager_backup/  (90일)    │
└───────────────────────────────────────────┘
```

| 계층 | 빈도 | 보존 |
|---|---|---|
| 운영 hourly (DB·nginx tar) | 매시 정각 | 최근 **12시간** rolling |
| m710q daily DB·tar | 매일 04:00 | 30일 매일 → 월초만 → 매년 12월 영구 |
| m710q daily media | 매일 04:00 | 이번 달 일별 + 최근 12개월 full + 12월 영구 |
| NAS (있을 때) | 매일 | 90일 → 월초 → 12월 영구 |

---

## 2. 운영 호스트(dolfinid) hourly

- **스크립트**: `/srv/fcmanager/scripts/backup_db.py` (repo `scripts/backup_db.py` 를 배치)
- **방식**: SQLite **online backup API** — 컨테이너가 DB 에 쓰는 중에도 안전.
- **트랙**: `fcsky`(/srv/fcmanager/db.sqlite3) + `dolfinid_nginx`(/etc/nginx/sites-available/, 권한 없으면 skip).
- **retention**: `RETAIN_COUNT=12` (최근 12시간).
- **디스크 가드**: `MIN_FREE_GB=2` 미만이면 abort + ERROR 로그 + exit 1.
- `HH` 는 **UTC** 시각. 예: `fcmanager_20260616_00.sqlite3` = 06-16 09:00 KST.

### 설치 (dolfinid 에서, 1회)

```bash
sudo mkdir -p /srv/fcmanager/scripts /srv/fcmanager/backup
sudo cp scripts/backup_db.py /srv/fcmanager/scripts/   # repo 에서 복사/배치
# cron (DB 쓰기 권한 있는 계정):
crontab -e
# 0 * * * * /usr/bin/python3 /srv/fcmanager/scripts/backup_db.py >> /srv/fcmanager/backup/backup.log 2>&1
```

> 표준 라이브러리만 쓰므로 별도 venv 불필요(python3 만 있으면 됨).

---

## 3. 백업 호스트(m710q) daily pull

- **스크립트**: `/home/jikhanjung/scripts/backup-fcmanager.sh`
- **cron**: `0 4 * * *` (fsis 03:00, ghdb 03:30 과 겹치지 않게 04:00)
- **방식**: m710q → dolfinid **SSH 키 인증 pull**(scp/rsync). 운영은 SSH 만 받음.
- **운영 접속 설정**: 스크립트 상단 기본값 `honestjung@34.64.158.160:/srv/fcmanager`.
  환경변수로 override: `FCMANAGER_REMOTE_USER`, `FCMANAGER_REMOTE_HOST`, `FCMANAGER_REMOTE_PATH`.

### 설치 (m710q 에서, 1회)

```bash
cp scripts/backup-fcmanager.sh /home/jikhanjung/scripts/
chmod +x /home/jikhanjung/scripts/backup-fcmanager.sh
# SSH 키 인증 선행 (비번 없이 pull 되어야 cron 동작):
ssh-copy-id honestjung@34.64.158.160          # 또는 실제 user@host
# 첫 수동 실행으로 확인:
/home/jikhanjung/scripts/backup-fcmanager.sh --full-snapshot
tail -20 /home/jikhanjung/backups/fcmanager/backup.log
# cron 등록:
crontab -e   # 0 4 * * * /home/jikhanjung/scripts/backup-fcmanager.sh
```

- **DB 계층화**: 30일 이내 매일 / 30일~ 월초만 / 매년 12월 1일 영구.
- **media link-dest 체인**: 월 1일 `monthly/YYYYMM_full/` + 그 외 `daily/YYYYMMDD/`.
  변경 없는 파일은 inode 공유 → 디스크 거의 안 늘어남. 각 스냅이 완전한 트리라
  복원은 원하는 시점 디렉토리에서 그대로 rsync.
- **NAS**(`/nas/JikhanJung/fcmanager_backup/`)·**dev_data**(`/home/jikhanjung/dev_data/fcmanager/`)는
  디렉토리가 있을 때만 동작(없으면 WARN 후 skip).

---

## 4. 복원 절차

> ⚠️ **운영 호스트에서 컨테이너 가동 중 직접 `manage.py` 대량 쓰기·migrate 금지.**
> 컨테이너와 호스트가 같은 SQLite 를 동시에 쓰면 DB 가 손상될 수 있다(fsis devlog 074).
> 스키마 변경은 이미지 빌드 → push → entrypoint `migrate` 경로로만.

### 4.1 1~12시간 전 (운영 hourly, 가장 흔함)

```bash
# 1) 안전 백업
TS=$(date -u +%Y%m%d_%H%M%S)
cp -p /srv/fcmanager/db.sqlite3 /srv/fcmanager/backup/fcmanager_pre_restore_${TS}.sqlite3
# 2) 컨테이너 정지
cd /srv/fcmanager && docker compose -f deploy/docker-compose.yml down   # (compose 위치에 맞게)
# 3) WAL/SHM 잔여 제거
rm -f /srv/fcmanager/db.sqlite3-wal /srv/fcmanager/db.sqlite3-shm
# 4) 원하는 시각 백업으로 교체 (예: 09:00 KST = 00:00 UTC)
cp -p /srv/fcmanager/backup/fcmanager_20260616_00.sqlite3 /srv/fcmanager/db.sqlite3
# 5) 재시작 + 검증
docker compose -f deploy/docker-compose.yml up -d
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8003/FCManager/admin/login/
```

### 4.2 1~30일 전 (m710q 일별 DB)

```bash
scp /home/jikhanjung/backups/fcmanager/db_history/db_20260601.sqlite3 \
    honestjung@34.64.158.160:/tmp/restore.sqlite3
# 운영에서 4.1 의 정지/교체 절차 수행
```

### 4.3 30일~1년 전

m710q `db_history/` 는 30일 초과분이 **월초만** 남는다. 없으면 NAS(`db_history/`, 90일+월초+12월) 확인.

### 4.4 media 시점 복원

각 스냅이 완전한 트리라 단순 rsync:

```bash
# 어제(이번 달) 시점
rsync -avz --delete \
    /home/jikhanjung/backups/fcmanager/media_snapshots/daily/20260615/ \
    honestjung@34.64.158.160:/srv/fcmanager/media/
# 지난 달 1일 시점
rsync -avz --delete \
    /home/jikhanjung/backups/fcmanager/media_snapshots/monthly/202605_full/ \
    honestjung@34.64.158.160:/srv/fcmanager/media/
```

`--delete` 주의 — 사고 이후 추가된 유효 업로드도 함께 사라지니 사전 보관 필요.

### 4.5 전체 호스트 손상 (worst case)

```bash
rsync -avz m710q:/home/jikhanjung/backups/fcmanager/current/ /srv/fcmanager/
# 이후 docker compose up
```

---

## 5. 일상 점검

```bash
# 운영(dolfinid)
tail -20 /srv/fcmanager/backup/backup.log
ls -la /srv/fcmanager/backup/fcmanager_*.sqlite3 | tail -3
df -h /srv/fcmanager

# 백업(m710q)
tail -30 /home/jikhanjung/backups/fcmanager/backup.log
ls -la /home/jikhanjung/backups/fcmanager/db_history/ | head -5
```

`backup.log` 마지막에 `========== 백업 완료 ==========` 가 매일 찍히면 정상.
