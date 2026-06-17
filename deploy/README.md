# 배포 (Docker)

FCManager 애플리케이션 컨테이너 이미지 빌드/실행 안내.

## 빌드

프로젝트 **루트**를 빌드 컨텍스트로 사용한다(코드 전체를 COPY 하기 위함):

```bash
# 서브패스(/FCManager/) 배포용 — 정적 파일을 접두사에 맞춰 수집하도록 build-arg 지정
docker build -f deploy/Dockerfile --build-arg DJANGO_URL_PREFIX=FCManager \
  -t honestjung/fcmanager:0.1.2 -t honestjung/fcmanager:latest .
```

> 루트(`/`)에서 서비스하려면 `--build-arg DJANGO_URL_PREFIX` 를 생략한다.

## 실행

호스트 8000 포트는 portainer가 점유 중이므로 **8003** 으로 노출한다.

```bash
docker run --rm -p 8003:8000 \
  -e DJANGO_URL_PREFIX=FCManager \
  -e DJANGO_SECRET_KEY="$(openssl rand -base64 48)" \
  -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1" \
  -e DJANGO_SEED=1 \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_PASSWORD=change-me \
  -v fcsky-db:/app/db \
  honestjung/fcmanager:0.1.2
```

→ http://localhost:8003/FCManager/  (admin: `/FCManager/admin/`)

> 권장: `docker compose -f deploy/docker-compose.yml up --build` (포트·접두사·볼륨이
> 미리 설정됨).

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DJANGO_SECRET_KEY` | (개발용 키) | 운영에선 반드시 지정 |
| `DJANGO_DEBUG` | `false` (이미지 기본) | `true`/`false` |
| `DJANGO_URL_PREFIX` | (없음=루트) | 서브패스 배포 접두사. 예: `FCManager` → 사이트가 `/FCManager/` 하위. **빌드 시 동일한 `--build-arg` 도 지정**해야 정적 파일이 맞음 |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | 콤마 구분 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (없음) | 콤마 구분, 예: `https://fcsky.example.com` |
| `DJANGO_SEED` | (없음) | `1` 이면 시작 시 초기 데이터 시드(멱등) |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | (없음) | 지정 시 관리자 계정 생성 |

## 주의

- 현재 DB는 SQLite(`/app/db.sqlite3`)다. 데이터 영속화는 해당 경로를 볼륨으로
  마운트하거나, 운영 전 PostgreSQL 전환을 권장(로드맵 Phase 5).
- 업로드 미디어(`/app/media`)도 영속화하려면 볼륨 마운트 필요.
- `docker compose -f deploy/docker-compose.yml up` 로도 실행 가능.

## nginx 리버스 프록시 (서브패스 `/FCManager/`)

Django가 `/FCManager/` 접두사를 **직접 라우팅**하므로 nginx는 경로를 자르지 말고
(`rewrite`/접두사 제거 없이) 그대로 컨테이너로 넘긴다. 정적 파일은 WhiteNoise가
`/FCManager/static/` 에서 직접 서빙한다.

```nginx
location /FCManager/ {
    proxy_pass http://127.0.0.1:8003;   # 경로 그대로 전달(끝에 / 없음 = 접두사 유지)
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;   # HTTPS 인식(보안 쿠키·CSRF)
}
```

> HTTPS 도메인을 쓰면 `DJANGO_CSRF_TRUSTED_ORIGINS=https://<도메인>` 과
> `DJANGO_ALLOWED_HOSTS` 에 도메인을 추가한다.
