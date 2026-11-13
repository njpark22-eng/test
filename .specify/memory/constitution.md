# vibe-agent Constitution

진동 FFT 진단 에이전트 데모. 규칙의 출처는 `CLAUDE.md`와 `SPEC.md`이며, 이 문서는 spec-kit 작업(specify, plan, tasks, implement)이 항상 지켜야 할 원칙만 모은다. 충돌하면 `CLAUDE.md`가 우선한다.

## Core Principles

### I. 입력 원본 불변 (NON-NEGOTIABLE)
- 계측 엑셀(`data/*.xlsx` 등)은 계측기 원본으로 간주하고 읽기 전용으로만 연다. 수정, 덮어쓰기, 삭제를 만들지 않는다. 예외는 가상 데이터를 새로 만드는 `--make-data`뿐이다.
- 결과 파일 `result-N.xlsx/png`는 새 번호로만 저장하고 기존 파일을 덮어쓰거나 지우지 않는다.
- 사람 검수 승인 파일 `review-N.json`은 사람이 `! python approve.py result-N`으로만 만든다. 에이전트와 웹은 만들지 않는다.

### II. 판정 로직 단일 출처
- 판정과 FFT 계산은 `vibe_agent.py`(`spectrum`, `analyze_signal`, `rule_verdict`, `RULES`)만 가진다. 웹이나 다른 진입점에서 다시 구현하지 않고 import해서 쓴다.
- `rule_verdict`와 `RULES` 문자열은 항상 같이 수정한다. 기준값(RMS 4.5, 2X/1X 0.5, 베어링/1X 0.7, 저주파 20)을 바꾸면 `tests/`도 같이 수정한다.
- RMS 기준은 시간신호 전체 RMS가 아니라 FFT 최대 피크의 RMS(`peak_rms_mm_s`)와 비교한다. FFT 진폭 단위는 RMS(mm/s).
- 1X와 베어링 외륜 주파수는 채널별 rpm과 볼 개수로 계산한다(볼 개수 1은 베어링 미사용 채널).

### III. 가상 데이터와 비밀 값 보호
- 시연 데이터는 가상 신호만 쓴다. 실제 계측 데이터와 개인정보를 저장소, 배포본, 로그에 넣지 않는다.
- API 키와 `.env`는 읽거나 커밋하지 않고 출력하지 않는다. 웹 데모는 Claude API를 호출하지 않으므로 키를 배포 환경에 넣지 않는다.

### IV. 테스트와 동기화 검사 (NON-NEGOTIABLE)
- 코드 수정 후에는 항상 `uv run pytest`를 돌린다. 웹 코드를 추가하면 5채널 기대 판정(CH1 재계측 권장, CH2 정상, CH3 베어링 점검 요망, CH4 발란싱 요망, CH5 정렬 요망)을 확인하는 엔드포인트 테스트를 같이 넣는다.
- `.claude/hooks/`의 훅(입력 엑셀 차단, 키·결과 파일 보호, 규칙 동기화 검사)을 우회하지 않는다. 테스트 개수가 바뀌면 DEMO.md, PILOT.md, RETRO.md의 개수도 고친다.

### V. 화면은 판정과 근거 수치가 먼저
- 웹 화면은 규칙 기반 판정(`--offline`과 같은 결과)만 보여 주고 "가상 데이터, 규칙 기반 판정"임을 표시한다. 화면의 숫자는 모두 `analyze_signal` 결과에서 나온다.
- 디자인과 문구는 slop 방지 규칙을 따른다(아래 'Web Demo Standards'). 디자인 때문에 판정 값이나 `RULES` 문구를 바꾸지 않는다.

## Web Demo Standards

