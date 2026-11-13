# vibe-agent

진동 FFT 진단 에이전트 데모. 단일 파일 `vibe_agent.py` + `tests/`.

## 명령
- 테스트: `uv run pytest`
- 실행: `uv run python vibe_agent.py [--offline|--plot|--ui|--make-data]`
  - `--make-data`: 가상 계측 데이터를 `data/CH1~CH5.xlsx`로 생성 (신호 생성 코드를 바꾸면 다시 실행)
  - `--ui`: 채널 수 입력, 파일 선택, 분석 UI (tkinter). `--offline`을 같이 주면 항상 규칙 기반

## 규칙
- 판정 로직은 `rule_verdict`와 `RULES` 문자열을 항상 같이 수정한다.
- 기준값(RMS_LIMIT 4.5, 2X/1X 비율 0.5, 베어링/1X 비율 0.7)을 바꾸면 tests/도 같이 수정한다.
- RMS 기준은 시간신호 전체 RMS가 아니라 FFT 최대 피크의 RMS(`peak_rms_mm_s`)와 비교한다. FFT 진폭 단위는 RMS(mm/s).
- 장비(채널)마다 회전수(rpm)가 다르다. 1X, 베어링 외륜 주파수는 채널별 rpm과 볼 개수로 계산한다
  (외륜 주파수 = 회전주파수/2 x 0.8 x 볼 개수, 볼 개수 1은 베어링 미사용 채널).
- 시연 데이터는 가상 신호만 사용한다. 실제 계측 데이터, 개인정보 금지.
- 입력 데이터 엑셀(`data/*.xlsx` 등)은 계측기 원본으로 간주하므로 수정·덮어쓰기 금지 (읽기 전용으로만 연다). 예외는 가상 데이터를 새로 만드는 `--make-data`뿐.
  `.claude/settings.json`의 deny 규칙과 PreToolUse 훅(`.claude/hooks/block_input_excel.py`)이 엑셀·`data/` 수정을 차단한다.
- API 키, .env는 읽거나 커밋하지 않는다. 키 값을 출력하는 명령(echo, printenv, env 등)은 `.claude/hooks/guard_demo.py`가 차단한다.
- 결과 파일 `result-N.xlsx/png`는 새 번호로만 저장하고 기존 파일을 덮어쓰거나 지우지 않는다 (`guard_demo.py`가 차단).
- 사람 검수 승인 파일 `review-N.json`은 사람이 `! python approve.py result-N`으로만 만든다. 에이전트는 실행/작성/수정 불가(`guard_demo.py`·deny 규칙), `--check`로 확인만 가능.
- `.claude/hooks/check_rules_sync.py`(PostToolUse)가 `rule_verdict`와 `RULES` 숫자 일치, 기준값 변경 시 tests/ 동시 수정 여부를 검사한다. 훅 동작 테스트는 `tests/test_hooks.py`.
- 코드 수정 후에는 항상 pytest를 돌린다.

