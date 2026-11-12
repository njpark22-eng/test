# 시연 스크립트 (혼자, 10분)

시연 5분 + 설계/안전장치/회고 5분 구성

| 시간 | 내용 |
|---|---|
| 0:00~1:00 | **문제 소개** 진동 계측 결과를 사람이 FFT 보고 판정하는 일을 에이전트가 하게 만들었다. 판정은 정상, 베어링 점검, 발란싱, 정렬, 재계측 권장 다섯 가지. |
| 1:00~2:30 | **구조 설명** 신호 5개 생성, Claude가 `list_signals`, `analyze_signal` 도구를 호출해 분석. 규칙은 FFT 최대 피크 RMS 4.5 기준과 1X, 2X, 베어링 성분 비율(2X 0.5, 베어링 0.7). 채널(장비)마다 회전수가 다름. |
| 2:30~5:00 | **라이브 실행** `uv run python vibe_agent.py` 실행. `[도구 호출]` 로그와 채널별 판정을 보여 준다. 정답: CH1 재계측 권장 / CH2 정상 / CH3 베어링 점검 / CH4 발란싱 / CH5 정렬 |
| 5:00~6:00 | **스펙트럼** `spectra.png`에서 CH3 베어링 피크, CH5 2X 피크, CH1 재계측 안내 문구를 짚는다. |
| 6:00~7:30 | **안전장치** `.claude/settings.json`의 deny 규칙(.env 읽기, rm -rf, curl, force push)과 수정 후 pytest 자동 실행 hook. `.gitignore`와 비밀 값 확인. |
| 7:30~8:30 | **에이전트 설계** agents 2개: `signal-analyst`(수정 권한), `diagnosis-reviewer`(읽기 전용). 역할과 도구 권한을 나눈 이유. `uv run pytest` 통과 화면. |
| 8:30~9:30 | **사람이 확인한 지점과 이유 + 회고 세 줄** 에이전트 판정을 직접 검증한 부분(경계값, 규칙 일치 등)과 그 이유. 잘된 것, 막힌 것, 다음에 할 것. |
| 9:30~10:00 | **마무리** 한 줄 요약, 질문 받기. |

## 실행이 안 될 때
- API 오류: `uv run python vibe_agent.py --offline`으로 전환
- 그래도 안 되면 미리 찍어 둔 캡처를 보여 준다.

## 시연 전 준비
- [ ] `ANTHROPIC_API_KEY` 환경변수 설정 (화면에 노출 주의)
- [ ] `uv run python vibe_agent.py --make-data` 로 data/CH1~CH5.xlsx 생성
- [ ] `uv run python vibe_agent.py --plot` 로 spectra.png 생성
- [ ] UI 시연 시 `uv run python vibe_agent.py --ui` 실행, 채널 5개에 CH1~CH5.xlsx 선택 (회전수 자동 입력 확인)
- [ ] 예비 캡처 2~3장 저장
- [ ] 10분 안에 끝나는지 전체 리허설 1회
