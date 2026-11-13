"""실제 Postgres(Neon) 저장소 테스트. TEST_DATABASE_URL이 있을 때만 실행한다.
운영 DB가 아니라 테스트용 DB(예: Neon 브랜치)를 가리켜야 한다."""
import os
import uuid

import pytest

from vibe_web import analysis
from vibe_web.store import PgStore

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL이 없어 실제 DB 테스트를 건너뜁니다")


def channel(content: bytes):
    return {"channel": "CH1", "rpm": 1800, "balls": 1, "verdict": "정상", "result": {"channel": "CH1"},
            "spectrum": {"f": [0.0, 0.5], "amp": [0.0, 1.0]}, "content": content}


def test_insert_dedupe_and_read_back():
    store = PgStore(URL)
    content = uuid.uuid4().bytes * 4
    first = store.insert_run(analysis.thresholds(), [channel(content)])
    second = store.insert_run(analysis.thresholds(), [channel(content)])
    assert second == first + 1 or second > first
    run = store.get_run(first)
    assert run["channels"][0]["verdict"] == "정상"
    assert run["thresholds"] == analysis.thresholds()
    assert any(r["id"] == second for r in store.list_runs())


def test_update_and_delete_are_rejected_by_database():
    import psycopg
    store = PgStore(URL)
    run_id = store.insert_run(analysis.thresholds(), [channel(uuid.uuid4().bytes * 4)])
    with psycopg.connect(URL) as conn:
        for sql in ("UPDATE analysis_runs SET channel_count = 2 WHERE id = %s",
                    "DELETE FROM analysis_runs WHERE id = %s",
                    "UPDATE channel_results SET rpm = 1 WHERE run_id = %s",
                    "DELETE FROM channel_results WHERE run_id = %s"):
            with pytest.raises(psycopg.Error):
                conn.execute(sql, (run_id,))
            conn.rollback()
        for sql in ("UPDATE measurement_files SET size_bytes = 1",
                    "DELETE FROM measurement_files"):
            with pytest.raises(psycopg.Error):
                conn.execute(sql)
            conn.rollback()
