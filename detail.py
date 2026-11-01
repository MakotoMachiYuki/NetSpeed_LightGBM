"""Detail pop-up: classification details + the user's speedtest data."""

from __future__ import annotations

import html

import streamlit as st

import api
import config as cfg


def _fmt(v, kind: str) -> str:
    if v is None:
        return "–"
    if kind == "mbps":
        return f"{v / 1000:,.2f}"
    if kind == "ms":
        return f"{v:,.0f}"
    if kind == "int":
        return f"{int(v):,}"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    return f"{v:.4f}"


def _data_table(last: dict, year: int) -> str:
    feats = last["prediction"]["features"]
    summary = api.year_summary(year)
    loc = last.get("location")
    cols = [
        ("Download (Mbps)", "avg_d_kbps", "mbps"),
        ("Upload (Mbps)", "avg_u_kbps", "mbps"),
        ("Latency (ms)", "avg_lat_ms", "ms"),
        ("DL Latency (ms)", "avg_lat_down_ms", "ms"),
        ("UL Latency (ms)", "avg_lat_up_ms", "ms"),
    ]
    rows: list[tuple[str, dict | None, str]] = [("Your speedtest", feats, "dt-you")]
    if loc:
        near = api.nearby(year, round(float(loc["lat"]), 5), round(float(loc["lon"]), 5))
        nt = near["nearest"]
        rows.append((f"Nearest tile · {nt['quality']} ({nt['dist_km']:.2f} km)", nt, ""))
    label = last["prediction"]["label"]
    rows.append((f"{label} class avg · {year}", summary["mean_by_class"].get(label), ""))
    rows.append((f"Indonesia avg · {year}", summary["mean_all"], ""))

    head = (
        "<tr><th>Source</th>"
        + "".join(f'<th><span class="dt-metric-pill">{name}</span></th>' for name, _, _ in cols)
        + "</tr>"
    )
    body = ""
    for title, src, cls in rows:
        row_cls = f' class="{cls}"' if cls else ""
        cells = []
        for _, key, kind in cols:
            val = src.get(key) if src else None
            cells.append(f"<td>{_fmt(val, kind)}</td>")
        body += f"<tr{row_cls}><th>{html.escape(title)}</th>{''.join(cells)}</tr>"
    return (
        '<div class="dt-section">'
        f'<div class="dt-section-head"><h4>Speedtest Data</h4>'
        f'<span>Compared with Ookla {year} dataset averages</span></div>'
        f'<div class="dt-wrap"><table class="dt-table dt-data">{head}{body}</table></div>'
        "</div>"
    )


def _details_panel(last: dict, year: int) -> str:
    p, t = last["prediction"], last["test"]
    loc = last.get("location")
    meta = t.get("meta") or {}
    if loc:
        src = loc.get("label") or (
            f"GPS (±{loc.get('accuracy') or 0:.0f} m)" if loc.get("source") == "gps" else "IP-based (approx.)"
        )
        loc_txt = f"{loc['lat']:.5f}, {loc['lon']:.5f}"
        near = api.nearby(year, round(float(loc["lat"]), 5), round(float(loc["lon"]), 5))
        nt = near["nearest"]
        match = "matches" if nt["quality"] == p["label"] else "differs from"
        near_txt = f"{nt['quality']} · {html.escape(nt['province'])} <small>({match} your result)</small>"
    else:
        src, loc_txt, near_txt = "Not available", "–", "–"

    client_ip = meta.get("clientIp") or meta.get("ip") or "–"
    ip_ver = meta.get("ipVersion") or ("IPv6" if ":" in str(client_ip) else "IPv4")
    colo_code = api.format_colo(meta.get("colo"))
    server_city = meta.get("serverCity") or colo_code
    server_html = (
        f"{html.escape(str(server_city))} <small>({html.escape(colo_code)})</small>"
        if server_city != colo_code
        else html.escape(str(server_city))
    )
    org = meta.get("asOrganization") or ""
    asn = f"AS{meta['asn']}" if meta.get("asn") else ""
    net_txt = f"{html.escape(org)} <small>({asn})</small>" if org and asn else html.escape(org or asn or "–")

    left_items = [
        ("Predicted class", f'<span class="dt-cls big" style="--c:{p["color"]}">{p["label"]}</span>'),
        ("Confidence", f"{p['confidence'] * 100:.2f}%"),
        ("Inference time", f"{p['infer_ms']:.2f} ms"),
        ("Tested at", html.escape(str(last["timestamp"]))),
        ("Location", f"{loc_txt} <small>({html.escape(src)})</small>"),
        (f"Nearest tile ({year})", near_txt),
    ]
    right_items = [
        ("Your network", net_txt),
        ("Your IP address", f'<span class="dt-ip">{html.escape(str(client_ip))}</span> <small>({html.escape(ip_ver)})</small>'),
        ("Server location", server_html),
        (
            "Connection & Data used",
            (
                f"{'Mobile Data' if t.get('conn_type') == 'data' else 'Wi-Fi'} · "
                f"{(t.get('bytes_down', 0) + t.get('bytes_up', 0)) / 1_000_000:.1f} MB "
                f"<small>({'≤ ' + str(cfg.SPEEDTEST_DATA_MAX_MB) + ' MB cap' if t.get('conn_type') == 'data' else 'Unlimited'})</small>"
            ),
        ),
        ("Jitter", f"{t.get('jitter_ms', 0)} ms"),
        ("Test duration", f"{t.get('duration_s', 0)} s"),
    ]

    def _render_col(pairs: list[tuple[str, str]]) -> str:
        return "".join(f'<div class="dt-kv"><span>{k}</span><b>{v}</b></div>' for k, v in pairs)

    return (
        '<div class="dt-panel">'
        '<div class="dt-section-head"><h4>Classification Details</h4>'
        '<span>LightGBM prediction, location &amp; network metadata</span></div>'
        '<div class="dt-kv-grid">'
        f'<div class="dt-kv-col">{_render_col(left_items)}</div>'
        f'<div class="dt-kv-col">{_render_col(right_items)}</div>'
        "</div>"
        "</div>"
    )


@st.dialog("Classification Details", width="large")
def show(last: dict, year: int) -> None:
    st.html(_details_panel(last, year) + _data_table(last, year))
