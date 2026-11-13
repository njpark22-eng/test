---

description: "웹 데모(Vercel 배포) 구현 작업 목록"
---

# 작업 목록: 웹 데모 (Vercel 배포)

**입력**: `specs/001-web-demo/`의 설계 문서
**선행 문서**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md
**테스트**: spec의 FR-011이 테스트 추가를 요구하므로 테스트 작업을 포함한다.
**구성**: 사용자 스토리(US1~US3)별로 묶어 각각 독립 구현·검증이 가능하다.

## 형식: `[ID] [P?] [스토리] 설명 (파일 경로)`

- **[P]**: 다른 파일이고 미완료 작업에 의존하지 않아 병렬 가능
- **[US1~US3]**: 해당 사용자 스토리 작업(설정·기반·마무리 단계에는 붙이지 않음)

## 공통 규칙 (모든 작업에 적용)

- `vibe_agent.py`는 수정하지 않는다. 판정·FFT는 import해서 쓰고 다시 구현하지 않는다(원칙 II, FR-001).
- `data/*.xlsx`는 읽기만 한다. 수정·삭제·덮어쓰기와 `result-N`, `review-N.json` 생성을 만들지 않는다(원칙 I, FR-002).
- 화면의 숫자는 모두 `analyze_signal` 결과다. 문구와 디자인은 CLAUDE.md의 '슬롭 방지' 체크리스트와 '웹 디자인' 색조 규칙을 따른다.
- 코드를 바꾼 뒤에는 `uv run pytest`를 실행한다(원칙 IV).

---

## 1단계: 설정 (공유 기반 파일)

- [X] T001 [P] `.python-version`을 만들고 `3.13`을 적는다 (`.python-version`)
- [X] T002 `pyproject.toml`에서 `dependencies`를 `numpy`, `openpyxl>=3.1.5`, `fastapi`로 줄이고, `anthropic`, `matplotlib`, `httpx`를 `[dependency-groups] dev`(pytest와 같은 그룹)로 옮긴다. `uv run`은 dev 그룹을 기본으로 설치하므로 CLI·UI·에이전트와 테스트가 그대로 동작하고, Vercel은 `dependencies`만 설치한다. 이어서 `uv lock`으로 `uv.lock`을 갱신한다 (`pyproject.toml`, `uv.lock`)
- [X] T003 [P] `vercel.json`을 만든다: 함수 리전 `icn1`, `functions`의 `includeFiles`에 `vibe_agent.py`와 `data/*.xlsx`, `excludeFiles`에 `tests/**`, `.claude/**`, `.specify/**`, `specs/**`, `*.pptx`, `result-*`, `review-*`. 키 이름과 glob 문법은 Preview 빌드 로그로 확인한다(research.md 3번) (`vercel.json`)
- [X] T004 [P] `.vercelignore`를 만든다: `.venv/`, `tests/`, `.claude/`, `.specify/`, `specs/`, `*.pptx`, `~$*`, `result-*`, `review-*`, `.pytest_cache/`, `__pycache__/` (`.vercelignore`)
- [X] T005 [P] `.gitignore`에 `.vercel/`을 추가한다 (`.gitignore`)

**확인**: `uv run pytest`가 기존 102개 그대로 통과한다. 의존성 이동 때문에 import 오류가 나면 T002를 다시 본다.

---

## 2단계: 기반 (모든 스토리의 선행 조건)

**⚠️ 이 단계가 끝나기 전에는 사용자 스토리 작업을 시작하지 않는다.**

- [X] T006 `api/index.py`를 만든다: 저장소 루트를 `sys.path`에 넣고 `import vibe_agent as va`, FastAPI `app` 생성(제목 `vibe-agent demo`). 엔드포인트는 아직 없다 (`api/index.py`)
- [X] T007 `tests/test_web.py`를 만든다: `fastapi.testclient.TestClient(app)` 픽스처와 기대 판정 상수(CH1 재계측 권장 / CH2 정상 / CH3 베어링 점검 요망 / CH4 발란싱 요망 / CH5 정렬 요망)를 둔다. `data/`는 건드리지 않는다 (`tests/test_web.py`)

