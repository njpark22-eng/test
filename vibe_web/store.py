"""저장소: 가상 계측 원본과 분석 결과를 추가만 가능한 형태로 저장한다.

수정·삭제 메서드는 만들지 않는다. Postgres는 트리거로도 UPDATE/DELETE를 막는다.
PgStore는 Neon Postgres(DATABASE_URL), MemoryStore는 테스트용이다. 두 구현은 같은 메서드를 가진다.
"""
import hashlib
import threading
from datetime import datetime, timedelta, timezone

from vibe_web.errors import ApiError

APPEND_ONLY_TABLES = ("measurement_files", "analysis_runs", "channel_results")

SCHEMA_SQL = [
    """CREATE TABLE IF NOT EXISTS measurement_files (
        id bigserial PRIMARY KEY,
        sha256 text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        content bytea NOT NULL,
        size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 1048576),
        channel text NOT NULL CHECK (channel IN ('CH1','CH2','CH3','CH4','CH5')),
        uploaded_at timestamptz NOT NULL DEFAULT now()
    )""",
    "ALTER TABLE measurement_files ADD COLUMN IF NOT EXISTS filename text",
    """CREATE TABLE IF NOT EXISTS analysis_runs (
        id bigserial PRIMARY KEY,
        created_at timestamptz NOT NULL DEFAULT now(),
        thresholds jsonb NOT NULL,
        channel_count smallint NOT NULL CHECK (channel_count BETWEEN 1 AND 5)
    )""",
    """CREATE TABLE IF NOT EXISTS channel_results (
        id bigserial PRIMARY KEY,
        run_id bigint NOT NULL REFERENCES analysis_runs(id),
        file_id bigint NOT NULL REFERENCES measurement_files(id),
        channel text NOT NULL CHECK (channel IN ('CH1','CH2','CH3','CH4','CH5')),
        rpm integer NOT NULL CHECK (rpm > 0 AND rpm <= 20000),
        balls integer NOT NULL CHECK (balls BETWEEN 1 AND 100),
        verdict text NOT NULL CHECK (verdict IN ('재계측 권장','정상','베어링 점검 요망','발란싱 요망','정렬 요망')),
        result jsonb NOT NULL,
        spectrum jsonb NOT NULL,
        UNIQUE (run_id, channel)
    )""",
    """CREATE OR REPLACE FUNCTION reject_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION '% 테이블은 추가만 가능합니다 (수정·삭제 금지)', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql""",
] + [
    f"""CREATE OR REPLACE TRIGGER {t}_append_only
        BEFORE UPDATE OR DELETE ON {t}
        FOR EACH ROW EXECUTE FUNCTION reject_change()"""
    for t in APPEND_ONLY_TABLES
]


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _channel_detail(c: dict) -> dict:
    return {"channel": c["channel"], "rpm": c["rpm"], "balls": c["balls"], "sha256": c["sha256"],
            "verdict": c["verdict"], "r": c["result"],
            "f": c["spectrum"]["f"], "amp": c["spectrum"]["amp"]}


class MemoryStore:
    """테스트용 저장소. 추가만 가능하다."""

    def __init__(self):
        self._lock = threading.Lock()
        self.files: dict[str, dict] = {}
        self.runs: list[dict] = []

    def recent_run_count(self, hours: int = 1) -> int:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return sum(1 for r in self.runs if r["created_at"] >= since)

    def insert_run(self, thresholds: dict, channels: list[dict]) -> int:
        """channels: [{channel, rpm, balls, verdict, result, spectrum, content}]"""
        with self._lock:
            new_files = {}
            rows = []
            for c in channels:
                sha = sha256_hex(c["content"])
                if sha not in self.files and sha not in new_files:
                    new_files[sha] = {"id": len(self.files) + len(new_files) + 1, "sha256": sha,
                                      "content": c["content"], "channel": c["channel"],
                                      "size_bytes": len(c["content"]), "filename": c.get("filename"),
                                      "uploaded_at": datetime.now(timezone.utc)}
                rows.append({**{k: c[k] for k in ("channel", "rpm", "balls", "verdict", "result", "spectrum")},
                             "sha256": sha})
            run = {"id": len(self.runs) + 1, "created_at": datetime.now(timezone.utc),
                   "thresholds": dict(thresholds), "channel_count": len(rows), "channels": rows}
            self.files.update(new_files)
            self.runs.append(run)
            return run["id"]

    def list_files(self, limit: int = 100) -> list[dict]:
        files = sorted(self.files.values(), key=lambda f: f["id"], reverse=True)[:limit]
        return [{"id": f["id"], "sha256": f["sha256"], "channel": f["channel"], "size_bytes": f["size_bytes"],
                 "filename": f["filename"], "uploaded_at": f["uploaded_at"].isoformat()} for f in files]

    def get_file(self, file_id: int) -> dict | None:
        for f in self.files.values():
            if f["id"] == file_id:
                return {k: f[k] for k in ("id", "sha256", "content", "channel", "size_bytes", "filename")}
        return None

    def list_runs(self, limit: int = 100) -> list[dict]:
        out = []
        for r in sorted(self.runs, key=lambda r: r["id"], reverse=True)[:limit]:
            out.append({"id": r["id"], "created_at": r["created_at"].isoformat(),
                        "channel_count": r["channel_count"],
                        "verdicts": [{"channel": c["channel"], "verdict": c["verdict"]}
                                     for c in sorted(r["channels"], key=lambda c: c["channel"])]})
        return out

    def get_run(self, run_id: int) -> dict | None:
        for r in self.runs:
            if r["id"] == run_id:
                return {"id": r["id"], "created_at": r["created_at"].isoformat(),
                        "thresholds": r["thresholds"],
                        "channels": [_channel_detail(c) for c in sorted(r["channels"], key=lambda c: c["channel"])]}
        return None


