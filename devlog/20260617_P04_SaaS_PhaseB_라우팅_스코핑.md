# 20260617_P04 — SaaS Phase B: 라우팅 + 쿼리 스코핑 (세부 계획)

> 상위 계획: [P03](20260617_P03_SaaS_멀티테넌트_전환계획.md) · 선행: [053 Phase A](20260617_053_SaaS_PhaseA_테넌트모델.md)
> 목표: "요청마다 어느 클럽인지 알고(`request.club`), 그 클럽 데이터만 보여주고, 그 클럽으로 저장한다."
> 완료 기준: **2번째 클럽을 만들어도 클럽 간 데이터가 새지 않는다(격리)** + fcsky 단독 동작은 기존 그대로.

## 작업 표면 (현 코드 기준)

- 라우트 ~39개(teams 14·matches 9·competitions 10·notices 5·gallery 1)
- 뷰 ~50개, 뷰 내 직접 `.objects` 호출 ~54곳 → 스코핑 손볼 지점.
- 현재 전부 `config/urls.py` 에서 root 로 묶이고, `URL_PREFIX=FcSky` 면 통째로 `/FcSky/` 하위.

## 설계 결정 (확정)

| 항목 | 결정 |
|---|---|
| 테넌트 식별 | **경로 기반** `/<club-slug>/...` (서브도메인은 후속) |
| reverse/`{% url %}` | **`set_script_prefix()` 방식** — 미들웨어가 슬러그를 떼고 script prefix 로 설정. 뷰·템플릿 무변경 |
| 정적/미디어 | **테넌트 밖 공유 경로**(`/static/`, `/media/`) — 슬러그 접두사 없음 |
| 공유 모델 | `Competition`·`Division` 은 필터 안 함. 단 그 대회의 **경기·순위·입상은 `club` 교집합**으로 |
| 권한 판정 | Phase B 는 데이터 스코프만. "이 클럽 운영진인가"는 **Phase C(`ClubMembership`)** |

### reverse 메커니즘 상세 (핵심)

현 `URL_PREFIX` 는 URLconf 를 정적으로 래핑한다. 멀티테넌트는 이를 **요청별 동적**으로:

1. `TenantMiddleware` 가 `request.path_info` 첫 세그먼트를 슬러그로 해석.
2. `Club` 조회 성공 → `request.club` 설정 + `path_info` 에서 `/<slug>` 제거 +
   `django.urls.set_script_prefix("/<slug>/")`.
3. 이후 root URLconf 가 슬러그 없는 경로로 정상 resolve, `reverse()`/`{% url %}` 는
   script prefix 를 자동으로 다시 붙임 → **기존 뷰·템플릿 한 줄도 안 바뀜**.
4. 정적/미디어 URL 은 슬러그 밖이어야 하므로 `STATIC_URL`/`MEDIA_URL` 에서 `URL_PREFIX` 제거.

플랫폼 경로(`/`, `/signup/`, `/accounts/login|logout/`, `/admin/`)는 슬러그 해석을 건너뛴다.

## 단계 분할

### B1 — 미들웨어 + URL 재구성 (라우팅)
- `apps/clubs/middleware.py`: `TenantMiddleware`(위 메커니즘). 슬러그 미스 → 404,
  비활성 클럽(`is_active=False`) → 404/안내.
- `config/urls.py`: 플랫폼 경로(admin·accounts·랜딩·signup)를 테넌트 밖으로 분리.
  앱 URL 은 그대로(미들웨어가 prefix 처리).
- `settings`: `STATIC_URL`/`MEDIA_URL` 에서 `URL_PREFIX` 분리, 미들웨어 등록.
- **회귀 확인**: `/fcsky/...` 로 전 페이지 200, 정적/미디어 로드 정상.

### B2 — 공개 조회 뷰 스코핑 (읽기)
- 모든 공개 뷰의 조회를 `request.club` 으로 필터(holamodels: Team·Player·Match·
  Opponent·OpponentMatch·Notice·GalleryItem·Award).
- 공유 모델 처리: 대회 목록/상세는 **이 클럽이 참가한 대회만**(CompetitionEntry/Match 기준),
  순위·득점·입상은 `club` 교집합.
- `get_absolute_url`(slug 기반: Team 등)은 script prefix 로 자동 처리되나, slug 가
  이제 클럽 내 unique 라 **lookup 도 `club` 한정**으로(`get_object_or_404(..., club=request.club, slug=...)`).

### B3 — 쓰기/관리 뷰 스코핑 + club 자동 주입
- 운영진 생성/편집 뷰(팀·선수·공지·경기·라인업·대회 입력 등)에서 객체 생성 시
  `club=request.club` 주입, 편집 대상 조회도 `club` 한정.
- 폼 선택지(선수·상대팀 드롭다운 등)도 `request.club` 으로 제한.

### B4 — 중앙 강제 + 격리 테스트
- 스코핑을 한 곳에서 강제: 루트 모델에 매니저 `objects.for_club(club)` +
  뷰 베이스(믹스인) 또는 헬퍼. 누락 방지.
- **격리 테스트**: 2번째 클럽(`demo`) 생성 + 소량 데이터 → 클럽 A 유저가 B 의 URL/객체
  접근 시 404/빈 결과 단위테스트. 교차 누출 0 확인.

### B5 — non-null 확정
- 모든 쓰기가 `club` 을 채우는 게 보장된 뒤, 8개 모델 `club` FK `null=False` 로 AlterField
  마이그레이션(데이터는 Phase A 에서 이미 backfill).

## 위험 / 주의

- **데이터 누출**: 스코핑 누락 1곳 = 사고. B4 의 중앙 강제 + 격리 테스트가 방어선.
- **전역 `is_staff` 잔재**: B 단계에선 "현재 클럽 데이터만" 보이게 하되, 운영진 판정 자체는
  Phase C 까지 전역. 그 사이 superuser/staff 는 모든 클럽 접근 가능(의도된 임시 상태).
- **기존 `/FcSky/` 링크·배포**: `URL_PREFIX=FcSky` → 슬러그 `fcsky` 로 전환. nginx/북마크는
  `/FcSky/` → `/fcsky/` 301 리다이렉트로 흡수(대소문자).
- **static/media 경로 변경**: 운영 nginx 의 `/FcSky/static|media/` alias 도 함께 조정 필요.

## 비범위 (후속 Phase)

- **C**: 클럽별 권한(`ClubMembership` 기반 운영진 판정), 클럽 생성·멤버 초대 화면.
- **D**: 브랜딩 분리(context processor 로 'FC Sky' → `request.club.name`, 로고/테마).
- 서브도메인·커스텀 도메인, 결제, schema/DB-per-tenant.

## 운영 전환 메모

- Phase B 까지 끝나면 운영 배포 시: `DJANGO_URL_PREFIX` 제거(슬러그가 대체),
  nginx 에 `/FcSky/ → /fcsky/` 리다이렉트 + static/media alias 조정, 이미지 빌드·배포.
- 배포 전 B4 격리 테스트 그린 필수.
