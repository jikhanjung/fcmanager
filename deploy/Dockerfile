# FCManager — Django 애플리케이션 이미지(멀티테넌트 SaaS)
# 빌드는 프로젝트 루트를 컨텍스트로:  docker build -f deploy/Dockerfile -t honestjung/fcmanager:0.5.7 .
FROM python:3.12-slim

# 릴리스 버전 단일 소스는 config/version.py. build.sh 가 그 값을 --build-arg 로 넘겨
# LABEL·런타임 ENV 에 반영한다(미지정 시 settings 가 version.py 를 직접 읽음).
ARG APP_VERSION=

LABEL org.opencontainers.image.title="FCManager" \
      org.opencontainers.image.description="FCManager — 축구 클럽 관리 SaaS (Django)" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/jikhanjung/fcmanager"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DEBUG=false \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

# gosu: entrypoint 가 root 로 시작해 마운트(/app/hostdb) 소유 uid 로 권한을 드롭할 때 사용.
# 호스트마다 uid 매핑이 달라도(m710q=1000·dolfinid 계정 구성 상이) 한 이미지로 커버 —
# "디렉터리 마운트 소유권 함정"(devlog 088, 계약 §동사 deploy)의 근본 해소. cdGTS 동형.
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* && gosu nobody true

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

# 비루트 실행은 Dockerfile USER 고정이 아니라 entrypoint 의 gosu 드롭으로 —
# root 로 시작해 /app/hostdb 소유 uid 를 런타임 감지 후 그 uid 로 exec(호스트 무관).
# 최종 서비스 프로세스(gunicorn)는 비-root, root 는 시작 순간(소유 정리)에만 존재.

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
