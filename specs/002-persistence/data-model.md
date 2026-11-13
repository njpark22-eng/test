# 데이터 모델: 가상 계측 데이터 저장과 결과 이력

모든 테이블은 추가만 가능하다. `BEFORE UPDATE OR DELETE` 트리거가 예외를 일으켜 수정·삭제를 막는다(research.md 2번).

## measurement_files (계측 원본)

| 열 | 형식 | 제약 | 설명 |
|---|---|---|---|
| `id` | bigserial | 기본 키 | |
| `sha256` | text | 필수, 유일, 64자 16진수 | 원본 바이트의 SHA-256 |
| `content` | bytea | 필수 | 올린 엑셀 원본 바이트. 크기 1 MB 이하 |
| `size_bytes` | integer | 필수, 1 이상 1,048,576 이하 | |
| `channel` | text | 필수, `CH1`~`CH5` | 처음 올릴 때의 채널 |
| `filename` | text | 선택, 200자 이하 | 처음 올릴 때의 파일 이름(경로 제외). 저장된 파일 목록에 보인다. 기존 테이블에는 `ADD COLUMN IF NOT EXISTS`로 추가 |
| `uploaded_at` | timestamptz | 필수, 기본 `now()` | |

같은 해시를 다시 올리거나 저장된 파일을 골라 분석하면 새 행을 만들지 않고 기존 `id`를 참조한다(파일 이름도 처음 값 유지).

## analysis_runs (분석 실행)

| 열 | 형식 | 제약 | 설명 |
|---|---|---|---|
| `id` | bigserial | 기본 키 | |
| `created_at` | timestamptz | 필수, 기본 `now()` | 실행 시각 (시간당 횟수 제한에 쓴다) |
| `thresholds` | jsonb | 필수 | 판정에 쓴 고정 기준값 `{rms_limit, lowfreq_noise_limit, ratio_2x_over_1x, ratio_bearing_over_1x}` |
| `channel_count` | smallint | 필수, 1~5 | |

## channel_results (채널 결과)

| 열 | 형식 | 제약 | 설명 |
|---|---|---|---|
| `id` | bigserial | 기본 키 | |
| `run_id` | bigint | 필수, `analysis_runs.id` 참조 | |
| `file_id` | bigint | 필수, `measurement_files.id` 참조 | |
| `channel` | text | 필수, `CH1`~`CH5` | 실행 안에서 유일 |
| `rpm` | integer | 필수, 0 초과 20,000 이하 | 사용한 회전수 |
| `balls` | integer | 필수, 1~100 | 사용한 볼 개수 (1이면 베어링 미사용) |
| `verdict` | text | 필수 | `rule_verdict` 결과 5가지 중 하나 |
| `result` | jsonb | 필수 | `analyze_signal` 반환값 전체 |
| `spectrum` | jsonb | 필수 | `{f: [...], amp: [...]}` 0~600 Hz |

유일 제약: `(run_id, channel)`.

## 관계

- 분석 실행 1건 → 채널 결과 1~5개 → 각각 계측 원본 1개.
- 계측 원본 1개는 여러 채널 결과에서 참조될 수 있다(같은 파일을 다시 올린 경우).

## 판정 값

`재계측 권장`, `정상`, `베어링 점검 요망`, `발란싱 요망`, `정렬 요망` 다섯 가지뿐이다. 앱이 `rule_verdict`의 반환값만 저장한다.

## 상태 전환

없다. 행은 한 번 만들어지면 바뀌지 않는다.
