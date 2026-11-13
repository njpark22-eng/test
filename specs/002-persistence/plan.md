# 구현 계획: 가상 계측 데이터 저장과 결과 이력

**브랜치**: `002-persistence` (작업 브랜치는 `main`) | **작성일**: 2026-11-13 | **명세**: [spec.md](spec.md)

**입력**: `specs/002-persistence/spec.md`, `.specify/memory/constitution.md`, `CLAUDE.md`

## 요약

`001-web-demo`의 FastAPI 앱에 쓰기 기능을 더한다. 사용자가 가상 엑셀을 올리면(토큰 필요) 서버가 `vibe_agent`의 함수로 분석하고, 원본 바이트와 분석 결과를 Neon Postgres에 추가만 가능한 형태로 저장한다. 저장된 실행은 누구나 목록·상세로 본다. 기준값은 고정이라 버전 관리 기능이 없고, 판정에 쓴 값을 결과와 함께 기록한다. 근거는 [research.md](research.md)에 있다.

## 기술 맥락

**언어/버전**: Python 3.13 (`.python-version`)

**주요 의존성**: FastAPI, numpy, openpyxl(기존). 추가: `psycopg[binary]`(Postgres 드라이버), `python-multipart`(파일 업로드 폼). 모두 `dependencies`에 둔다(Vercel 번들에 필요).

**저장소**: Neon Postgres. 연결 문자열은 환경변수 `DATABASE_URL`(Neon 풀링 주소)로만 받는다. 테스트는 실제 DB 없이 메모리 저장소로 돌린다.

**테스트**: pytest + FastAPI `TestClient`. 저장소를 `Depends`로 주입해 테스트에서 메모리 저장소로 바꾼다. 실제 DB 테스트는 `TEST_DATABASE_URL`이 있을 때만 실행한다(없으면 건너뜀).

**대상 플랫폼**: Vercel Python 함수(`icn1`), 브라우저.

**프로젝트 유형**: 웹 서비스(기존 `api/` 확장).

**성능 목표**: 5채널 업로드부터 결과 표시까지 수 초. 목록·상세 1초 이내(가상 데이터 100건 기준).

**제약**: 쓰기 토큰 `WRITE_TOKEN`(환경변수), 요청 본문 약 4.5 MB 제한 안에서 파일 1개 1 MB, 합계 4 MB, 시간당 30회. 저장된 원본과 결과는 수정·삭제 불가. `vibe_agent.py`는 수정하지 않는다.

**규모/범위**: 화면 3개(올리기, 이력 목록·상세), 엔드포인트 6개, 테이블 4개.

## 원칙 점검 (Constitution Check)

| 원칙 | 판단 | 근거 |
|---|---|---|
| I. 입력 원본 불변 | 통과 | 저장소의 `data/*.xlsx`는 건드리지 않는다. 올린 원본은 DB에 추가만 하고 DB 트리거가 UPDATE/DELETE를 막는다. `result-N`, `review-N.json`은 만들지 않는다. |
| II. 판정 로직 단일 출처 | 통과 | `va.read_xlsx`, `va.detect_rpm`, `va.rpm_mismatch`, `va.spectrum`, `va.analyze_signal`, `va.rule_verdict`를 호출한다. `vibe_agent.py`는 수정하지 않는다. 2X/1X 0.5, 베어링/1X 0.7은 코드 상수가 없어 경계 테스트로 고정값과의 일치를 확인한다. |
| III. 가상 데이터와 비밀 값 | 통과 | 가상 데이터만 받고 화면에 경고를 표시한다. `DATABASE_URL`, `WRITE_TOKEN`은 환경변수로만 받고 코드·로그·응답에 남기지 않는다. |
| IV. 테스트와 동기화 검사 | 통과(구현 시 확인) | 기준값을 바꾸지 않으므로 동기화 대상 변경이 없다. 테스트를 추가하고 문서의 테스트 개수를 갱신한다. |
| V. 판정과 근거 수치가 먼저 | 통과 | 결과 화면은 판정 표와 FFT 그래프 중심이다. 판정 색은 의미색, 나머지는 파랑·회색. |

위반 없음. 한 가지 설계 주의: `vibe_agent`의 `analyze_signal`이 모듈 전역(`SIGNALS`, `RPM`, `BALLS`)을 읽으므로, 업로드 분석은 고유 임시 키로 넣고 잠금 아래에서 호출한 뒤 반드시 지운다. 기존 `/api/analyze`도 같은 잠금을 쓴다([research.md](research.md) 3번).

## 프로젝트 구조

### 문서 (이 기능)

```text
specs/002-persistence/
├── plan.md              # 구현 계획 (이 파일)
├── research.md          # 조사와 결정
├── data-model.md        # 테이블 구조
├── quickstart.md        # 실행·검증 안내
├── contracts/
│   └── api.md           # 엔드포인트 계약
├── checklists/
│   └── requirements.md
└── tasks.md             # 작업 목록
```

### 소스 코드 (저장소 루트)

```text
api/
├── index.py             # 앱과 라우트 (001 확장)
├── analysis.py          # vibe_agent 호출을 잠금 아래에서 감싸는 분석 함수
├── store.py             # 저장소: PgStore, MemoryStore, 스키마 SQL
├── auth.py              # 쓰기 토큰 검사
├── page.html            # 001 판정 화면 (공통 파일 사용으로 정리)
├── upload.html          # 올리기 화면
├── runs.html            # 이력 목록·상세 화면
├── shared.css           # 공통 스타일(색 토큰, 배지, 카드)
└── shared.js            # 공통 스크립트(배지, 스펙트럼 SVG)
tests/
├── test_web.py          # 001 (기존)
├── test_persistence.py  # 002: 업로드, 검증, 저장, 이력, 토큰, 읽기 전용
└── test_store_pg.py     # 실제 DB (TEST_DATABASE_URL 있을 때만)
vercel.json              # includeFiles에 api/** 추가
pyproject.toml / uv.lock # psycopg, python-multipart 추가
```

**구조 결정**: 기존 `api/`에 모듈을 나눠 추가한다. 저장소는 인터페이스(PgStore/MemoryStore)로 분리해 DB 없이 테스트한다. 화면은 공통 CSS·JS를 `api/`에 두고 각 HTML이 불러온다.

## 단계 요약

- **0단계(조사)**: [research.md](research.md)
- **1단계(설계)**: [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md)
- **다음**: [tasks.md](tasks.md)

## 복잡도 추적

위반 없음.
