"""PreToolUse hook: 입력 데이터 엑셀(data/*.xlsx 등) 수정·덮어쓰기 차단.

- Edit/Write/NotebookEdit: 대상 경로가 data/ 아래이거나 .xlsx/.xlsm/.xls 이면 차단
  (result-N.xlsx 는 프로그램이 만드는 결과 파일이므로 허용)
- Bash: 엑셀/data 경로를 대상으로 rm, mv, cp, 리다이렉트, sed -i, touch 등 쓰기 명령이면 차단
  (`vibe_agent.py --make-data` 는 가상 데이터를 새로 만드는 예외라 허용)
차단은 종료 코드 2 + stderr 메시지.
"""
import json
import re
import sys

EXCEL = re.compile(r"\.(xlsx|xlsm|xls)\b", re.I)
RESULT = re.compile(r"(^|[\/])result-\d+\.xlsx$", re.I)
DATA_DIR = re.compile(r"(^|[\/])data[\/]", re.I)
WRITE_CMD = re.compile(r"(\brm\b|\bmv\b|\bcp\b|\btouch\b|\btruncate\b|\bsed\s+-i|\bdel\b|\berase\b|"
                       r"Remove-Item|Move-Item|Copy-Item|Set-Content|Out-File|(?<![<-])>{1,2}(?!&))", re.I)


def block(msg):
    print(f"차단: {msg} (입력 데이터 엑셀은 계측기 원본이라 수정 금지. 예외는 --make-data)", file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}
    if tool in ("Edit", "Write", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if RESULT.search(path):
            return
        if EXCEL.search(path):
            block(f"{path} 수정 시도")
    elif tool == "Bash":
        cmd = inp.get("command", "")
        cmd = re.sub(r"\d*>\s*(/dev/null|&\d)", "", cmd)  # /dev/null, 2>&1 은 쓰기 아님
        if "--make-data" in cmd:
            return
        targets_input = EXCEL.search(cmd) or re.search(r"\bdata[\/]", cmd, re.I)
        if targets_input and WRITE_CMD.search(cmd):
            # result-N.xlsx 만 다루는 명령은 허용
            stripped = re.sub(r"result-\d+\.(xlsx|png)", "", cmd, flags=re.I)
            if (EXCEL.search(stripped) or re.search(r"\bdata[\/]", stripped, re.I)) and WRITE_CMD.search(stripped):
                block("엑셀/data 경로에 쓰기 명령")


main()
