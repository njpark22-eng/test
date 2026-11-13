"""가상 계측 데이터 저장과 이력(002) 테스트. 실제 DB 없이 메모리 저장소로 돌린다.
입력 엑셀(data/*.xlsx)은 읽기만 하고 수정하지 않는다."""
import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import vibe_agent as va
from vibe_web import analysis
from vibe_web.errors import ApiError
from vibe_web.main import app, get_store
from vibe_web.store import MemoryStore, PgStore

TOKEN = "test-token"
EXPECTED = {"CH1": "재계측 권장", "CH2": "정상", "CH3": "베어링 점검 요망",
            "CH4": "발란싱 요망", "CH5": "정렬 요망"}
CHANNELS = list(EXPECTED)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("WRITE_TOKEN", TOKEN)
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def demo_bytes(ch):
    return (va.DATA_DIR / f"{ch}.xlsx").read_bytes()


def auth(token=TOKEN):
    return {"X-Write-Token": token}


def post_run(client, contents, rpm=None, balls=None, token=TOKEN):
    n = len(contents)
    rpm = rpm if rpm is not None else [str(va.DEFAULT_RPM[c]) for c in CHANNELS[:n]]
    balls = balls if balls is not None else [str(va.DEFAULT_BALLS[c]) for c in CHANNELS[:n]]
    files = [("files", (f"CH{i}.xlsx", c, "application/octet-stream")) for i, c in enumerate(contents, 1)]
    return client.post("/api/runs", files=files, data={"rpm": rpm, "balls": balls},
                       headers=auth(token) if token is not None else {})


def all_demo():
    return [demo_bytes(c) for c in CHANNELS]


