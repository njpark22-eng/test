"""사람 검수 승인 파일(review-N.json) 생성/확인.

사용:
  python approve.py result-3          # 사람이 직접 실행: 채널별 판정을 직접 입력하고 승인
  python approve.py result-3 --check  # 승인 파일이 있고 결과 파일이 그대로인지 확인 (종료 코드 0/1)

에이전트가 실행하면 의미가 없으므로 Claude Code에서는 `! python approve.py result-3`처럼
사람이 직접 실행한다 (.claude/hooks/guard_demo.py와 settings.json deny 규칙이 에이전트 실행을 차단).
결과 파일(result-N.xlsx/png)은 읽기만 하고, review-N.json은 새로 만들기만 한다(덮어쓰기 금지).
"""
import datetime
import getpass
import hashlib
import json
import re
import sys
from pathlib import Path

EXTS = (".xlsx", ".png")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_path(name, folder="."):
    m = re.fullmatch(r"result-(\d+)", name)
    if not m:
        raise ValueError(f"결과 이름 형식이 아님: {name} (예: result-3)")
    return Path(folder) / f"review-{m.group(1)}.json"


def read_agent_verdicts(xlsx):
    """result-N.xlsx에서 {채널: 에이전트 판정(마지막 열)} 읽기 (읽기 전용)"""
    from openpyxl import load_workbook
    wb = load_workbook(xlsx, read_only=True, data_only=True)
    rows = [r for r in wb.active.iter_rows(min_row=2, values_only=True) if r and r[0]]
    wb.close()
    return {str(r[0]): str(r[-1]) for r in rows}


def build_record(name, folder, human, reviewer, now=None):
    folder = Path(folder)
    files = [folder / f"{name}{e}" for e in EXTS]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise FileNotFoundError(f"결과 파일 없음: {', '.join(missing)}")
    agent = read_agent_verdicts(folder / f"{name}.xlsx")
    diff = {ch: {"human": human.get(ch), "agent": a} for ch, a in agent.items() if human.get(ch) != a}
    return {
        "result": name,
        "reviewer": reviewer,
        "reviewed_at": (now or datetime.datetime.now()).isoformat(timespec="seconds"),
        "sha256": {f.name: sha256(f) for f in files},
        "human_verdicts": human,
        "agent_verdicts": agent,
        "mismatches": diff,
    }


def write_review(name, folder, human, reviewer, now=None):
    out = review_path(name, folder)
    if out.exists():
        raise FileExistsError(f"{out.name} 이미 있음 (덮어쓰기 금지)")
    rec = build_record(name, folder, human, reviewer, now)
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return out, rec


def check(name, folder="."):
    """승인 파일 검증. 문제 목록을 반환 (빈 목록이면 통과)"""
    out = review_path(name, folder)
    if not out.exists():
        return [f"{out.name} 없음: 사람 검수 승인 전"]
    rec = json.loads(out.read_text(encoding="utf-8"))
    problems = []
    for fname, digest in rec.get("sha256", {}).items():
        p = Path(folder) / fname
        if not p.exists():
            problems.append(f"{fname} 없음")
        elif sha256(p) != digest:
            problems.append(f"{fname} 이 승인 이후 변경됨")
    if not rec.get("human_verdicts"):
        problems.append("사람 판정 기록 없음")
    return problems


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    name = argv[0]
    if "--check" in argv:
        problems = check(name)
        for p in problems:
            print("미승인:", p)
        if not problems:
            print("승인 확인됨:", review_path(name).name)
        return 1 if problems else 0

    agent = read_agent_verdicts(f"{name}.xlsx")
    print(f"{name}.xlsx / {name}.png 를 직접 열어 확인한 뒤, 채널별 판정을 입력하세요.")
    print("(에이전트 판정은 보여주지 않습니다. 입력 후 비교합니다.)")
    human = {ch: input(f"{ch} 판정: ").strip() for ch in agent}
    out_name = review_path(name).name
    if input(f"{out_name} 로 검수 승인하시겠습니까? (yes 입력): ").strip() != "yes":
        print("승인 취소")
        return 1
    out, rec = write_review(name, ".", human, getpass.getuser())
    print("저장:", out)
    for ch, d in rec["mismatches"].items():
        print(f"  불일치 {ch}: 사람={d['human']!r} / 에이전트={d['agent']!r}")
    if not rec["mismatches"]:
        print("  모든 채널 판정이 에이전트와 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
