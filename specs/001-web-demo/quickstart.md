# 빠른 시작과 검증: 웹 데모

구현이 끝난 뒤 처음부터 끝까지 동작을 확인하는 안내다. 구현 코드는 여기에 쓰지 않는다. 엔드포인트 형식은 [contracts/api.md](contracts/api.md), 데이터 구조는 [data-model.md](data-model.md)를 본다.

## 준비

- Python 환경: `uv`가 설치되어 있어야 한다.
- 가상 데이터: 저장소에 포함된 `data/CH1~CH5.xlsx`가 있어야 한다. 없으면 `uv run python vibe_agent.py --make-data`로 만든다(입력 엑셀을 고치는 유일한 예외).
- 환경변수는 필요 없다.

## 1. 로컬 테스트

```
uv run pytest
```

기대 결과: 기존 102개와 웹 테스트가 모두 통과한다. 웹 테스트가 추가되면 DEMO.md, PILOT.md, RETRO.md의 테스트 개수를 같이 고친다.

## 2. 로컬 실행

```
uv run uvicorn api.index:app
```

브라우저에서 `http://127.0.0.1:8000/`을 연다.

기대 결과
- 첫 화면에 판정 표와 FFT 그래프 5개가 보인다.
- 판정: CH1 재계측 권장 / CH2 정상 / CH3 베어링 점검 요망 / CH4 발란싱 요망 / CH5 정렬 요망.
- '가상 데이터, 규칙 기반 판정' 표시와 `RULES` 원문이 보인다.
- `http://127.0.0.1:8000/api/analyze`가 200과 `channels` 5개를 돌려준다.

## 3. 사람이 확인할 곳

- 경계값 근처 채널의 판정과 근거 수치(`peak_rms_mm_s`, 2X/1X, 베어링/1X)가 `uv run python vibe_agent.py --offline` 결과와 같다.
- CH3 그래프의 BPFO 세로줄이 `rpm/60/2 x 0.8 x 9`(= 90 Hz)에 있고, CH1·CH2·CH4·CH5에는 BPFO 세로줄이 없다.
- 입력 엑셀이 바뀌지 않았다(`git status`에 `data/` 변경이 없다).

## 4. 화면 점검

- 휴대폰 폭(약 360 px)에서 가로 스크롤이 없고 표가 카드로 접힌다.
- 다크 모드(`prefers-color-scheme: dark`)에서 글자와 판정 배지의 대비가 충분하다.
- Noto Sans KR 로딩을 막아도(네트워크 차단) 대체 폰트로 레이아웃이 유지된다.
- 색은 흰색, 회색, 파랑 `#0C4CA3`과 판정 의미색 3가지뿐이다. 판정은 색과 함께 판정명 글자로 읽힌다.
- 화면 문구에 수식어, 근거 없는 성능 주장, 이모지 아이콘, 가짜 지표가 없다(CLAUDE.md '슬롭 방지' 체크리스트).

## 5. Vercel 배포 확인

1. `main`에 push하면 Vercel이 빌드한다. 빌드 로그에서 Python 버전과 함수 크기를 확인한다.
2. Preview URL에서 위 2번의 기대 결과를 확인한다. `/api/analyze`가 5채널을 돌려주면 데이터 파일이 번들에 들어간 것이다.
3. 폰트 직접 서빙을 쓰는 경우 Preview에서 폰트 파일이 200으로 응답하는지 확인한다.
4. 첫 응답 시간(콜드 스타트 포함)을 한 번 기록한다.
5. 문제가 없으면 Production으로 올린다.

## 실패했을 때

| 증상 | 확인할 것 |
|---|---|
| `PYTHON_ENTRYPOINT_NOT_FOUND` | `api/index.py`가 있고 `app` 객체가 있는지 |
| `/api/analyze`가 500 | 번들에 `data/*.xlsx`가 포함되었는지(`vercel.json`의 `includeFiles`) |
| 함수 크기 초과 | `anthropic`, `matplotlib`이 의존성에 남아 있지 않은지, `excludeFiles`가 적용되었는지 |
| 한글이 깨짐 | 대체 폰트 지정과 `<meta charset="utf-8">` |
