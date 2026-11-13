# 조사 결과: 웹 데모 (Vercel 배포)

조사일 2026-11-13. 미해결 항목(NEEDS CLARIFICATION)은 아래 결정으로 모두 정리했다. 웹 검색 결과는 제3자 글이 섞여 있어 `확인 필요`로 표시한 항목은 Preview 배포에서 직접 검증한다.

## 1. Python 진입점

- **결정**: `api/index.py`에 FastAPI `app`을 둔다. `tool.vercel.entrypoint`는 쓰지 않는다.
- **근거**: 빌드 오류 메시지가 `api/index.py`를 지원 진입점 목록에 포함한다. FastAPI는 의존성으로 프레임워크를 감지하므로 추가 설정이 필요 없다.
- **검토한 대안**: 루트 `app.py` — 동작은 같지만 CLI인 `vibe_agent.py`와 루트에 섞인다. `tool.vercel.entrypoint` 지정 — 기본 경로가 있으면 불필요한 설정이다.

## 2. 번들 크기와 의존성 분리

- **결정**: 웹 의존성은 `fastapi`, `numpy`, `openpyxl`로 제한하고 `anthropic`, `matplotlib`은 선택 의존성 그룹으로 옮긴다. `httpx`는 테스트용으로만 개발 그룹에 둔다.
- **근거**:
  - Vercel Python 번들 한도는 비압축 500MB다(공식 문서 기준. 오래된 글의 250MB는 이전 값이다). `CLAUDE.md`에 적힌 250MB를 500MB로 고친다.
  - Vercel은 Python 번들을 트리 셰이킹하지 않아 프로젝트 파일 전체가 포함된다. 그래서 `excludeFiles`와 `.vercelignore`가 필요하다.
  - 직접 확인: `vibe_agent.py`는 import 시 `matplotlib`, `anthropic`을 불러오지 않는다(함수 안에서만 import). `tkinter`는 `try/except ImportError`로 감싸져 있고, 막았을 때도 `import vibe_agent`가 성공하고 `tk=None`, 신호 5개가 로드되었다. 따라서 웹 번들에서 이 라이브러리를 빼도 import가 깨지지 않는다.
- **검토한 대안**: 의존성을 그대로 두기 — 한도 안이어도 콜드 스타트가 느려진다. 웹용 `requirements.txt` 별도 작성 — `pyproject.toml`·`uv.lock`과 이중 관리가 된다.

## 3. 데이터 파일 포함

- **결정**: `vercel.json`의 `functions`에서 `includeFiles`로 `vibe_agent.py`와 `data/*.xlsx`를 포함하고, `excludeFiles`로 `tests/**`, `.claude/**`, `.specify/**`, `specs/**`, `*.pptx`, `result-*`, `review-*`를 제외한다. 배포 후 `/api/analyze`가 5채널을 돌려주는지로 확인한다.
- **근거**: `vibe_agent.py`가 `Path(__file__).parent / "data"`를 읽으므로 `data/`가 함수 번들에 들어가야 한다. Vercel은 정적 분석으로 읽지 않는 파일을 빠뜨릴 수 있어 명시한다.
- **확인 필요**: `includeFiles`/`excludeFiles` 키 이름과 glob 문법을 Preview 배포 로그로 확인한다. 안 되면 `api/` 아래로 데이터 경로를 옮기지 않고(원본 불변 원칙) 설정 문법만 고친다.

## 4. 정적 페이지 서빙

- **결정**: 화면은 `api/page.html` 한 파일로 두고 `GET /`이 파일을 읽어 반환한다. 스타일과 스크립트는 인라인이다.
- **근거**: 빌드 단계가 없고, 화면 문구와 스타일이 한 파일에 모여 slop 방지 점검이 쉽다. 같은 함수 번들에 들어가므로 별도 정적 경로 설정이 필요 없다.
- **검토한 대안**: `public/index.html` — Vercel CDN이 직접 서빙해 빠르지만 FastAPI의 `/`와 라우팅이 겹쳐 확인할 것이 늘어난다. 템플릿 엔진(Jinja2) — 의존성이 늘고 이 규모에는 과하다.