**확인**: `uv run pytest tests/test_web.py`가 수집은 되고(테스트 0개여도 오류 없음) 기존 테스트는 영향이 없다.

---

## 3단계: 사용자 스토리 1 - 5채널 판정 결과 보기 (우선순위: P1) 🎯 MVP

**목표**: URL을 열면 첫 화면에서 CH1~CH5의 판정과 근거 수치를 본다.

**독립 테스트**: `uv run uvicorn api.index:app` 실행 후 `/`와 `/api/analyze`에서 5채널 판정이 기대값 5/5와 일치한다.

### 테스트 (US1)

> 먼저 작성해 실패하는 것을 확인한 뒤 구현한다.

- [X] T008 [P] [US1] `/api/analyze`가 200이고 `channels` 길이 5, 판정 5개가 기대값과 일치하며 `rules`가 `vibe_agent.RULES`와 같은지 확인하는 테스트 (`tests/test_web.py`)
- [X] T009 [P] [US1] `GET /`이 200, `text/html`이고 본문에 '규칙 기반 판정' 표시가 있는지 확인하는 테스트 (`tests/test_web.py`)
- [X] T010 [P] [US1] 데이터가 없을 때(`monkeypatch`로 `va.SIGNALS`를 비움) `/api/analyze`가 500과 `error` 문자열을 돌려주고, `POST /api/analyze`는 405인지 확인하는 테스트 (`tests/test_web.py`)

### 구현 (US1)

- [X] T011 [US1] `GET /api/analyze`를 구현한다. 채널마다 `va.analyze_signal`, `va.rule_verdict`, `va.spectrum`(0~600 Hz만)을 호출해 contracts/api.md 형식으로 돌려준다. 값은 반올림하거나 고치지 않는다. `va.SIGNALS`가 비어 있으면 500과 `{"error": "계측 파일(CH1~CH5.xlsx)을 찾을 수 없습니다. --make-data로 생성하세요"}` (`api/index.py`)
- [X] T012 [US1] `GET /`을 구현한다. `api/page.html`을 읽어 `text/html; charset=utf-8`로 반환한다 (`api/index.py`)
- [X] T013 [US1] `api/page.html`을 만든다: `<meta charset="utf-8">`와 viewport, 제목, '가상 데이터, 규칙 기반 판정' 표시, 판정 표(채널, rpm, 최대 피크 RMS와 기준 4.5, 2X/1X, BPFO/1X — 볼 개수 1은 `-`, 결함 진단), `/api/analyze` 호출 후 채우기, 로딩·오류 상태 문구. 첫 화면이 곧 판정 표이며 히어로·마케팅 영역은 없다. 숫자 열은 오른쪽 정렬, `tabular-nums`, 단위 표기 (`api/page.html`)
- [X] T014 [US1] 판정 색 토큰과 배지를 `api/page.html`에 넣는다: 색은 `:root` 토큰. 판정 색만 의미로 고정(정상 초록, 재계측 권장·베어링 점검 요망 주황, 발란싱 요망·정렬 요망 빨강, 채도를 낮춘 톤)하고 판정 배지·셀에만 쓴다. 나머지는 흰색, 회색, 파랑 `#0C4CA3`뿐. 색과 함께 판정명 글자와 기호를 쓴다 (`api/page.html`)

**확인**: T008~T010이 통과한다. 로컬 실행 화면에서 판정 5개가 기대값과 같다(quickstart.md 2번).

**체크포인트**: 여기까지만으로 Vercel 배포 실패가 해결되고 시연이 가능하다(MVP).

---

## 4단계: 사용자 스토리 2 - 채널별 FFT 스펙트럼 확인 (우선순위: P2)

**목표**: 채널별 FFT 그래프에서 판정 근거(1X, 2X, 베어링 피크, 허용기준선)를 눈으로 확인한다.

**독립 테스트**: 그래프의 1X/2X/BPFO 세로줄 위치가 `rpm/60`, `2 x 1X`, `1X/2 x 0.8 x 볼 개수`와 같다. CH3에만 BPFO 세로줄이 있다.

### 테스트 (US2)

