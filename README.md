# DART 공시 데일리

매일 밤 00:05(KST)에 전 영업일 DART 공시를 수집해서
**시총 상위 500 유니버스로 거른 뒤 → 규칙으로 중요도를 매기고 → 상위 건만 LLM으로 요약**하는 정적 사이트.

지배구조 테마 아이디에이션이 1순위 목적이라, 단순 유형 분류가 아니라
**승계·지분이동 / 자본정책·밸류업 / 수주공시 변경**을 시그널로 따로 잡는다.

---

## 폴더 구조

```
rules/rules.yaml        점수 체계 전부. 튜닝은 여기만 고치면 됨
scripts/
  run_daily.py          하루치 파이프라인 (수집→매칭→채점→요약)
  score.py              룰 엔진 (시그널 판정 로직)
  parse_doc.py          공시 원문 → 구조화 필드
  summarize.py          Anthropic API 요약
  universe.py           KRX Open API로 시총 상위 500 갱신
  build_site.py         data/ → docs/data/ + 트래커 생성
  selftest.py           네트워크 없이 룰 엔진 검증 (26개 케이스)
data/daily/*.json       날짜별 결과 (원본)
data/state/             정정 diff·이력 비교용 상태
docs/                   GitHub Pages가 서빙하는 사이트
```

## 로컬 실행

```bash
pip install -r requirements.txt
export DART_API_KEY=...        # opendart.fss.or.kr
export KRX_API_KEY=...         # openapi.krx.co.kr (없으면 직전 유니버스 재사용)
export ANTHROPIC_API_KEY=...   # 없으면 요약 생략, 규칙 점수만

python scripts/selftest.py                 # 룰 검증
python scripts/run_daily.py 2026-09-04     # 특정일
python scripts/run_daily.py                # 자동(전 영업일)
python scripts/build_site.py
```

## 룰 튜닝

`rules/rules.yaml`만 고치면 된다. 코드 수정 불필요.

- `types` — 공시 유형별 기본 점수. 위에서부터 첫 매치를 쓰므로 **순서가 중요**
- `market_cap_bonus` / `price_move_bonus` / `penalties` — 가감점
- `signals` — 시그널별 가중치·임계값. `w`, `scale`, 임계 숫자만 바꾸면 됨
  (새 시그널 *추가*는 `scripts/score.py`의 `eval_signals`에 판정 로직도 넣어야 함)
- `grades` — 등급 컷
- `llm.min_score` / `llm.max_per_day` — 요약 비용 상한

버전을 올리면 사이트 하단에 룰셋 버전이 찍히므로, 언제 기준이 바뀌었는지 추적된다.

## 비용

Haiku 기준 1건당 입력 약 4~8k 토큰. 하루 20건 상한이면 월 1~2달러 수준.
`llm.max_per_day`로 상한을 조절한다.
