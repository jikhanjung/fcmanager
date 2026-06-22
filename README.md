# FCManager 웹사이트

**FCManager**(K7=20-30대 / 40대 / 50대)의 선수단·대회·일정·결과·입상 내역을
관리하고 공개하는 Django 사이트. 향후 실시간 중계 확장을 목표로 한다.

## 기술 스택
- Django 5.1, Python 3.12
- Django Template + Bootstrap 5
- DB: SQLite(개발) → PostgreSQL(운영 예정)

## 프로젝트 구조
```
config/              프로젝트 설정 (settings, urls)
apps/teams/          팀, 선수, 팀 소속(TeamMembership)
apps/competitions/   시즌, 대회, 대회 출전, 입상 내역(Award)
apps/matches/        상대팀, 경기(Match), 경기 이벤트(MatchEvent)
templates/           Bootstrap 기반 템플릿
```

## 개발 환경 실행
```bash
source ~/venv/fcmanager/bin/activate     # 가상환경
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
- 사이트: http://127.0.0.1:8000/
- 관리자: http://127.0.0.1:8000/admin/  (계정은 `createsuperuser` 또는 `.env` 의 `DJANGO_SUPERUSER_PASSWORD` 로 생성)

## 데이터 입력
Phase 1에서는 **Django 관리자(/admin/)** 에서 모든 데이터를 입력한다.
1. 시즌(Season) 등록 → 2. 팀(Team) 등록 → 3. 선수(Player) 등록 후 팀 소속(인라인) 지정
4. 대회(Competition) + 대회 출전(CompetitionEntry) → 5. 상대팀 → 6. 경기(Match) + 이벤트 → 7. 입상 내역(Award)

## 로드맵
- [x] **Phase 1** — 모델 + 관리자 입력 + 기본 페이지
- [ ] **Phase 2** — 공개 조회 페이지(선수단/일정·결과/순위/명예의 전당)
- [ ] **Phase 3** — 회원/권한, 공지·갤러리, 통계 자동 집계
- [ ] **Phase 4** — 실시간 중계(Django Channels)
- [ ] **Phase 5** — PostgreSQL 전환 및 배포
