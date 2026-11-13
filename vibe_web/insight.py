"""이력 상세에 보여 줄 판정 근거와 인사이트 문구.

판정은 다시 계산하지 않는다. 판정(`verdict`)은 저장된 값(vibe_agent.rule_verdict 결과)을 그대로 쓰고,
여기서는 저장된 분석 값(analyze_signal)과 저장 당시 기준값으로 근거 수치와 해석 문구를 만든다.
문구는 저장된 값에서 요청할 때마다 만들어지며 DB에 저장하지 않는다.
"""

NOTE = "규칙 기반 추정입니다. 원인은 현장 점검으로 확정하세요."
ACTION_VERDICTS = ("발란싱 요망", "정렬 요망")


def _n(x, digits: int = 2) -> str:
    return f"{float(x):.{digits}f}"


def _ratio(a, b) -> float | None:
    """a/b, b가 0이면 None (표시용)"""
    return None if not b else float(a) / float(b)


def _times(a, b) -> str:
    q = _ratio(a, b)
    return "해당 없음" if q is None else f"{q:.1f}배"


def _peak_location(r: dict) -> str:
    peak = r["peak_freq_hz"]
    f1 = r["shaft_1X_hz"]
    if peak < 2.0:
        return "2 Hz 미만 저주파 영역"
    for name, hz in (("1X", f1), ("2X", 2 * f1), ("BPFO", r.get("bearing_BPFO_hz"))):
        if hz and abs(peak - hz) <= 0.03 * hz:
            return name
    return "1X, 2X, BPFO와 겹치지 않는 주파수"


def basis(r: dict, verdict: str, t: dict) -> list[str]:
    """판정 근거: 값과 기준의 비교, 어느 규칙에 해당했는지"""
    over = r["peak_rms_mm_s"] > r["rms_limit_mm_s"]
    lines = [
        f"최대 피크 RMS {_n(r['peak_rms_mm_s'])} mm/s({_n(r['peak_freq_hz'], 1)} Hz)를 기준 "
        f"{_n(r['rms_limit_mm_s'], 1)} mm/s와 비교: {'기준 초과' if over else '기준 이하'}",
        f"1X {_n(r['shaft_1X_hz'], 1)} Hz: {_n(r['rms_1X'])} mm/s, "
        f"2X {_n(2 * r['shaft_1X_hz'], 1)} Hz: {_n(r['rms_2X'])} mm/s, "
        f"2X/1X {_n(r['ratio_2X_over_1X'])} (기준 {t['ratio_2x_over_1x']})",
    ]
    if r["bearing_BPFO_hz"] is None:
        lines.append("볼 개수가 1이라 베어링 주파수를 쓰지 않으며 베어링 판정을 하지 않음")
    else:
        lines.append(
            f"BPFO {_n(r['bearing_BPFO_hz'], 1)} Hz: {_n(r['rms_bearing_BPFO'])} mm/s, "
            f"베어링/1X {_n(r['ratio_bearing_over_1X'])} (기준 {t['ratio_bearing_over_1x']})")
    lines.append(f"2 Hz 미만 저주파 노이즈 {_n(r['lowfreq_noise_rms'])} mm/s (기준 {t['lowfreq_noise_limit']} mm/s)")
    decided = {
        "재계측 권장": "저주파 노이즈가 기준을 넘어 1X와 2X가 가려지므로 다른 규칙은 적용하지 않음 (규칙 0)",
        "베어링 점검 요망": f"최대 피크 RMS가 기준 이하이고 베어링/1X가 {t['ratio_bearing_over_1x']} 이상 (규칙 1)",
        "정상": "최대 피크 RMS가 기준 이하이고 이상 징후가 없음 (규칙 2)",
        "정렬 요망": f"최대 피크 RMS가 기준 초과이고 2X/1X가 {t['ratio_2x_over_1x']} 이상 (규칙 3)",
        "발란싱 요망": f"최대 피크 RMS가 기준 초과이고 2X/1X가 {t['ratio_2x_over_1x']} 미만이라 1X가 지배적 (규칙 4)",
    }
    lines.append("판정: " + decided.get(verdict, f"{verdict} (규칙 설명 없음)"))
    return lines


def graph_notes(r: dict) -> list[str]:
    """그래프 읽기: 세로줄과 피크가 무엇을 뜻하는지"""
    marks = f"1X {_n(r['shaft_1X_hz'], 1)} Hz, 2X {_n(2 * r['shaft_1X_hz'], 1)} Hz"
    if r["bearing_BPFO_hz"] is not None:
        marks += f", BPFO {_n(r['bearing_BPFO_hz'], 1)} Hz"
    return [
        f"세로줄은 {marks}이고, 점선 가로줄은 기준 {_n(r['rms_limit_mm_s'], 1)} mm/s입니다",
        f"가장 큰 피크는 {_n(r['peak_freq_hz'], 1)} Hz({_peak_location(r)})에 {_n(r['peak_rms_mm_s'])} mm/s로 있습니다",
    ]


