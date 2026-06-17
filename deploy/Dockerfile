# FCManager — Django 애플리케이션 이미지(멀티테넌트 SaaS)
# 빌드는 프로젝트 루트를 컨텍스트로:  docker build -f deploy/Dockerfile -t honestjung/fcmanager:0.5.7 .
FROM python:3.12-slim

# 릴리스 버전(단일 소스). 이 값을 올리면 LABEL·런타임 ENV·navbar 표시가 함께 바뀐다.
ARG APP_VERSION=0.6.0

LABEL org.opencontainers.image.title="FCManager" \
      org.opencontainers.image.description="FCManager — 축구 클럽 관리 SaaS (Django)" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/honestjung/fcsky"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DEBUG=false \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 엔트리포인트 (고정 경로로 복사)
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 애플리케이션 코드
COPY . .

# SaaS(전용 도메인 루트)에서는 URL_PREFIX 미사용 → 정적은 /static/ 로 수집(기본값 빈 값).
# (서브패스 배포가 필요하면 --build-arg DJANGO_URL_PREFIX=... 로 접두사 지정 가능)
ARG DJANGO_URL_PREFIX=""
ENV DJANGO_URL_PREFIX=${DJANGO_URL_PREFIX}

# 정적 파일 수집 (WhiteNoise manifest 생성). 빌드 시 SECRET_KEY 기본값 사용.
RUN python manage.py collectstatic --noinput

# 비루트 사용자로 실행
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
