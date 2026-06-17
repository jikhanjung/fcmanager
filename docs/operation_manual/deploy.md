# FC Sky 배포 운영 매뉴얼 (dolfinid)

> **대상**: 운영자 (dolfinid = honestjung@34.64.158.160)
> **원칙**: 개발 소스(`~/projects/FcSky`)는 git 체크아웃일 뿐 **런타임이 아니다**.
> 운영 컨테이너는 `/srv/FcSky/` 에 둔 파일로만 기동한다.
> **관련**: `devlog/20260617_050_배포_런타임_srv분리.md`, `docs/operation_manual/backup.md`

---

## 0. 구조 요약

```
~/projects/FcSky/            # git 체크아웃 (소스). 여기서 직접 기동하지 않는다.
  ├─ deploy/sync_to_srv.sh   #   → /srv 로 운영 파일 복사하는 진입점
  ├─ deploy/host/docker-compose.yml, deploy.sh   # /srv 로 복사될 운영 파일
  └─ scripts/backup_db.py    #   → /srv 로 복사될 hourly 백업 스크립트

/srv/FcSky/                  # 런타임 (운영 기동은 여기서만)
  ├─ db.sqlite3, media/, backup/, maintenance/
  ├─ docker-compose.yml      # sync_to_srv 가 복사 (build 없이 IMAGE_TAG pull)
  ├─ deploy.sh               # sync_to_srv 가 복사 (버전 스왑)
  ├─ scripts/backup_db.py    # sync_to_srv 가 복사
  └─ .env                    # 호스트 관리(비밀 + IMAGE_TAG). sync 대상 아님
```

---

## 1. 최초 1회 마이그레이션 (현 구조 → 새 구조)

> 지금 운영은 `~/projects/FcSky/deploy/` 에서 `docker compose up`(컨테이너 `deploy-web-1`)으로
> 돌고 있다. 이를 `/srv/FcSky/` 기동(컨테이너 `fcsky`)으로 한 번만 옮긴다.

```bash
# (1) 소스 최신화 + 운영 파일 동기화
cd ~/projects/FcSky
git pull
./deploy/sync_to_srv.sh

# (2) .env 를 런타임 위치로 복사 + IMAGE_TAG 추가
#     (원본 deploy/.env 는 남겨둬도 무방 — cp)
cp -p deploy/.env /srv/FcSky/.env
grep -q '^IMAGE_TAG=' /srv/FcSky/.env || echo "IMAGE_TAG=0.5.7" >> /srv/FcSky/.env
sed 's/=.*/=***/' /srv/FcSky/.env        # 확인(값 마스킹): SECRET_KEY, IMAGE_TAG 두 줄

# (3) 기존(개발소스 기동) 컨테이너 내리기  → 포트 8003 해제
cd ~/projects/FcSky/deploy
docker compose down                       # deploy-web-1 종료

# (4) 새 위치에서 기동 (pull → pre-deploy 스냅샷 → up → 헬스체크)
/srv/FcSky/deploy.sh 0.5.7

# (5) 검증
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/FcSky/admin/login/   # 200 기대
docker compose -f /srv/FcSky/docker-compose.yml ps                                     # fcsky Up
```

마이그레이션 후 `~/projects/FcSky` 는 순수 소스로만 두고, 운영 기동·재기동은 `/srv/FcSky` 에서만 한다.

---

## 2. 평상시 배포 (버전 올릴 때)

```bash
# (m710q) 이미지 빌드·푸시
docker build -f deploy/Dockerfile --build-arg DJANGO_URL_PREFIX=FcSky \
  -t honestjung/fcsky:X.Y.Z . && docker push honestjung/fcsky:X.Y.Z

# (dolfinid) 동기화 + 교체
cd ~/projects/FcSky && git pull
./deploy/sync_to_srv.sh        # 운영 파일(compose/deploy.sh/backup_db.py) 갱신
/srv/FcSky/deploy.sh X.Y.Z     # 이미지 pull → IMAGE_TAG 갱신 → down → 스냅샷 → up → 헬스체크
```

- `deploy.sh` 가 컨테이너 교체 전 **pre-deploy DB 스냅샷**을 `/srv/FcSky/backup/pre_deploy/` 에 남긴다(최근 10개).
- 새 마이그레이션은 컨테이너 entrypoint 가 시작 시 `migrate` 로 자동 적용.
- down~up 사이 짧은 공백엔 nginx 가 502 → `maintenance.html` 자동 노출.

---

## 3. 롤백

```bash
# 직전 버전으로 이미지만 되돌리기
/srv/FcSky/deploy.sh <이전버전>

# DB 까지 되돌려야 하면 (배포 직후 사고): pre-deploy 스냅샷 사용
ls -1t /srv/FcSky/backup/pre_deploy/fcsky_pre_deploy_*.sqlite3 | head
cd /srv/FcSky && docker compose down
cp -p /srv/FcSky/backup/pre_deploy/fcsky_pre_deploy_<버전>_<TS>.sqlite3 /srv/FcSky/db.sqlite3
rm -f /srv/FcSky/db.sqlite3-wal /srv/FcSky/db.sqlite3-shm
docker compose up -d
```

마이그레이션 자체를 되돌리려면(새 구조 실패 시): `/srv/FcSky` 컨테이너 down 후
`cd ~/projects/FcSky/deploy && docker compose up -d` 로 기존 방식 복귀.

---

## 4. 주의

- **운영 컨테이너 가동 중 호스트에서 직접 `manage.py` 대량 쓰기·migrate 금지** — 컨테이너와
  호스트가 같은 SQLite 를 동시에 쓰면 DB 손상. 스키마 변경은 이미지 빌드→push→entrypoint migrate.
- `.env` 비밀값(`DJANGO_SECRET_KEY`)은 git 비추적. `/srv/FcSky/.env` 권한 600 유지.
- 관리자(`admin`) 비번은 **2026-06-17 운영에서 교체 완료**. compose 의
  `DJANGO_SUPERUSER_PASSWORD` 는 신규 DB 부트스트랩용 기본값일 뿐, 기존 운영 계정
  비번을 바꾸지 않는다(entrypoint 는 계정이 없을 때만 생성). 운영 실제 비번은
  `/srv/FcSky/.env` 또는 별도 비밀 관리로 둘 것(평문 커밋 금지).

---

## 5. m710q 후속 (마이그레이션 완료 후 1회)

`.env` 가 `/srv/FcSky/.env` 로 옮겨지면, m710q 백업 스크립트의 `.env` pull 경로도 갱신해야 한다.
repo 는 이미 `/srv/FcSky/.env` 로 정정돼 있으니 배포본만 갱신:

```bash
# m710q
cd ~/projects/FcSky && git pull
cp scripts/backup-fcsky.sh ~/scripts/backup-fcsky.sh
~/scripts/backup-fcsky.sh --full-snapshot
grep '\.env' ~/backups/FcSky/backup.log | tail -1     # ".env 복사 완료" 확인
```
