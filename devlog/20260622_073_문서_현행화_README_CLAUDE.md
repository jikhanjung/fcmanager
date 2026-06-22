# 20260622_073 — 문서 현행화 (README·CLAUDE.md·HANDOFF)

> repo 리네임(devlog 070)·레거시 fcsky 폐기(devlog 072) 정리에 이어, 코드 실제 상태와
> 벌어져 있던 프로젝트 문서(README·CLAUDE.md)를 현행화.

## 배경

README·CLAUDE.md 가 단일 클럽·초기 Phase 기준으로 남아 있어 실제와 불일치:
- 멀티테넌트 SaaS 전환·배포가 반영 안 됨(단일 사이트로 서술).
- 앱 구조에 `clubs`/`notices`/`gallery` 누락, `competitions` 에 **제거된 `Season`** 표기 잔존.
- 대회 아래 **부문(Division)** 구조 미반영.
- "데이터 입력은 1차적으로 Django Admin" — 실제로는 대부분 **운영진 웹 화면**(`/manage/`·
  `/teams/`·`/matches/`, `@staff_required`)에서 입력하도록 전환된 상태.
- 로드맵/현재 상태가 "Phase 1·2 완료"에 멈춰 있음(실제 Phase 1~4 완료 + 배포).

## 확인 (코드 근거)

서브에이전트로 실제 모델·URL·뷰를 조사해 추측 없이 반영:
- `Season` 모델 없음 — `Competition.year` 직접 보유. `Competition → Division(연령대) →
  CompetitionEntry(팀/Opponent) → Match(home/away entry)` 구조.
- 웹 입력 가능: 대회·부문(`/manage/competitions/`), 팀·명단(`/teams/…`), 선수(`/manage/players/`),
  경기 결과·이벤트·영상(`/matches/<pk>/edit/`), 클럽(`/clubs/new/`).
- 아직 admin 전용: CompetitionEntry·Award·Opponent·MatchLineup·ClubMembership·부문 시간 오버라이드.

## 변경

- **README.md**: 제목/소개를 멀티테넌트 SaaS(`fcmanager.app`, FC Sky=첫 클럽)로, 앱 구조 보강,
  "도메인 구조" 절 신설, "데이터 입력"을 웹 화면 중심으로 재작성, DB(SQLite 운영·PG 보류)·
  로드맵(Phase 1~5) 반영, HANDOFF/TODOs/devlog 링크 추가.
- **CLAUDE.md**: 구조(clubs/notices/gallery 추가, Division 반영, Season 제거),
  도메인 핵심(멀티테넌트 Club FK·대회→부문→참가팀→경기, TeamMembership 선수↔팀↔대회,
  MatchEvent=실시간 중계 기반), 데이터 입력 규칙(운영진 웹 화면 중심), 현재 상태(Phase 1~4 완료)로 정정.
- **HANDOFF.md**: 최종 갱신일 2026-06-20 → 2026-06-22.

## 커밋

- `7480f44` README 현행화
- `6284162` CLAUDE.md 현행화
- `68803d4` HANDOFF 최종 갱신일

## 메모

- 에셋 파일명(`fcskylogo.png`)은 그대로 — 클럽별 로고·CI 작업 때 정리 예정.
