# 엔드포인트 계약: 웹 데모

엔드포인트는 GET 두 개뿐이다. 쓰기, 업로드, 삭제 엔드포인트는 만들지 않는다(원칙 I, FR-002).

## `GET /`

판정 표, FFT 그래프, 판정 규칙, '가상 데이터, 규칙 기반 판정' 표시가 들어간 한 페이지를 돌려준다.

| 항목 | 값 |
|---|---|
| 상태 코드 | 200 |
| `Content-Type` | `text/html; charset=utf-8` |
| 본문 | `api/page.html` 내용. 화면은 로드 후 `GET /api/analyze`를 호출해 채우고, 호출이 실패하면 오류 문구를 보여 준다 |

## `GET /api/analyze`

가상 데이터 5채널을 분석해 JSON으로 돌려준다. 쿼리 매개변수는 없다.

### 성공 응답 (200)

```json
{
  "channels": [
    {
      "r": {
        "channel": "CH3",
        "rpm": 1500,
        "shaft_1X_hz": 25.0,
        "bearing_balls": 9,
        "bearing_BPFO_hz": 90.0,
        "lowfreq_noise_rms": 0.0,
        "peak_rms_mm_s": 0.0,
        "peak_freq_hz": 0.0,
        "rms_limit_mm_s": 4.5,
        "rms_1X": 0.0,
        "rms_2X": 0.0,
        "rms_bearing_BPFO": 0.0,
        "ratio_2X_over_1X": 0.0,
        "ratio_bearing_over_1X": 0.0
      },
      "verdict": "베어링 점검 요망",
      "f": [0.0, 0.5],
      "amp": [0.0, 0.0]
    }
  ],
  "rules": "판정 규칙: ..."
}
```

위 값은 구조를 보이기 위한 자리표시 숫자다. 실제 값은 `analyze_signal`이 계산한다.

| 필드 | 형식 | 설명 |
|---|---|---|
| `channels` | 배열(5개, CH1~CH5 순서) | 채널별 결과 |
| `channels[].r` | 객체 | `analyze_signal` 반환값 그대로([data-model.md](../data-model.md)) |
| `channels[].verdict` | 문자열 | `rule_verdict` 결과. 다섯 가지 중 하나 |
| `channels[].f` | 숫자 배열 | 0~600 Hz 주파수(Hz) |
| `channels[].amp` | 숫자 배열 | 같은 길이의 RMS 진폭(mm/s) |
| `rules` | 문자열 | `RULES` 원문 |

기대 판정(기본 데이터): CH1 재계측 권장 / CH2 정상 / CH3 베어링 점검 요망 / CH4 발란싱 요망 / CH5 정렬 요망.

### 오류 응답 (500)

저장소의 가상 데이터가 번들에 없거나 5개가 모두 없을 때.

```json
{ "error": "계측 파일(CH1~CH5.xlsx)을 찾을 수 없습니다. --make-data로 생성하세요" }
```

문구는 무슨 일이 생겼고 사용자가 무엇을 하면 되는지를 한 줄로 쓴다(slop 방지 문구 규칙).

## 계약 검증 (테스트)

- `GET /` → 200, `text/html`, 본문에 '규칙 기반 판정' 표시 포함.
- `GET /api/analyze` → 200, `channels` 길이 5, 판정 5개가 기대값과 일치, `rules`가 `vibe_agent.RULES`와 같음.
- 데이터 없음(테스트에서 `SIGNALS`를 비움) → 500과 `error` 문자열.
- 허용하지 않는 메서드(`POST /api/analyze` 등) → 405.
