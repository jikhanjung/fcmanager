# 20261023_098 — emSign CA 손상 대응 베이스 재빌드 + Django 5.2.18 (0.6.27 배포)

## 배경

- **GHSA-6q48-6c7w-9gw2**: eMudhra/emSign 중간 CA 키 손상. 운영 이미지(0.6.26 이하)의 OS 신뢰 저장소
  (Debian `ca-certificates 20250419`)가 **`emSign ECC Root CA - G3`** 를 여전히 신뢰 → 아웃바운드
  HTTPS MITM 여지. (banjang 세션의 다중 프로젝트 점검 요청으로 착수.)
- 같은 릴리스에 미배포 상태였던 `7f3c566`(Django 5.1.15 → 5.2.18 LTS)이 함께 실린다.

## 점검

| 이미지 | ca-certificates | emSign_ECC_Root_CA_-_G3 | certifi |
|--------|-----------------|-------------------------|---------|
| 0.6.25 / 0.6.26 | 20250419 | **있음** | 미설치 |
| 0.6.27 (`--pull` 재빌드) | 20250419+deb13u1 | 없음 | 미설치 |

- certifi 는 의존성에 없다(requests/httpx 미사용) → 핀 불요. Dockerfile 은 pip 업그레이드 없음.
- **Dockerfile 변경 없음** — 해결은 `python:3.12-slim`(trixie) 베이스 갱신분. `build.sh` 가 `--pull` 을
  쓰지 않으므로 빌드 전 `docker pull python:3.12-slim` 으로 로컬 베이스 캐시를 먼저 갱신했다.
- 마이그레이션: 운영 스냅샷 사본에 `migrate --plan` → 없음. `makemigrations --check` 변경 없음. 테스트 112 통과.

## 배포

1. `DEPLOY.md` 0.6.27 델타 노트 → preflight(위험 표면·seed 냄새 🟢)
2. `./deploy/build.sh 0.6.27` → Docker Hub `0.6.27`·`latest` push, `git push`
3. `/srv/fcmanager/deploy-dev.sh 0.6.27` — smoke PASS, 주요 페이지(`/`·`/fcsky/`·경기·통계·로그인·admin) 200
4. `./deploy/remote-prod.sh 0.6.27` — 7/7·smoke PASS(`club=1, match=28`), pre_deploy 스냅샷 보존
5. 운영 컨테이너: emSign **0**, `ca-certificates 20250419+deb13u1`, Django 5.2.18, 공개 페이지 200, 에러 로그 0

## 남은 것

- `build.sh` 에 `--pull` 이 없어 베이스 보안 갱신이 "빌드 호스트에 마침 최신 베이스가 있는가"에 달려 있다.
  `--pull` 추가 여부는 별건(재현성 vs 보안 갱신 트레이드오프) — 이번엔 델타 노트에 수동 절차로 기록.
