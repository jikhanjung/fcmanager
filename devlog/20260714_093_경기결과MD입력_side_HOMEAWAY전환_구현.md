# 20260714_093 — 경기 결과 `.md` 입력 + `MatchEvent.side` HOME/AWAY 전환 (구현)

> 계획: [`20260714_P06`](20260714_P06_경기결과_MD입력_side_homeaway전환.md). 본 문서는 그 구현 기록.

## 배경

2026-07-12 K7 서초구 디비전 3경기(15/16/22) 결과 입력이 발단. 그중 16·22 는
**상대팀끼리의 경기**(우리 팀 미참가)라 득점자를 `MatchEvent.side`(OUR/OPPONENT,
*우리 클럽* 기준)로는 표현 불가. side 를 **HOME/AWAY(절대 기준)** 로 전환하고,
동시에 **"경기당 `.md` 1개"** 재사용 입력 포맷 + `import_results` 관리 명령을 신설했다.

## 한 일

### A. `MatchEvent.side` OUR/OPPONENT → HOME/AWAY
- `models.py`: `Side.HOME("홈")/AWAY("원정")`, `default=HOME`.
- 마이그레이션 `0019`(AlterField) + `0020`(RunPython 데이터 변환, reverse 제공).
  경기별 `our_is_home`(우리 entry 가 홈인지)으로 변환: 우리 경기는 OUR→HOME/AWAY,
  상대팀 경기는 detail 컨벤션(OUR=홈) 유지. `entry.club_id == match.club_id` 로 판정.
- `services.py`:
  - `recompute_score` **home/away 기준 재작성**(`홈=GOAL@HOME + OWN_GOAL@AWAY`),
    `our_entry` 조기 반환 제거 → 상대팀 경기도 이벤트로 산출.
  - `our_events`/`scorers`: `side=OUR` 필터 제거 → **`player__isnull=False`**.
    (선수 FK 는 우리 클럽 선수에만 링크되므로 "우리 팀 이벤트"와 동치.)
- `views.py`: 콘솔 UI 는 **OUR/OPPONENT UX 유지**, 저장 시 `to_side()` 헬퍼로
  HOME/AWAY 번역(`our_is_home` 기준). goal/event/sub/pso 핸들러 교체.
- `match_detail.html`: side 값 스왑(OPPONENT→AWAY 정렬, OUR→HOME 이름),
  라이브 JS 득점자 라벨 폴백 `player → description → side_display`.
- `admin.py`: 인라인 주석 갱신.

### B. `.md` 포맷 + `import_results` 명령
- 포맷(경기당 1파일): 프론트매터(competition/date/kickoff/venue/home/away/score/
  **half_minutes**/status/stage) + 선택적 `## 이벤트` 표(| 분 | 팀 | 유형 | 선수 | 도움 |).
  - half 는 컬럼 없이 `half_minutes` + 절대 분에서 파생(`분 ≤ half_minutes → 전반`).
  - 상대팀·미상 득점자는 `player=null` + `description=이름`(상대 선수 명단 미보유).
- `apps/matches/management/commands/import_results.py`:
  `import_results <file.md> … [--apply] [--create]`. 기본 dry-run, atomic apply,
  매칭(대회 슬러그 + KST date + home/away name), **이벤트 섹션 있으면 단일 소스로
  삭제 후 재구성(멱등)**, 우리 선수 로스터 이름 링크 + 미해결 경고.

### C. 테스트 — 전체 **77개 그린**
- 신규: side 번역(우리 홈/원정별 HOME/AWAY 저장), 상대팀 경기 recompute,
  import 매칭/스코어/미상/멱등/dry-run/이벤트 보존.

## 데이터 (2026-07-12 · `k7-seocho-2026` · 인재개발원)

PDF(KFA 경기기록)에서 추출 — **계획의 "(미상)" 3건이 실제로는 모두 밝혀짐**:

| Match | 경기 | 득점 | 계획 대비 |
|------|------|------|-----------|
| #15 | 시누쓰 0-2 스카이 K7(우리·원정) | 박찬영 14', 동재민 21' | 일치 |
| #16 | HUMBLEFC 4-2 ACI | 빈선규 21'·정준완 23' / 오봉준 40'·김준수 58'·**신원우 60'** / 심재영 50' 자책(ACI) | 60' = 신원우(미상 아님) |
| #22 | FC오키나와 1-0 리얼FC | **박상욱 45'** | 45' = 박상욱(미상 아님) |

- `.md` 3건은 `data/results/2026-07-12_*.md` 에 작성. `/data/` 는 gitignore →
  **리포 미추적**(운영 결과 입력 데이터로 취급, 계약 seed 레인 경계 준수). 배포 후
  컨테이너에 전송해 import.
- dev_data 읽기전용 조회로 등록명(스카이 K7·HUMBLEFC·ACI·시누쓰·FC오키나와·리얼FC)·
  로스터 확인 → dry-run **미해결 선수 경고 0건**(박찬영·동재민 링크). 세 경기 모두
  현재 이벤트 0건이라 삭제-재구성이 순수 추가(파괴 위험 없음).

## 롤아웃

- 개발/검증: m710q 도커 test target(`deploy-dev.sh`, 8005, DB=`/srv/fcmanager/db`
  = dev_data 복사본) 에서 신 이미지 기동 → migrate(side 변환) → `import_results`
  dry-run→apply → 공개 페이지·콘솔 육안.
- 운영: 버전 범프 → build → `remote-prod.sh` (엔트리포인트 migrate) → 운영 컨테이너
  `import_results --apply`.

## 후속

- 배포·데이터 계약상 `.md` 는 운영 입력물(리포 밖). 향후 상대팀 선수 명단을 모델로
  들이면 description → Player 승격 경로 고려(현재는 불필요).