class PgStore:
    """Neon Postgres 저장소. 요청마다 연결을 열고 닫는다(서버리스, 풀링 주소 권장)."""

    _schema_ready = False
    _schema_lock = threading.Lock()

    def __init__(self, url: str):
        self._url = url

    def _connect(self):
        import psycopg
        try:
            return psycopg.connect(self._url, connect_timeout=10)
        except Exception:
            # from None: 연결 문자열이 담길 수 있는 원본 예외를 로그·트레이스백에 잇지 않는다
            raise ApiError(503, "저장소에 연결하지 못했습니다. 잠시 뒤 다시 시도하거나 DATABASE_URL을 확인하세요") from None

    def _ensure_schema(self, conn) -> None:
        if PgStore._schema_ready:
            return
        with PgStore._schema_lock:
            if PgStore._schema_ready:
                return
            with conn.transaction():
                for stmt in SCHEMA_SQL:
                    conn.execute(stmt)
            PgStore._schema_ready = True

    def _run(self, fn):
        import psycopg
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            return fn(conn)
        except ApiError:
            raise
        except psycopg.Error:
            raise ApiError(503, "저장소 작업에 실패했습니다. 잠시 뒤 다시 시도하세요") from None
        finally:
            conn.close()

    def recent_run_count(self, hours: int = 1) -> int:
        def fn(conn):
            row = conn.execute("SELECT count(*) FROM analysis_runs WHERE created_at > now() - make_interval(hours => %s)",
                               (hours,)).fetchone()
            return int(row[0])
        return self._run(fn)

    def insert_run(self, thresholds: dict, channels: list[dict]) -> int:
        from psycopg.types.json import Jsonb

        def fn(conn):
            with conn.transaction():   # 원본과 결과는 함께 저장되거나 모두 저장되지 않는다
                file_ids = []
                for c in channels:
                    sha = sha256_hex(c["content"])
                    row = conn.execute(
                        "INSERT INTO measurement_files (sha256, content, size_bytes, channel, filename) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (sha256) DO NOTHING RETURNING id",
                        (sha, c["content"], len(c["content"]), c["channel"], c.get("filename"))).fetchone()
                    if row is None:
                        row = conn.execute("SELECT id FROM measurement_files WHERE sha256 = %s", (sha,)).fetchone()
                    file_ids.append(row[0])
                run_id = conn.execute(
                    "INSERT INTO analysis_runs (thresholds, channel_count) VALUES (%s, %s) RETURNING id",
                    (Jsonb(thresholds), len(channels))).fetchone()[0]
                for c, file_id in zip(channels, file_ids):
                    conn.execute(
                        "INSERT INTO channel_results (run_id, file_id, channel, rpm, balls, verdict, result, spectrum) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (run_id, file_id, c["channel"], c["rpm"], c["balls"], c["verdict"],
                         Jsonb(c["result"]), Jsonb(c["spectrum"])))
                return run_id
        return self._run(fn)

    def list_files(self, limit: int = 100) -> list[dict]:
        def fn(conn):
            rows = conn.execute(
                "SELECT id, sha256, channel, size_bytes, filename, uploaded_at "
                "FROM measurement_files ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
            return [{"id": r[0], "sha256": r[1], "channel": r[2], "size_bytes": r[3], "filename": r[4],
                     "uploaded_at": r[5].isoformat()} for r in rows]
        return self._run(fn)

    def get_file(self, file_id: int) -> dict | None:
        def fn(conn):
            r = conn.execute("SELECT id, sha256, content, channel, size_bytes, filename "
                             "FROM measurement_files WHERE id = %s", (file_id,)).fetchone()
            if r is None:
                return None
            return {"id": r[0], "sha256": r[1], "content": bytes(r[2]), "channel": r[3],
                    "size_bytes": r[4], "filename": r[5]}
        return self._run(fn)

    def list_runs(self, limit: int = 100) -> list[dict]:
        def fn(conn):
            rows = conn.execute(
                "SELECT r.id, r.created_at, r.channel_count, "
                "(SELECT json_agg(json_build_object('channel', c.channel, 'verdict', c.verdict) ORDER BY c.channel) "
                " FROM channel_results c WHERE c.run_id = r.id) "
                "FROM analysis_runs r ORDER BY r.id DESC LIMIT %s", (limit,)).fetchall()
            return [{"id": r[0], "created_at": r[1].isoformat(), "channel_count": r[2], "verdicts": r[3] or []}
                    for r in rows]
        return self._run(fn)

    def get_run(self, run_id: int) -> dict | None:
        def fn(conn):
            run = conn.execute("SELECT id, created_at, thresholds FROM analysis_runs WHERE id = %s",
                               (run_id,)).fetchone()
            if run is None:
                return None
            rows = conn.execute(
                "SELECT c.channel, c.rpm, c.balls, f.sha256, c.verdict, c.result, c.spectrum "
                "FROM channel_results c JOIN measurement_files f ON f.id = c.file_id "
                "WHERE c.run_id = %s ORDER BY c.channel", (run_id,)).fetchall()
            return {"id": run[0], "created_at": run[1].isoformat(), "thresholds": run[2],
                    "channels": [{"channel": r[0], "rpm": r[1], "balls": r[2], "sha256": r[3], "verdict": r[4],
                                  "r": r[5], "f": r[6]["f"], "amp": r[6]["amp"]} for r in rows]}
        return self._run(fn)