def make_xlsx(rows, fs=5120.0):
    wb = Workbook()
    ws = wb.active
    ws.append(["time_s", "velocity_mm_s"])
    for i in range(rows):
        ws.append([i / fs, 0.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- 토큰 ----------
def test_write_without_or_wrong_token_is_rejected(client, store):
    assert post_run(client, all_demo(), token=None).status_code == 401
    assert post_run(client, all_demo(), token="wrong").status_code == 401
    assert store.runs == []


def test_write_rejected_when_server_token_not_set(client, store, monkeypatch):
    monkeypatch.delenv("WRITE_TOKEN")
    assert post_run(client, all_demo()).status_code == 401
    assert client.get("/api/config").json()["write_enabled"] is False


def test_read_needs_no_token(client):
    assert client.get("/api/runs").status_code == 200
    assert client.get("/api/config").status_code == 200


def test_token_value_is_not_in_responses(client):
    res = post_run(client, all_demo(), token="wrong")
    assert TOKEN not in res.text and "wrong" not in res.text


# ---------- 업로드와 저장 ----------
def test_upload_five_channels_matches_expected_and_local_analysis(client, store):
    res = post_run(client, all_demo())
    assert res.status_code == 201
    run = res.json()
    got = {c["channel"]: c["verdict"] for c in run["channels"]}
    assert got == EXPECTED
    for c in run["channels"]:
        assert c["r"] == va.analyze_signal(c["channel"])        # 로컬 결과와 같음
        assert c["sha256"] == hashlib.sha256(demo_bytes(c["channel"])).hexdigest()
        assert len(c["f"]) == len(c["amp"]) > 0 and max(c["f"]) <= 600
    assert run["thresholds"] == analysis.thresholds()


def test_same_files_twice_keep_one_copy_of_originals(client, store):
    assert post_run(client, all_demo()).status_code == 201
    assert post_run(client, all_demo()).status_code == 201
    assert len(store.files) == 5
    assert len(store.runs) == 2


def test_failed_save_leaves_nothing(client, store):
    class Failing(MemoryStore):
        def insert_run(self, thresholds, channels):
            raise ApiError(503, "저장소 작업에 실패했습니다. 잠시 뒤 다시 시도하세요")
    failing = Failing()
    app.dependency_overrides[get_store] = lambda: failing
    res = post_run(client, all_demo())
    assert res.status_code == 503
    assert failing.runs == [] and failing.files == {}


def test_upload_leaves_no_temp_keys_and_input_files_unchanged(client):
    files = sorted(va.DATA_DIR.glob("CH*.xlsx"))
    before = [(f.stat().st_mtime_ns, f.stat().st_size) for f in files]
    keys_before = set(va.SIGNALS)
    assert post_run(client, all_demo()).status_code == 201
    assert set(va.SIGNALS) == keys_before
    assert not any(k.startswith("UP-") for k in list(va.RPM) + list(va.BALLS))
    assert before == [(f.stat().st_mtime_ns, f.stat().st_size) for f in files]


# ---------- 검증 ----------
def test_size_limits(client, store):
    assert post_run(client, [b"x" * (analysis.MAX_FILE_BYTES + 1)]).status_code == 413
    big = b"x" * (900 * 1024)
    assert post_run(client, [big] * 5).status_code == 413     # 합계 4 MB 초과
    assert store.runs == []


@pytest.mark.parametrize("contents", [
    [b"hello"],                                      # 엑셀이 아님
    [make_xlsx(0)],                                  # 데이터 행 없음
    [make_xlsx(1000, fs=1000.0)],                    # 샘플링 주파수 다름
    [],                                              # 파일 없음
])
def test_invalid_files_are_rejected(client, store, contents):
    if contents:
        res = post_run(client, contents, rpm=["1800"], balls=["1"])
    else:
        res = client.post("/api/runs", data={"rpm": [], "balls": []}, headers=auth())
    assert res.status_code == 422
    assert "error" in res.json() and store.runs == []


def test_zip_bomb_is_rejected(client, store):
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/big.bin", b"\0" * (analysis.MAX_UNPACKED_BYTES + 1))
    assert len(buf.getvalue()) < analysis.MAX_FILE_BYTES          # 크기 한도는 통과하는 작은 파일
    res = post_run(client, [buf.getvalue()], rpm=["1800"], balls=["1"])
    assert res.status_code == 422 and store.runs == []


def test_more_than_five_channels_rejected(client):
    assert post_run(client, [demo_bytes("CH2")] * 6, rpm=["1800"] * 6, balls=["1"] * 6).status_code == 422


@pytest.mark.parametrize("rpm", ["0", "20001", "abc", "", "1.5"])
def test_invalid_rpm_rejected(client, store, rpm):
    assert post_run(client, [demo_bytes("CH2")], rpm=[rpm], balls=["1"]).status_code == 422
    assert store.runs == []


@pytest.mark.parametrize("balls", ["0", "101", "1.5", "x"])
def test_invalid_balls_rejected(client, store, balls):
    assert post_run(client, [demo_bytes("CH2")], rpm=["1800"], balls=[balls]).status_code == 422
    assert store.runs == []


def test_rpm_without_1x_peak_is_rejected_with_detected_rpm(client, store):
    res = post_run(client, [demo_bytes("CH2")], rpm=["900"], balls=["1"])   # CH2의 1X는 30 Hz(1800 rpm)
    assert res.status_code == 422
    assert res.json()["detected_rpm"] == 1800
    assert store.runs == []


def test_hourly_limit(client, store):
    for i in range(analysis.RUNS_PER_HOUR):
        store.insert_run(analysis.thresholds(), [{
            "channel": "CH1", "rpm": 1800, "balls": 1, "verdict": "정상", "result": {},
            "spectrum": {"f": [0.0], "amp": [0.0]}, "content": f"file{i}".encode()}])
    assert post_run(client, all_demo()).status_code == 429


def test_no_store_configured_returns_503(client, monkeypatch):
    app.dependency_overrides.clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert post_run(client, all_demo()).status_code == 503
    assert client.get("/api/runs").status_code == 503


# ---------- inspect ----------
def test_inspect_returns_rpm_and_preview_without_saving(client, store):
    res = client.post("/api/inspect", files={"file": ("CH2.xlsx", demo_bytes("CH2"), "application/octet-stream")},
                      headers=auth())
    assert res.status_code == 200
    body = res.json()
    assert body["rpm_detected"] == 1800 and body["fs"] == va.FS and len(body["preview"]) == 20
    assert store.runs == [] and store.files == {}
    assert client.post("/api/inspect", files={"file": ("a.xlsx", b"x", "x")}).status_code == 401


# ---------- 고정 기준값 ----------
def base(**kw):
    r = {"lowfreq_noise_rms": 0.0, "peak_rms_mm_s": 1.0, "rms_limit_mm_s": va.RMS_LIMIT,
         "ratio_2X_over_1X": 0.0, "ratio_bearing_over_1X": 0.0}
    r.update(kw)
    return r


def test_recorded_thresholds_match_rule_verdict_boundaries():
    t = analysis.thresholds()
    over = va.RMS_LIMIT + 0.01
    assert t["rms_limit"] == va.RMS_LIMIT == 4.5
    assert va.rule_verdict(base(peak_rms_mm_s=va.RMS_LIMIT)) == "정상"
    assert va.rule_verdict(base(peak_rms_mm_s=over)) == "발란싱 요망"
    assert t["ratio_2x_over_1x"] == 0.5
    assert va.rule_verdict(base(peak_rms_mm_s=over, ratio_2X_over_1X=0.5)) == "정렬 요망"
    assert va.rule_verdict(base(peak_rms_mm_s=over, ratio_2X_over_1X=0.49)) == "발란싱 요망"
    assert t["ratio_bearing_over_1x"] == 0.7
    assert va.rule_verdict(base(ratio_bearing_over_1X=0.7)) == "베어링 점검 요망"
    assert va.rule_verdict(base(ratio_bearing_over_1X=0.69)) == "정상"
    assert t["lowfreq_noise_limit"] == va.LOWNOISE_LIMIT == 20.0
    assert va.rule_verdict(base(lowfreq_noise_rms=va.LOWNOISE_LIMIT)) == "정상"
    assert va.rule_verdict(base(lowfreq_noise_rms=va.LOWNOISE_LIMIT + 0.01)) == "재계측 권장"


# ---------- 이력 ----------
def test_list_and_detail(client):
    assert client.get("/api/runs").json() == {"runs": []}
    post_run(client, all_demo())
    post_run(client, [demo_bytes("CH2")], rpm=["1800"], balls=["1"])
    runs = client.get("/api/runs").json()["runs"]
    assert [r["id"] for r in runs] == [2, 1]                     # 최신순
    assert runs[1]["channel_count"] == 5 and runs[0]["channel_count"] == 1
    assert {v["channel"]: v["verdict"] for v in runs[1]["verdicts"]} == EXPECTED
    detail = client.get("/api/runs/1").json()
    assert detail["thresholds"] == analysis.thresholds()
    assert [c["channel"] for c in detail["channels"]] == CHANNELS
    assert client.get("/api/runs/99").status_code == 404
    assert "error" in client.get("/api/runs/99").json()


def test_no_update_or_delete_paths(client):
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)("/api/runs").status_code == 405
        assert getattr(client, method)("/api/runs/1").status_code == 405
    for cls in (MemoryStore, PgStore):
        assert not [n for n in dir(cls) if n.startswith(("update", "delete", "remove", "drop"))]


# ---------- 화면 ----------
def test_screens_escape_server_values():
    """서버에서 온 값을 innerHTML에 넣기 전에 esc()를 거친다 (XSS 방어)"""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "vibe_web" / "static" / "shared.js").read_text(encoding="utf-8")
    assert "function esc(" in js
    for expr in ("${r.channel}", "${r.rpm}", "${c.sha256}", "${v}"):
        assert expr not in js, f"이스케이프 없이 삽입: {expr}"


def test_pages(client):
    upload = client.get("/upload")
    assert upload.status_code == 200 and "가상 데이터만 올리세요" in upload.text
    assert client.get("/runs").status_code == 200
    assert client.get("/runs/5").status_code == 200
    css = client.get("/assets/shared.css")
    js = client.get("/assets/shared.js")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