## 웹 데모 (Vercel 배포)
- 배경: Vercel이 `pyproject.toml`만 보고 Python 웹 앱으로 판단해 `PYTHON_ENTRYPOINT_NOT_FOUND`로 빌드가 실패했다. `vibe_agent.py`는 CLI/tkinter 도구라 진입점이 없으므로 웹 진입점을 따로 둔다.
- 구조: `api/index.py`(FastAPI `app`)가 진입점이다. `vibe_agent`를 import해서 쓰고 FFT·판정 로직을 다시 구현하지 않는다(`spectrum`, `analyze_signal`, `rule_verdict`, `RULES` 재사용). 웹 때문에 `vibe_agent.py`의 판정 로직을 바꿔야 하면 기존 규칙(`rule_verdict`와 `RULES` 동시 수정, tests/ 동시 수정)을 그대로 따른다.
- 저장소의 `data/CH1~CH5.xlsx`는 읽기만 한다(수정·덮어쓰기 금지). `result-N.xlsx/png`, `review-N.json`은 웹에서 만들지 않는다(서버리스 파일 시스템은 쓰기 불가). `--make-data`와 `data/` 수정 차단 규칙은 그대로 유효하다.
- 쓰기(002-persistence): 사용자가 올린 가상 엑셀 원본과 분석 결과를 Neon Postgres에 추가만 가능하게 저장한다(수정·삭제 금지, DB 트리거로도 차단). 쓰기(`/api/inspect`, `/api/runs`)는 헤더 `X-Write-Token`이 환경변수 `WRITE_TOKEN`과 같아야 하고 읽기(`/api/runs`, `/runs`)는 공개다. 환경변수 `DATABASE_URL`(Neon 풀링 주소), `WRITE_TOKEN`은 코드·커밋·로그·응답에 남기지 않는다. 데이터는 가상 신호뿐이고 업로드 화면에 '가상 데이터만 올리세요'를 항상 표시한다. 한도: 파일 1개 1 MB, 합계 4 MB, 채널 1~5개, 시간당 30회. 기준값(RMS 4.5, 2X/1X 0.5, 베어링/1X 0.7, 저주파 20)은 고정이며 웹에서 바꾸지 않고 결과에 기록만 한다. `vibe_agent.analyze_signal`이 전역(`SIGNALS`, `RPM`, `BALLS`)을 읽으므로 전역을 건드리는 코드는 `api/analysis.py`의 잠금 아래에서만 실행한다.
- 테스트는 실제 DB 없이 `MemoryStore`로 돌린다. 실제 DB 테스트(`tests/test_store_pg.py`)는 `TEST_DATABASE_URL`(운영이 아닌 테스트용 브랜치)이 있을 때만 실행한다.
- 판정 방식: 규칙 기반(`--offline`과 같은 결과)만 쓴다. 웹에서 Claude API를 호출하지 않고 `ANTHROPIC_API_KEY`를 Vercel 환경변수로 넣지 않는다.
- 데이터: 가상 신호만 쓴다. 실제 계측 데이터, 개인정보를 올리지 않고 화면에 "가상 데이터, 규칙 기반 판정"임을 표시한다.
- 화면 구성(SPEC 기준):
  - 채널별 판정 표: 채널, rpm, 최대 피크 RMS(기준 4.5), 2X/1X, BPFO/1X(볼 개수 1은 `-`), 결함 진단
  - 채널별 FFT 그래프: 1X, 2X, BPFO 세로줄(볼 개수 1은 BPFO 없음), RMS 단위 mm/s, 재계측 안내
  - 판정 규칙 문구는 `RULES`를 그대로 보여 준다(별도로 하드코딩하지 않는다).
  - 기대 판정: CH1 재계측 권장 / CH2 정상 / CH3 베어링 점검 요망 / CH4 발란싱 요망 / CH5 정렬 요망
- 사람 검수 승인(`approve.py`)은 웹에 포함하지 않는다. 사람이 `! python approve.py result-N`으로만 한다.
- 배포: 웹 의존성(fastapi 등)을 추가하면 `pyproject.toml`과 `uv.lock`을 같이 갱신한다. 로컬 확인은 `uv run uvicorn api.index:app`. 웹 코드를 추가하면 tests/에 엔드포인트 테스트(5채널 기대 판정 일치)를 넣고 `uv run pytest`를 돌린다.
- 시연 문서(DEMO.md, PILOT.md, RETRO.md)의 테스트 개수(현재 143개)는 테스트를 추가하면 같이 고친다.

