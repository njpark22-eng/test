"""Vercel 웹 데모 앱.

가상 계측 데이터를 vibe_agent의 규칙 기반 판정으로 분석해 보여 주고(001),
가상 파일을 올려 분석한 원본·결과를 저장해 이력으로 보여 주며, 저장된 파일은 다시 올리지 않고
골라서 분석할 수 있다(002). 판정/FFT 로직은 vibe_agent.py를 import해서 쓰며 여기서 다시 구현하지 않는다.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response

import vibe_agent as va
from vibe_web import analysis, insight
from vibe_web.errors import ApiError
from vibe_web.store import PgStore

app = FastAPI(title="vibe-agent demo")

HERE = Path(__file__).resolve().parent / "static"
NO_DATA_MESSAGE = "계측 파일(CH1~CH5.xlsx)을 찾을 수 없습니다. --make-data로 생성하세요"
PREVIEW_ROWS = 20
MAX_FILENAME = 200


@app.exception_handler(ApiError)
def _api_error(_: Request, exc: ApiError):
    return JSONResponse(exc.body(), status_code=exc.status)


@app.exception_handler(RequestValidationError)
def _validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "요청 형식이 올바르지 않습니다. 화면에서 파일과 값을 다시 입력하세요"},
                        status_code=422)


def get_store():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ApiError(503, "저장소가 설정되지 않았습니다. 관리자가 DATABASE_URL을 설정해야 합니다")
    return PgStore(url)


def _page(name: str) -> HTMLResponse:
    return HTMLResponse((HERE / name).read_text(encoding="utf-8"))


# ---------- 화면 ----------
@app.get("/", response_class=HTMLResponse)
def index():
    return _page("page.html")


@app.get("/upload", response_class=HTMLResponse)
def upload_page():
    return _page("upload.html")


@app.get("/runs", response_class=HTMLResponse)
def runs_page():
    return _page("runs.html")


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: int):
    return _page("runs.html")


@app.get("/assets/shared.css")
def shared_css():
    return Response((HERE / "shared.css").read_text(encoding="utf-8"), media_type="text/css; charset=utf-8")


@app.get("/assets/shared.js")
def shared_js():
    return Response((HERE / "shared.js").read_text(encoding="utf-8"),
                    media_type="application/javascript; charset=utf-8")


# ---------- 001: 저장소에 포함된 가상 데이터 판정 ----------
@app.get("/api/analyze")
def analyze():
    if not va.SIGNALS:
        return JSONResponse({"error": NO_DATA_MESSAGE}, status_code=500)
    return {"channels": analysis.analyze_demo(), "rules": va.RULES}


# ---------- 002: 설정, 올리기, 저장된 파일, 이력 ----------
@app.get("/api/config")
def config():
    return {
        "limits": {"max_file_bytes": analysis.MAX_FILE_BYTES, "max_total_bytes": analysis.MAX_TOTAL_BYTES,
                   "max_channels": analysis.MAX_CHANNELS, "runs_per_hour": analysis.RUNS_PER_HOUR},
        "thresholds": analysis.thresholds(),
    }


def _read_files(files: list[UploadFile], allow_empty: bool = False) -> list[bytes]:
    if not files:
        if allow_empty:
            return []
        raise ApiError(422, "올릴 파일을 1~5개 고르세요")
    if len(files) > analysis.MAX_CHANNELS:
        raise ApiError(422, f"채널은 최대 {analysis.MAX_CHANNELS}개까지 올릴 수 있습니다")
    contents, total = [], 0
    for i, f in enumerate(files, 1):
        content = f.file.read(analysis.MAX_FILE_BYTES + 1)
        if len(content) > analysis.MAX_FILE_BYTES:
            raise ApiError(413, f"CH{i}: 파일이 {analysis.MAX_FILE_BYTES // 1024 // 1024} MB를 넘습니다. 더 작은 파일을 올리세요")
        if not content:
            raise ApiError(422, f"CH{i}: 빈 파일입니다. 계측 데이터가 들어 있는 .xlsx를 올리세요")
        total += len(content)
        contents.append(content)
    if total > analysis.MAX_TOTAL_BYTES:
        raise ApiError(413, f"한 번에 올리는 파일 합계가 {analysis.MAX_TOTAL_BYTES // 1024 // 1024} MB를 넘습니다. 채널 수를 줄여 나눠 올리세요")
    return contents


def _clean_name(name: str | None) -> str | None:
    if not name:
        return None
    name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:MAX_FILENAME] or None


def _inspect_info(content: bytes, label: str = "파일") -> dict:
    tt, x = analysis.read_upload(content, label)
    return {"samples": int(x.size), "fs": va.FS, "rpm_detected": va.detect_rpm(x),
            "preview": [[float(a), float(b)] for a, b in zip(tt[:PREVIEW_ROWS], x[:PREVIEW_ROWS])]}


@app.post("/api/inspect")
def inspect(file: UploadFile = File(...)):
    """올린 파일을 검증하고 자동 회전수와 앞부분을 돌려준다 (저장하지 않는다)"""
    return _inspect_info(_read_files([file])[0])


@app.get("/api/files")
def list_files(store=Depends(get_store)):
    """저장된 원본 파일 목록 (다시 올리지 않고 고를 수 있다). 내용은 돌려주지 않는다"""
    return {"files": store.list_files(100)}


@app.get("/api/files/{file_id}")
def inspect_stored(file_id: int, store=Depends(get_store)):
    """저장된 파일의 자동 회전수와 앞부분"""
    f = store.get_file(file_id)
    if f is None:
        raise ApiError(404, "저장된 파일을 찾을 수 없습니다. 목록에서 다시 고르세요")
    return {**_inspect_info(f["content"], f["filename"] or f"#{file_id}"), "id": f["id"],
            "sha256": f["sha256"], "filename": f["filename"]}


@app.post("/api/runs", status_code=201)
def create_run(files: list[UploadFile] = File(default=[]), file_ids: list[str] = Form(default=[]),
               rpm: list[str] = Form(default=[]), balls: list[str] = Form(default=[]),
               store=Depends(get_store)):
    """채널마다 새로 올린 파일이나 저장된 파일(file_ids) 중 하나로 분석하고 저장한다.
    file_ids는 채널 순서대로 저장된 파일 번호 또는 빈 문자열(새로 올린 파일 사용)이다."""
    if store.recent_run_count(1) >= analysis.RUNS_PER_HOUR:
        raise ApiError(429, f"최근 1시간에 저장할 수 있는 횟수({analysis.RUNS_PER_HOUR}회)를 넘었습니다. 잠시 뒤 다시 시도하세요")
    uploads = _read_files(files, allow_empty=bool(file_ids))
    names = [_clean_name(f.filename) for f in files]
    slots = [s.strip() for s in file_ids] if file_ids else [""] * len(uploads)
    n = len(slots)
    if not (1 <= n <= analysis.MAX_CHANNELS):
        raise ApiError(422, f"채널은 1~{analysis.MAX_CHANNELS}개여야 합니다")
    if sum(1 for s in slots if not s) != len(uploads):
        raise ApiError(422, "올린 파일 수와 저장된 파일을 고르지 않은 채널 수가 맞지 않습니다")
    if len(rpm) != n:
        raise ApiError(422, "채널마다 회전수(rpm)를 입력하세요")
    balls = balls or ["1"] * n
    if len(balls) != n:
        raise ApiError(422, "채널마다 볼 개수를 입력하세요")

    new_files = iter(zip(uploads, names))
    sources = []          # [(내용, 파일 이름)]
    for i, slot in enumerate(slots, 1):
        if slot:
            stored = store.get_file(analysis.parse_int(slot, f"CH{i}", 1, 2**62, "저장된 파일 번호"))
            if stored is None:
                raise ApiError(404, f"CH{i}: 저장된 파일을 찾을 수 없습니다. 목록에서 다시 고르세요")
            sources.append((stored["content"], stored["filename"]))
        else:
            sources.append(next(new_files))

    items = []
    for i, (content, _) in enumerate(sources, 1):
        label = f"CH{i}"
        _, x = analysis.read_upload(content, label)
        r = analysis.parse_int(rpm[i - 1], label, 1, analysis.RPM_MAX, "회전수")
        b = analysis.parse_int(balls[i - 1], label, 1, analysis.BALLS_MAX, "볼 개수")
        analysis.check_rpm(x, r, label)
        items.append({"channel": label, "x": x, "rpm": r, "balls": b})

    results = analysis.analyze_channels(items)
    for res, (content, name) in zip(results, sources):
        res["content"] = content
        res["filename"] = name
    run_id = store.insert_run(analysis.thresholds(), results)
    return insight.attach(store.get_run(run_id))


@app.get("/api/runs")
def list_runs(store=Depends(get_store)):
    return {"runs": store.list_runs(100)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: int, store=Depends(get_store)):
    run = store.get_run(run_id)
    if run is None:
        raise ApiError(404, "해당 분석 실행을 찾을 수 없습니다. 이력 목록에서 다시 고르세요")
    return insight.attach(run)