- 프레임워크: FastAPI + 정적 HTML/바닐라 JS, 빌드 단계 없음. 진입점 `api/index.py`의 `app`. 저장소의 `data/`는 읽기 전용이고, 올린 가상 원본과 결과는 Neon에 추가만 가능하게 저장한다(002).
- 배포: Vercel. `.python-version` 고정, 웹 의존성은 `numpy`, `openpyxl`, `fastapi`로 제한(`anthropic`, `matplotlib` 제외), `vercel.json`(리전 `icn1`, 번들은 `vibe_agent.py`와 `data/*.xlsx`), `.vercelignore`로 발표자료·검수 파일·`.venv`·`tests`·`.claude` 제외. 의존성을 바꾸면 `uv.lock`도 갱신한다.
- 폰트: Noto Sans KR(400/500/700, `font-display: swap`), 가능하면 woff2 직접 서빙. 폰트 로딩이 실패해도 레이아웃이 무너지지 않아야 한다.
- 디자인 스킬: 기본은 `frontend-design`과 `dataviz`. 템플릿 느낌이 남으면 `hallmark` 또는 `taste-skill` 중 하나만 추가한다. 외부 스킬 설치는 사용자 확인 후 SKILL.md를 읽고 하며, 설치하면 출처와 버전을 `CLAUDE.md`에 적는다. 같은 역할의 스킬을 겹쳐 쓰지 않는다.
- 색조: 흰 배경 + 파랑 한 가지(`#0C4CA3`) + 회색 계열의 미니멀 디자인(사용자 제공 참고 이미지 기준). 판정 색만 예외로 의미로 고정한다(정상=초록, 재계측/베어링=주황, 발란싱/정렬=빨강, 판정 배지·셀에만 사용). 색만으로 구분하지 않고 글자와 기호를 같이 쓴다. 참고 이미지의 로고, 회사명, 상표는 화면과 문서에 쓰지 않는다. 숫자는 `tabular-nums`와 단위(mm/s, rpm, Hz)를 표기하고, 라이트/다크와 휴대폰 폭(가로 스크롤 없음)을 지원한다.
- Slop 방지(디자인): 보라·청록·분홍 그라디언트, 글래스 효과, 이모지 아이콘, 가짜 지표·후기·로고, 히어로 영역과 마케팅 CTA, 같은 카드 반복을 쓰지 않는다. 첫 화면이 곧 판정 결과다.
- Slop 방지(문구, 한국어): 수식어·홍보 문구와 근거 없는 성능 주장("실시간", "AI가 정확히 진단")을 쓰지 않는다. 번역투와 피동 남용을 줄이고, 같은 대상은 같은 이름으로 쓴다. 판정명은 SPEC 표기(재계측 권장, 정상, 베어링 점검 요망, 발란싱 요망, 정렬 요망)를 그대로 쓴다. 오류 문구는 무슨 일이 생겼고 무엇을 하면 되는지 한 줄로 쓴다.
- 실사용 전환(실제 데이터 업로드, 인증, 외부 저장소, 설비별 기준값)은 SPEC에 먼저 명세하고 사람이 '가상 데이터만' 전제를 깰지 결정한 뒤에 구현한다.

## Development Workflow

- 언어: `specs/` 아래 모든 md 파일은 한글로 쓴다(템플릿의 영어 제목 포함). 코드 식별자, 명령, 경로, 약어만 원문을 유지한다.
- 순서: `/speckit-specify`(spec.md) → `/speckit-clarify`(선택) → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`. 각 산출물은 이 constitution과 `CLAUDE.md`를 위반하는지 먼저 검사한다.
- 신호/FFT 코드 변경은 `signal-analyst`, 판정 규칙 검토는 `diagnosis-reviewer`(읽기 전용)에 맡긴다.
- 배포 전: 로컬 `uv run pytest` → `uv run uvicorn api.index:app` 확인 → `main` push → Preview에서 5채널 판정 확인 → Production.
- 사람 확인 지점: 판정 경계값, `rule_verdict`와 `RULES` 일치, 채널별 rpm 기준 1X·BPFO 계산, 결과 파일과 화면 판정 일치, 최종 승인(`approve.py`).

## Governance

- 이 constitution은 spec-kit 산출물에 적용되고, `CLAUDE.md`와 `SPEC.md`와 어긋나면 그 두 문서를 먼저 고친 뒤 이 문서를 맞춘다.
- 개정은 변경 이유를 커밋 메시지에 적고 아래 버전을 올린다.

**Version**: 1.0.0 | **Ratified**: 2026-11-13 | **Last Amended**: 2026-11-13
