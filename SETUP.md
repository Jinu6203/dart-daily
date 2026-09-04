# 처음 한 번만 하는 설정

## 1. API 키 3개 준비

| 키 | 발급처 | 비고 |
|---|---|---|
| `DART_API_KEY` | opendart.fss.or.kr → 인증키 신청 | 이미 있음(로컬 MCP에서 쓰는 키 그대로) |
| `KRX_API_KEY` | openapi.krx.co.kr | 이미 있음. 없으면 유니버스 갱신만 건너뜀 |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys → Create Key | 새로 발급. 결제수단 등록 + 5달러 정도 충전 |

## 2. GitHub 리포지토리 만들기

1. github.com → New repository → 이름 `dart-daily` → **Public** → Create
2. 받은 폴더를 그 리포지토리에 올린다 (웹 UI 드래그앤드롭도 됨)

## 3. Secrets 등록

리포지토리 → **Settings → Secrets and variables → Actions → New repository secret**
위 표의 이름 그대로 3개를 각각 등록한다.

## 4. Actions 쓰기 권한

**Settings → Actions → General → Workflow permissions** →
`Read and write permissions` 선택 → Save
(매일 결과를 리포지토리에 커밋해야 하므로 필요)

## 5. GitHub Pages 켜기

**Settings → Pages → Source: Deploy from a branch** →
Branch `main`, 폴더 `/docs` → Save
1~2분 뒤 `https://<아이디>.github.io/dart-daily/` 로 열린다.

## 6. 첫 실행

**Actions 탭 → 공시 데일리 업데이트 → Run workflow** →
날짜를 비워두면 자동, 특정일을 다시 돌리려면 `2026-09-04` 형식으로 입력.

이후에는 매일 **00:05 KST**에 자동으로 돈다.

---

## 자주 겪는 문제

**Actions가 실패함 / `DART_API_KEY` 에러**
→ Secret 이름 철자 확인. 대소문자까지 정확히 같아야 함.

**요약이 안 붙고 점수만 나옴**
→ `ANTHROPIC_API_KEY`가 없거나 잔액 부족. 규칙 점수는 정상 작동하므로 사이트는 그대로 뜬다.

**시총 순위가 갱신 안 됨**
→ KRX Open API는 `활용신청 승인`된 api_id만 호출된다.
`stk_bydd_trd`(유가증권 일별매매정보), `ksq_bydd_trd`(코스닥 일별매매정보) 두 개가 승인돼 있어야 한다.

**cron이 정시에 안 돎**
→ GitHub Actions의 스케줄은 부하에 따라 5~30분 밀릴 수 있다. 정확한 정시 실행이 필요하면 수동 실행을 쓴다.

**과거 날짜를 채우고 싶음**
→ Actions → Run workflow에 날짜를 하나씩 넣어 돌리면 `data/daily/`에 쌓이고
사이트 상단 날짜 선택기에 자동으로 추가된다. (DART 목록 API는 과거 조회가 자유롭다)