### 프레임워크와 환경 설정 (Vercel)
- 프레임워크: FastAPI + 정적 HTML/바닐라 JS 한 페이지. 빌드 단계(npm, 번들러)를 두지 않고, 그래프는 서버가 준 스펙트럼 배열을 SVG/canvas로 그린다(외부 CDN을 쓰면 버전을 고정한다). 이유: Vercel이 FastAPI 진입점을 자동 인식하고, 기존 Python 판정 코드를 그대로 재사용하며, 시연 중 장애 지점이 적다.
- 진입점: `api/index.py`의 `app`. `pyproject.toml`에 `[tool.vercel] entrypoint`를 따로 쓰지 않아도 되게 이 경로를 유지한다.
- Python 버전: `.python-version`으로 고정하고(Vercel 지원 버전, 로컬 `uv`와 동일) `requires-python`과 어긋나지 않게 한다.
- 의존성 분리: 웹 함수에는 `numpy`, `openpyxl`, `fastapi`만 필요하다. `anthropic`, `matplotlib`은 CLI/UI/에이전트용이라 웹 번들에서 빼서 함수 크기(Vercel Python 비압축 500MB 제한, 공식 문서 기준)와 콜드 스타트를 줄인다(`pyproject.toml`의 선택 의존성 그룹으로 나누거나 웹용 `requirements.txt` 사용). 분리 전에 `vibe_agent.py`가 import 시점에 `matplotlib`/`anthropic`을 불러오지 않는지 확인하고, 분리 후 `uv.lock`과 pytest를 맞춘다.
- `vercel.json`(구현 시 작성): 함수 리전은 사용자와 가까운 `icn1`(서울)로 지정, 번들 파일은 `vibe_agent.py`와 `data/*.xlsx`만 포함하도록 `includeFiles`/`excludeFiles`로 제한한다. 데이터 파일이 배포본에 실제로 들어갔는지 배포 후 `/api/analyze`로 확인한다.
- `.vercelignore`와 `.gitignore`: `.vercel/`, `.venv/`, `tests/`, `.claude/`, `*.pptx`, `result-*`, `review-*`, `~$*`를 배포 대상에서 제외한다(발표자료와 검수 파일이 배포되지 않게).
- 환경변수: 시연 웹은 필요 없음. 에이전트 모드를 웹에 추가하는 경우에만 `ANTHROPIC_API_KEY`를 Vercel 대시보드의 Sensitive 변수로 Production/Preview를 나눠 넣고, 코드·로그·응답에 값을 남기지 않는다(`.env`는 읽거나 커밋하지 않는다).
- 배포 절차: 로컬 `uv run pytest` 통과 → `uv run uvicorn api.index:app`으로 화면 확인 → GitHub `main`에 push하면 Vercel이 자동 빌드. Preview 배포에서 5채널 기대 판정을 확인한 뒤 Production으로 올린다. 빌드 실패 시 로그의 오류 코드를 먼저 확인한다.
- 시연 배포와 실사용 배포의 구분:

| 항목 | 시연(데모) | 실사용 |
|---|---|---|
| 데이터 | 가상 신호만. 저장소 포함 5채널(읽기 전용)과, 사용자가 올린 가상 엑셀(Neon에 추가만 저장, 002에서 구현) | 실제 계측 엑셀. 별도 명세와 결정 필요(인증 포함) |
| 접근 | 공개 가능(가상 데이터뿐) | 인증 필수(Vercel Deployment Protection 또는 로그인). 실제 데이터를 공개 URL에 두지 않는다 |
| 판정 | 규칙 기반 | 규칙 기반 + 설비별 기준값(ISO 등급) 설정. 기준값 변경 시 tests/ 동시 수정 |
| 결과 | 화면 표시만 | `result-N` 새 번호 저장(덮어쓰기 금지), 사람 검수 승인 기록 보관 방식 별도 설계 |
| 제한 | 없음 | 함수 요청 본문 크기와 실행 시간 제한(플랜별 확인)에 맞춰 업로드 크기·채널 수·fs 검증, 초과 시 명확한 오류 |
| 로그 | 기본 | 데이터 값, 키, 개인정보를 로그에 남기지 않는다 |

- 실사용 전환은 위 표의 항목마다 SPEC.md에 명세를 먼저 추가한 뒤 구현한다. 이 문서와 SPEC.md는 '가상 데이터만' 전제이므로, 실제 데이터를 쓰는 순간 그 전제가 깨진다는 점을 먼저 사람이 결정한다.

