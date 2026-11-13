"""vibe_agent 호출을 모아 둔 분석 함수.

판정·FFT·회전수 추정은 모두 vibe_agent의 함수를 그대로 호출하며 여기서 다시 구현하지 않는다.
vibe_agent.analyze_signal은 모듈 전역(SIGNALS, RPM, BALLS)을 읽으므로, 전역을 건드리는 코드는
모두 이 모듈의 잠금 아래에서 실행한다.
"""
import io
import os
import tempfile
import threading
import uuid
import zipfile

import numpy as np

import vibe_agent as va
from api.errors import ApiError

LOCK = threading.RLock()
MAX_HZ = 600                       # 저장·표시하는 스펙트럼의 최대 주파수 (Hz)
MAX_FILE_BYTES = 1024 * 1024       # 파일 1개 한도
MAX_TOTAL_BYTES = 4 * 1024 * 1024  # 한 번에 올리는 합계 한도 (배포 환경 요청 크기 제한 이내)
MAX_UNPACKED_BYTES = 30 * 1024 * 1024   # 엑셀(zip)을 풀었을 때 크기 한도 (가상 데이터 파일은 수 MB 이하)
MAX_CHANNELS = 5
RUNS_PER_HOUR = 30
RPM_MAX = 20000
BALLS_MAX = 100

# rule_verdict가 함수 안 숫자로 갖고 있어 상수로 읽을 수 없는 기준값. 값이 어긋나면
# tests/test_persistence.py의 경계 테스트가 실패한다.
RATIO_2X_OVER_1X = 0.5
RATIO_BEARING_OVER_1X = 0.7


def thresholds() -> dict:
    """판정에 쓰는 고정 기준값 (결과와 함께 기록)"""
    return {
        "rms_limit": va.RMS_LIMIT,
        "lowfreq_noise_limit": va.LOWNOISE_LIMIT,
        "ratio_2x_over_1x": RATIO_2X_OVER_1X,
        "ratio_bearing_over_1x": RATIO_BEARING_OVER_1X,
    }


def trim_spectrum(x) -> dict:
    f, amp = va.spectrum(x)
    keep = f <= MAX_HZ
    return {"f": [round(float(v), 2) for v in f[keep]],
            "amp": [round(float(v), 3) for v in amp[keep]]}


def read_upload(content: bytes, label: str):
    """올린 엑셀 바이트를 vibe_agent.read_xlsx로 읽어 (시간, 속도) 배열을 돌려준다.
    read_xlsx는 경로를 받으므로 임시 파일을 쓰고 바로 지운다 (입력 데이터 폴더와 무관)."""
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise ApiError(422, f"{label}: 엑셀(.xlsx) 파일이 아닙니다. 계측기에서 받은 .xlsx 파일을 올리세요")
    with zipfile.ZipFile(io.BytesIO(content)) as z:   # 압축 폭탄 방지: 풀었을 때 크기를 먼저 확인
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED_BYTES:
            raise ApiError(422, f"{label}: 엑셀 내용이 너무 큽니다. 계측 데이터만 들어 있는 .xlsx를 올리세요")
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        try:
            return va.read_xlsx(path)
        except ValueError as e:
            msg = str(e).replace(os.path.basename(path), label)
            raise ApiError(422, msg) from None
        except Exception:
            raise ApiError(422, f"{label}: 엑셀을 읽을 수 없습니다. A열 time_s, B열 velocity_mm_s 형식의 .xlsx인지 확인하세요") from None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def analyze_channels(items: list[dict]) -> list[dict]:
    """items: [{channel, x(속도 배열), rpm, balls}] -> 채널별 결과.
    임시 키로 vibe_agent 전역에 넣고 호출 직후 반드시 지운다."""
    out = []
    with LOCK:
        keys = []
        try:
            for it in items:
                key = f"UP-{uuid.uuid4().hex}-{it['channel']}"
                keys.append(key)
                va.SIGNALS[key] = it["x"]
                va.RPM[key] = it["rpm"]
                va.BALLS[key] = it["balls"]
                r = va.analyze_signal(key)
                r["channel"] = it["channel"]
                out.append({"channel": it["channel"], "rpm": it["rpm"], "balls": it["balls"],
                            "verdict": va.rule_verdict(r), "result": r,
                            "spectrum": trim_spectrum(it["x"])})
        finally:
            for key in keys:
                va.SIGNALS.pop(key, None)
                va.RPM.pop(key, None)
                va.BALLS.pop(key, None)
    return out


def analyze_demo() -> list[dict]:
    """저장소에 포함된 가상 데이터 5채널 분석 (001 화면). 전역을 읽는 동안 잠근다."""
    with LOCK:
        names = [n for n in va.SIGNALS if not n.startswith("UP-")]
        channels = []
        for ch in names:
            r = va.analyze_signal(ch)
            sp = trim_spectrum(va.SIGNALS[ch])
            channels.append({"r": r, "verdict": va.rule_verdict(r), "f": sp["f"], "amp": sp["amp"]})
    return channels


def parse_int(text, label: str, low: int, high: int, what: str) -> int:
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        raise ApiError(422, f"{label}: {what}은 정수여야 합니다 ({low}~{high})")
    if not (low <= value <= high):
        raise ApiError(422, f"{label}: {what}은 {low}~{high} 범위여야 합니다")
    return value


def check_rpm(x: np.ndarray, rpm: int, label: str) -> None:
    """입력 rpm의 1X 성분이 최대 피크의 20% 미만이면 거부 (로컬 UI와 같은 규칙)"""
    miss = va.rpm_mismatch(x, rpm)
    if miss is not None:
        f1, peak = miss
        detected = va.detect_rpm(x)
        raise ApiError(
            422,
            f"{label}: 입력한 {rpm} rpm의 1X({f1:.1f} Hz)에 뚜렷한 피크가 없습니다. "
            f"신호의 최대 피크는 {peak:.1f} Hz이며 자동 추정 회전수는 {detected} rpm입니다",
            channel=label, detected_rpm=detected)
