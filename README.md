# vibe-agent: 진동 진단 에이전트 (시연용)

진동 계측 데이터(엑셀)를 FFT로 분석해 정상 / 베어링 점검 / 발란싱 / 정렬 / 재계측 권장을 판정합니다.
Claude가 도구(`list_signals`, `analyze_signal`)를 호출하며 판단하는 에이전트입니다.
시연 데이터는 모두 numpy로 생성한 가상 신호입니다. 실제 설비·개인정보는 없습니다.

## 설치
    uv sync            # 또는: pip install numpy anthropic matplotlib openpyxl pytest

## 실행
    export ANTHROPIC_API_KEY=...   # .env에 두지 말고 환경변수로, 저장소에 커밋 금지
    uv run python vibe_agent.py --make-data  # 가상 계측 데이터를 data/CH1~CH5.xlsx로 생성 (최초 1회)
    uv run python vibe_agent.py              # 에이전트 모드
    uv run python vibe_agent.py --offline    # API 없이 규칙 기반 (시연 백업)
    uv run python vibe_agent.py --plot       # spectra.png 생성
    uv run python vibe_agent.py --ui         # 파일 선택 UI (API 키 없으면 규칙 기반)
    uv run python vibe_agent.py --ui --offline

## UI 사용 순서 (`--ui`)
1. 채널 개수 입력 (안내는 1~32, 지금은 5채널까지 가능)
2. 채널마다 `파일 선택`으로 엑셀 선택 -> 데이터 표와 시간 신호 그래프 표시
3. 회전수(rpm)는 신호의 1X에 맞춰 자동으로 채워짐. 다른 값을 입력하면 1X와 맞는지 바로 확인하고 다시 입력받음
4. 베어링 볼 개수 입력 (기본값 CH3은 9, 나머지는 1). 기본값과 다르면 확인창이 뜸. 1은 베어링 주파수 미사용
5. `분석 실행` -> 채널별 FFT 그림, RMS 기준 만족/불만족, 결함 진단 표시

## 데이터 형식
엑셀 1개 = 채널 1개. A열 `time_s`, B열 `velocity_mm_s`, 샘플링 주파수 5120 Hz.
시연용 파일에는 시간 신호 그래프가 들어 있으나, 분석에는 데이터(A, B열)만 사용합니다.

**입력 데이터 엑셀 파일은 수정 금지입니다.** 계측기에서 다운받은 원본 데이터로 간주하므로, 직접 편집하거나
프로그램이 덮어쓰지 않습니다. 분석은 읽기 전용으로 파일을 열고, 결과는 `result-N.xlsx`와 `result-N.png`로 따로 저장합니다.
(예외: `--make-data`는 시연용 가상 데이터 `data/CH1~CH5.xlsx`를 새로 만드는 명령이며 실제 계측 데이터에는 쓰지 않습니다.)

## 결과 파일
분석을 실행하면(`--offline`, 에이전트, `--ui` 모두) 실행 폴더에 결과 파일 2개가 같은 일련번호로 저장됩니다.
- `result-N.xlsx`: 채널별 결과 표 (채널, 회전수, 볼 개수, 최대 피크 RMS, 기준 만족/불만족/재계측, 1X/2X/BPFO RMS, 결함 진단)
- `result-N.png`: 채널별 FFT 그래프(1X/2X/BPFO, 허용기준선) + 판정 설명 텍스트. 에이전트 모드면 Claude 진단도 함께 들어갑니다.

실행할 때마다 가장 큰 번호 + 1로 새로 만들어 이전 결과를 덮어쓰지 않습니다. 두 파일은 `.gitignore` 대상이라 커밋되지 않습니다.
(`--plot`의 `spectra.png`는 이와 별개입니다.)

## 테스트
    uv run pytest

## 판정 규칙
기준 비교 값은 FFT 최대 피크의 RMS(mm/s)이며, 기준은 4.5 mm/s입니다. FFT 진폭도 RMS 단위입니다.
- 2Hz 미만 저주파 노이즈 RMS가 20 mm/s 초과: 재계측 권장 (아래 규칙은 적용하지 않음).
- 기준 이하: 베어링 성분/1X >= 0.7 이면 베어링 점검, 아니면 정상.
- 기준 초과: 2X/1X >= 0.5 이면 정렬, 아니면 발란싱.

1X = 회전수(rpm)/60 Hz. 베어링 외륜 주파수 = (1X / 2) x 0.8 x 볼 개수 (약산식).
볼 개수 1인 채널은 베어링 판정을 하지 않고 FFT 그림에도 베어링 세로줄을 그리지 않습니다.
