"""Sinh dashboard 6 panel dạng HTML từ data/logs.jsonl theo contract config/dashboard.yaml.

Chạy:  python scripts/build_dashboard.py
Mở:    data/dashboard.html
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

CONTRACT = REPO_ROOT / "config" / "dashboard.yaml"
LOGS = REPO_ROOT / "data" / "logs.jsonl"
OUTPUT = REPO_ROOT / "data" / "dashboard.html"


def parse_ts(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def percentile(values: list[float], p: int) -> float:
    """Cùng công thức với app/metrics.py để số liệu khớp endpoint /metrics."""
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def load_records() -> list[dict]:
    if not LOGS.exists():
        return []
    records = []
    for line in LOGS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def in_window(records: list[dict], minutes: int):
    stamped = [(parse_ts(r.get("ts", "")), r) for r in records]
    stamped = [(t, r) for t, r in stamped if t is not None]
    if not stamped:
        now = datetime.now(timezone.utc)
        return [], now - timedelta(minutes=minutes), now
    end = max(t for t, _ in stamped)
    start = end - timedelta(minutes=minutes)
    kept = [r for t, r in stamped if start <= t <= end]
    return kept, start, end


def by_minute(pairs) -> list:
    buckets = defaultdict(float)
    for ts, value in pairs:
        buckets[ts.strftime("%H:%M")] += value
    return sorted(buckets.items())


# --- SVG helpers -------------------------------------------------------------

W, H = 460, 150
PAD_L, PAD_B, PAD_T = 46, 22, 12


def bar_chart(labels, values, threshold, fmt="{:.0f}") -> str:
    if not values:
        return '<div class="empty">Chưa có dữ liệu trong cửa sổ thời gian</div>'
    top = max(values)
    if threshold is not None:
        top = max(top, threshold)
    top = top * 1.15 or 1.0

    plot_w, plot_h = W - PAD_L - 8, H - PAD_B - PAD_T
    slot = plot_w / len(values)
    bw = max(2.0, min(slot * 0.68, 26.0))
    parts = ['<svg viewBox="0 0 %d %d" role="img">' % (W, H)]

    for frac in (0, 0.5, 1):
        y = PAD_T + plot_h * (1 - frac)
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (PAD_L, y, W - 8, y))
        parts.append('<text class="tick" x="%d" y="%.1f">%s</text>' % (PAD_L - 6, y + 3.5, fmt.format(top * frac)))

    for i, v in enumerate(values):
        h = (v / top) * plot_h if top else 0
        x = PAD_L + slot * i + (slot - bw) / 2
        y = PAD_T + plot_h - h
        cls = "bar breach" if (threshold is not None and v > threshold) else "bar"
        parts.append(
            '<rect class="%s" x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2"><title>%s: %s</title></rect>'
            % (cls, x, y, bw, max(h, 1), labels[i], fmt.format(v))
        )

    if threshold is not None:
        y = PAD_T + plot_h * (1 - threshold / top)
        parts.append('<line class="slo" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (PAD_L, y, W - 8, y))
        parts.append('<text class="slolabel" x="%d" y="%.1f">SLO %s</text>' % (W - 10, y - 5, fmt.format(threshold)))

    step = max(1, len(labels) // 6)
    for i in range(0, len(labels), step):
        x = PAD_L + slot * i + slot / 2
        parts.append('<text class="tick xtick" x="%.1f" y="%d">%s</text>' % (x, H - 6, labels[i]))

    parts.append("</svg>")
    return "".join(parts)


def gauge(value: float, threshold: float, direction: str, fmt="{:.2f}") -> str:
    """Thanh ngang có vạch threshold. direction='gte' nghĩa là càng cao càng tốt."""
    top = max(1.0, value * 1.2, threshold * 1.2)
    pct = min(100.0, value / top * 100)
    tpct = min(100.0, threshold / top * 100)
    ok = value >= threshold if direction == "gte" else value <= threshold
    cls = "fill" if ok else "fill breach"
    return (
        '<div class="gauge"><div class="%s" style="width:%.1f%%"></div>'
        '<div class="mark" style="left:%.1f%%"></div></div>'
        '<div class="gaugelegend"><span>0</span><span>vạch SLO %s</span><span>%s</span></div>'
        % (cls, pct, tpct, fmt.format(threshold), fmt.format(top))
    )


def status_pill(ok: bool) -> str:
    return '<span class="pill ok">ĐẠT</span>' if ok else '<span class="pill bad">VƯỢT NGƯỠNG</span>'


# --- Panels ------------------------------------------------------------------

def build_panels(records: list[dict], contract: dict) -> list[str]:
    thresholds = {p["id"]: p.get("threshold", {}) for p in contract["panels"]}
    titles = {p["id"]: p["title"] for p in contract["panels"]}
    units = {p["id"]: p.get("unit", "") for p in contract["panels"]}

    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    panels = []

    def card(pid, headline, sub, body, ok):
        return (
            '<section class="card"><header><div><h2>%s</h2>'
            '<span class="unit">đơn vị: %s</span></div>%s</header>'
            '<div class="headline">%s</div><div class="sub">%s</div>%s</section>'
            % (titles[pid], units[pid], status_pill(ok), headline, sub, body)
        )

    # 1. Latency
    lat_recs = [r for r in sent if r.get("latency_ms") is not None]
    lat = [float(r["latency_ms"]) for r in lat_recs]
    labels = [(parse_ts(r["ts"]) or datetime.now(timezone.utc)).strftime("%H:%M:%S") for r in lat_recs]
    t = thresholds["latency"]
    p50, p95, p99 = percentile(lat, 50), percentile(lat, 95), percentile(lat, 99)
    ok = p95 <= t["value"]
    panels.append(card(
        "latency",
        '<b class="%s">%s</b> <small>ms p95</small>' % ("" if ok else "danger", format(p95, ",.0f")),
        "p50 %s ms &middot; p99 %s ms &middot; ngưỡng p95 ≤ %s ms &middot; n=%d"
        % (format(p50, ",.0f"), format(p99, ",.0f"), format(t["value"], ","), len(lat)),
        bar_chart(labels, lat, float(t["value"])),
        ok,
    ))

    # 2. Traffic
    t = thresholds["traffic"]
    pairs = [(parse_ts(r["ts"]), 1.0) for r in received if parse_ts(r.get("ts", ""))]
    buckets = by_minute(pairs)
    rate = (sum(v for _, v in buckets) / len(buckets)) if buckets else 0.0
    ok = rate >= t["value"]
    panels.append(card(
        "traffic",
        '<b>%.1f</b> <small>req/phút</small>' % rate,
        "tổng %d request &middot; ngưỡng ≥ %s req/phút" % (len(received), t["value"]),
        bar_chart([k for k, _ in buckets], [v for _, v in buckets], None),
        ok,
    ))

    # 3. Errors
    t = thresholds["errors"]
    total_req = len(received)
    rate_pct = (len(failed) / total_req * 100) if total_req else 0.0
    ok = rate_pct <= t["value"]
    breakdown = Counter(r.get("error_type", "unknown") for r in failed)
    rows = "".join('<li><span>%s</span><b>%d</b></li>' % (k, v) for k, v in breakdown.most_common()) \
        or '<li class="muted"><span>Không có lỗi nào trong cửa sổ</span><b>0</b></li>'
    panels.append(card(
        "errors",
        '<b class="%s">%.2f</b> <small>%%</small>' % ("" if ok else "danger", rate_pct),
        "%d lỗi / %d request &middot; ngưỡng ≤ %s%%" % (len(failed), total_req, t["value"]),
        '<ul class="breakdown">%s</ul>%s' % (rows, gauge(rate_pct, float(t["value"]), "lte", "{:.1f}")),
        ok,
    ))

    # 4. Cost
    t = thresholds["cost"]
    cpairs = [(parse_ts(r["ts"]), float(r.get("cost_usd", 0))) for r in sent if parse_ts(r.get("ts", ""))]
    cbuckets = by_minute(cpairs)
    total_cost = sum(float(r.get("cost_usd", 0)) for r in sent)
    ok = total_cost <= t["value"]
    panels.append(card(
        "cost",
        '<b class="%s">$%.4f</b> <small>tổng</small>' % ("" if ok else "danger", total_cost),
        "ngưỡng tổng ≤ $%s &middot; trung bình $%.4f/request"
        % (t["value"], (total_cost / len(sent) if sent else 0)),
        bar_chart([k for k, _ in cbuckets], [v for _, v in cbuckets], None, "{:.3f}"),
        ok,
    ))

    # 5. Tokens
    t = thresholds["tokens"]
    tin = sum(int(r.get("tokens_in", 0)) for r in sent)
    tout = sum(int(r.get("tokens_out", 0)) for r in sent)
    ok = max(tin, tout) <= t["value"]
    panels.append(card(
        "tokens",
        '<b>%s</b> <small>tokens</small>' % format(tin + tout, ","),
        "input %s &middot; output %s &middot; ngưỡng mỗi chiều ≤ %s"
        % (format(tin, ","), format(tout, ","), format(t["value"], ",")),
        bar_chart(["input", "output"], [float(tin), float(tout)], None),
        ok,
    ))

    # 6. Quality
    t = thresholds["quality"]
    q = [float(r["quality_score"]) for r in sent if r.get("quality_score") is not None]
    mean_q = sum(q) / len(q) if q else 0.0
    ok = mean_q >= t["value"]
    panels.append(card(
        "quality",
        '<b class="%s">%.3f</b> <small>điểm trung bình</small>' % ("" if ok else "danger", mean_q),
        "n=%d &middot; ngưỡng ≥ %s" % (len(q), t["value"]),
        gauge(mean_q, float(t["value"]), "gte") + bar_chart(labels, q, None, "{:.2f}"),
        ok,
    ))

    return panels


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0f1117;color:#e6e8ee;font:14px/1.5 "Segoe UI",Roboto,system-ui,sans-serif}
.wrap{max-width:1480px;margin:0 auto;padding:22px}
.top{display:flex;flex-wrap:wrap;gap:14px;align-items:baseline;justify-content:space-between;
     border-bottom:1px solid #262a36;padding-bottom:14px;margin-bottom:20px}
h1{margin:0;font-size:21px;letter-spacing:.2px}
.meta{color:#8b93a7;font-size:12.5px;display:flex;gap:16px;flex-wrap:wrap}
.meta b{color:#c3cadb;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:16px}
.card{background:#161a23;border:1px solid #262a36;border-radius:10px;padding:15px 16px 12px}
.card header{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px}
h2{margin:0;font-size:14.5px;font-weight:600;color:#e6e8ee}
.unit{font-size:11.5px;color:#7d8598}
.headline{font-size:15px;margin-top:6px}
.headline b{font-size:30px;font-weight:650;color:#5fb3f5;letter-spacing:-.5px}
.headline b.danger{color:#ff6b6b}
.headline small{color:#8b93a7;font-size:12.5px;margin-left:3px}
.sub{color:#8b93a7;font-size:12px;margin:3px 0 10px}
.pill{font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap;letter-spacing:.4px}
.pill.ok{background:#12331f;color:#4ade80;border:1px solid #1d5233}
.pill.bad{background:#3a1418;color:#ff8080;border:1px solid #5e1f26}
svg{width:100%;height:auto;display:block}
line.grid{stroke:#242938;stroke-width:1}
.bar{fill:#3d7fd6}
.bar.breach{fill:#e0525f}
.slo{stroke:#f5a524;stroke-width:1.6;stroke-dasharray:5 4}
.slolabel{fill:#f5a524;font-size:10px;text-anchor:end;font-weight:600}
.tick{fill:#6c7488;font-size:9.5px;text-anchor:end}
.xtick{text-anchor:middle}
.breakdown{list-style:none;margin:0 0 10px;padding:0;font-size:12.5px}
.breakdown li{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #212634}
.breakdown li.muted{color:#6c7488}
.gauge{position:relative;height:11px;background:#212634;border-radius:6px;overflow:hidden;margin-top:6px}
.gauge .fill{height:100%;background:#3d7fd6;border-radius:6px}
.gauge .fill.breach{background:#e0525f}
.gauge .mark{position:absolute;top:-3px;width:2px;height:17px;background:#f5a524}
.gaugelegend{display:flex;justify-content:space-between;color:#6c7488;font-size:10.5px;margin:4px 0 8px}
.empty{color:#6c7488;font-size:12.5px;padding:26px 0;text-align:center}
footer{color:#6c7488;font-size:11.5px;margin-top:20px;border-top:1px solid #262a36;padding-top:12px}
"""


