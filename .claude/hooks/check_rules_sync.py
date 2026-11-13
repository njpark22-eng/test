"""PostToolUse hook: 판정 규칙 동기화 검사 (vibe_agent.py 또는 tests/ 수정 후 실행).

CLAUDE.md 규칙을 자동으로 강제한다.
 1) rule_verdict의 기준값과 RULES 문자열의 숫자가 같은지
 2) 기준값(RMS_LIMIT, LOWNOISE_LIMIT, 2X/1X, 베어링/1X)이 tests/에 들어 있는지
 3) 커밋(HEAD) 대비 rule_verdict만 또는 RULES만 바뀌지 않았는지
 4) 커밋(HEAD) 대비 기준값이 바뀌었는데 tests/가 그대로가 아닌지
불일치가 있으면 종료 코드 2 + stderr (수정을 막지는 않고 Claude에게 고치도록 알림).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _num(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return float(m.group(1)) if m else None


def extract(src):
    rules = (re.search(r'RULES = f?"""(.*?)"""', src, re.S) or [None, ""])[1]
    m = re.search(r"def rule_verdict\(r\):(.*?)(?=\n\S|\Z)", src, re.S)
    body = m.group(1) if m else ""
    return {
        "rules": rules,
        "body": body,
        "rms": _num(r"^RMS_LIMIT\s*=\s*([\d.]+)", src, re.M),
        "low": _num(r"^LOWNOISE_LIMIT\s*=\s*([\d.]+)", src, re.M),
        "a2": _num(r'ratio_2X_over_1X"\]\s*>=\s*([\d.]+)', body),
        "bearing": _num(r'ratio_bearing_over_1X"\]\s*>=\s*([\d.]+)', body),
        "rules_a2": _num(r"ratio_2X_over_1X\s*>=\s*([\d.]+)", rules),
        "rules_a2_lt": _num(r"2X/1X\s*<\s*([\d.]+)", rules),
        "rules_bearing": _num(r"대비\s*([\d.]+)\s*이상", rules),
    }


def _norm(s):
    return re.sub(r"\s+", "", s)


def check(src, tests_text, head_src=None, head_tests=None):
    """불일치 메시지 목록을 반환 (없으면 빈 리스트)"""
    cur, msgs = extract(src), []
    if cur["a2"] != cur["rules_a2"] or cur["a2"] != cur["rules_a2_lt"]:
        msgs.append(f"rule_verdict의 2X/1X 기준({cur['a2']})과 RULES 문자열({cur['rules_a2']}, {cur['rules_a2_lt']})이 다름")
    if cur["bearing"] != cur["rules_bearing"]:
        msgs.append(f"rule_verdict의 베어링/1X 기준({cur['bearing']})과 RULES 문자열({cur['rules_bearing']})이 다름")
    wants = {"RMS_LIMIT": f"{cur['rms']:g}" if cur["rms"] is not None else None,
             "LOWNOISE_LIMIT": f"{cur['low']:.1f}" if cur["low"] is not None else None,
             "2X/1X": f"{cur['a2']:g}" if cur["a2"] is not None else None,
             "베어링/1X": f"{cur['bearing']:g}" if cur["bearing"] is not None else None}
    for name, text in wants.items():
        if text and text not in tests_text:
            msgs.append(f"기준값 {name}={text}이 tests/에 없음 (기준값을 바꾸면 tests/도 같이 수정)")
    if head_src is not None:
        old = extract(head_src)
        if (_norm(cur["body"]) != _norm(old["body"])) != (_norm(cur["rules"]) != _norm(old["rules"])):
            msgs.append("rule_verdict와 RULES 중 한쪽만 수정됨 (항상 같이 수정)")
        changed = [k for k in ("rms", "low", "a2", "bearing") if cur[k] != old[k]]
        if changed and head_tests is not None and _norm(tests_text) == _norm(head_tests):
            msgs.append(f"기준값({', '.join(changed)})이 바뀌었는데 tests/가 그대로임")
    return msgs


def _git_show(path):
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    path = (data.get("tool_input") or {}).get("file_path", "").replace("\\", "/")
    if not (path.endswith("vibe_agent.py") or "/tests/" in path):
        return
    src = (ROOT / "vibe_agent.py").read_text(encoding="utf-8")
    tests_text = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "tests").glob("test_vibe_agent*.py")))
    head_tests = "\n".join(filter(None, [_git_show("tests/test_vibe_agent.py")])) or None
    msgs = check(src, tests_text, _git_show("vibe_agent.py"), head_tests)
    if msgs:
        print("판정 규칙 동기화 필요:\n- " + "\n- ".join(msgs), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
