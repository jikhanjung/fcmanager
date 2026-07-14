# 20260714_P06 — 경기 결과 `.md` 입력 워크플로 + `MatchEvent.side` home/away 전환

> **배경**: 2026-07-12 K7 서초구 디비전 3경기 결과 입력에서 출발. 그중 2건은
> **상대팀끼리의 경기**(우리 팀 미참가)라 득점자를 기록하려면 `MatchEvent.side`
> (OUR/OPPONENT)로는 표현이 불가능하다(OUR/OPPONENT는 *우리 클럽* 기준). 이에
> side 를 **HOME/AWAY(절대 기준)** 로 전환하고, 동시에 **"경기당 `.md` 1개"** 재사용
> 입력 포맷 + `import_results` 관리 명령을 신설한다.
>
> **P05 뒤집기**: `20260617_P05` 는 "MatchEvent.side(OUR/OPPONENT) — 이벤트는 우리
> 경기에만 존재 → 그대로 둔다"고 결정했다. 이제 상대팀 경기에도 이벤트를 남기므로
> 그 전제가 깨진다. 본 문서가 그 결정을 갱신한다.

## 0. 결정 요약 (2026-07-14)

| 항목 | 결정 |
|------|------|
| `MatchEvent.side` | OUR/OPPONENT → **HOME/AWAY** 전면 전환 (+ 데이터 마이그레이션) |
| 입력 경로 | 운영 DB shell 직접 X → **`.md` + `import_results` 관리 명령** 정식 경로 |
| `.md` 단위 | **경기당 1개 파일** (KFA 경기기록 PDF 1건 = `.md` 1건 대응) |
| 이벤트 범위 | 스코어 + 득점자/자책골 (+ 가능 시 경고·교체). 불완전분은 파일에 `(미상)` 명시 |
| 개발/검증 | **개발/테스트 환경**(도커 test target = dev_data 폐기 사본)에서 구현·검증 |
| 운영 반영 | 개발 검증 후 **정식 이미지 빌드 → 배포 → 운영에서 `import_results --apply`** |

## 1. 목표 데이터 (2026-07-12 · `k7-seocho-2026` · 인재개발원)

세 경기 픽스처는 이미 존재(일정 사전 등록). 15번은 우리 팀 경기라 스코어·득점자까지
입력돼 있고 **시간만** 새 데이터로 수정한다. 16·22 는 스코어·이벤트를 채운다.

| Match | 킥오프(KST) | 홈 | 스코어 | 원정 | 현재 상태 | 조치 |
|------|-----------|-----|--------|------|----------|------|
| **15** | 11:20 | 시누쓰 | 0–2 | 스카이 K7 | 스코어·득점자 O | 득점 **시간만** 14'/21' 로 수정 |
| **16** | 12:30 | HUMBLEFC | 4–2 | ACI | 스코어 None | 4–2 + 득점자 |
| **22** | 13:40 | FC오키나와 | 1–0 | 리얼FC | 스코어 None | 1–0 + 득점자 |

### 득점자 상세 (PDF 기준, `(미상)` = 기록 없음)

**Match 15 — 시누쓰 0–2 스카이 K7** (우리 경기, 스카이=원정)
- 스카이 박찬영 **14'** (기존 13' → 14')
- 스카이 동재민 **21'** (기존 20' → 21')

**Match 16 — HUMBLEFC 4–2 ACI** (전반 0–2, 후반 4–0)
- ACI 빈선규 21' · ACI 정준완 23' (원정 2골, 전반)
- HUMBLE 오봉준 40' · HUMBLE 김준수 58' · **HUMBLE (미상) ~60'** (홈 필드 3골)
- ACI 심재영 50' **자책골**(홈 득점으로 산입) → HUMBLE 계 4골
- 검산: 홈 = 필드3 + 자책1 = 4 ✓ / 원정 = 2 ✓

**Match 22 — FC오키나와 1–0 리얼FC** (전반 0–0, 후반 1–0)
- 오키나와 **(미상) 45'** (홈 1골)

