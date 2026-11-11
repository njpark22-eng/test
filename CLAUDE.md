# vibe-agent

진동 FFT 진단 에이전트 데모. 단일 파일 `vibe_agent.py` + `tests/`.

## 명령
- 테스트: `uv run pytest`
- 실행: `uv run python vibe_agent.py [--offline|--plot|--ui|--make-data]`
  - `--make-data`: 가상 계측 데이터를 `data/CH1~CH4.xlsx`로 생성 (신호 생성 코드를 바꾸면 다시 실행)
  - `--ui`: 채널 수 입력, 파일 선택, 분석 UI (tkinter). `--offline`을 같이 주면 항상 규칙 기반

## 규칙
- 판정 로직은 `rule_verdict`와 `RULES` 문자열을 항상 같이 수정한다.
- 기준값(RMS_LIMIT 4.5, 2X/1X 비율 0.5, 베어링/1X 비율 0.7)을 바꾸면 tests/도 같이 수정한다.
- RMS 기준은 시간신호 전체 RMS가 아니라 FFT 최대 피크의 RMS(`peak_rms_mm_s`)와 비교한다. FFT 진폭 단위는 RMS(mm/s).
- 장비(채널)마다 회전수(rpm)가 다르다. 1X, 베어링 외륜 주파수는 채널별 rpm과 볼 개수로 계산한다
  (외륜 주파수 = 회전주파수/2 x 0.8 x 볼 개수, 볼 개수 1은 베어링 미사용 채널).
- 시연 데이터는 가상 신호만 사용한다. 실제 계측 데이터, 개인정보 금지.
- API 키, .env는 읽거나 커밋하지 않는다.
- 코드 수정 후에는 항상 pytest를 돌린다.

## 에이전트
- `.claude/agents/signal-analyst.md`: 신호/FFT 코드 담당 (수정 권한)
- `.claude/agents/diagnosis-reviewer.md`: 판정 규칙 검토 담당 (읽기 전용)
