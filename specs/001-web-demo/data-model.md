# 데이터 모델: 웹 데모

웹은 읽기 전용이라 저장되는 데이터가 없다. 아래는 요청마다 메모리에서 만들어지는 값의 구조다. 값은 모두 `vibe_agent`의 함수가 만든다.

## 채널 (Channel)

| 필드 | 설명 | 출처 |
|---|---|---|
| 이름 | `CH1`~`CH5` | `vibe_agent.CHANNELS` |
| rpm | 장비별 회전수 | `vibe_agent.RPM` (기본 900/1800/1500/1200/2400) |
| 볼 개수 | 1이면 베어링 미사용 | `vibe_agent.BALLS` (기본 1/1/9/1/1) |
| 시간 신호 | 속도 mm/s, 5,120 Hz, 2초 | 저장소의 가상 데이터를 `read_xlsx`로 읽은 값 |

규칙
- 5개 파일이 모두 있어야 로드된다(`load_signals`). 하나라도 없으면 `SIGNALS`가 비어 오류로 응답한다.
- 웹은 rpm과 볼 개수를 바꾸지 않는다. 기본값을 그대로 쓴다.

## 분석 결과 (Analysis)

`vibe_agent.analyze_signal(채널)`의 반환값을 그대로 쓴다. 웹이 값을 반올림하거나 고치지 않는다.

| 필드 | 단위 | 설명 |
|---|---|---|
| `channel` | - | 채널 이름 |
| `rpm` | rpm | 회전수 |
| `shaft_1X_hz` | Hz | 1X 주파수 = rpm/60 |
| `bearing_balls` | 개 | 볼 개수 |
| `bearing_BPFO_hz` | Hz | 외륜 주파수. 볼 개수 1이면 `null` |
| `lowfreq_noise_rms` | mm/s | 2 Hz 미만 저주파 노이즈 RMS |
| `peak_rms_mm_s` | mm/s | FFT 최대 피크 RMS. 판정 기준과 비교하는 값 |
| `peak_freq_hz` | Hz | 최대 피크 주파수 |
| `rms_limit_mm_s` | mm/s | 기준 4.5 |
| `rms_1X`, `rms_2X` | mm/s | 1X, 2X RMS |
| `rms_bearing_BPFO` | mm/s | 베어링 RMS. 볼 개수 1이면 `null` |
| `ratio_2X_over_1X` | - | 2X/1X |
| `ratio_bearing_over_1X` | - | 베어링/1X. 볼 개수 1이면 0.0 |

## 판정 (Verdict)

`vibe_agent.rule_verdict(분석 결과)`의 문자열. 값은 다섯 가지뿐이다.

| 판정 | 화면 색 구분 |
|---|---|
| 정상 | 초록 |
| 재계측 권장 | 주황 |
| 베어링 점검 요망 | 주황 |
| 발란싱 요망 | 빨강 |
| 정렬 요망 | 빨강 |

판정 우선순위는 `RULES`를 따른다(저주파 노이즈 → 베어링 → 정상 → 정렬 → 발란싱). 화면에서 다시 계산하지 않는다.

## 스펙트럼 (Spectrum)

`vibe_agent.spectrum(시간 신호)`의 결과 중 0~600 Hz만 보낸다.

| 필드 | 단위 | 설명 |
|---|---|---|
| `f` | Hz | 주파수 배열 |
| `amp` | mm/s (RMS) | 진폭 배열 (Hanning 보정 후 peak/√2) |

## 관계

- 채널 1개 → 분석 결과 1개 → 판정 1개, 스펙트럼 1개.
- 응답은 채널 5개의 목록과 판정 규칙 원문(`RULES`)을 함께 담는다.

## 상태 전환

없다. 모든 요청은 같은 입력에서 같은 결과를 돌려준다(저장, 캐시, 세션 없음).
