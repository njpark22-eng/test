# 빠른 시작과 검증: 가상 계측 데이터 저장과 결과 이력

구현 코드는 여기에 쓰지 않는다. 엔드포인트는 [contracts/api.md](contracts/api.md), 테이블은 [data-model.md](data-model.md)를 본다.

## 준비

- 환경변수 두 개가 필요하다. 값은 저장소·로그·화면에 남기지 않는다.
  - `DATABASE_URL`: Neon 연결 문자열(풀링 주소 권장)
  - `WRITE_TOKEN`: 쓰기 토큰(직접 정한 긴 무작위 문자열)
- 로컬은 셸에 설정하거나 저장소 밖의 설정으로 넣는다. `.env`는 커밋하지 않는다. Vercel은 프로젝트 환경변수(Sensitive)에 넣는다.
- 테스트용 DB는 Neon 브랜치를 따로 만들어 `TEST_DATABASE_URL`로 지정하는 것을 권한다. 운영 DB에 테스트 데이터를 쌓지 않기 위해서다.

## 1. 로컬 테스트 (DB 없이)

```
uv run pytest
```

기대 결과: 기존 테스트와 `tests/test_persistence.py`가 모두 통과한다. 메모리 저장소로 돌아 실제 DB를 쓰지 않는다. `tests/test_store_pg.py`는 `TEST_DATABASE_URL`이 없으면 건너뛴다.

## 2. 로컬 실행 (DB 연결)

```
uv run uvicorn api.index:app
```

`DATABASE_URL`, `WRITE_TOKEN`을 설정한 셸에서 실행한다. 처음 DB를 쓰는 요청이 테이블과 트리거를 만든다(멱등).

기대 결과
- `http://127.0.0.1:8000/upload`에 '가상 데이터만 올리세요' 문구가 보인다.
- `data/CH1~CH5.xlsx` 5개를 고르면 채널별 rpm이 자동으로 채워진다(900/1800/1500/1200/2400). 볼 개수는 CH3만 9로 바꾼다.
- 분석을 실행하면 판정이 CH1 재계측 권장 / CH2 정상 / CH3 베어링 점검 요망 / CH4 발란싱 요망 / CH5 정렬 요망이다.
- `http://127.0.0.1:8000/runs`에 방금 실행이 보이고, 상세에서 같은 수치와 그래프, 판정에 쓴 기준값이 보인다.

## 3. 사람이 확인할 곳

- 같은 5개 파일의 판정이 `uv run python vibe_agent.py --offline`과 같다.
- 올린 파일의 SHA-256과 상세에 보이는 해시가 같다.
- 토큰 없이 올리기를 시도하면 거부되고, 목록과 상세는 토큰 없이 열린다.
- `data/*.xlsx`가 바뀌지 않았다(`git status`에 변경 없음).
- 저장된 행을 수정·삭제하려는 SQL이 거부된다(`TEST_DATABASE_URL` 테스트 또는 Neon 콘솔에서 확인).

## 4. 화면 점검

- 휴대폰 폭에서 가로 스크롤이 없고 다크 모드에서 글자가 읽힌다.
- 색은 흰색, 회색, 파랑 `#0C4CA3`과 판정 의미색 3가지뿐이다.
- 오류 문구가 무슨 일이 생겼고 무엇을 하면 되는지 한 줄로 나온다.

## 5. Vercel 배포 확인

1. 프로젝트 환경변수에 `DATABASE_URL`, `WRITE_TOKEN`(Sensitive)을 넣는다.
2. `main`에 push하면 빌드된다. 빌드 로그에서 `psycopg`, `python-multipart` 설치와 함수 크기를 본다.
3. Preview에서 위 2번 시나리오를 수행한다. `/api/config`의 `write_enabled`가 `true`인지 먼저 본다.
4. 업로드 한 번의 소요 시간을 기록한다.
5. 문제가 없으면 Production으로 올린다.

## 실패했을 때

| 증상 | 확인할 것 |
|---|---|
| 업로드가 401 | 입력한 토큰과 Vercel의 `WRITE_TOKEN`, `/api/config`의 `write_enabled` |
| 503 | `DATABASE_URL`이 있는지, 풀링 주소인지, 연결 허용 설정 |
| 413 | 파일이 1 MB, 합계 4 MB 이내인지 |
| 422 rpm 경고 | 입력 rpm이 신호의 1X와 맞는지(자동 입력값 사용) |
| 429 | 최근 1시간 저장 횟수(30회) |
