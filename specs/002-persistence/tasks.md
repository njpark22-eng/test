---

description: "가상 계측 데이터 저장과 결과 이력 구현 작업 목록"
---

# 작업 목록: 가상 계측 데이터 저장과 결과 이력

**입력**: `specs/002-persistence/`의 설계 문서
**선행 문서**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md
**테스트**: 포함한다(실제 DB 없이 메모리 저장소로 실행, 실제 DB 테스트는 `TEST_DATABASE_URL`이 있을 때만).
**구성**: 사용자 스토리별(US1, US2)로 묶었다. 기준값 버전 관리(스토리 3)는 기준값 고정 결정으로 제외했다.

## 형식: `[ID] [P?] [스토리] 설명 (파일 경로)`

## 공통 규칙

- `vibe_agent.py`는 수정하지 않는다. 판정·FFT·rpm 추정은 `va.*`를 호출한다(원칙 II).
- `data/*.xlsx`는 읽기만 한다. 저장된 원본·결과는 수정·삭제 기능을 만들지 않는다(원칙 I).
- `DATABASE_URL`, `WRITE_TOKEN` 값은 코드·로그·응답·커밋에 남기지 않는다(원칙 III).
- 코드를 바꾼 뒤에는 `uv run pytest`를 실행한다(원칙 IV). 화면은 CLAUDE.md 색조·슬롭 방지 규칙을 따른다.

---

## 1단계: 설정

- [X] T001 `psycopg[binary]`와 `python-multipart`를 `dependencies`에 추가하고 `uv.lock`을 갱신한다 (`pyproject.toml`, `uv.lock`)
- [X] T002 [P] `vercel.json`의 `includeFiles`에 `api/**`(HTML, CSS, JS)를 포함시킨다 (`vercel.json`)

## 2단계: 기반

**⚠️ 이 단계가 끝나기 전에는 사용자 스토리 작업을 시작하지 않는다.**

- [X] T003 `api/analysis.py`를 만든다: 잠금 하나, 고정 기준값 `thresholds()`(`va.RMS_LIMIT`, `va.LOWNOISE_LIMIT`, 2X/1X 0.5, 베어링/1X 0.7), 임시 키로 `analyze_signal`을 부르고 반드시 지우는 `analyze_channels(...)`, 0~600 Hz 스펙트럼 자르기 (`api/analysis.py`)
- [X] T004 `api/store.py`를 만든다: 스키마 SQL(테이블 4개, 수정·삭제 차단 트리거), `MemoryStore`, `PgStore`(`psycopg`, 요청마다 연결, 한 트랜잭션 저장, 멱등 스키마), 공통 메서드 `recent_run_count`, `insert_run`, `list_runs`, `get_run` (`api/store.py`)
- [X] T005 [P] `api/auth.py`를 만든다: `X-Write-Token`을 `WRITE_TOKEN`과 `hmac.compare_digest`로 비교, 토큰 미설정이면 거부 (`api/auth.py`)
- [X] T006 `api/page.html`의 스타일과 공통 스크립트(배지, 스펙트럼 SVG)를 `api/shared.css`, `api/shared.js`로 옮기고 `page.html`이 이를 불러오게 한다. `/assets/shared.css`, `/assets/shared.js` 라우트를 추가한다. 화면이 001과 같아야 한다 (`api/shared.css`, `api/shared.js`, `api/page.html`, `api/index.py`)
- [X] T007 `api/index.py`에 저장소 주입(`get_store`, 없으면 503), 기존 `/api/analyze`를 잠금 아래로 옮기고 순회를 `list(va.SIGNALS)`로 바꾼다, `GET /api/config`를 추가한다 (`api/index.py`)

---

## 3단계: 사용자 스토리 1 - 가상 계측 엑셀 올리고 분석하기 (우선순위: P1) 🎯 MVP

**독립 테스트**: 가상 엑셀 5개를 올려 판정이 기대값이고 저장된 해시가 올린 파일의 SHA-256과 같다.

### 테스트 (US1)

- [X] T008 [P] [US1] 토큰 없음/틀림/서버 토큰 미설정 → 401, 읽기는 토큰 없이 200 (`tests/test_persistence.py`)
- [X] T009 [P] [US1] 정상 업로드 5개 → 201, 판정이 기대값, 저장된 해시 일치, 로컬 `analyze_signal` 결과와 같음 (`tests/test_persistence.py`)
- [X] T010 [P] [US1] 검증 실패: 413(크기), 422(엑셀 아님, 샘플링 주파수, 채널 수 0·6개, rpm 범위, 볼 개수 0·101·소수, rpm 1X 불일치), 429(시간당 30회), 503(저장소 없음) (`tests/test_persistence.py`)
- [X] T011 [P] [US1] 같은 파일 재업로드 시 원본 행은 그대로이고 결과 행만 늘어남, 저장 실패 시 부분 저장이 없음 (`tests/test_persistence.py`)
- [X] T012 [P] [US1] `/api/inspect` 가 자동 rpm과 앞 20행을 돌려주고 아무것도 저장하지 않음, 업로드 후 `va.SIGNALS`에 임시 키가 남지 않음, `data/*.xlsx` 변경 없음 (`tests/test_persistence.py`)
- [X] T013 [P] [US1] 고정 기준값이 `rule_verdict` 경계와 일치함(0.5 → 정렬 요망, 0.49 → 발란싱 요망, 0.7 → 베어링 점검 요망, 0.69 → 정상, `RMS_LIMIT`, `LOWNOISE_LIMIT`) (`tests/test_persistence.py`)