### 웹 디자인 (스킬과 규칙)
- 조사 결과(2026-11-13, 웹 검색. 대부분 제3자 소개 글이라 설치 전 저장소를 직접 확인한다):
  - `frontend-design`(Anthropic): 코드 전에 미적 방향을 정하게 해서 기본 스타일(Inter, 보라 그라디언트, 둥근 카드)로 흐르는 것을 막는다. 이 환경에 이미 설치되어 있다(`frontend-design:frontend-design`).
  - `taste-skill`(Leonxlnx/taste-skill, MIT): 레이아웃, 타이포, 색, 간격, 모션을 수치 규칙으로 정해 '템플릿 같은 AI 느낌'을 막는다. 미설치. v2가 실험 단계라 동작이 바뀔 수 있고 같은 이름의 포크가 있어 원 저장소를 확인해야 한다.
  - `hallmark`(Nutlope/hallmark): anti-AI-slop 규칙(단계별 설계 흐름, 슬롭 검사 게이트)과 audit/redesign 모드. 미설치. 포크가 여러 개라 버전을 확인해야 한다.
  - `apple-design`(emilkowalski/skills): 스프링, 제스처 같은 모션과 인터랙션용이며 시각 스타일 스킬이 아니다. Apple 공식 제품이 아니다. 이 데모는 정적 대시보드라 필요하지 않다.
  - 차트는 이 환경의 `dataviz` 스킬을 쓴다(색, 범례, 축, 툴팁 규칙).
- 적용 방침(이 프로젝트가 진단 결과를 읽는 대시보드이고 시연 시간이 짧다는 점 기준):
  - 기본: `frontend-design`으로 방향을 정하고 `dataviz`로 FFT 그래프와 판정 표를 만든다.
  - 템플릿 느낌이 남으면 `hallmark` audit 또는 `taste-skill` 중 하나만 추가한다. 스타일 엔진 스킬 둘을 동시에 쓰지 않는다.
  - 외부 스킬 설치(`npx skills add ...`)는 제3자 코드를 `.claude/skills/`에 넣는 일이므로 사용자 확인 후 하고, SKILL.md 내용을 읽은 뒤 쓴다. 설치하면 이 문서에 버전과 출처를 적는다.
  - 스킬 지시가 이 문서의 규칙(판정 로직 재구현 금지, 읽기 전용, 가상 데이터 표시)과 충돌하면 이 문서가 우선이다.
- 한글 폰트: Noto Sans KR. `font-family: "Noto Sans KR", system-ui, sans-serif`. 400/500/700만 불러오고(`font-display: swap`), 가능하면 woff2를 `public`(정적 경로)에 두고 직접 서빙해 외부 의존을 없앤다. Google Fonts를 쓰면 시연 네트워크가 막혔을 때 시스템 폰트로 대체되므로 그래도 레이아웃이 무너지지 않아야 한다. 웹 폰트 설정은 `result-N.png`용 matplotlib 폰트(`set_korean_font`)와 별개이며 서로 바꾸지 않는다.
- 판정 화면 규칙:
  - 색조(사용자 제공 참고 이미지 기준, 2026-11-13): 흰 배경에 파랑 한 가지(`#0C4CA3`, 이미지 로고에서 추출)와 회색 계열만 쓰는 미니멀 디자인. 색은 `:root` 토큰으로 정의한다.
    - 파랑 `#0C4CA3`: 제목, 링크, 그래프 선, 강조. 진한 파랑 `#08397B`: 눌림·호버. 회색: 본문, 구분선, 보조 텍스트. 다크 모드는 같은 파랑 계열을 밝게 조정한다.
    - 판정 색만 예외로 의미로 고정한다(사용자 결정): 정상=초록, 재계측 권장/베어링 점검 요망=주황, 발란싱 요망/정렬 요망=빨강. 이 세 색은 판정 배지와 판정 셀에만 쓰고, 채도를 낮춘 톤으로 정해 `:root` 토큰으로 둔다. 색만으로 구분하지 않고 판정명 글자와 기호를 같이 쓴다.
    - 판정 외의 모든 요소(배경, 제목, 표, 그래프, 버튼)는 파랑과 회색만 쓴다.
    - 참고 이미지는 색조 기준일 뿐이다. 이미지의 로고, 회사명, 상표를 화면·README·발표 문구에 넣지 않고 특정 회사의 서비스처럼 보이게 하지 않는다.
  - 숫자 열은 오른쪽 정렬과 `font-variant-numeric: tabular-nums`, 단위(mm/s, rpm, Hz)를 항상 표기한다.
  - 라이트/다크 모두 대비를 확보하고(`prefers-color-scheme`), 색은 `:root` 토큰으로 정의한다. 휴대폰 폭에서도 가로 스크롤 없이 보이고, 표는 좁은 화면에서 카드로 접는다.
  - 그래프: 1X/2X/BPFO 세로줄은 색이 아니라 선 모양(실선·점선·긴 점선)과 직접 라벨로 구분한다(스펙트럼 선은 파랑, 세로줄은 회색 계열). 허용기준선(4.5 mm/s)을 표시한다.
  - 장식(그라디언트, 글래스, 과한 모션)보다 판정과 근거 수치가 먼저 읽히는 것을 우선한다. 모션은 로딩/전환에 짧게만 쓰고 `prefers-reduced-motion`을 따른다.
