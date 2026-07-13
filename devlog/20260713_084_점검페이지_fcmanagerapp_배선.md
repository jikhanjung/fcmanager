# 20260713_084 — 점검 페이지 fcmanager.app 배선 (배포 중 502 → 503 점검 안내)

## 배경
- 컨테이너 업데이트(`deploy.sh` down~up) 중 수 초간 **502**가 사용자에게 그대로 노출됨.
- devlog 023 에서 점검 페이지를 만들었으나 대상은 **레거시 FcSky(`/FcSky/` 경로, 2026biennale)**
  뿐이었다. 현 운영 도메인 `fcmanager.app`(컨테이너 127.0.0.1:8004) 의 nginx 설정엔
  `error_page` 배선이 없었고, `/srv/fcmanager/maintenance/` 디렉토리는 비어 있었다.
  → `deploy.sh` 주석("nginx 가 502 → maintenance.html 자동 노출")과 실제 상태가 어긋나 있었음.

## 참고 패턴
- cdGTS(`/etc/nginx/sites-available/cdgts`)의 방식:
  `error_page 502 503 504 =503 /maintenance.html;` + `internal` 전용 location(`root /srv/cdGTS`).
  502 를 **503 으로 재기술**해 검색엔진/클라이언트에 "일시적"임을 알리고, `Retry-After 10`.

## 구현 (서버 로컬 — git 비추적 파일 + 리포 예시 동기화)
1. **점검 페이지**: `/srv/fcmanager/maintenance/maintenance.html`
   - FCManager 브랜드 팔레트(navy `#0a1633`, sky `#2f80ff`), 스피너 + 다크모드 대응.
   - `<meta http-equiv="refresh" content="10">` → 10초마다 자동 새로고침.
   - 한글 안내("시스템 업데이트 중입니다") + 영문 보조 문구.
2. **nginx** `/etc/nginx/sites-available/fcmanager` 의 443·80 블록 `location /` 뒤에:
   ```nginx
   error_page 502 503 504 =503 /maintenance.html;
   location = /maintenance.html {
       root /srv/fcmanager/maintenance;
       internal;
       add_header Retry-After 10 always;
       add_header Cache-Control "no-store, must-revalidate" always;
   }
   ```
   - 백업: `/etc/nginx/sites-available/fcmanager.bak-maint-20260713`.
3. **리포 동기화**(재현·재설치용): `deploy/host/maintenance.html` 추가 +
   `deploy/host/nginx-fcmanager.conf.example` 에 동일 블록·설치 커맨드 반영.

## 테스트
- `sudo nginx -t` 통과(경고는 기존 사이트 간 SSL 옵션 중복, 무관) → `systemctl reload nginx`.
- 평상시: `https://fcmanager.app/` → **200**.
- `docker compose stop web` 후 요청 → **HTTP/2 503** + `Retry-After: 10` +
  `Cache-Control: no-store, must-revalidate` + FCManager 점검 페이지 본문 확인.
- `docker compose start web` → 1초 후 200 복구.

## 남은 것 / 메모
- nginx 설정·maintenance.html 실제 배치는 서버 로컬(git 비추적). 서버 재구성 시
  `deploy/host/` 예시로 재설치. certbot 이 443 블록 재작성해도 error_page 블록은 유지됨.
- 레거시 FcSky(2026biennale) 점검 배선은 devlog 023 그대로(별개 트랙).
