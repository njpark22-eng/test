# vibe-agent: 진동 진단 에이전트 (시연용)

진동 계측 데이터(엑셀)를 FFT로 분석해 정상 / 베어링 점검 / 발란싱 / 정렬을 판정합니다.
Claude가 도구(`list_signals`, `analyze_signal`)를 호출하며 판단하는 에이전트입니다.
시연 데이터는 모두 numpy로 생성한 가상 신호입니다. 실제 설비·개인정보는 없습니다.

## 설치
    uv sync            # 또는: pip install numpy anthropic matplotlib openpyxl pytest

## 실행
    export ANTHROPIC_API_KEY=...   # .env에 두지 말고 환경변수로, 저장소에 커밋 금지
    uv run python vibe_agent.py --make-data  # 가상 계측 데이터를 data/CH1~CH4.xlsx로 생성 (최초 1회)
    uv run python vibe_agent.py              # 에이전트 모드
    uv run python vibe_agent.py --offline    # API 없이 규칙 기반 (시연 백업)
    uv run python vibe_agent.py --plot       # spectra.png 생성
    uv run python vibe_agent.py --ui         # 파일 선택 UI (API 키 없으면 규칙 기반)
    uv run python vibe_agent.py --ui --offline

## UI 사용 순서 (`--ui`)
1. 채널 개수 입력 (안내는 1~32, 지금은 4채널까지 가능)
2. 채널마다 `파일 선택`으로 엑셀 선택 -> 데이터 표와 시간 신호 그래프 표시
3. 회전수(rpm)는 신호의 1X에 맞춰 자동으로 채워짐. 다른 값을 입력하면 1X와 맞는지 바로 확인하고 다시 입력받음
4. 베어링 볼 개수 입력 (기본값 CH1·3·4는 1, CH2는 9). 기본값과 다르면 확인창이 뜸. 1은 베어링 주파수 미사용
5. `분석 실행` -> 채널별 FFT 그림, RMS 기준 만족/불만족, 결함 진단 표시

## 데이터 형식
엑셀 1개 = 채널 1개. A열 `time_s`, B열 `velocity_mm_s`, 샘플링 주파수 5120 Hz.
시연용 파일에는 시간 신호 그래프가 들어 있으나, 분석에는 데이터(A, B열)만 사용합니다.

## 테스트
    uv run pytest

## 판정 규칙
기준 비교 값은 FFT 최대 피크의 RMS(mm/s)이며, 기준은 4.5 mm/s입니다. FFT 진폭도 RMS 단위입니다.
- 기준 이하: 베어링 성분/1X >= 0.7 이면 베어링 점검, 아니면 정상.
- 기준 초과: 2X/1X >= 0.5 이면 정렬, 아니면 발란싱.

1X = 회전수(rpm)/60 Hz. 베어링 외륜 주파수 = (1X / 2) x 0.8 x 볼 개수 (약산식).
볼 개수 1인 채널은 베어링 판정을 하지 않고 FFT 그림에도 베어링 세로줄을 그리지 않습니다.
