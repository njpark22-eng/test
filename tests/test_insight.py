"""이력 상세의 판정 근거와 인사이트 문구 테스트. 판정은 다시 계산하지 않고 저장된 값을 설명만 한다."""
import copy

import pytest
from fastapi.testclient import TestClient

import vibe_agent as va
from vibe_web import analysis, insight
from vibe_web.main import app, get_store
from vibe_web.store import MemoryStore

EXPECTED = {"CH1": "재계측 권장", "CH2": "정상", "CH3": "베어링 점검 요망",
            "CH4": "발란싱 요망", "CH5": "정렬 요망"}


@pytest.fixture
def run():
    store = MemoryStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    files = [("files", (f"{c}.xlsx", (va.DATA_DIR / f"{c}.xlsx").read_bytes(), "x")) for c in EXPECTED]
    res = client.post("/api/runs", files=files, data={
        "rpm": [str(va.DEFAULT_RPM[c]) for c in EXPECTED], "balls": [str(va.DEFAULT_BALLS[c]) for c in EXPECTED]})
    assert res.status_code == 201
    yield client.get(f"/api/runs/{res.json()['id']}").json()
    app.dependency_overrides.clear()


def test_every_channel_has_basis_graph_notes_meaning_and_action(run):
    for c in run["channels"]:
        i = c["insight"]
        assert len(i["basis"]) == 5 and i["graph"] and i["meaning"] and i["action"]
        assert str(round(c["r"]["peak_rms_mm_s"], 2)) in i["basis"][0]        # 근거에 실제 수치가 들어간다


def test_basis_names_the_rule_that_decided_each_verdict(run):
    rule = {"CH1": "규칙 0", "CH2": "규칙 2", "CH3": "규칙 1", "CH4": "규칙 4", "CH5": "규칙 3"}
    for c in run["channels"]:
        assert rule[c["channel"]] in c["insight"]["basis"][-1]
        assert c["verdict"] == EXPECTED[c["channel"]]          # 판정은 저장된 값 그대로


def test_basis_uses_stored_thresholds_not_hardcoded_numbers(run):
    r = run["channels"][3]["r"]
    t = dict(run["thresholds"], ratio_2x_over_1x=0.9)          # 저장 당시 기준값이 다르다고 가정
    assert "(기준 0.9)" in insight.basis(r, "발란싱 요망", t)[1]
    assert "0.9 미만" in insight.basis(r, "발란싱 요망", t)[-1]


def test_channel_specific_insights(run):
    by = {c["channel"]: c["insight"] for c in run["channels"]}
    assert "저주파" in by["CH1"]["meaning"] and "다시 계측" in by["CH1"]["action"]
    assert "90.0 Hz" in by["CH3"]["meaning"] and "BPFO" in by["CH3"]["graph"][0]
    assert "BPFO" not in by["CH4"]["graph"][0]                 # 볼 개수 1 채널은 BPFO를 말하지 않는다
    assert "불평형" in by["CH4"]["meaning"] and "발란싱" in by["CH4"]["action"]
    assert "정렬" in by["CH5"]["meaning"] and "커플링" in by["CH5"]["action"]
    assert "이상 징후가 없" in by["CH2"]["basis"][-1] and "이상 징후" not in by["CH4"]["basis"][-1]


def test_graph_notes_locate_the_peak(run):
    by = {c["channel"]: c["insight"]["graph"][1] for c in run["channels"]}
    assert "저주파 영역" in by["CH1"]
    assert "(1X)" in by["CH2"] and "(1X)" in by["CH4"] and "(1X)" in by["CH5"]


def test_summary_counts_and_priorities(run):
    s = run["summary"]
    assert s["headline"] == "5채널 중 정상 1, 재계측 권장 1, 베어링 점검 요망 1, 발란싱 요망 1, 정렬 요망 1"
    assert s["priorities"][0].startswith("CH4 발란싱 요망") and s["priorities"][1].startswith("CH5 정렬 요망")
    assert any(p.startswith("CH3") for p in s["priorities"]) and any(p.startswith("CH1") for p in s["priorities"])
    assert "현장 점검" in s["note"]


def test_no_division_by_zero_on_empty_signal():
    c = {"channel": "CH1", "verdict": "정상", "r": {
        "channel": "CH1", "rpm": 1800, "shaft_1X_hz": 30.0, "bearing_balls": 1, "bearing_BPFO_hz": None,
        "lowfreq_noise_rms": 0.0, "peak_rms_mm_s": 0.0, "peak_freq_hz": 0.0, "rms_limit_mm_s": 4.5,
        "rms_1X": 0.0, "rms_2X": 0.0, "rms_bearing_BPFO": None, "ratio_2X_over_1X": 0.0,
        "ratio_bearing_over_1X": 0.0}}
    out = insight.channel_insight(copy.deepcopy(c), analysis.thresholds())
    assert out["meaning"] and out["basis"]
    low = copy.deepcopy(c)
    low["verdict"] = "재계측 권장"
    low["r"]["lowfreq_noise_rms"] = 50.0
    assert "해당 없음" in insight.channel_insight(low, analysis.thresholds())["meaning"]   # 1X가 0이어도 오류 없음


def test_unknown_verdict_does_not_crash(run):
    out = insight.channel_insight({"channel": "CH1", "verdict": "새 판정", "r": run["channels"][0]["r"]},
                                  run["thresholds"])
    assert "규칙 설명 없음" in out["basis"][-1]


def test_insight_is_not_stored(run):
    store = app.dependency_overrides[get_store]()
    assert "insight" not in str(store.runs[0]["channels"][0].keys())
    assert "summary" not in store.runs[0]


def test_history_screen_shows_insight_sections():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "vibe_web" / "static"
    js = (root / "shared.js").read_text(encoding="utf-8")
    for heading in ("판정 근거", "인사이트", "그래프 읽기"):
        assert heading in js
    assert "summaryHtml(run.summary)" in (root / "runs.html").read_text(encoding="utf-8")
