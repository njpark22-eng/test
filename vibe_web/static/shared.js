// 공통 화면 함수: 배지, 판정 표, 채널 카드(FFT 스펙트럼 SVG), 탐색
const LIMIT_LABEL = "기준";

function verdictClass(v) {
  if (v === "정상") return "v-ok";
  if (v === "재계측 권장" || v === "베어링 점검 요망") return "v-warn";
  return "v-bad";
}

function fmt(n, d) { return Number(n).toFixed(d); }

// 서버에서 온 값은 HTML에 넣기 전에 이스케이프한다
function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function badge(v) { return `<span class="badge ${verdictClass(v)}">${esc(v)}</span>`; }

function nav(current) {
  const links = [["/", "판정"], ["/upload", "올리기"], ["/runs", "이력"]];
  return `<nav class="top" aria-label="메뉴">${links.map(([href, name]) =>
    `<a href="${href}"${href === current ? ' aria-current="page"' : ""}>${name}</a>`).join("")}</nav>`;
}

function table(channels) {
  const rows = channels.map(({ r, verdict }) => {
    const bearing = r.bearing_BPFO_hz === null ? "-" : fmt(r.ratio_bearing_over_1X, 2);
    return `<tr>
      <td class="ch" data-label="채널">${esc(r.channel)}</td>
      <td class="num" data-label="회전수 (rpm)">${esc(r.rpm)}</td>
      <td class="num" data-label="최대 피크 RMS (mm/s)">${fmt(r.peak_rms_mm_s, 2)} (기준 ${esc(r.rms_limit_mm_s)})</td>
      <td class="num" data-label="2X/1X">${fmt(r.ratio_2X_over_1X, 2)}</td>
      <td class="num" data-label="BPFO/1X">${bearing}</td>
      <td data-label="결함 진단">${badge(verdict)}</td>
    </tr>`;
  }).join("");
  return `<table class="cards">
    <thead><tr><th>채널</th><th class="num">회전수 (rpm)</th><th class="num">최대 피크 RMS (mm/s)</th><th class="num">2X/1X</th><th class="num">BPFO/1X</th><th>결함 진단</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function spectrum({ r, f, amp }) {
  const W = 900, H = 230, L = 52, R = 12, T = 22, B = 34;
  const fmax = f[f.length - 1];
  const ymax = Math.max(...amp, r.rms_limit_mm_s * 1.3) * 1.08;
  const X = hz => L + (W - L - R) * hz / fmax;
  const Y = a => T + (H - T - B) * (1 - a / ymax);
  const curve = f.map((hz, i) => `${i ? "L" : "M"}${X(hz).toFixed(1)},${Y(amp[i]).toFixed(1)}`).join("");

  let xt = "";
  for (let hz = 0; hz <= fmax; hz += 100) {
    xt += `<line class="axis" x1="${X(hz)}" x2="${X(hz)}" y1="${H - B}" y2="${H - B + 4}"/>`
        + `<text x="${X(hz)}" y="${H - B + 17}" text-anchor="middle">${hz}</text>`;
  }
  // 1X/2X/BPFO는 색이 아니라 선 모양과 라벨로 구분
  const marks = [
    { hz: r.shaft_1X_hz, dash: "", label: "1X" },
    { hz: 2 * r.shaft_1X_hz, dash: "6 3", label: "2X" },
  ];
  if (r.bearing_BPFO_hz !== null) marks.push({ hz: r.bearing_BPFO_hz, dash: "12 4 2 4", label: "BPFO" });
  const lines = marks.filter(m => m.hz <= fmax).map((m, i) =>
    `<line class="mark" x1="${X(m.hz)}" x2="${X(m.hz)}" y1="${T}" y2="${H - B}" stroke-dasharray="${m.dash}"/>`
    + `<text x="${X(m.hz) + 3}" y="${T + 10 + i * 12}">${m.label} ${fmt(m.hz, 1)} Hz</text>`).join("");

  const ly = Y(r.rms_limit_mm_s);
  return `<svg class="spec" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(r.channel)} FFT 스펙트럼">
    <line class="axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>
    <line class="axis" x1="${L}" x2="${L}" y1="${T}" y2="${H - B}"/>
    ${xt}
    <text x="${L - 6}" y="${H - B + 4}" text-anchor="end">0</text>
    <text x="${L - 6}" y="${T + 4}" text-anchor="end">${fmt(ymax, 0)}</text>
    <text x="${L}" y="12">RMS (mm/s)</text>
    <text x="${W - R}" y="${H - 4}" text-anchor="end">주파수 (Hz)</text>
    <path class="curve" d="${curve}"/>
    <line class="limit" x1="${L}" x2="${W - R}" y1="${ly}" y2="${ly}"/>
    <text x="${W - R}" y="${ly - 4}" text-anchor="end">${LIMIT_LABEL} ${esc(r.rms_limit_mm_s)} mm/s</text>
    ${lines}
  </svg>`;
}

// 이력 상세: 판정 근거, 인사이트, 그래프 읽기 (서버가 저장된 값으로 만든 문구)
function insightHtml(c) {
  const i = c.insight;
  if (!i) return "";
  const list = items => `<ul>${items.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`;
  return `<div class="insight">
    <h3>판정 근거</h3>${list(i.basis)}
    <h3>인사이트</h3><p>${esc(i.meaning)}</p><p><strong>조치</strong> ${esc(i.action)}</p>
    <h3>그래프 읽기</h3>${list(i.graph)}
  </div>`;
}

function summaryHtml(s) {
  if (!s) return "";
  const items = s.priorities.map(t => `<li>${esc(t)}</li>`).join("");
  return `<section class="summary"><h2>요약</h2><p>${esc(s.headline)}</p>
    ${items ? `<p class="note">우선순위</p><ol>${items}</ol>` : ""}<p class="note">${esc(s.note)}</p></section>`;
}

function card(c) {
  const { r, verdict } = c;
  const bearing = r.bearing_BPFO_hz === null ? "베어링 미사용" : `볼 ${esc(r.bearing_balls)}개`;
  const note = verdict === "재계측 권장"
    ? `<p class="remeasure">2 Hz 미만 저주파 노이즈(${fmt(r.lowfreq_noise_rms, 1)} mm/s)가 커서 1X와 2X를 가립니다. 센서 부착 상태와 케이블을 확인한 뒤 다시 계측하세요.</p>`
    : "";
  const hash = c.sha256 ? `<p class="hash">원본 SHA-256 ${esc(c.sha256)}</p>` : "";
  return `<section class="card">
    <header><span class="name">${esc(r.channel)}</span>${badge(verdict)}
      <span class="meta">${esc(r.rpm)} rpm · 1X ${fmt(r.shaft_1X_hz, 1)} Hz · ${bearing}</span></header>
    ${note}${spectrum(c)}${insightHtml(c)}${hash}</section>`;
}