> 주의: KFA PDF 상단에 "등록된 기록이 없습니다(필드/GK)"라 골 기록은 라인업 `득점`
> 칸(분)·자책골 표에서만 복원한 **비공식·부분** 데이터다. 미상 항목은 파일에 명시한다.

## 2. `MatchEvent.side` → HOME/AWAY 리팩터

### 2.1 모델 (`apps/matches/models.py`)
- `Side.OUR/OPPONENT` → **`HOME="HOME"("홈")` / `AWAY="AWAY"("원정")`**. `default=Side.HOME`.
- `player` 도움말 유지("우리 팀 이벤트일 때 선택") — 선수 링크는 여전히 우리 팀 한정.

### 2.2 데이터 마이그레이션 (기존 이벤트 변환, `RunPython` + reverse 제공)
경기별로 `home_entry`/`away_entry`/`our_entry` 를 보고 변환:
- **우리 경기**(our_entry 존재): `our_is_home = our_entry == home_entry`
  - `OUR → HOME if our_is_home else AWAY`
  - `OPPONENT → AWAY if our_is_home else HOME`
- **상대팀 경기**(our_entry 없음): 기존 detail 템플릿 컨벤션(OUR=홈) 따름
  - `OUR → HOME`, `OPPONENT → AWAY`
- 통합식: `OUR → AWAY` 는 (우리 경기 && our_entry==away) 일 때만, 그 외 `OUR → HOME`.
- reverse: 위 규칙의 역(롤백 대비). 운영 현황상 변환 대상은 소수(예: match 15 의 2골: OUR·스카이=원정 → **AWAY**).

### 2.3 `apps/matches/services.py`
- `recompute_score()` **home/away 기준으로 재작성** — `home_score = GOAL@HOME + OWN_GOAL@AWAY`,
  `away_score = GOAL@AWAY + OWN_GOAL@HOME`, PSO 동일. `our_entry` 조기 반환 제거 →
  상대팀 경기도 이벤트로 산출 가능(콘솔은 여전히 우리 경기에만 사용).
- `our_events()`·`scorers()` 의 `side=OUR` 필터 **제거**, `player__isnull=False` 로 대체.
  (선수 FK 는 우리 클럽 선수에만 존재하므로 이것만으로 "우리 팀 이벤트" 와 동치.)
- `build_timeline()` 의 `a.side == e.side` 페어링·`serialize_timeline()` 의 `side`/`side_display`
  는 그대로 동작(값만 HOME/AWAY).

### 2.4 콘솔 뷰 (`apps/matches/views.py`)
- 콘솔 UI 는 **"우리/상대" UX 유지**(운영자는 자기 팀 중계). POST 의 `OUR/OPPONENT` 를
  뷰에서 home/away 로 **번역**: `our_is_home = match.our_entry == match.home_entry`
  → 우리쪽=`HOME if our_is_home else AWAY`, 상대쪽=반대. 선수는 우리쪽에만 세팅.
- goal/event/sub/pso/delete 핸들러의 `Side.OUR` 참조 전부 위 번역 헬퍼로 교체.

### 2.5 템플릿
- `match_detail.html`: 이벤트 팀 표기를 **side→entry 이름으로 일원화** —
  `side=='HOME' → home_entry.name`, `AWAY → away_entry.name` (우리/상대 분기 제거).
  L76 정렬 `'OPPONENT'→'AWAY'`, L171 JS `it.side==='AWAY'`.
- `match_live.html`: 버튼 `data-goal="OUR"/"OPPONENT"` **그대로**(콘솔 UX). 라이브 타임라인
  `side_display` 는 serialize 가 채운 값 사용.
- `match_edit.html`: `f.side` 폼셋 — choices 자동 반영, 변경 불요.