## 5. 한글 폰트 (Noto Sans KR)

- **결정**: 1차 구현은 Google Fonts 스타일시트(400/500/700, `display=swap`)와 시스템 폰트 대체(`system-ui, "Malgun Gothic", sans-serif`)로 한다. 직접 서빙(woff2)은 Preview에서 정적 경로 서빙이 확인되면 `public/fonts/`로 옮긴다.
- **근거**: 외부 폰트가 막혀도 레이아웃이 유지되어야 한다는 요구(spec 사용자 스토리 3)를 대체 폰트로 만족한다. 직접 서빙은 한글 폰트 파일 크기(수백 KB~1MB대)와 FastAPI 프로젝트의 `public/` 서빙 여부를 확인해야 한다(`확인 필요`).
- **검토한 대안**: 처음부터 woff2 직접 서빙 — 외부 의존이 없어지지만 서빙 방식이 확인되기 전에는 위험하다.

## 6. 판정 색과 화면 색조

- **결정**: 색은 `:root` 토큰으로 둔다. 기본 파랑 `#0C4CA3`, 눌림 `#08397B`, 회색 계열, 판정 의미색 3가지(정상 초록, 재계측·베어링 주황, 발란싱·정렬 빨강). 판정 의미색은 판정 배지와 셀에만 쓴다.
- **근거**: 사용자가 제공한 참고 이미지에서 흰색을 뺀 최다 색이 `#0C4CA3`이었다(2026-11-13 직접 추출). 판정 색만 의미로 고정한다는 사용자 결정(CLAUDE.md '웹 디자인')을 따른다.
- **주의**: 참고 이미지의 로고, 회사명, 상표는 화면에 쓰지 않는다.
- **확인 필요**: 의미색 3가지의 구체적 값(채도를 낮춘 톤)과 라이트/다크 대비 비율은 구현 때 정하고 `frontend-design`과 `dataviz` 규칙으로 점검한다.

## 7. 그래프 그리기

- **결정**: 서버가 0~600 Hz 스펙트럼 배열(주파수, RMS 진폭)을 JSON으로 주고 브라우저가 인라인 SVG로 그린다. 외부 차트 라이브러리를 쓰지 않는다.
- **근거**: 빌드와 외부 CDN 의존을 없애고, 선 하나와 세로줄 3개, 기준선 1개만 그리면 되어 라이브러리가 필요하지 않다. 1X/2X/BPFO는 색이 아니라 선 모양(실선, 점선, 긴 점선)과 직접 라벨로 구분한다.
- **검토한 대안**: Plotly, Chart.js — 확대·툴팁이 편하지만 용량이 크고 버전을 고정해야 한다.

## 8. 테스트 방식

- **결정**: FastAPI `TestClient`(`httpx` 필요)로 `GET /`(200), `GET /api/analyze`(5채널 기대 판정), 데이터가 없을 때 오류를 확인한다. 데이터가 없는 경우는 `va.SIGNALS`를 비우거나 `monkeypatch`로 만든다. 실제 `data/`는 건드리지 않는다.
- **근거**: 기존 pytest 102개와 같은 실행 방식을 쓰고, 입력 엑셀을 수정하지 않는다(원칙 I).

## 9. 해결하지 못한 항목

- Vercel이 지원하는 Python 버전 목록: 검색에서 확인하지 못했다. `.python-version`에 `3.13`을 적고 빌드 로그에서 실제 버전을 확인한다. 지원하지 않으면 지원 버전 중 로컬과 가장 가까운 것으로 맞춘다.
- 함수 실행 시간 제한과 요청 본문 제한: 플랜별로 다르다. 데모 규모(5채널, 10,240 샘플)에서는 문제가 되지 않을 것으로 보고, 배포 후 첫 응답 시간만 기록한다.

## 출처

- Vercel Python 런타임 문서: https://vercel.com/docs/functions/runtimes/python
- Vercel 함수 제한: https://vercel.com/docs/functions/limitations
- uv 프로젝트 배포 안내: https://pydevtools.com/handbook/how-to/how-to-deploy-a-uv-project-to-vercel/
