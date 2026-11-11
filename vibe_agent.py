"""진동 계측 진단 에이전트 (교육 시연용)
- 계측 데이터(엑셀 4개, data/CH*.xlsx) 읽기 -> FFT -> 특징량 추출 -> 판정
- 엑셀 파일은 계측기에서 받은 time 데이터라고 가정 (시연에서는 --make-data로 가상 생성)
- 기본: Claude가 도구(tool)를 호출하며 판단하는 에이전트
- --offline : API 없이 규칙 기반으로만 실행 (시연 백업용)
- --make-data : 가상 계측 데이터를 data/CH1~CH4.xlsx로 생성 (최초 1회)

설치: pip install numpy anthropic matplotlib openpyxl
실행: export ANTHROPIC_API_KEY=...  후  python vibe_agent.py
"""
import json, os, sys
from pathlib import Path
import numpy as np

FS, DUR = 5120, 2.0          # 샘플링 주파수(Hz), 길이(s)
# 장비(채널)마다 회전수가 다름. 시연용 가상 데이터의 회전수 (rpm)
DEFAULT_RPM = {"CH1": 1800, "CH2": 1500, "CH3": 1200, "CH4": 2400}
RPM = dict(DEFAULT_RPM)      # 분석에 쓰는 채널별 회전수 (UI에서는 사용자 입력으로 덮어씀)
# 베어링 볼 개수. 1이면 베어링 주파수를 쓰지 않는 채널(FFT 그림에 BPFO 표시/베어링 판정 없음)
DEFAULT_BALLS = {"CH1": 1, "CH2": 9, "CH3": 1, "CH4": 1}
BALLS = dict(DEFAULT_BALLS)
RMS_LIMIT = 4.5              # 속도 RMS 기준 (mm/s)
t = np.arange(0, DUR, 1 / FS)
DATA_DIR = Path(__file__).parent / "data"
CHANNELS = ("CH1", "CH2", "CH3", "CH4")


# ---------- 1. 신호 생성 (속도 mm/s, peak 진폭 기준) ----------
def shaft_hz(rpm):
    """회전수(rpm) -> 1X 주파수(Hz)"""
    return rpm / 60.0


def bpfo_hz(rpm, balls):
    """베어링 외륜 결함 주파수(Hz) 약산식 = (회전주파수 / 2) x 0.8 x 볼 개수 (지름 불필요)"""
    return shaft_hz(rpm) / 2 * 0.8 * balls


def has_bearing(balls):
    """볼 개수가 2 이상이어야 베어링 주파수를 사용 (1은 베어링 미적용 채널)"""
    return balls >= 2


def make_signal(a1, a2=0.0, abrg=0.0, noise=0.1, seed=0, rpm=1800, balls=1):
    rng = np.random.default_rng(seed)
    fs1, fb = shaft_hz(rpm), bpfo_hz(rpm, balls)
    s = a1 * np.sin(2 * np.pi * fs1 * t)
    s += a2 * np.sin(2 * np.pi * 2 * fs1 * t + 0.5)
    s += abrg * np.sin(2 * np.pi * fb * t) + 0.5 * abrg * np.sin(2 * np.pi * 2 * fb * t)
    return s + rng.normal(0, noise, t.size)


# 가상 계측 데이터 생성용 (실제 현장에서는 계측기가 엑셀을 만들어 준다고 가정)
SYNTH = {
    "CH1": make_signal(2.0, 0.2, 0.0, noise=0.2, seed=1, rpm=DEFAULT_RPM["CH1"]),    # 정상
    "CH2": make_signal(2.4, 0.4, 2.0, noise=0.2, seed=2, rpm=DEFAULT_RPM["CH2"],
                       balls=DEFAULT_BALLS["CH2"]),                                  # 베어링 이상 (기준 이하)
    "CH3": make_signal(16.0, 1.0, 0.0, noise=0.2, seed=3, rpm=DEFAULT_RPM["CH3"]),   # 1X 지배 + 기준 초과
    "CH4": make_signal(14.0, 9.0, 0.0, noise=0.2, seed=4, rpm=DEFAULT_RPM["CH4"]),   # 1X + 2X + 기준 초과
}


