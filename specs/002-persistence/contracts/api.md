# 엔드포인트 계약: 가상 계측 데이터 저장과 결과 이력

기존 `GET /`, `GET /api/analyze`(001)는 그대로다. 아래는 추가되는 것이다. 수정·삭제 엔드포인트는 만들지 않는다.

## 공통

- 쓰기(`POST`)는 요청 헤더 `X-Write-Token`이 환경변수 `WRITE_TOKEN`과 같아야 한다. 읽기(`GET`)는 토큰이 필요 없다.
- 오류 본문은 `{"error": "한 줄 안내"}` 형식이다. 안내는 무슨 일이 생겼고 무엇을 하면 되는지 쓴다.
- 토큰과 `DATABASE_URL` 값은 어떤 응답에도 넣지 않는다.

| 상태 | 의미 |
|---|---|
| 401 | 토큰이 없거나 틀림, 또는 서버에 `WRITE_TOKEN`이 설정되지 않음 |
| 413 | 파일 1개 1 MB 초과 또는 합계 4 MB 초과 |
| 422 | 형식·값 검증 실패 (엑셀 형식, 샘플링 주파수, 채널 수, rpm, 볼 개수) |
| 429 | 시간당 30회 초과 |
| 503 | 저장소(`DATABASE_URL`)가 설정되지 않았거나 연결 실패 |

## `GET /api/config`

화면이 쓰는 고정 설정. 토큰 없이 읽는다.

```json
{
  "limits": {"max_file_bytes": 1048576, "max_total_bytes": 4194304, "max_channels": 5, "runs_per_hour": 30},
  "thresholds": {"rms_limit": 4.5, "lowfreq_noise_limit": 20.0, "ratio_2x_over_1x": 0.5, "ratio_bearing_over_1x": 0.7},
  "write_enabled": true
}
```

`write_enabled`는 서버에 `WRITE_TOKEN`이 설정되어 있는지만 알려 준다.

## `POST /api/inspect` (토큰 필요)

파일 하나를 읽어 검증하고 자동 rpm과 데이터 앞부분을 돌려준다. 저장하지 않는다.

- 요청: 멀티파트, 필드 `file`
- 성공 200

```json
{"samples": 10240, "fs": 5120.0, "rpm_detected": 1800, "preview": [[0.0, 0.12], [0.000195, 0.31]]}
```

`preview`는 앞 20행이다. 실패는 413/422.

## `POST /api/runs` (토큰 필요)

파일을 검증하고 분석한 뒤 원본과 결과를 저장한다.

- 요청: 멀티파트. 필드 `files`(1~5개, 순서대로 CH1~CH5), `rpm`(파일 수만큼, 정수), `balls`(파일 수만큼, 정수, 생략하면 모두 1)
- 검증: 크기, 엑셀 형식, 샘플링 주파수 5,120 Hz, rpm 0 초과 20,000 이하, 볼 개수 1~100 정수, 입력 rpm의 1X 성분이 최대 피크의 20% 이상(아니면 422와 `{"error", "channel", "detected_rpm"}`)
- 성공 201: 아래 상세 응답과 같은 본문
- 원본과 결과는 한 트랜잭션으로 저장한다. 실패하면 아무것도 남기지 않는다.

## `GET /api/runs`

저장된 분석 실행 목록, 최신순, 최대 100건.

```json
{"runs": [{"id": 12, "created_at": "2026-11-13T05:00:00+00:00", "channel_count": 5,
           "verdicts": [{"channel": "CH1", "verdict": "재계측 권장"}]}]}
```

## `GET /api/runs/{id}`

```json
{"id": 12, "created_at": "...", "thresholds": {"rms_limit": 4.5, "lowfreq_noise_limit": 20.0,
  "ratio_2x_over_1x": 0.5, "ratio_bearing_over_1x": 0.7},
 "channels": [{"channel": "CH1", "rpm": 900, "balls": 1, "sha256": "...", "r": {}, "verdict": "재계측 권장",
               "f": [], "amp": []}]}
```

`r`은 저장된 `analyze_signal` 값 그대로, `f`/`amp`는 저장된 스펙트럼이다. 없는 `id`는 404.

## 화면 경로

| 경로 | 내용 |
|---|---|
| `GET /upload` | 올리기 화면. '가상 데이터만 올리세요. 실제 계측 데이터는 금지'를 항상 표시 |
| `GET /runs` | 이력 목록 |
| `GET /runs/{id}` | 같은 HTML이 상세를 보여 줌 |
| `GET /assets/shared.css`, `/assets/shared.js` | 공통 스타일·스크립트 |

## 계약 검증 (테스트)

- 토큰 없음/틀림/서버 토큰 미설정 → 401. 읽기는 토큰 없이 200.
- 정상 업로드 5개 → 201, 판정이 기대값, 저장된 해시가 올린 파일의 SHA-256과 같음.
- 크기 초과 413, 잘못된 형식·rpm·볼 개수·샘플링 주파수 422, 횟수 초과 429, 저장소 없음 503.
- 같은 파일 재업로드 → 원본 행이 늘지 않고 결과 행은 늘어남.
- `PUT/PATCH/DELETE`는 405.