def main() -> None:
    configure_utf8_stdio()
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["dashboard"]
    window = int(contract.get("time_range_minutes", 60))
    refresh = int(contract.get("refresh_seconds", 30))

    all_records = load_records()
    records, start, end = in_window(all_records, window)
    panels = build_panels(records, contract)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    meta = (
        '<span>Time range: <b>%d phút</b> (%s → %s UTC)</span>'
        '<span>Auto refresh: <b>%ds</b></span>'
        '<span>Nguồn: <b>data/logs.jsonl</b></span>'
        '<span>Bản ghi trong cửa sổ: <b>%d</b></span>'
        % (window, start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"), refresh, len(records))
    )

    html = (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="%d">'
        '<title>%s</title><style>%s</style></head><body><div class="wrap">'
        '<div class="top"><h1>%s</h1><div class="meta">%s</div></div>'
        '<div class="grid">%s</div>'
        '<footer>Sinh lúc %s bằng scripts/build_dashboard.py &middot; '
        'panel, đơn vị và threshold lấy trực tiếp từ config/dashboard.yaml &middot; '
        'vạch cam = SLO/threshold, cột đỏ = vượt ngưỡng</footer>'
        '</div></body></html>'
        % (refresh, contract["title"], CSS, contract["title"], meta, "".join(panels), generated)
    )

    OUTPUT.write_text(html, encoding="utf-8")
    print("Đã sinh dashboard: %s" % OUTPUT)
    print("Cửa sổ %d phút: %d/%d bản ghi" % (window, len(records), len(all_records)))


if __name__ == "__main__":
    main()