def make_data(folder=DATA_DIR):
    """가상 계측 time 데이터를 채널별 엑셀(time_s, velocity_mm_s)로 저장"""
    from openpyxl import Workbook
    from openpyxl.chart import Reference, ScatterChart, Series
    Path(folder).mkdir(parents=True, exist_ok=True)
    for ch, x in SYNTH.items():
        wb = Workbook()
        ws = wb.active
        ws.title = ch
        ws.append(["time_s", "velocity_mm_s"])
        for ti, xi in zip(t, x):
            ws.append([round(float(ti), 6), round(float(xi), 5)])
        # 시간 신호 그래프 삽입 (확인용: load_signals는 A/B열 데이터만 읽고 차트는 사용하지 않음)
        n = len(x)
        chart = ScatterChart()
        chart.title = f"{ch} 시간 신호"
        chart.style = 2
        chart.x_axis.title = "Time (s)"
        chart.y_axis.title = "Velocity (mm/s)"
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        chart.legend = None
        # 0 대칭 + 눈금 간격의 배수로 범위 설정 (0이 눈금에 오고, 최대/최소 안 잘림)
        ylim, step = nice_ylim(x)
        chart.y_axis.scaling.min, chart.y_axis.scaling.max = -ylim, ylim
        chart.y_axis.majorUnit = step
        chart.x_axis.scaling.min, chart.x_axis.scaling.max = 0, DUR
        series = Series(Reference(ws, min_col=2, min_row=2, max_row=n + 1),
                        Reference(ws, min_col=1, min_row=2, max_row=n + 1))
        series.marker.symbol = "none"
        series.graphicalProperties.line.width = 6000
        chart.series.append(series)
        chart.width, chart.height = 24, 10
        ws.add_chart(chart, "D2")
        wb.save(Path(folder) / f"{ch}.xlsx")
        print("계측 데이터 저장:", Path(folder) / f"{ch}.xlsx")


def read_xlsx(path):
    """엑셀(time_s, velocity_mm_s) 한 개를 읽어 (시간 배열, 속도 배열) 반환. 그래프 등 다른 요소는 무시"""
    from openpyxl import load_workbook
    path = Path(path)
    wb = load_workbook(path, read_only=True, data_only=True)
    rows = [r for r in wb.active.iter_rows(min_row=2, values_only=True)
            if r and r[0] is not None and r[1] is not None]
    wb.close()
    if len(rows) < 2:
        raise ValueError(f"{path.name}: 데이터 행이 없습니다 (A열 time_s, B열 velocity_mm_s 필요)")
    tt = np.array([r[0] for r in rows], dtype=float)
    x = np.array([r[1] for r in rows], dtype=float)
    fs = (tt.size - 1) / float(tt[-1] - tt[0])  # 시간 반올림 오차에 둔감하도록 전체 구간 기준
    if abs(fs - FS) > 1e-3 * FS:
        raise ValueError(f"{path.name}: 샘플링 주파수 {fs:.1f} Hz != {FS} Hz")
    return tt, x


def load_signals(folder=DATA_DIR):
    """채널별 엑셀(time_s, velocity_mm_s)을 읽어 {채널: 속도 배열}로 반환"""
    out = {}
    for ch in CHANNELS:
        path = Path(folder) / f"{ch}.xlsx"
        if not path.exists():
            raise FileNotFoundError(f"{path} 없음 - `python vibe_agent.py --make-data`로 생성하세요")
        out[ch] = read_xlsx(path)[1]
    return out


def nice_ylim(x):
    """0 대칭 y축 범위와 눈금 간격 (0이 눈금에 오고 최대/최소값이 잘리지 않음)"""
    raw = max(float(np.abs(x).max()) * 1.05, 1e-9)
    step = next((s for s in (0.5, 1, 2, 2.5, 5, 10, 20, 50, 100) if raw / s <= 6), 200)
    return float(np.ceil(raw / step) * step), step


SIGNALS = load_signals() if all((DATA_DIR / f"{c}.xlsx").exists() for c in CHANNELS) else {}


# ---------- 2. 도구: FFT 특징량 추출 ----------
def spectrum(x):
    """FFT 스펙트럼. 진폭은 RMS 값(= peak / sqrt(2), mm/s)으로 반환"""
    amp = 2 * np.abs(np.fft.rfft(x * np.hanning(x.size))) / (x.size * 0.5) / np.sqrt(2)
    return np.fft.rfftfreq(x.size, 1 / FS), amp


def peak_near(f, amp, target, tol=0.03):
    m = (f > target * (1 - tol)) & (f < target * (1 + tol))
    if not m.any():   # 낮은 주파수에서는 탐색 구간에 FFT 빈이 없을 수 있음 -> 가장 가까운 빈 사용
        return float(amp[np.argmin(np.abs(f - target))])
    return float(amp[m].max())


ONEX_MIN_RATIO = 0.2   # 입력 회전수의 1X 성분이 최대 피크의 20% 이상이어야 회전수가 맞다고 봄


