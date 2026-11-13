"""approve.py: 사람 검수 승인 파일 생성/검증 테스트"""
import importlib.util
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("approve", ROOT / "approve.py")
approve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approve)


@pytest.fixture
def folder(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["채널", "판정"])
    ws.append(["CH1", "발란싱"])
    ws.append(["CH2", "정상"])
    wb.save(tmp_path / "result-3.xlsx")
    (tmp_path / "result-3.png").write_bytes(b"png")
    return tmp_path


def test_check_fails_without_review(folder):
    assert approve.check("result-3", folder)


def test_write_and_check_ok(folder):
    out, rec = approve.write_review("result-3", folder, {"CH1": "발란싱", "CH2": "정상"}, "tester")
    assert out.name == "review-3.json"
    assert rec["mismatches"] == {}
    assert approve.check("result-3", folder) == []


def test_mismatch_recorded(folder):
    _, rec = approve.write_review("result-3", folder, {"CH1": "정렬", "CH2": "정상"}, "tester")
    assert rec["mismatches"] == {"CH1": {"human": "정렬", "agent": "발란싱"}}


def test_result_changed_after_approval_detected(folder):
    approve.write_review("result-3", folder, {"CH1": "발란싱", "CH2": "정상"}, "tester")
    (folder / "result-3.png").write_bytes(b"changed")
    assert any("변경" in p for p in approve.check("result-3", folder))


def test_no_overwrite(folder):
    approve.write_review("result-3", folder, {"CH1": "a", "CH2": "b"}, "tester")
    with pytest.raises(FileExistsError):
        approve.write_review("result-3", folder, {"CH1": "a", "CH2": "b"}, "tester")


def test_missing_result_file(folder):
    (folder / "result-3.png").unlink()
    with pytest.raises(FileNotFoundError):
        approve.write_review("result-3", folder, {}, "tester")


def test_bad_name():
    with pytest.raises(ValueError):
        approve.review_path("foo")