- 디자인 변경 후 확인: 5채널 판정이 기대와 같은지, 1X/2X/BPFO 표시가 SPEC과 같은지, 휴대폰 폭, 다크 모드, 폰트 로딩 실패 시 화면을 본다. 디자인 때문에 판정 값이나 문구(`RULES`)를 바꾸지 않는다.

### Slop 방지 (문구와 디자인, 웹 화면·README·발표 문구에 적용)
- 조사 결과(2026-11-13, 웹 검색. 제3자 목록이라 설치 전 저장소와 SKILL.md를 직접 확인한다. 모두 미설치):
  - 문구: `stop-slop`(hardikpandya/stop-slop, 예측 가능한 문구·구조·리듬 제거, 8개 규칙과 점수표), `humanizer`(blader/humanizer, 위키백과 'Signs of AI writing' 기반 24~29개 패턴, 포크가 여럿이고 AI 탐지 회피용이 아님).
  - 한국어 문구: `humanize-korean`(번역투, 기계적 병렬, 피동 남용 등 40여 개 패턴), `daleseo/korean-skills`의 `humanizer`(의미와 사실 보존 원칙), `im-ai-copyeditor`(맞춤법·번역 문체·AI 문체 교정). 한국어는 영어용 스킬을 그대로 쓰면 맞지 않아 한국어용을 우선한다.
  - 디자인: `design-slop`(gauravtiwari, 시각 효과로 가린 약한 위계, 두꺼운 테두리 둥근 컨테이너, 근거 없는 수치·후기 탐지), `Design Anti-Slop`(mcpmarket, 보라·청록·분홍 팔레트와 상투적 CTA), `avoid-ai-design`(HTML/CSS·Tailwind 코드의 AI 티 감사와 재작성), `hallmark`·`taste-skill`(위 '웹 디자인' 항목).
