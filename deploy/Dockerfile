# FC Sky — Django 애플리케이션 이미지
# 빌드는 프로젝트 루트를 컨텍스트로:  docker build -f deploy/Dockerfile -t honestjung/fcsky:0.2.2 .
FROM python:3.12-slim

# 릴리스 버전(단일 소스). 이 값을 올리면 LABEL·런타임 ENV·navbar 표시가 함께 바뀐다.
ARG APP_VERSION=0.2.2

LABEL org.opencontainers.image.title="FC Sky" \
      org.opencontainers.image.description="FC Sky 웹사이트 (Django)" \
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

# 서브패스 배포 시 정적 파일 내부 url() 참조도 접두사에 맞춰 수집해야 하므로
# collectstatic 전에 동일 접두사를 적용한다(런타임 DJANGO_URL_PREFIX와 일치시킬 것).
#   docker build --build-arg DJANGO_URL_PREFIX=FcSky ...
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
