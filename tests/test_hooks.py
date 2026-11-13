"""시연용 훅(.claude/hooks) 동작 테스트"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load("guard_demo")
sync = _load("check_rules_sync")
FAKE_KEY = "sk-ant-" + "x" * 12


# ---------- guard_demo: API 키 노출 ----------
@pytest.mark.parametrize("cmd", [
    "echo $ANTHROPIC_API_KEY",
    "printenv ANTHROPIC_API_KEY",
    "printenv",
    "env",
    "env | grep KEY",
    "set",
    'python -c "import os; print(os.environ[\'ANTHROPIC_API_KEY\'])"',
    "Write-Host $env:ANTHROPIC_API_KEY",
    f"export ANTHROPIC_API_KEY={FAKE_KEY}",
])
def test_key_exposure_blocked(cmd):
    assert guard.evaluate("Bash", {"command": cmd})


@pytest.mark.parametrize("cmd", [
    "uv run python vibe_agent.py --offline",
    "uv run pytest -q",
    "uv run python vibe_agent.py --ui 2>/dev/null",
    "git status",
])
def test_normal_commands_allowed(cmd):
    assert guard.evaluate("Bash", {"command": cmd}) is None


def test_key_literal_in_file_blocked():
    assert guard.evaluate("Write", {"file_path": "notes.txt", "content": f"key={FAKE_KEY}"})
    assert guard.evaluate("Edit", {"file_path": "a.py", "new_string": FAKE_KEY})


# ---------- guard_demo: 결과 파일 덮어쓰기 ----------
@pytest.mark.parametrize("cmd", [
    "rm result-1.xlsx",
    "mv result-1.png old.png",
    "cp backup.xlsx result-2.xlsx",
    "echo x > result-3.png",
])
def test_result_overwrite_commands_blocked(cmd):
    assert guard.evaluate("Bash", {"command": cmd})


@pytest.mark.parametrize("cmd", ["ls result-1.xlsx", "cp result-1.xlsx backup.xlsx", "git status result-1.png"])
def test_result_read_commands_allowed(cmd):
    assert guard.evaluate("Bash", {"command": cmd}) is None


def test_existing_result_file_write_blocked_new_allowed(tmp_path):
    existing = tmp_path / "result-1.xlsx"
    existing.write_text("x")
    assert guard.evaluate("Write", {"file_path": str(existing), "content": "y"})
    assert guard.evaluate("Write", {"file_path": str(tmp_path / "result-2.xlsx"), "content": "y"}) is None


# ---------- check_rules_sync ----------
SRC = '''RMS_LIMIT = 4.5
LOWNOISE_LIMIT = 20.0
RULES = f"""판정 규칙:
0) 저주파 {LOWNOISE_LIMIT:g}
1) bearing 성분이 1X 대비 0.7 이상
3) ratio_2X_over_1X >= 0.5
4) (2X/1X < 0.5)"""


def rule_verdict(r):
    over = r["peak_rms_mm_s"] > r["rms_limit_mm_s"]
    if over:
        return "정렬" if r["ratio_2X_over_1X"] >= 0.5 else "발란싱"
    return "베어링" if r["ratio_bearing_over_1X"] >= 0.7 else "정상"
'''
TESTS = "4.5 20.0 0.5 0.7"


def test_sync_ok():
    assert sync.check(SRC, TESTS, SRC, TESTS) == []


def test_sync_rules_text_mismatch():
    bad = SRC.replace("대비 0.7 이상", "대비 0.8 이상")
    assert any("RULES" in m for m in sync.check(bad, TESTS))


def test_sync_only_code_changed_vs_head():
    changed = SRC.replace('"ratio_2X_over_1X"] >= 0.5', '"ratio_2X_over_1X"] >= 0.6')
    msgs = sync.check(changed, TESTS, SRC, TESTS)
    assert any("RULES" in m for m in msgs)


def test_sync_threshold_changed_without_tests():
    new = SRC.replace("RMS_LIMIT = 4.5", "RMS_LIMIT = 5.0")
    msgs = sync.check(new, TESTS, SRC, TESTS)
    assert any("tests/" in m for m in msgs)
    assert sync.check(new, TESTS + " 5.0", SRC, TESTS) == []


def test_current_repo_values_match_rules():
    """실제 vibe_agent.py의 rule_verdict와 RULES 숫자가 일치"""
    src = (ROOT / "vibe_agent.py").read_text(encoding="utf-8")
    tests_text = (ROOT / "tests" / "test_vibe_agent.py").read_text(encoding="utf-8")
    assert sync.check(src, tests_text) == []
    assert re.search(r"RULES", src)


# ---------- 사람 검수 승인 파일 (review-N.json) ----------
@pytest.mark.parametrize("cmd", [
    "python approve.py result-3",
    "uv run python approve.py result-3",
    "echo '{}' > review-3.json",
    "rm review-1.json",
    "mv review-1.json x.json",
    "cp fake.json review-4.json",
])
def test_review_forgery_commands_blocked(cmd):
    assert guard.evaluate("Bash", {"command": cmd})


@pytest.mark.parametrize("cmd", [
    "python approve.py result-3 --check",
    "cat review-1.json",
    "git commit -m 'approve 반영'",
    "git add approve.py tests/test_approve.py",
])
def test_review_read_commands_allowed(cmd):
    assert guard.evaluate("Bash", {"command": cmd}) is None


def test_review_file_write_blocked():
    assert guard.evaluate("Write", {"file_path": "review-3.json", "content": "{}"})
    assert guard.evaluate("Edit", {"file_path": "review-1.json", "new_string": "x"})