### 구현 (US1)

- [X] T014 [US1] `POST /api/inspect`를 구현한다: 크기·형식 검증, `va.read_xlsx`(임시 파일), `va.detect_rpm`, 앞 20행 (`api/index.py`)
- [X] T015 [US1] `POST /api/runs`를 구현한다: 멀티파트 검증, 채널 수·rpm·볼 개수 검증, `va.rpm_mismatch`, 횟수 제한, 잠금 아래 분석, 원본과 결과 한 트랜잭션 저장, 201 응답 (`api/index.py`)
- [X] T016 [US1] `api/upload.html`과 `GET /upload`를 만든다: 토큰 입력(`sessionStorage`), '가상 데이터만 올리세요. 실제 계측 데이터는 금지' 상시 표시, 채널 수(1~5)와 파일 선택, 자동 rpm과 데이터 앞부분 표시, rpm·볼 개수 입력(오류는 한 줄), 분석 실행, 결과 표시 (`api/upload.html`, `api/index.py`)

---

## 4단계: 사용자 스토리 2 - 저장된 결과 목록과 상세 보기 (우선순위: P2)

**독립 테스트**: 두 번 실행한 뒤 목록에 최신순 2건이 보이고 상세가 저장 당시 수치와 같다.

### 테스트 (US2)

- [X] T017 [P] [US2] 목록 최신순, 빈 목록, 상세가 저장값과 같음, 없는 id는 404, 상세에 기준값 기록 (`tests/test_persistence.py`)
- [X] T018 [P] [US2] `PUT/PATCH/DELETE`가 405, 저장소에 수정·삭제 메서드가 없음 (`tests/test_persistence.py`)
- [X] T019 [P] [US2] 실제 DB(`TEST_DATABASE_URL`): 스키마 멱등, UPDATE/DELETE가 트리거로 거부, 원본 중복 방지. 변수가 없으면 건너뜀 (`tests/test_store_pg.py`)

### 구현 (US2)

- [X] T020 [US2] `GET /api/runs`, `GET /api/runs/{id}`를 구현한다 (`api/index.py`)
- [X] T021 [US2] `api/runs.html`과 `GET /runs`, `GET /runs/{id}`를 만든다: 목록(실행 시각, 채널 수, 판정 요약), 상세(판정 표, FFT 그래프, 원본 해시, 판정에 쓴 기준값), 빈 목록 안내 (`api/runs.html`, `api/index.py`)
- [X] T022 [US2] 세 화면에 공통 탐색(판정, 올리기, 이력)을 넣는다 (`api/page.html`, `api/upload.html`, `api/runs.html`)

---

## 5단계: 마무리

- [X] T023 [P] 화면 문구와 디자인을 CLAUDE.md 슬롭 방지 체크리스트로 점검하고 고친다 (`api/*.html`, `api/shared.css`)
- [X] T024 `diagnosis-reviewer`로 판정·FFT를 다시 구현하지 않고 `va.*`만 호출하는지, 수정·삭제 경로가 없는지 검토한다 (`api/`)
- [X] T025 `uv run pytest` 통과를 확인하고 DEMO, PILOT, RETRO, CLAUDE의 테스트 개수를 새 값으로 고친다. README에 올리기·이력 사용법과 환경변수를 적는다 (`DEMO.md`, `PILOT.md`, `RETRO.md`, `CLAUDE.md`, `README.md`)
- [X] T026 헤드리스 브라우저로 올리기·이력 화면을 캡처해 데스크톱·휴대폰 폭을 확인한다
- [ ] T027 환경변수(`DATABASE_URL`, `WRITE_TOKEN`)를 Vercel에 넣고 push, Preview에서 quickstart.md 5번을 수행한다. push는 사용자 확인 후에 한다

---

## 의존 관계

- 1단계 → 2단계 → 3단계(US1) → 4단계(US2) → 5단계. US2는 US1이 저장한 데이터를 읽으므로 US1 뒤에 한다.
- T006(공통 파일 정리)은 T016, T021 전에 끝낸다. T003, T004, T005는 서로 다른 파일이라 병렬로 할 수 있다.
- 같은 파일(`api/index.py`, `tests/test_persistence.py`)을 고치는 작업은 순서대로 한다.

## 구현 전략

MVP는 1~3단계(US1)다. 업로드→분석→저장이 되면 이력(US2)은 읽기 기능만 더하면 된다. 각 단계 뒤에 `uv run pytest`를 돌린다. 커밋과 push는 사용자가 요청할 때만 한다.