- [X] T015 [P] [US2] `/api/analyze`의 `f`와 `amp` 길이가 같고 `f` 최댓값이 600 Hz 이하이며, `bearing_BPFO_hz`가 CH3만 숫자(90.0)이고 나머지는 `null`인지 확인하는 테스트 (`tests/test_web.py`)

### 구현 (US2)

- [X] T016 [US2] `api/page.html`에 채널별 FFT 그래프를 인라인 SVG로 그린다: 스펙트럼 선은 파랑, X축 0~600 Hz, Y축 RMS(mm/s), 외부 차트 라이브러리 없음 (`api/page.html`)
- [X] T017 [US2] 1X/2X는 모든 채널에, BPFO는 `bearing_BPFO_hz`가 있는 채널에만 세로줄을 그린다. 색이 아니라 선 모양(실선, 점선, 긴 점선)과 직접 라벨로 구분하고 회색 계열로 그린다. 허용기준선 4.5 mm/s와 단위를 표시한다 (`api/page.html`)
- [X] T018 [US2] 판정이 재계측 권장인 채널(CH1)에 재계측 안내 문구를 그래프 위나 옆에 쓴다. 문구는 원인과 조치를 한 줄로 쓴다 (`api/page.html`)

**확인**: T015가 통과한다. quickstart.md 3번(CH3 BPFO 90 Hz, 다른 채널 BPFO 없음)을 눈으로 확인한다.

---

## 5단계: 사용자 스토리 3 - 판정 규칙 확인과 다른 화면 환경 (우선순위: P3)

**목표**: 판정 규칙 문구를 읽고, 휴대폰이나 다크 모드에서도 화면을 본다.

**독립 테스트**: 규칙 문구가 `RULES`와 같고, 휴대폰 폭·다크 모드·폰트 로딩 실패에서도 화면이 깨지지 않는다.

### 구현 (US3)

- [X] T019 [P] [US3] `api/page.html` 하단에 `/api/analyze`의 `rules` 원문을 그대로 보여 준다. 규칙 문구를 화면에 따로 쓰지 않는다 (`api/page.html`)
- [X] T020 [P] [US3] 휴대폰 폭(약 360 px)에서 가로 스크롤 없이 표가 카드로 접히게 하는 반응형 스타일과 16 px 좌우 여백을 넣는다 (`api/page.html`)
- [X] T021 [P] [US3] `prefers-color-scheme: dark` 다크 모드 토큰을 정의한다(`:root:not([data-theme="light"])` 규칙 포함). 판정 배지의 글자 대비를 확인한다 (`api/page.html`)
- [X] T022 [P] [US3] Noto Sans KR(400/500/700, `display=swap`) Google Fonts 스타일시트와 대체 폰트(`system-ui, "Malgun Gothic", sans-serif`)를 지정한다. 외부 폰트가 막혀도 레이아웃이 유지되어야 한다 (`api/page.html`)
- [X] T023 [US3] 모션은 로딩 표시 정도로만 쓰고 `prefers-reduced-motion`을 따르게 한다 (`api/page.html`)

**확인**: quickstart.md 4번(화면 점검)을 모두 통과한다.

---

## 6단계: 마무리와 공통 작업

