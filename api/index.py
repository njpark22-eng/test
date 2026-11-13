"""Vercel 웹 데모 진입점 (읽기 전용).

저장소에 포함된 가상 계측 데이터를 vibe_agent의 규칙 기반 판정으로 분석해 보여 준다.
판정/FFT 로직은 vibe_agent.py를 import해서 쓰며 여기서 다시 구현하지 않는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import vibe_agent as va

app = FastAPI(title="vibe-agent demo")

PAGE_PATH = Path(__file__).resolve().parent / "page.html"
MAX_HZ = 600   # 그래프로 보내는 최대 주파수 (Hz)
NO_DATA_MESSAGE = "계측 파일(CH1~CH5.xlsx)을 찾을 수 없습니다. --make-data로 생성하세요"


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(PAGE_PATH.read_text(encoding="utf-8"))


@app.get("/api/analyze")
def analyze():
    if not va.SIGNALS:
        return JSONResponse({"error": NO_DATA_MESSAGE}, status_code=500)
    channels = []
    for ch in va.SIGNALS:
        r = va.analyze_signal(ch)
        f, amp = va.spectrum(va.SIGNALS[ch])
        keep = f <= MAX_HZ
        channels.append({
            "r": r,
            "verdict": va.rule_verdict(r),
            "f": [round(float(v), 2) for v in f[keep]],
            "amp": [round(float(v), 3) for v in amp[keep]],
        })
    return {"channels": channels, "rules": va.RULES}
