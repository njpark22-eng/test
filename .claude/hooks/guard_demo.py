"""PreToolUse hook: 시연 중 실수 방지.

1) API 키 노출 차단: 키 값을 출력하는 Bash(echo/printenv/env 덤프 등), 키 리터럴(sk-ant-...)이 든 명령·파일 쓰기
2) 결과 파일 덮어쓰기 차단: 이미 있는 result-N.xlsx/png를 Edit/Write 하거나 rm/mv/덮어쓰기 하는 명령.
   결과 파일은 프로그램이 새 번호(가장 큰 번호 + 1)로만 만든다.
차단은 종료 코드 2 + stderr 메시지.
"""
import json
import os
import re
import sys

KEY_VAR = re.compile(r"ANTHROPIC_API_KEY|API_KEY", re.I)
KEY_LITERAL = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")
KEY_PRINT = re.compile(r"\b(echo|printf|print|printenv|cat|type|Write-Host|Write-Output)\b|\$env:|os\.environ|getenv|process\.env", re.I)
ENV_DUMP = re.compile(r"(^|[;&|(]\s*)(env|printenv|set)\s*($|[;&|)])|\bexport\s+-p\b|\bdeclare\s+-x\b|Get-ChildItem\s+Env:", re.I)

RESULT = re.compile(r"result-\d+\.(xlsx|png)", re.I)
WRITE_CMD = re.compile(r"(\brm\b|\bmv\b|\btouch\b|\btruncate\b|\bsed\s+-i|\bdel\b|\berase\b|Remove-Item|Move-Item|"
                       r"Set-Content|Out-File|(?<![<-])>{1,2}(?!&))", re.I)
CP_TO_RESULT = re.compile(r"\bcp\b[^;&|]*\s\S*result-\d+\.(xlsx|png)\s*($|[;&|])", re.I)

# 사람 검수 승인 파일: 사람이 approve.py로만 만든다 (에이전트 실행/작성 차단)
REVIEW = re.compile(r"review-\d+\.json", re.I)
CP_TO_REVIEW = re.compile(r"\bcp\b[^;&|]*\s\S*review-\d+\.json\s*($|[;&|])", re.I)
APPROVE_RUN = re.compile(r"\b(python[\d.]*(\.exe)?|py|uv\s+run(\s+python)?)\s+(\S*[/\\])?approve\.py", re.I)


def _strip_devnull(cmd):
    return re.sub(r"\d*>\s*(/dev/null|&\d)", "", cmd)


def evaluate(tool, inp):
    """차단해야 하면 사유 문자열, 아니면 None"""
    if tool == "Bash":
        cmd = _strip_devnull(inp.get("command", ""))
        if KEY_LITERAL.search(cmd):
            return "명령에 API 키 값이 들어 있음 (키는 환경변수로만 사용)"
        if ENV_DUMP.search(cmd):
            return "환경변수 전체 출력 명령은 API 키를 노출할 수 있음"
        if KEY_VAR.search(cmd) and KEY_PRINT.search(cmd):
            return "API 키 값을 출력하는 명령 (화면 공유 중 키 노출 방지)"
        if RESULT.search(cmd) and (WRITE_CMD.search(RESULT.sub("", cmd)) or CP_TO_RESULT.search(cmd)):
            return "결과 파일(result-N)을 삭제/이동/덮어쓰는 명령 (결과는 새 번호로만 저장)"
        if APPROVE_RUN.search(cmd) and "--check" not in cmd:
            return "approve.py는 사람이 직접 실행 (Claude Code에서는 `! python approve.py result-N`)"
        if REVIEW.search(cmd) and (WRITE_CMD.search(REVIEW.sub("", cmd)) or CP_TO_REVIEW.search(cmd)):
            return "승인 파일(review-N.json)은 사람만 만들 수 있음 (수정/삭제/이동 금지)"
    elif tool in ("Edit", "Write", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        body = " ".join(str(inp.get(k, "")) for k in ("content", "new_string", "new_source"))
        if REVIEW.search(os.path.basename(path)):
            return "승인 파일(review-N.json)은 사람만 만들 수 있음 (에이전트가 쓰기 금지)"
        if KEY_LITERAL.search(body):
            return "파일에 API 키 값을 쓰려는 시도 (커밋 방지)"
        if RESULT.search(os.path.basename(path)) and os.path.exists(path):
            return f"기존 결과 파일 {os.path.basename(path)} 덮어쓰기 (결과는 새 번호로만 저장)"
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    why = evaluate(data.get("tool_name", ""), data.get("tool_input", {}) or {})
    if why:
        print(f"차단: {why}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