### 2.6 테스트 (`apps/matches/tests.py`)
- 콘솔 액션 테스트는 UI 계약(OUR/OPPONENT) 유지 → POST 파라미터 그대로.
- 저장 결과 검증을 `side="HOME"/"AWAY"` 로 갱신. 상대팀 경기 이벤트/스코어 케이스 **추가**.
- `recompute_score` home/away 재작성 회귀 테스트 추가.

## 3. `.md` 포맷 (경기당 1개)

파일 위치·이름: **`data/results/<YYYY-MM-DD>_<홈slug>-vs-<원정slug>.md`**.
프론트매터(메타) + `## 이벤트` 표.

```markdown
---
competition: k7-seocho-2026      # 대회 슬러그
date: 2026-07-12                 # KST 경기일
kickoff: "12:30"                 # KST 킥오프(선택; 매칭·보정용)
venue: 인재개발원
home: HUMBLEFC                   # 시스템 등록명(참가팀 name)
away: ACI
score: 4-2                       # home-away
status: FINISHED                 # 기본 FINISHED
stage: GROUP                     # 기본 GROUP
---

## 이벤트
| 분 | 팀 | 유형 | 선수 | 도움 |
|----|------|------|------|------|
| 21 | ACI      | 득점   | 빈선규  |     |
| 23 | ACI      | 득점   | 정준완  |     |
| 40 | HUMBLEFC | 득점   | 오봉준  |     |
| 50 | ACI      | 자책골 | 심재영  |     |
| 58 | HUMBLEFC | 득점   | 김준수  |     |
| 60 | HUMBLEFC | 득점   | (미상)  |     |
```

### 규격
- **팀 컬럼** = `home`/`away` 에 적은 이름 중 하나(문자열 일치). 파서가 home/away →
  `MatchEvent.side` 로 변환. 우리 팀 쪽 선수는 로스터에서 Player 링크, 상대팀·`(미상)`
  은 `player=null` + `description=선수명`(또는 공란).
- **유형** = 득점/도움/자책골/경고/퇴장/교체IN/교체OUT ↔ `EventType`.
  자책골은 **범한 팀(side)** 에 기록(예: ACI 심재영 자책 → side=AWAY → 홈 득점 산입).
- **도움** 은 같은 행 득점에 링크(`goal` FK).
- 팀 이름은 **KFA 정식명이 아니라 시스템 등록명**(`스카이 K7`, `HUMBLEFC`, `ACI` …).

### 매칭 규칙 (기존 픽스처에 결과 채우기)
1. `competition` 슬러그로 대회 조회.
2. 그 대회에서 `kickoff` **날짜(KST)==date** 이고 `home_entry.name==home` &&
   `away_entry.name==away` 인 Match 검색.
3. 정확히 1건 → 갱신. 0건 → 오류(`--create` 시 참가팀 name 으로 entry 해석 후 픽스처 생성).
   2건↑ → 오류(수동 확인).

## 4. `import_results` 관리 명령 (`apps/matches/management/commands/`)

### 인터페이스
```
python manage.py import_results <file.md> [<file2.md> …] [--apply] [--create]
```
- **기본 = dry-run**: 파싱·매칭·계획된 변경(before→after diff)만 출력, 쓰기 없음.
- `--apply`: `transaction.atomic` 안에서 반영. `--create`: 매칭 실패 시 픽스처 생성 허용.

### 동작
1. 프론트매터·이벤트표 파싱(경기당 1파일). 여러 파일 인자 순회.
2. §3 매칭 규칙으로 대상 Match 결정.
3. 스코어 반영: `score` 를 home/away 로 분해해 `home_score`/`away_score`, `status`,
   `venue`/`kickoff`(있으면) 세팅.
4. **이벤트 동기화**(파일에 `## 이벤트` 섹션이 있을 때만): 대상 Match 의
   기록성 이벤트(득점/자책/도움/경고/퇴장/교체)를 파일 기준으로 **재구성**
   (기존 것 삭제 후 재생성) → 멱등. 섹션이 없으면 이벤트는 **손대지 않음**.
   - 우리 팀 side 선수는 로스터(해당 팀 클럽 선수)에서 이름으로 Player 조회, 없으면
     **경고** + `player=null`+`description=이름`.