def meaning_and_action(r: dict, verdict: str, t: dict) -> dict:
    limit = r["rms_limit_mm_s"]
    peak = r["peak_rms_mm_s"]
    times_limit = _times(peak, limit)
    if verdict == "재계측 권장":
        return {
            "meaning": (f"2 Hz 미만 저주파 성분이 {_n(r['lowfreq_noise_rms'])} mm/s로 1X({_n(r['rms_1X'])} mm/s)의 "
                        f"{_times(r['lowfreq_noise_rms'], r['rms_1X'])}라 1X와 2X로 판단하기 어렵습니다. "
                        "센서 부착 상태, 케이블, 신호 드리프트를 먼저 의심합니다."),
            "action": "센서 고정과 케이블을 확인하고 다시 계측하세요. 재계측 전에는 이 채널의 판정을 근거로 쓰지 마세요.",
        }
    if verdict == "정상":
        pct = _ratio(peak, limit)
        bearing = ("" if r["bearing_BPFO_hz"] is None else
                   f" 베어링 성분도 1X의 {_n(r['ratio_bearing_over_1X'])}배로 기준({t['ratio_bearing_over_1x']}) 미만입니다.")
        return {
            "meaning": f"최대 피크 {_n(peak)} mm/s는 기준의 {'-' if pct is None else f'{pct * 100:.0f}%'}입니다.{bearing}",
            "action": "정기 점검 주기대로 같은 조건의 계측을 이어 추세를 확인하세요.",
        }
    if verdict == "베어링 점검 요망":
        return {
            "meaning": (f"전체 진동은 기준 이하지만 BPFO {_n(r['bearing_BPFO_hz'], 1)} Hz 성분이 1X의 "
                        f"{_n(r['ratio_bearing_over_1X'])}배입니다. 베어링 외륜 결함의 초기 징후일 수 있습니다."),
            "action": "윤활 상태, 소음, 온도를 점검하고 같은 조건으로 다시 계측해 BPFO 성분이 커지는지 추세를 보세요.",
        }
    if verdict == "발란싱 요망":
        return {
            "meaning": (f"최대 피크 {_n(peak)} mm/s는 기준의 {times_limit}이고 1X가 지배적(2X/1X "
                        f"{_n(r['ratio_2X_over_1X'])})입니다. 회전체 불평형일 가능성이 있습니다."),
            "action": "현장 발란싱을 한 뒤 다시 계측해 1X 성분이 기준 이하로 내려갔는지 확인하세요.",
        }
    if verdict == "정렬 요망":
        return {
            "meaning": (f"최대 피크 {_n(peak)} mm/s는 기준의 {times_limit}이고 2X가 1X의 "
                        f"{_n(r['ratio_2X_over_1X'])}배입니다. 축 정렬(커플링) 불량일 가능성이 있습니다."),
            "action": "커플링 정렬 상태를 점검하고 조정한 뒤 다시 계측해 2X 성분이 줄었는지 확인하세요.",
        }
    return {"meaning": f"{verdict}", "action": "규칙 설명이 없는 판정입니다. 판정 규칙을 확인하세요."}


def channel_insight(c: dict, t: dict) -> dict:
    return {"basis": basis(c["r"], c["verdict"], t),
            "graph": graph_notes(c["r"]),
            **meaning_and_action(c["r"], c["verdict"], t)}


def summary(channels: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for c in channels:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    order = ("정상", "재계측 권장", "베어링 점검 요망", "발란싱 요망", "정렬 요망")
    parts = [f"{v} {counts[v]}" for v in order if v in counts]
    headline = f"{len(channels)}채널 중 " + ", ".join(parts)

    def over_limit(c):
        q = _ratio(c["r"]["peak_rms_mm_s"], c["r"]["rms_limit_mm_s"])
        return q if q is not None else 0.0

    urgent = sorted((c for c in channels if c["verdict"] in ACTION_VERDICTS), key=over_limit, reverse=True)
    priorities = [f"{c['channel']} {c['verdict']}: 최대 피크가 기준의 {_times(c['r']['peak_rms_mm_s'], c['r']['rms_limit_mm_s'])}"
                  for c in urgent]
    priorities += [f"{c['channel']} {c['verdict']}" for c in channels
                   if c["verdict"] in ("베어링 점검 요망", "재계측 권장")]
    return {"headline": headline, "priorities": priorities, "note": NOTE}


def attach(run: dict) -> dict:
    """저장된 실행 상세에 근거·인사이트와 요약을 붙인다 (저장된 값은 바꾸지 않는다)"""
    for c in run["channels"]:
        c["insight"] = channel_insight(c, run["thresholds"])
    run["summary"] = summary(run["channels"])
    return run
