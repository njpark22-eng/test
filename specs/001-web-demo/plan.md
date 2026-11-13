# 구현 계획: 웹 데모 (Vercel 배포)

**브랜치**: `001-web-demo` (현재 작업 브랜치는 `main`, 브랜치는 만들지 않음) | **작성일**: 2026-11-13 | **명세**: [spec.md](spec.md)

**입력**: `specs/001-web-demo/spec.md`, `.specify/memory/constitution.md`, `CLAUDE.md`

## 요약

`vibe_agent.py`의 규칙 기반 판정 결과를 읽기 전용 웹 화면으로 보여 준다. FastAPI 앱(`api/index.py`)이 `vibe_agent`를 import해 `/api/analyze`(JSON)와 `/`(한 페이지 HTML)를 제공하고, Vercel에 배포한다. 판정·FFT 로직은 다시 구현하지 않는다. 화면은 흰 배경, 파랑 `#0C4CA3`, 회색, 판정 의미색 3가지로 제한한 미니멀 디자인이다. 근거와 결정은 [research.md](research.md)에 있다.

## 기술 맥락

**언어/버전**: Python 3.13 (로컬 `uv` 3.13.14). Vercel 런타임 버전은 `.python-version`으로 고정하고 배포 후 빌드 로그에서 확인한다.

**주요 의존성**: FastAPI(추가), numpy, openpyxl(기존). `anthropic`, `matplotlib`은 웹 번들에서 제외한다. 확인 결과 `vibe_agent.py`는 import 시점에 둘을 불러오지 않고 tkinter도 try로 감싸져 있어(`tk=None`) 없어도 import된다.

**저장소**: 없음. 저장소에 포함된 가상 데이터 `data/CH1~CH5.xlsx`를 읽기 전용으로만 연다.

**테스트**: pytest(기존 102개) + 웹 테스트 추가(FastAPI `TestClient`, `httpx` 필요).

**대상 플랫폼**: Vercel Python 함수(서울 `icn1`), 브라우저(데스크톱, 휴대폰, 라이트/다크).

**프로젝트 유형**: 웹 서비스(백엔드 1개 + 정적 한 페이지). 기존 CLI와 한 저장소에 공존한다.

**성능 목표**: 5채널 x 10,240 샘플 FFT. 콜드 스타트 포함 첫 응답이 수 초 이내(수치 측정은 Preview에서 1회 기록). 부하 목표는 두지 않는다.

**제약**: 읽기 전용, Claude API 호출 없음, 환경변수 없음, 번들 크기는 Vercel Python 한도(비압축 500MB, 공식 문서 기준)보다 훨씬 작게 유지.

**규모/범위**: 화면 1개, 엔드포인트 2개, 채널 5개, 사용자 1~2명 + 시연 참석자.

## 원칙 점검 (Constitution Check)

*관문: 0단계 전에 통과해야 하고 1단계 설계 후 다시 확인한다.*

| 원칙 | 판단 | 근거 |
|---|---|---|
| I. 입력 원본 불변 | 통과 | 엔드포인트는 GET 2개뿐이고 쓰기 코드가 없다. `read_xlsx`는 읽기 전용으로만 연다. `result-N`, `review-N.json` 생성 없음. |
| II. 판정 로직 단일 출처 | 통과 | `api/index.py`는 `va.spectrum`, `va.analyze_signal`, `va.rule_verdict`, `va.RULES`만 호출한다. `vibe_agent.py`는 수정하지 않는다. |
| III. 가상 데이터와 비밀 값 | 통과 | 가상 데이터만 번들한다. 환경변수와 API 키를 쓰지 않는다. `.vercelignore`로 검수 파일·발표자료를 제외한다. |
| IV. 테스트와 동기화 검사 | 통과(구현 시 확인) | 웹 테스트를 추가하고 `uv run pytest`를 돌린다. 테스트 개수가 바뀌면 DEMO/PILOT/RETRO의 102개도 고친다. |
| V. 판정과 근거 수치가 먼저 | 통과 | 첫 화면이 판정 표다. 랜딩/히어로 없음. 판정 색만 의미색, 나머지는 파랑·회색. |

위반 없음. Complexity Tracking은 비워 둔다.

설계 후 재확인(1단계 이후): 위 판단이 그대로 유효하다. `contracts/api.md`의 엔드포인트가 GET 2개뿐이고 `data-model.md`에 쓰기 상태가 없다.

## 프로젝트 구조

### 문서 (이 기능)

```text
specs/001-web-demo/
├── plan.md              # 구현 계획 (이 파일)
├── research.md          # 0단계: 조사와 결정
├── data-model.md        # 1단계: 데이터 모델
├── quickstart.md        # 1단계: 실행·검증 안내
├── contracts/
│   └── api.md           # 1단계: 엔드포인트 계약
└── tasks.md             # /speckit-tasks 에서 생성
```

### 소스 코드 (저장소 루트)

```text
api/
├── index.py             # FastAPI app: GET /, GET /api/analyze
└── page.html            # 화면(스타일·스크립트 인라인). index.py가 읽어 반환
public/
└── fonts/               # Noto Sans KR woff2 (400/500/700) — Preview에서 정적 서빙 확인 후 확정
vibe_agent.py            # 기존, 수정 없음
data/CH1~CH5.xlsx        # 기존, 읽기 전용
tests/
└── test_web.py          # /, /api/analyze, 데이터 없음 오류, 5채널 기대 판정
vercel.json              # 리전 icn1, includeFiles/excludeFiles
.vercelignore
.python-version
pyproject.toml           # fastapi 추가, anthropic/matplotlib은 선택 의존성 그룹으로 이동
uv.lock
```

**구조 결정**: 단일 저장소에 `api/`(웹)를 추가하고 기존 `vibe_agent.py`와 `tests/`를 그대로 쓴다. 화면 HTML은 `api/page.html` 한 파일로 두어 문구(상수)와 스타일을 한곳에서 점검할 수 있게 한다(slop 방지 점검 방법과 일치).

## 단계 요약

- **0단계(조사)**: [research.md](research.md) — Vercel 진입점·번들 한도, 의존성 분리 가능 여부, 폰트 서빙, 데이터 포함 방식 결정.
- **1단계(설계)**: [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md).
- **다음**: `/speckit-tasks`로 작업 목록 생성.

## 복잡도 추적

위반 없음.