5. 출력: 경기별 변경 요약(스코어 diff, 이벤트 추가/삭제 수, 미해결 선수 경고).

### 멱등·안전
- 재실행 시 동일 결과(변경 0). 이벤트는 (분, side, 유형, 선수/설명) 순 정렬로 결정적.
- 파일이 이벤트 섹션을 가지면 그 경기 이벤트의 **단일 소스**가 된다 → 15번 파일은
  기존 2골(→14'/21')을 반드시 포함해야 안전(포함하므로 시간만 갱신되는 no-op 아님/의도적 수정).
- 콘솔로 넣은 데이터를 파괴하지 않도록, 이벤트 섹션 없는 파일은 스코어만 만진다.

## 5. 롤아웃 순서

### 5.1 개발/검증 (운영 무영향)
- 코드 구현(§2~4)은 repo 에서. **마이그레이션·import 는 dev_data 폐기 사본에서 검증**:
  도커 test target(`/srv/fcmanager/deploy-dev.sh X.Y.Z`, HOST_PORT 8005, DB=dev_data 복사·폐기; CLAUDE.md·devlog 087) 로 신 이미지 기동 → `migrate` → `import_results --dry-run`→`--apply` → 공개 페이지·콘솔 육안 확인.
  - dev_data **미러(daily 갱신)** 에 직접 migrate 금지 — 반드시 복사본(test target)에서.
- `python manage.py test apps.matches` 그린.

### 5.2 빌드·배포
- 버전 범프 → `deploy/build.sh` → `deploy/remote-prod.sh X.Y.Z`(운영 self-heal 배포).
- 배포 시 엔트리포인트가 `migrate` 실행 → side 데이터 마이그레이션 적용.

### 5.3 데이터 반영
- `data/results/2026-07-12_*.md` 3개 작성(§1 데이터).
- 운영 컨테이너에서 `import_results *.md --dry-run` 검토 → `--apply`.

### 5.4 스모크/검증
- 공개: 순위표(16·22 반영), 경기 상세 타임라인(홈/원정 득점자 표기), 득점 순위(우리 선수 불변).
- 콘솔: 우리 경기 득점 기록/삭제가 여전히 정상(회귀 없음).

## 6. 리스크 & 완화

| 리스크 | 완화 |
|--------|------|
| 데이터 마이그레이션 오변환(중계 타임라인 좌우 반전) | 변환 규칙 단위 테스트 + test target 육안 확인, reverse 제공 |
| 라이브 콘솔 회귀(우리/상대 번역 버그) | 콘솔 UI 계약 유지 + 기존 테스트 + home/away 번역 헬퍼 단일화 |
| import 가 콘솔 입력 이벤트 삭제 | 이벤트 섹션 있는 파일만 이벤트 동기화, atomic + dry-run 선검토 |
| 상대팀 선수는 Player 없음 | player=null + description 로 이름 보존(리더보드 영향 없음) |
| 부분/미상 득점자 | `(미상)` 명시, 스코어는 `score` 라인이 정본 |

## 7. 작업 체크리스트

- [ ] 모델: `Side` HOME/AWAY + 마이그레이션(RunPython, reverse)
- [ ] services: `recompute_score` 재작성 · `our_events`/`scorers` 필터 교체
- [ ] views: 콘솔 우리/상대→home/away 번역 헬퍼 · 핸들러 교체
- [ ] 템플릿: detail 표기 일원화 · JS side 값 · live/edit 확인
- [ ] tests: side 값 갱신 + 상대팀 경기/ recompute 회귀 추가
- [ ] `.md` 포맷 파서 + `import_results` 명령(dry-run/apply/create)
- [ ] `data/results/2026-07-12_*.md` 3건 작성
- [ ] test target 검증(마이그레이션·import·육안) → 빌드·배포 → 운영 import
- [ ] 작업 devlog(### 문서) + 커밋
