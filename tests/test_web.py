"""웹 데모(api/index.py) 테스트. 입력 엑셀은 읽기만 하고 수정하지 않는다."""
import pytest
from fastapi.testclient import TestClient

import vibe_agent as va
from api.index import app

EXPECTED = {
    "CH1": "재계측 권장",
    "CH2": "정상",
    "CH3": "베어링 점검 요망",
    "CH4": "발란싱 요망",
    "CH5": "정렬 요망",
}


@pytest.fixture
def client():
    return TestClient(app)


# ---------- US1: 5채널 판정 ----------
def test_analyze_returns_expected_verdicts(client):
    res = client.get("/api/analyze")
    assert res.status_code == 200
    body = res.json()
    assert len(body["channels"]) == 5
    got = {c["r"]["channel"]: c["verdict"] for c in body["channels"]}
    assert got == EXPECTED
    assert body["rules"] == va.RULES


def test_analyze_values_come_from_vibe_agent(client):
    """화면 숫자는 analyze_signal 결과 그대로여야 한다 (웹에서 다시 계산하지 않음)"""
    for c in client.get("/api/analyze").json()["channels"]:
        assert c["r"] == va.analyze_signal(c["r"]["channel"])
        assert c["verdict"] == va.rule_verdict(c["r"])


def test_root_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "규칙 기반 판정" in res.text


def test_analyze_without_data_returns_error(client, monkeypatch):
    monkeypatch.setattr(va, "SIGNALS", {})
    res = client.get("/api/analyze")
    assert res.status_code == 500
    assert "CH1~CH5" in res.json()["error"]


def test_write_methods_not_allowed(client):
    assert client.post("/api/analyze").status_code == 405
    assert client.put("/api/analyze").status_code == 405
    assert client.delete("/api/analyze").status_code == 405


# ---------- US2: 스펙트럼 ----------
def test_spectrum_arrays_and_bpfo(client):
    channels = client.get("/api/analyze").json()["channels"]
    for c in channels:
        assert len(c["f"]) == len(c["amp"]) > 0
        assert max(c["f"]) <= 600
    bpfo = {c["r"]["channel"]: c["r"]["bearing_BPFO_hz"] for c in channels}
    assert bpfo["CH3"] == 90.0          # 1500rpm: 25Hz/2 x 0.8 x 9
    assert all(v is None for ch, v in bpfo.items() if ch != "CH3")


# ---------- 화면의 판정 이름이 rule_verdict와 어긋나지 않는지 ----------
def test_page_knows_every_verdict_name():
    """page.html의 판정 색 분류가 쓰는 판정 문자열이 rule_verdict 반환값과 같아야 한다"""
    page = (va.Path(__file__).resolve().parent.parent / "api" / "page.html").read_text(encoding="utf-8")
    for name in ("정상", "재계측 권장", "베어링 점검 요망"):   # 초록/주황으로 따로 분류하는 판정
        assert f'"{name}"' in page
    # 나머지(발란싱 요망, 정렬 요망)는 빨강 기본값이므로 판정 이름 집합이 5개로 유지되는지 확인
    assert set(EXPECTED.values()) == {"재계측 권장", "정상", "베어링 점검 요망", "발란싱 요망", "정렬 요망"}


# ---------- 읽기 전용 확인 ----------
def test_analyze_does_not_modify_input_files(client):
    files = sorted(va.DATA_DIR.glob("CH*.xlsx"))
    before = [(f.stat().st_mtime_ns, f.stat().st_size) for f in files]
    client.get("/api/analyze")
    after = [(f.stat().st_mtime_ns, f.stat().st_size) for f in files]
    assert before == after
