import pytest
from vibe_agent import (BALLS, RPM, SIGNALS, analyze_signal, bpfo_hz, detect_rpm, draw_spectrum,
                        rpm_mismatch, rule_verdict)

EXPECTED = {
    "CH1": "정상",
    "CH2": "베어링 점검 요망",
    "CH3": "발란싱 요망",
    "CH4": "정렬 요망",
}


@pytest.mark.parametrize("ch,expected", EXPECTED.items())
def test_verdict(ch, expected):
    assert rule_verdict(analyze_signal(ch)) == expected


def test_four_channels():
    assert set(SIGNALS) == set(EXPECTED)


def test_normal_below_limit():
    r = analyze_signal("CH1")
    assert r["peak_rms_mm_s"] < r["rms_limit_mm_s"]


def test_bearing_below_limit_but_high_bearing_peak():
    r = analyze_signal("CH2")
    assert r["peak_rms_mm_s"] < r["rms_limit_mm_s"]
    assert r["ratio_bearing_over_1X"] >= 0.7


@pytest.mark.parametrize("ratio,expected", [(0.69, "정상"), (0.7, "베어링 점검 요망")])
def test_bearing_ratio_threshold_is_0_7(ratio, expected):
    r = {"peak_rms_mm_s": 1.0, "rms_limit_mm_s": 4.5,
         "ratio_2X_over_1X": 0.0, "ratio_bearing_over_1X": ratio}
    assert rule_verdict(r) == expected


@pytest.mark.parametrize("ch", ["CH3", "CH4"])
def test_peak_rms_over_limit(ch):
    r = analyze_signal(ch)
    assert r["peak_rms_mm_s"] > r["rms_limit_mm_s"]


def test_each_channel_has_different_rpm():
    rpms = {ch: analyze_signal(ch)["rpm"] for ch in EXPECTED}
    assert len(set(rpms.values())) == len(EXPECTED)


@pytest.mark.parametrize("ch", EXPECTED)
def test_peak_is_at_channel_1x(ch):
    # 장비마다 회전수가 달라도, 최대 피크는 그 채널의 1X 주파수(rpm/60)에 있어야 함
    r = analyze_signal(ch)
    assert r["shaft_1X_hz"] == pytest.approx(r["rpm"] / 60, abs=0.01)
    assert r["peak_freq_hz"] == pytest.approx(r["shaft_1X_hz"], abs=1.0)


def test_bpfo_approx_formula():
    # 외륜 주파수 = (회전주파수 / 2) x 0.8 x 볼 개수
    assert bpfo_hz(1800, 9) == pytest.approx(30 / 2 * 0.8 * 9)   # 108 Hz
    assert bpfo_hz(1500, 9) == pytest.approx(90.0)


def test_default_balls():
    assert BALLS == {"CH1": 1, "CH2": 9, "CH3": 1, "CH4": 1}
    r = analyze_signal("CH2")
    assert r["bearing_balls"] == 9 and r["bearing_BPFO_hz"] == pytest.approx(90.0)


@pytest.mark.parametrize("ch", ["CH1", "CH3", "CH4"])
def test_no_bearing_channels_skip_bearing(ch):
    r = analyze_signal(ch)
    assert r["bearing_BPFO_hz"] is None and r["rms_bearing_BPFO"] is None
    assert r["ratio_bearing_over_1X"] == 0.0
    assert rule_verdict(r) != "베어링 점검 요망"


def _axes(ch, balls):
    from matplotlib.figure import Figure
    ax = Figure().add_subplot(111)
    draw_spectrum(ax, SIGNALS[ch], "t", RPM[ch], balls)
    return ax


@pytest.mark.parametrize("ch", ["CH1", "CH2", "CH3", "CH4"])
def test_bearing_lines_shown_for_any_ball_count_except_1(ch):
    # 볼 개수가 1이 아니면 해당 위치에 피크가 없어도 (기본값과 달라도) 세로줄과 범례를 표시
    for balls in (2, 9, 12):
        labels = [t.get_text() for t in _axes(ch, balls).get_legend().get_texts()]
        assert any(s.startswith("BPFO") for s in labels)
        assert any(s.startswith("2×BPFO") for s in labels)
    labels = [t.get_text() for t in _axes(ch, 1).get_legend().get_texts()]
    assert not any("BPFO" in s for s in labels)


def test_legend_shows_bpfo_frequency():
    labels = [t.get_text() for t in _axes("CH2", 9).get_legend().get_texts()]
    assert "BPFO 90.0 Hz" in labels and "2×BPFO 180.0 Hz" in labels
    assert "1X 25.0 Hz" in labels and "2X 50.0 Hz" in labels


def _vlines(balls):
    return len(_axes("CH2", balls).lines) - 2   # 곡선 1 + 허용기준 가로선 1 제외 = 1X/2X/BPFO/2xBPFO 세로줄


def test_bearing_lines_removed_without_bearing():
    assert _vlines(balls=9) == 4   # 1X, 2X, BPFO, 2xBPFO
    assert _vlines(balls=1) == 2   # 1X, 2X 만


@pytest.mark.parametrize("ch", EXPECTED)
def test_detect_rpm_from_signal(ch):
    assert detect_rpm(SIGNALS[ch]) == pytest.approx(RPM[ch], rel=0.01)
    assert rpm_mismatch(SIGNALS[ch], detect_rpm(SIGNALS[ch])) is None


@pytest.mark.parametrize("ch", EXPECTED)
def test_rpm_matches_signal(ch):
    assert rpm_mismatch(SIGNALS[ch], RPM[ch]) is None
    assert rpm_mismatch(SIGNALS[ch], RPM[ch] * 1.02) is None   # 2% 오차는 허용


@pytest.mark.parametrize("ch", EXPECTED)
def test_wrong_rpm_detected(ch):
    mm = rpm_mismatch(SIGNALS[ch], RPM[ch] * 1.5)
    assert mm is not None
    assert mm[1] == pytest.approx(RPM[ch] / 60, abs=1.0)   # 실제 최대 피크는 진짜 1X


def test_rpm_mismatch_low_rpm_does_not_crash():
    assert rpm_mismatch(SIGNALS["CH1"], 30) is not None   # 0.5 Hz: 탐색 구간이 빈 경우


def test_spectrum_is_rms_not_peak():
    # CH1은 1X peak 진폭 2.0 mm/s -> RMS 약 1.41, 최대 피크는 1X 성분
    r = analyze_signal("CH1")
    assert r["rms_1X"] == pytest.approx(2.0 / 2 ** 0.5, abs=0.02)
    assert r["peak_rms_mm_s"] == r["rms_1X"]
    assert r["peak_freq_hz"] == pytest.approx(30.0, abs=1.0)


def test_misalignment_has_high_2x():
    assert analyze_signal("CH4")["ratio_2X_over_1X"] >= 0.5