def detect_rpm(x):
    """신호의 FFT 최대 피크를 1X로 보고 그에 맞는 회전수(rpm)를 추정 (포물선 보간으로 빈 간격보다 정밀하게)"""
    f, amp = spectrum(x)
    k = int(np.argmax(amp[1:])) + 1
    delta = 0.0
    if k < amp.size - 1:
        a, b, c = amp[k - 1], amp[k], amp[k + 1]
        if a - 2 * b + c != 0:
            delta = 0.5 * (a - c) / (a - 2 * b + c)
    return int(round((k + delta) * (f[1] - f[0]) * 60))


def rpm_mismatch(x, rpm):
    """입력한 회전수의 1X 주파수에 뚜렷한 피크가 없으면 (1X Hz, 최대 피크 Hz)를 반환, 맞으면 None"""
    f, amp = spectrum(x)
    f1 = shaft_hz(rpm)
    k = int(np.argmax(amp[1:])) + 1   # DC 제외 최대 피크
    if peak_near(f, amp, f1) >= ONEX_MIN_RATIO * amp[k]:
        return None
    return f1, float(f[k])


def analyze_signal(name):
    x = SIGNALS[name]
    f, amp = spectrum(x)
    f1 = shaft_hz(RPM[name])   # 장비(채널)별 회전수 기준 주파수
    balls = BALLS.get(name, 1)
    bearing = has_bearing(balls)
    fb = bpfo_hz(RPM[name], balls) if bearing else None
    a1 = peak_near(f, amp, f1)
    a2 = peak_near(f, amp, 2 * f1)
    abrg = peak_near(f, amp, fb) if bearing else None   # 베어링 미적용 채널은 베어링 성분을 보지 않음
    k = int(np.argmax(amp[1:])) + 1   # DC 성분 제외, FFT 최대 피크
    return {
        "channel": name,
        "rpm": RPM[name],
        "shaft_1X_hz": round(f1, 2),
        "bearing_balls": balls,
        "bearing_BPFO_hz": round(fb, 1) if bearing else None,
        "peak_rms_mm_s": round(float(amp[k]), 2),   # 판정 기준과 비교하는 값 (FFT 최대 피크의 RMS)
        "peak_freq_hz": round(float(f[k]), 1),
        "rms_limit_mm_s": RMS_LIMIT,
        "rms_1X": round(a1, 2),
        "rms_2X": round(a2, 2),
        "rms_bearing_BPFO": round(abrg, 2) if bearing else None,
        "ratio_2X_over_1X": round(a2 / a1, 2),
        "ratio_bearing_over_1X": round(abrg / a1, 2) if bearing else 0.0,
    }


def list_signals():
    out = {}
    for ch in SIGNALS:
        balls = BALLS.get(ch, 1)
        out[ch] = {"rpm": RPM[ch], "shaft_1X_hz": round(shaft_hz(RPM[ch]), 2), "bearing_balls": balls,
                   "bearing_BPFO_hz": round(bpfo_hz(RPM[ch], balls), 1) if has_bearing(balls) else None}
    return {"channels": out}


# ---------- 3. 규칙 (프롬프트로도, 오프라인 판정으로도 사용) ----------
RULES = """판정 규칙:
기준 비교 값은 FFT 최대 피크의 RMS(peak_rms_mm_s)이며 overall RMS가 아님.
1) peak_rms가 기준 이하이고 bearing 성분이 1X 대비 0.7 이상 -> '베어링 점검 요망'
   (외륜 주파수 = 회전주파수/2 x 0.8 x 볼 개수. 볼 개수 1은 베어링 주파수 미적용 채널이라 베어링 판정을 하지 않음)
2) peak_rms가 기준 이하이고 이상 징후 없음 -> '정상'
3) peak_rms가 기준 초과이고 ratio_2X_over_1X >= 0.5 -> '정렬(Misalignment) 요망'
4) peak_rms가 기준 초과이고 1X가 지배적(2X/1X < 0.5) -> '발란싱 요망'"""


def rule_verdict(r):
    over = r["peak_rms_mm_s"] > r["rms_limit_mm_s"]
    if over:
        return "정렬 요망" if r["ratio_2X_over_1X"] >= 0.5 else "발란싱 요망"
    return "베어링 점검 요망" if r["ratio_bearing_over_1X"] >= 0.7 else "정상"


# ---------- 4. 에이전트 루프 ----------
TOOLS = [
    {"name": "list_signals", "description": "분석 가능한 채널 목록과 채널(장비)별 회전수/기준 주파수를 반환",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "analyze_signal", "description": "채널의 FFT 특징량(최대 피크 RMS, 1X/2X/베어링 성분 RMS)을 계산",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}},
                      "required": ["name"]}},
]
DISPATCH = {"list_signals": lambda **_: list_signals(),
            "analyze_signal": lambda name: analyze_signal(name)}


