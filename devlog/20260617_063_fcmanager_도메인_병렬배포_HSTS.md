# 20260617_063 — fcmanager.app 병렬 배포 + HTTPS/HSTS (dolfinid)

> 멀티테넌트 SaaS(FCManager)를 전용 도메인 `fcmanager.app` 으로 **신규 가동**.
> 기존 `fcsky`(레거시 `/FcSky/` 서브패스)는 **그대로 두고 나란히(parallel)** 운영.

## 결정 / 문서와 다른 점

배포 매뉴얼(deploy.md)·devlog 050/061/062 는 fcsky 를 **교체(in-place)** 하는 전제였으나,
이번엔 **병렬 운영**(레거시 fcsky 유지 + fcmanager 신규)으로 진행. 그래서:

- **포트 분리**: 레거시 fcsky `8003` 유지 → fcmanager 는 **`8004`**.
- **런타임 분리**: `/srv/FcSky`(레거시) 그대로, **`/srv/fcmanager`** 신규 생성.
- **초기 데이터**: `/srv/FcSky` 의 일관 스냅샷을 복사해 0.6.0 마이그레이션으로 `fcsky` 클럽 backfill.

## 레포 변경 (포트 파라미터화)

병렬 운영을 위해 운영 compose/deploy.sh 의 포트를 `.env HOST_PORT` 로 override 가능하게(기본 8003 유지).

- `deploy/host/docker-compose.yml`: `ports: ["${HOST_PORT:-8003}:8000"]`
- `deploy/host/deploy.sh`: 헬스체크 포트를 `.env` 의 `HOST_PORT` 에서 읽음(기본 8003)

## dolfinid 실행 내역

1. **/srv/fcmanager 생성**: `scripts/ backup/pre_deploy/ media/ maintenance/`, 소유 `ubuntu:ubuntu`(컨테이너 uid 1000).
2. **DB**: `/srv/FcSky/backup/fcsky_20260617_05.sqlite3`(online backup API 일관 스냅샷) → `/srv/fcmanager/db.sqlite3`.
   가동 중 fcsky DB 직접 cp 대신 스냅샷 사용(쓰기 충돌 회피).
3. **media**: `/srv/FcSky/media/` rsync 복사.
4. **.env**: 새 `DJANGO_SECRET_KEY`(별도 발급) + `IMAGE_TAG=0.6.0` + `HOST_PORT=8004` (600, honestjung).
   superuser 비번 미지정 → 복사 DB 의 기존 `admin` 그대로 사용(entrypoint 는 계정 없을 때만 생성).
5. **sync_to_srv.sh** → compose/deploy.sh/backup_db.py 복사.
6. **deploy.sh 0.6.0**: pull → pre-deploy 스냅샷 → up(8004) → 헬스체크 통과.
7. **nginx**: `/etc/nginx/sites-available/fcmanager`(proxy → 8004, media alias `/srv/fcmanager/media`),
   sites-enabled 심링크, `nginx -t` OK, reload.
8. **certbot --nginx -d fcmanager.app -d www.fcmanager.app --redirect --hsts**:
   인증서 발급(만료 2026-09-15) + HTTP→HTTPS 301 + HSTS `max-age=31536000`(`always`).

## 검증

- backfill: `Club(fcsky,"FC Sky")` 1개, 팀 3·선수 59·경기 13 전량 fcsky 클럽으로 스코핑 확인.
- 신규: `https://fcmanager.app/` 200, `/fcsky/` 200, `/admin/login/` 200, HTTP→HTTPS 301, HSTS 헤더 존재.
- 레거시: `http://127.0.0.1:8003/FcSky/` 200 (무영향).
- 컨테이너: `fcsky`(8003, 0.5.7) + `fcmanager`(8004, 0.6.0) 동시 가동.

## 남은 후속 작업

- **신규 인스턴스 백업 cron 미설정** — hourly `backup_db.py` 는 아직 `/srv/FcSky` 트랙만 가동.
  `/srv/fcmanager/db.sqlite3` 는 현재 hourly/daily 백업 대상 아님 → cron 추가 필요(중요).
- m710q daily pull 의 대상 경로(`/srv/FcSky` → 신규 포함) 정리.
- 레거시 fcsky 최종 폐기 시점·절차(데이터 재복사 후 컨테이너/`/srv/FcSky` 정리) 결정.
- HSTS 강화(`includeSubDomains`/`preload`)는 보류 — 서브도메인 영향·preload 비가역성 때문에 별도 결정.

## 참고

- 도메인/이미지 준비: devlog 061, 리브랜딩: devlog 062, 배포 매뉴얼: `docs/operation_manual/deploy.md`.
