# FC Sky — Django 애플리케이션 이미지
# 빌드는 프로젝트 루트를 컨텍스트로:  docker build -f deploy/Dockerfile -t honestjung/fcsky:0.1.1 .
FROM python:3.12-slim

LABEL org.opencontainers.image.title="FC Sky" \
      org.opencontainers.image.description="FC Sky 동네 축구팀 웹사이트 (Django)" \
      org.opencontainers.image.version="0.1.1" \
      org.opencontainers.image.source="https://github.com/honestjung/fcsky"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DEBUG=false

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 엔트리포인트 (고정 경로로 복사)
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 애플리케이션 코드
COPY . .

# 정적 파일 수집 (WhiteNoise manifest 생성). 빌드 시 SECRET_KEY 기본값 사용.
RUN python manage.py collectstatic --noinput

# 비루트 사용자로 실행
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