def run_agent(emit=print):
    """Claude 에이전트 실행. 도구 호출 로그는 emit으로 내보내고, 최종 답변 텍스트를 반환"""
    import anthropic
    client = anthropic.Anthropic()
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    system = ("당신은 선박 회전기계 진동 진단 에이전트입니다. 도구로 모든 채널을 분석하고 "
              "채널별 판정과 근거 수치를 표로 정리하세요. 채널마다 다른 장비라 회전수(rpm)가 다릅니다.\n" + RULES)
    msgs = [{"role": "user", "content": "모든 채널을 진단해 주세요."}]
    while True:
        resp = client.messages.create(model=model, max_tokens=1500, system=system,
                                      tools=TOOLS, messages=msgs)
        msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                emit(f"[도구 호출] {b.name}({b.input})")
                out = DISPATCH[b.name](**b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": json.dumps(out, ensure_ascii=False)})
        msgs.append({"role": "user", "content": results})


def run_offline():
    print(RULES, "\n")
    for ch in SIGNALS:
        r = analyze_signal(ch)
        print(f"{ch}: {rule_verdict(r)}  | {r}")


def set_korean_font():
    """한글 폰트 (Windows: Malgun Gothic / macOS: AppleGothic / Linux: NanumGothic)"""
    import matplotlib
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
        if name in installed:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


XLABEL = "Frequency (Hz)  [1X=회전주파수, 2X=2배 성분, BPFO=베어링 외륜 결함 주파수]"


def draw_spectrum(ax, x, title, rpm, balls=1):
    """한 채널의 FFT 스펙트럼 + 허용기준선 + 주요 피크 표시를 ax에 그린다.
    rpm: 해당 장비 회전수, balls: 베어링 볼 개수 (1이면 BPFO/2xBPFO 세로줄을 그리지 않고,
    2 이상이면 해당 위치에 피크가 없어도 항상 세로줄과 범례를 표시)"""
    f, a = spectrum(x)
    f1 = shaft_hz(rpm)
    marks = [(f1, "r", "1X"), (2 * f1, "g", "2X")]
    if has_bearing(balls):
        fb = bpfo_hz(rpm, balls)
        marks += [(fb, "m", "BPFO"), (2 * fb, "tab:orange", "2×BPFO")]
    xmax = max(300, 1.1 * max(m[0] for m in marks))   # 표시하는 가장 높은 성분까지 보이도록
    ax.plot(f, a, lw=0.8)
    ax.set_xlim(0, xmax)
    ax.set_title(title)
    # 허용기준 가로선 (RMS 기준값을 그대로 표시)
    ax.axhline(RMS_LIMIT, color="k", ls="-.", lw=1, label=f"허용기준 RMS {RMS_LIMIT} mm/s")
    # 주요 피크 표시: 해당 성분의 RMS가 0.28 mm/s(peak 0.4) 이상일 때만 라벨
    ymax = max(a[f <= xmax].max(), RMS_LIMIT) * 1.25
    for k, c, lab in marks:
        ax.axvline(k, color=c, ls="--", alpha=0.4, label=f"{lab} {k:.1f} Hz")   # 범례에 주파수 표시
        pk = peak_near(f, a, k)
        if pk >= 0.28:
            ax.annotate(f"{lab}\n{k:.0f} Hz, {pk:.2f}", xy=(k, pk), xytext=(0, 8),
                        textcoords="offset points", ha="center", fontsize=8, color=c)
    ax.set_ylim(0, ymax)
    ax.set_ylabel("진폭 (mm/s, RMS)")
    ax.legend(loc="upper right", fontsize=8)


def plot_all(path="spectra.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    set_korean_font()
    fig, axs = plt.subplots(2, 2, figsize=(10, 6))
    for ax, (ch, x) in zip(axs.ravel(), SIGNALS.items()):
        draw_spectrum(ax, x, f"{ch} ({RPM[ch]} rpm): {rule_verdict(analyze_signal(ch))}",
                      RPM[ch], BALLS.get(ch, 1))
    fig.supxlabel(XLABEL)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print("스펙트럼 저장:", path)


# ---------- 5. UI (tkinter): 채널 수 입력 -> 파일 선택/표시 -> 분석 실행 ----------
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError:  # tkinter가 없는 환경에서는 --ui만 사용 불가
    tk = None

MAX_ROWS = 1000   # 데이터 표에 보여줄 최대 행 수 (그래프/분석은 전체 데이터 사용)


class VibeUI:
    def __init__(self, root, n, use_agent=False):
        import queue
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure
        self.Figure, self.Canvas = Figure, FigureCanvasTkAgg
        self.root, self.n, self.use_agent = root, n, use_agent
        self.chs = [f"CH{i + 1}" for i in range(n)]
        self.data = {}      # 채널 -> (시간 배열, 속도 배열, 파일 경로)
        self.tabs = {}
        self.file_var = {}
        self.rpm_var = {}   # 채널(장비)별 회전수 입력값
        self.rpm_entry = {}
        self.balls_var = {}   # 채널(장비)별 베어링 볼 개수 입력값
        self.balls_entry = {}
        self.balls_ok = {}    # 채널별로 마지막으로 확인된 볼 개수 문자열 (처음에는 기본값)
        self.rpm_ok = {}    # 채널별로 마지막으로 확인된(1X와 맞는) 회전수 문자열
        self._busy = False  # 경고/재입력 창이 떠 있는 동안 중복 검사 방지
        self.q = queue.Queue()
        self.summary = ""

        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        self.btn = ttk.Button(top, text="분석 실행", command=self.analyze, state="disabled")
        self.btn.pack(side="left")
        self.status = tk.StringVar(value=f"채널별로 계측 파일(.xlsx)을 선택하세요 (0/{n})")
        ttk.Label(top, textvariable=self.status).pack(side="left", padx=10)

        body = ttk.PanedWindow(root, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, padding=6)
        body.add(left, weight=0)
        self.nb = ttk.Notebook(body)
        body.add(self.nb, weight=1)
        for ch in self.chs:
            row = ttk.LabelFrame(left, text=ch, padding=6)
            row.pack(fill="x", pady=4)
            ttk.Button(row, text="파일 선택", command=lambda c=ch: self.choose(c)).pack(anchor="w")
            self.file_var[ch] = tk.StringVar(value="(미선택)")
            ttk.Label(row, textvariable=self.file_var[ch], wraplength=220).pack(anchor="w")
            rrow = ttk.Frame(row)
            rrow.pack(anchor="w", pady=(4, 0))
            ttk.Label(rrow, text="회전수").pack(side="left")
            self.rpm_var[ch] = tk.StringVar(value="")   # 파일을 고르면 신호의 1X에 맞는 rpm으로 채움
            self.rpm_entry[ch] = ttk.Entry(rrow, textvariable=self.rpm_var[ch], width=8, justify="right")
            self.rpm_entry[ch].pack(side="left", padx=4)
            # 값을 입력하고 Enter 또는 다른 곳으로 이동하면 바로 1X와 맞는지 확인
            self.rpm_entry[ch].bind("<Return>", lambda ev, c=ch: self._check_entry(c))
            self.rpm_entry[ch].bind("<FocusOut>", lambda ev, c=ch: self._check_entry(c))
            ttk.Label(rrow, text="rpm").pack(side="left")
            brow = ttk.Frame(row)
            brow.pack(anchor="w", pady=(4, 0))
            ttk.Label(brow, text="베어링 볼 개수").pack(side="left")
            self.balls_var[ch] = tk.StringVar(value=str(DEFAULT_BALLS.get(ch, 1)))
            self.balls_entry[ch] = ttk.Entry(brow, textvariable=self.balls_var[ch], width=5, justify="right")
            self.balls_entry[ch].pack(side="left", padx=4)
            self.balls_ok[ch] = self.balls_var[ch].get()
            # 값을 입력하고 Enter 또는 다른 곳으로 이동하면 바로 기본값과 다른지 확인
            self.balls_entry[ch].bind("<Return>", lambda ev, c=ch: self._check_balls(c))
            self.balls_entry[ch].bind("<FocusOut>", lambda ev, c=ch: self._check_balls(c))
            ttk.Label(brow, text="개").pack(side="left")
            ttk.Label(row, text="(1이면 베어링 주파수 미사용)", foreground="gray").pack(anchor="w")
            self._make_channel_tab(ch)
        self._make_result_tab()

    # --- 채널 탭: 데이터 표 + 시간 신호 그래프 ---
    def _make_channel_tab(self, ch):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=ch)
        tree = ttk.Treeview(f, columns=("t", "v"), show="headings")
        tree.heading("t", text="time_s")
        tree.heading("v", text="velocity_mm_s")
        tree.column("t", width=100, anchor="e")
        tree.column("v", width=120, anchor="e")
        sb = ttk.Scrollbar(f, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="y")
        sb.pack(side="left", fill="y")
        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True)
        note = tk.StringVar(value="파일을 선택하면 데이터와 시간 신호가 표시됩니다.")
        ttk.Label(right, textvariable=note).pack(anchor="w", padx=6, pady=4)
        fig = self.Figure(figsize=(7, 4))
        canvas = self.Canvas(fig, master=right)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.tabs[ch] = dict(frame=f, tree=tree, note=note, fig=fig, canvas=canvas)

    def choose(self, ch, path=None):
        if not path:
            path = filedialog.askopenfilename(
                title=f"{ch} 계측 파일 선택", filetypes=[("Excel", "*.xlsx")],
                initialdir=str(DATA_DIR if DATA_DIR.exists() else Path.cwd()))
        if not path:
            return
        try:
            tt, x = read_xlsx(path)
        except Exception as e:
            messagebox.showerror("파일 읽기 실패", f"{Path(path).name}\n\n{e}")
            return
        self.data[ch] = (tt, x, path)
        self.file_var[ch].set(Path(path).name)
        rpm = str(detect_rpm(x))   # 신호의 1X와 연결되는 회전수로 미리 채움 (수정 가능)
        self.rpm_var[ch].set(rpm)
        self.rpm_ok[ch] = rpm
        self._show_channel(ch)
        self.nb.select(self.tabs[ch]["frame"])
        k = len(self.data)
        self.status.set(f"파일 선택 {k}/{self.n}" + (" - '분석 실행'을 누르세요" if k == self.n else ""))
        self.btn.config(state="normal" if k == self.n else "disabled")

    def _show_channel(self, ch):
        t = self.tabs[ch]
        tt, x, path = self.data[ch]
        tree = t["tree"]
        tree.delete(*tree.get_children())
        for a, b in zip(tt[:MAX_ROWS], x[:MAX_ROWS]):
            tree.insert("", "end", values=(f"{a:.6f}", f"{b:.5f}"))
        t["note"].set(f"{Path(path).name} · 전체 {tt.size}행 중 앞 {min(MAX_ROWS, tt.size)}행 표시")
        fig = t["fig"]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(tt, x, lw=0.6)
        ylim, step = nice_ylim(x)
        ax.set_ylim(-ylim, ylim)
        ax.set_yticks(np.arange(-ylim, ylim + step / 2, step))
        ax.set_xlim(tt[0], tt[-1])
        ax.axhline(0, color="k", lw=0.6)
        ax.grid(alpha=0.3)
        ax.set_title(f"{ch} 시간 신호")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Velocity (mm/s)")
        fig.tight_layout()
        t["canvas"].draw()

    # --- 분석 결과 탭: FFT 그림 + 판정 표 + 진단 설명 ---
    def _make_result_tab(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="분석 결과")
        self.res_frame = f
        self.text = tk.Text(f, height=10, wrap="word")
        self.text.pack(side="bottom", fill="x")
        cols = ("ch", "rpm", "balls", "rms", "ok", "a1", "a2", "brg", "diag")
        self.table = ttk.Treeview(f, columns=cols, show="headings", height=self.n)
        for c, title, w in (("ch", "채널", 60), ("rpm", "회전수 (rpm)", 90), ("balls", "볼 개수", 60),
                            ("rms", "최대 피크 RMS (mm/s)", 140),
                            ("ok", f"기준 (≤{RMS_LIMIT})", 100), ("a1", "1X RMS", 70),
                            ("a2", "2X RMS", 70), ("brg", "BPFO RMS", 80), ("diag", "결함 진단", 200)):
            self.table.heading(c, text=title)
            self.table.column(c, width=w, anchor="center")
        self.table.tag_configure("bad", foreground="#c0392b")
        self.table.tag_configure("warn", foreground="#d68910")
        self.table.tag_configure("good", foreground="#1e8449")
        self.table.pack(side="bottom", fill="x")
        self.res_fig = self.Figure(figsize=(9, 5))
        self.res_canvas = self.Canvas(self.res_fig, master=f)
        self.res_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._set_text("채널별 파일을 선택한 뒤 '분석 실행'을 누르면 FFT 결과와 판정이 표시됩니다.")

    def _set_text(self, s):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", s)

    def _read_rpm(self, ch):
        """채널의 회전수 입력값을 검증해 반환. 1X가 신호와 안 맞으면 경고 후 다시 입력받음. 취소/오류면 None"""
        x = self.data[ch][1]
        while True:
            self.nb.select(self.tabs[ch]["frame"])
            try:
                rpm = float(self.rpm_var[ch].get().replace(",", ""))
                if not 0 < rpm <= 20000:
                    raise ValueError
            except ValueError:
                messagebox.showerror("회전수 입력 오류", f"{ch}: 회전수(rpm)는 0 초과 20000 이하의 숫자여야 합니다.")
                self.rpm_entry[ch].focus_set()
                return None
            mm = rpm_mismatch(x, rpm)
            if mm is None:
                rpm = int(rpm) if rpm.is_integer() else rpm
                self.rpm_var[ch].set(str(rpm))
                self.rpm_ok[ch] = str(rpm)
                return rpm
            messagebox.showwarning(
                "회전수 확인", f"{ch}: 입력한 회전수 {rpm:g} rpm(1X = {mm[0]:.1f} Hz)에서 "
                f"신호의 뚜렷한 피크가 보이지 않습니다.\n(신호의 최대 피크 주파수: {mm[1]:.1f} Hz)\n\n"
                "회전수를 다시 확인해 주세요.")
            new = simpledialog.askfloat("회전수 다시 입력", f"{ch} 회전수(rpm)를 다시 입력하세요",
                                        parent=self.root, initialvalue=self.rpm_ok.get(ch, rpm),
                                        minvalue=1, maxvalue=20000)
            if new is None:   # 취소
                self.rpm_entry[ch].focus_set()
                return None
            self.rpm_var[ch].set(f"{new:g}")

    def _read_balls(self, ch):
        """채널의 베어링 볼 개수 입력값을 검증해 반환 (1~100의 정수).
        기본값과 다르면 확인창을 띄우고, 아니오면 다시 입력받음. 오류/취소면 None"""
        default = DEFAULT_BALLS.get(ch, 1)
        while True:
            self.nb.select(self.tabs[ch]["frame"])
            try:
                balls = int(self.balls_var[ch].get().strip())
                if not 1 <= balls <= 100:
                    raise ValueError
            except ValueError:
                messagebox.showerror("볼 개수 입력 오류", f"{ch}: 베어링 볼 개수는 1~100 사이의 정수여야 합니다.\n"
                                     "(1이면 베어링 주파수를 사용하지 않습니다)")
                self.balls_entry[ch].focus_set()
                return None
            if balls == default or str(balls) == self.balls_ok.get(ch):   # 기본값이거나 이미 확인한 값
                self.balls_var[ch].set(str(balls))
                self.balls_ok[ch] = str(balls)
                return balls
            if messagebox.askyesno(
                    "볼 개수 확인", f"{ch}: 입력한 볼 개수 {balls}개가 기본값 {default}개와 다릅니다.\n\n"
                    "입력한 값이 맞습니까?\n(아니오를 누르면 다시 입력합니다)"):
                self.balls_ok[ch] = str(balls)
                return balls
            new = simpledialog.askinteger("볼 개수 다시 입력", f"{ch} 베어링 볼 개수를 다시 입력하세요",
                                          parent=self.root, initialvalue=default, minvalue=1, maxvalue=100)
            if new is None:   # 취소
                self.balls_entry[ch].focus_set()
                return None
            self.balls_var[ch].set(str(new))

    def _check_balls(self, ch):
        """볼 개수 입력칸에서 값이 바뀌면 바로 확인. 취소/오류면 이전에 확인된 값으로 복원"""
        if self._busy or self.balls_var[ch].get().strip() == self.balls_ok.get(ch):
            return
        self._busy = True
        try:
            if self._read_balls(ch) is None:
                self.balls_var[ch].set(self.balls_ok.get(ch, str(DEFAULT_BALLS.get(ch, 1))))
        finally:
            self._busy = False

    def _check_entry(self, ch):
        """회전수 입력칸에서 값이 바뀌면 바로 검사. 1X와 안 맞으면 경고 후 재입력, 취소하면 이전 값으로 복원"""
        if self._busy or ch not in self.data or self.rpm_var[ch].get() == self.rpm_ok.get(ch):
            return
        self._busy = True
        try:
            if self._read_rpm(ch) is None:
                self.rpm_var[ch].set(self.rpm_ok.get(ch, ""))
        finally:
            self._busy = False

    def analyze(self):
        rpms = {}
        for ch in self.chs:
            rpm = self._read_rpm(ch)
            if rpm is None:
                return
            rpms[ch] = rpm
        balls = {}
        for ch in self.chs:
            balls[ch] = self._read_balls(ch)
            if balls[ch] is None:
                return
        RPM.clear()
        RPM.update(rpms)
        BALLS.clear()
        BALLS.update(balls)
        SIGNALS.clear()
        SIGNALS.update({ch: self.data[ch][1] for ch in self.chs})
        results = {ch: analyze_signal(ch) for ch in self.chs}
        verdicts = {ch: rule_verdict(r) for ch, r in results.items()}

        fig = self.res_fig
        fig.clear()
        cols = min(self.n, 2)
        rows = -(-self.n // cols)
        for i, ch in enumerate(self.chs):
            draw_spectrum(fig.add_subplot(rows, cols, i + 1), SIGNALS[ch],
                          f"{ch} ({RPM[ch]} rpm): {verdicts[ch]}", RPM[ch], BALLS[ch])
        fig.supxlabel(XLABEL, fontsize=8)
        fig.tight_layout()
        self.res_canvas.draw()

        self.table.delete(*self.table.get_children())
        lines = []
        for ch, r in results.items():
            ok = r["peak_rms_mm_s"] <= r["rms_limit_mm_s"]
            tag = "bad" if not ok else ("good" if verdicts[ch] == "정상" else "warn")
            applied = r["bearing_BPFO_hz"] is not None   # 볼 개수 2 이상: 베어링 주파수 사용
            self.table.insert("", "end", tags=(tag,), values=(
                ch, r["rpm"], r["bearing_balls"], r["peak_rms_mm_s"], "만족" if ok else "불만족",
                r["rms_1X"], r["rms_2X"], r["rms_bearing_BPFO"] if applied else "-", verdicts[ch]))
            bearing = (f"BPFO {r['bearing_BPFO_hz']} Hz, BPFO/1X {r['ratio_bearing_over_1X']}" if applied
                       else "베어링 주파수 미사용(볼 1개)")
            lines.append(f"{ch} [{r['rpm']} rpm, 1X {r['shaft_1X_hz']} Hz]: {verdicts[ch]}  "
                         f"(최대 피크 RMS {r['peak_rms_mm_s']} @ {r['peak_freq_hz']} Hz / 기준 {r['rms_limit_mm_s']}, "
                         f"2X/1X {r['ratio_2X_over_1X']}, {bearing})")
        self.summary = "[규칙 기반 판정]\n" + "\n".join(lines)
        self.nb.select(self.res_frame)

        if self.use_agent:
            self._set_text(self.summary + "\n\n[Claude 에이전트 분석 중...]")
            self.btn.config(state="disabled")
            self.status.set("에이전트 분석 중...")
            import threading
            threading.Thread(target=self._agent_worker, daemon=True).start()
            self.root.after(100, self._poll)
        else:
            self._set_text(self.summary)
            self.status.set("분석 완료")

    def _agent_worker(self):
        try:
            self.q.put(("done", run_agent(emit=lambda m: self.q.put(("log", m)))))
        except Exception as e:  # API 오류 등: 규칙 기반 결과는 이미 표시됨
            self.q.put(("error", str(e)))

    def _poll(self):
        import queue
        try:
            while True:
                kind, msg = self.q.get_nowait()
                if kind == "log":
                    self.status.set(msg[:100])
                    continue
                if kind == "done":
                    self._set_text(self.summary + "\n\n[Claude 에이전트 진단]\n" + msg)
                else:
                    self._set_text(self.summary + f"\n\n[에이전트 호출 실패 - 규칙 기반 결과만 표시]\n{msg}")
                self.status.set("분석 완료")
                self.btn.config(state="normal")
                return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


CHANNEL_RANGE = 32   # 안내 문구에 표시하는 채널 범위 (1~32)
MAX_CHANNELS = 4     # 지금은 가상 데이터(CH1~CH4) 4채널까지만 지원


def ask_channel_count(root):
    """채널 개수를 입력받음. MAX_CHANNELS 초과 시 경고 후 다시 입력받고, 취소하면 None"""
    while True:
        n = simpledialog.askinteger("채널 개수", f"분석할 채널 개수를 입력하세요 (1~{CHANNEL_RANGE})",
                                    parent=root, minvalue=1)
        if n is None:
            return None
        if n > MAX_CHANNELS:
            messagebox.showwarning("채널 개수", f"지금은 {MAX_CHANNELS}채널까지만 가능합니다")
            continue
        return n


def run_ui(use_agent=False):
    if tk is None:
        sys.exit("tkinter를 사용할 수 없는 환경입니다")
    set_korean_font()
    root = tk.Tk()
    root.withdraw()
    n = ask_channel_count(root)
    if not n:
        root.destroy()
        return
    root.title("진동 진단 에이전트")
    root.geometry("1250x800")
    VibeUI(root, n, use_agent)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    # Windows 콘솔(cp949 등)에서도 한글이 깨지지 않도록 UTF-8 출력 강제
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")
    if "--ui" in sys.argv:
        run_ui(use_agent="--offline" not in sys.argv and bool(os.getenv("ANTHROPIC_API_KEY")))
        sys.exit()
    if "--make-data" in sys.argv:
        make_data()
        SIGNALS.update(load_signals())
    if not SIGNALS:
        sys.exit("계측 데이터 없음: `uv run python vibe_agent.py --make-data` 먼저 실행")
    if "--plot" in sys.argv:
        plot_all()
    if "--offline" in sys.argv or not os.getenv("ANTHROPIC_API_KEY"):
        run_offline()
    else:
        print(run_agent())