- 문구와 디자인은 서로 파일을 건드리지 않으므로 병렬로 점검한다. 문구는 화면 텍스트·README·DEMO/PILOT/RETRO·발표 문구를, 디자인은 `api/` 화면 코드와 스타일을 본다. 이 문서의 규칙과 충돌하는 제안은 적용하지 않는다.
- 설치 정책: 스킬 하나를 새로 설치하기 전에 사용자 확인을 받는다. 기본 점검은 스킬 없이 아래 체크리스트로 한다. 문구용 1개와 디자인용 1개까지만 추가하고 같은 역할의 스킬을 겹쳐 쓰지 않는다. 설치하면 출처와 버전을 이 문서에 적는다.
- 문구 체크리스트(한국어):
  - 판정명과 수치로 말한다. "혁신적인", "강력한", "원활한", "최적화된", "한눈에" 같은 수식어와 홍보 문구를 쓰지 않는다. 사실이 아닌 성능·효과 주장(예: "실시간", "AI가 정확히 진단")도 쓰지 않는다(이 화면은 가상 데이터와 규칙 기반이다).
  - 번역투와 피동 남용을 줄인다("~에 의해", "~를 통해", "~할 수 있습니다" 반복). 주어와 행위를 분명히 쓴다.
  - 같은 대상은 같은 이름으로 쓴다(예: '최대 피크 RMS', '결함 진단', '재계측 권장'). 판정명은 SPEC의 표기(재계측 권장, 정상, 베어링 점검 요망, 발란싱 요망, 정렬 요망)를 그대로 쓴다.
  - 기계적 3항 나열, "단순한 A가 아니라 B", 이모지 장식, 느낌표, 요약을 되풀이하는 마무리 문장을 쓰지 않는다.
  - 안내와 오류 문구는 무슨 일이 생겼고 사용자가 무엇을 하면 되는지를 한 줄로 쓴다(예: "data 폴더에 CH1~CH5 파일이 없습니다. `--make-data`로 생성하세요").
- 디자인 체크리스트:
  - 보라·청록·분홍 그라디언트, 글래스 효과, 이유 없는 그림자와 발광을 쓰지 않는다. 팔레트는 위 '색조'(흰색, 회색, 파랑 `#0C4CA3` 한 가지)와 판정 의미색 3가지로 제한하고 색을 더 늘리지 않는다.
  - 이모지를 아이콘 대신 쓰지 않는다(아이콘은 SVG 한 세트). 두꺼운 테두리의 둥근 카드를 모든 곳에 반복하지 않고 표와 그래프를 중심으로 위계를 만든다.
  - 가짜 지표, 가짜 후기, 가짜 로고, 의미 없는 대시보드 숫자를 넣지 않는다. 화면의 숫자는 모두 `analyze_signal` 결과에서 나온다.
  - 히어로 영역, 마케팅 CTA, 기능 소개 카드 3개 같은 랜딩 페이지 틀을 쓰지 않는다. 첫 화면이 곧 판정 결과다.
  - 점검 질문: "화면을 보고 AI가 만든 템플릿이라고 말할 수 있는가", "판정과 근거 수치가 3초 안에 읽히는가".
- 점검 방법: 화면 텍스트를 한 파일(또는 상수 모음)에 모아 위 문구 체크리스트로 훑고, 디자인은 5채널 화면을 휴대폰/데스크톱, 라이트/다크로 캡처해 체크리스트와 대조한다. 점검 결과로 판정 값이나 `RULES` 문구를 바꾸지 않는다.

## spec-kit
- 초기화됨(`specify init --here --integration claude`): `.specify/`(constitution, 템플릿, 스크립트)와 `.claude/skills/speckit-*`(slash 명령).
- 원칙은 `.specify/memory/constitution.md`, 웹 데모 명세는 `specs/001-web-demo/spec.md`. 규칙의 출처는 이 문서와 `SPEC.md`이며 어긋나면 이 문서를 먼저 고치고 constitution/spec을 맞춘다.
- 언어: `specs/` 아래 모든 md 파일(spec, plan, research, data-model, quickstart, contracts, tasks 등)은 한글로 쓴다. spec-kit 템플릿의 영어 제목(Summary, Technical Context, User Story 등)도 한글로 바꿔 쓰고, 코드 식별자·명령·파일 경로·약어(FFT, RMS, BPFO 등)만 원문을 유지한다. `/speckit-*` 명령으로 생성되는 파일도 같다.
- 진행 순서: `/speckit-clarify`(선택) → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`. `specs/`의 plan/tasks를 만든 뒤에도 이 문서의 읽기 전용·판정 로직 단일 출처 규칙이 우선한다.

## 에이전트
- `.claude/agents/signal-analyst.md`: 신호/FFT 코드 담당 (수정 권한)
- `.claude/agents/diagnosis-reviewer.md`: 판정 규칙 검토 담당 (읽기 전용)