- [X] T024 [P] 화면 문구를 CLAUDE.md '슬롭 방지' 문구 체크리스트로 훑는다: 수식어·홍보 문구, 근거 없는 성능 주장, 번역투, 이모지, 판정명 표기가 SPEC과 같은지. 걸리는 문구를 고친다 (`api/page.html`, `api/index.py`)
- [X] T025 [P] 디자인 체크리스트로 점검한다: 팔레트 4색 이내(흰색·회색·파랑·판정 3색), 그라디언트·글래스·이모지 아이콘·가짜 지표 없음, 참고 이미지의 로고·회사명·상표 없음 (`api/page.html`)
- [X] T026 `diagnosis-reviewer` 에이전트로 `api/index.py`가 판정·FFT 로직을 다시 구현하지 않고 `va.*`만 호출하는지 검토하고, 지적 사항을 반영한다 (`api/index.py`)
- [X] T027 `uv run pytest`가 모두 통과하는지 확인하고, 새 테스트 개수로 DEMO.md, PILOT.md, RETRO.md의 '102개'를 같이 고친다 (`DEMO.md`, `PILOT.md`, `RETRO.md`)
- [ ] T028 입력 엑셀이 바뀌지 않았는지 확인한다(`git status`에 `data/` 변경 없음). `uv run python vibe_agent.py --offline` 판정과 웹 판정이 같은지 사람이 대조한다 (quickstart.md 3번)
- [X] T029 `README.md`에 웹 데모 실행 방법(`uv run uvicorn api.index:app`)과 Vercel 배포 주소 자리를 추가한다 (`README.md`)
- [ ] T030 `main`에 push해 Vercel Preview를 만들고 quickstart.md 5번을 수행한다: 빌드 로그의 Python 버전·함수 크기, `/api/analyze`의 5채널 응답, 첫 응답 시간 기록. 결과를 research.md의 '해결하지 못한 항목'에 반영한다. push는 사용자 확인 후에 한다 (`specs/001-web-demo/research.md`)
- [ ] T031 Preview에서 `vercel.json` 문법, 데이터 번들 포함, 폰트 직접 서빙 가능 여부를 확인해 `vercel.json`과 research.md를 확정한다. 문제가 없으면 Production으로 올린다 (`vercel.json`, `specs/001-web-demo/research.md`)

---

## 의존 관계와 실행 순서

### 단계 의존

- **1단계(설정)**: 바로 시작. T002 이후에 의존성이 바뀌므로 T006 이전에 끝낸다.
- **2단계(기반)**: 1단계 후. 모든 사용자 스토리를 막는다.
- **3~5단계(US1~US3)**: 2단계 후. 우선순위 순서(P1 → P2 → P3)로 진행한다. 세 스토리가 모두 `api/page.html`을 고치므로 같은 파일 충돌을 피하려면 순서대로 하는 편이 안전하다.
- **6단계(마무리)**: 원하는 스토리가 끝난 후. T030·T031은 사용자 확인이 필요한 배포 작업이다.

### 스토리 의존

- **US1**: 2단계 후 시작. 다른 스토리에 의존하지 않는다.
- **US2**: US1의 `/api/analyze`와 `page.html` 골격에 의존한다(스펙트럼 배열은 T011에서 이미 제공).
- **US3**: US1의 `page.html` 골격에 의존한다.

### 스토리 안의 순서

- 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.
- `api/index.py` 작업(T011, T012) 후 `api/page.html` 작업(T013~)을 진행한다.

### 병렬 기회

- 1단계: T001, T003, T004, T005는 서로 다른 파일이라 병렬 가능(T002는 `uv.lock`을 바꾸므로 따로).
- US1 테스트: T008, T009, T010은 같은 파일(`tests/test_web.py`)이지만 독립적인 테스트 함수라 한 번에 작성하면 된다.
- US3: T019~T022는 `page.html`의 서로 다른 영역이라 병렬로 작성할 수 있으나, 같은 파일이므로 한 사람이 이어서 쓰는 편이 안전하다.
- 마무리: T024, T025는 병렬 가능.

### 병렬 예시: 1단계

```
T001 .python-version
T003 vercel.json
T004 .vercelignore
T005 .gitignore
```

---

## 구현 전략

### MVP 우선 (US1만)

1. 1단계(설정), 2단계(기반)를 끝낸다.
2. 3단계(US1)를 끝낸다.
3. **멈추고 검증한다**: `uv run pytest`와 로컬 실행으로 5채널 판정을 확인한다.
4. 배포(T030)로 Vercel 빌드 실패가 해결되었는지 확인한다.

### 점진 배포

1. 설정 + 기반 → 기반 완료
2. US1 → 독립 검증 → 배포(MVP)
3. US2 → 독립 검증 → 배포
4. US3 → 독립 검증 → 배포
5. 마무리(T024~T031)

### 주의

- `[P]`는 다른 파일이어야 한다. 같은 파일을 여러 작업이 고치면 순서대로 한다.
- 각 작업이나 논리 묶음이 끝날 때마다 `uv run pytest`를 돌린다.
- 판정 값이나 `RULES` 문구를 디자인 때문에 바꾸지 않는다.
- 커밋과 push는 사용자가 요청할 때만 한다.
