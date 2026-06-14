# 배포 (Docker)

FC Sky 애플리케이션 컨테이너 이미지 빌드/실행 안내.

## 빌드

프로젝트 **루트**를 빌드 컨텍스트로 사용한다(코드 전체를 COPY 하기 위함):

```bash
docker build -f deploy/Dockerfile -t honestjung/fcsky:0.1.1 -t honestjung/fcsky:latest .
```

## 실행

```bash
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY="$(openssl rand -base64 48)" \
  -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1" \
  -e DJANGO_SEED=1 \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_PASSWORD=change-me \
  -v fcsky-db:/app/db \
  honestjung/fcsky:0.1.1
```

→ http://localhost:8000

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DJANGO_SECRET_KEY` | (개발용 키) | 운영에선 반드시 지정 |
| `DJANGO_DEBUG` | `false` (이미지 기본) | `true`/`false` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | 콤마 구분 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (없음) | 콤마 구분, 예: `https://fcsky.example.com` |
| `DJANGO_SEED` | (없음) | `1` 이면 시작 시 초기 데이터 시드(멱등) |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | (없음) | 지정 시 관리자 계정 생성 |

## 주의

- 현재 DB는 SQLite(`/app/db.sqlite3`)다. 데이터 영속화는 해당 경로를 볼륨으로
  마운트하거나, 운영 전 PostgreSQL 전환을 권장(로드맵 Phase 5).
- 업로드 미디어(`/app/media`)도 영속화하려면 볼륨 마운트 필요.
- `docker compose -f deploy/docker-compose.yml up` 로도 실행 가능.
