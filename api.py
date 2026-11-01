"""Backend layer: dataset, LightGBM model, evaluation metrics, geo look-ups.

Everything heavy is cached with ``st.cache_resource`` so it is computed only
once per server process and shared by every user session.
"""

from __future__ import annotations

import html
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split

import config as cfg

EARTH_RADIUS_KM = 6371.0088


# ══════════════════════════════════════════════════════════════════════════════
# Loading
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def load_dataset() -> pd.DataFrame:
    """Load the Ookla Indonesia dataset (supports Parquet or CSV)."""
    if cfg.DATA_PATH.suffix.lower() == ".parquet":
        df = pd.read_parquet(cfg.DATA_PATH)
    else:
        try:
            df = pd.read_csv(cfg.DATA_PATH, engine="pyarrow")
        except Exception:  # pyarrow not available -> default engine
            df = pd.read_csv(cfg.DATA_PATH)
    df = df[df["quality"].isin(cfg.CLASS_NAMES)].reset_index(drop=True)
    # NOTE: the csv's own `quality_encoded` column uses a different order,
    # the model was trained with LABEL_MAPPING (Bad=0 ... Great=4).
    df["label"] = df["quality"].map(cfg.LABEL_MAPPING).astype("int8")
    return df


def get_carto_tiles_url() -> str:
    """Return the CARTO basemap URL constructed on the backend from `.env`."""
    base = cfg._CARTO_BASEMAP_URL
    key = cfg._CARTO_API_KEY
    if not key:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}key={key}"


def get_client_test_config() -> dict:
    """Public configuration passed to the in-browser speedtest runner."""
    return {
        "cf_url": cfg.CLOUDFLARE_SPEED_URL,
        "download_s": cfg.SPEEDTEST_DOWNLOAD_S,
        "upload_s": cfg.SPEEDTEST_UPLOAD_S,
        "streams": cfg.SPEEDTEST_STREAMS,
        "data_max_mb": cfg.SPEEDTEST_DATA_MAX_MB,
        "dl_max_mb": cfg.SPEEDTEST_DL_MAX_MB,
        "ul_max_mb": cfg.SPEEDTEST_UL_MAX_MB,
    }


@st.cache_resource(show_spinner=False)
def load_bundle() -> dict:
    """Load the exported LightGBM bundle (model + metadata)."""
    return joblib.load(cfg.MODEL_BUNDLE_PATH)


def get_model():
    return load_bundle()["model"]


# ══════════════════════════════════════════════════════════════════════════════
# Model evaluation 
# ══════════════════════════════════════════════════════════════════════════════
def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    labels = list(range(len(cfg.CLASS_NAMES)))
    p, r, f1, s = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    per_class = pd.DataFrame(
        {"Precision": p, "Recall": r, "F1-Score": f1, "Support": s},
        index=cfg.CLASS_NAMES,
    ).T  # rows = metric, columns = class (matches the detail mock-up)
    return {
        "per_class": per_class,
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "confusion": confusion_matrix(y_true, y_pred, labels=labels),
        "n": int(len(y_true)),
    }


@st.cache_resource(show_spinner=False)
def model_evaluation() -> dict:
    """Overall + per-year evaluation on the held-out test split."""
    df = load_dataset()
    bundle = load_bundle()
    X, y = df[cfg.FEATURES], df["label"]
    _, X_test, _, y_test = train_test_split(
        X, y, test_size=cfg.TEST_SIZE, random_state=cfg.RANDOM_STATE, stratify=y
    )
    t0 = time.perf_counter()
    y_pred = bundle["model"].predict(X_test)
    infer_s = time.perf_counter() - t0

    y_true = y_test.to_numpy()
    years = df.loc[X_test.index, "year"].to_numpy()

    result = {
        "all": _metrics(y_true, y_pred),
        "split": bundle.get("selected_split", "70:30"),
        "test_inference_s": infer_s,
        "years": {},
    }
    for yr in cfg.YEARS:
        mask = years == yr
        if mask.any():
            result["years"][yr] = _metrics(y_true[mask], y_pred[mask])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Classification of a user speedtest
# ══════════════════════════════════════════════════════════════════════════════
def build_features(test: dict) -> dict:
    """Map the browser speedtest payload to the model's feature space."""
    return {
        "avg_d_kbps": float(test.get("download_kbps") or 0),
        "avg_u_kbps": float(test.get("upload_kbps") or 0),
        "avg_lat_ms": float(test.get("latency_ms") or 0),
        "avg_lat_down_ms": float(test.get("latency_down_ms") or 0),
        "avg_lat_up_ms": float(test.get("latency_up_ms") or 0),
        "tests": cfg.USER_TESTS,
        "devices": cfg.USER_DEVICES,
    }


def classify(test: dict) -> dict:
    model = get_model()
    feats = build_features(test)
    X = pd.DataFrame([feats])[cfg.FEATURES]
    t0 = time.perf_counter()
    proba = model.predict_proba(X)[0]
    infer_ms = (time.perf_counter() - t0) * 1000
    code = int(np.argmax(proba))
    label = cfg.CLASS_NAMES[code]
    return {
        "features": feats,
        "label": label,
        "code": code,
        "confidence": float(proba[code]),
        "proba": {c: float(p) for c, p in zip(cfg.CLASS_NAMES, proba)},
        "infer_ms": infer_ms,
        "color": cfg.QUALITY_COLORS[label],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Geospatial helpers
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def year_frame(year: int) -> pd.DataFrame:
    df = load_dataset()
    return df[df["year"] == year].reset_index(drop=True)


def haversine_km(lat, lon, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    lat1, lon1 = np.radians(lat), np.radians(lon)
    lat2, lon2 = np.radians(lats), np.radians(lons)
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


@st.cache_data(show_spinner=False, max_entries=64)
def nearby(year: int, lat: float, lon: float) -> dict:
    """Nearest tile to a user location."""
    d = year_frame(year)
    dist = haversine_km(lat, lon, d["tile_y"].to_numpy(), d["tile_x"].to_numpy())
    nearest_idx = int(np.argmin(dist))
    nearest = d.iloc[nearest_idx]

    return {
        "nearest": {
            "lat": float(nearest["tile_y"]),
            "lon": float(nearest["tile_x"]),
            "dist_km": float(dist[nearest_idx]),
            "quality": str(nearest["quality"]),
            "province": str(nearest["Provinsi"]),
            **{f: float(nearest[f]) for f in cfg.FEATURES},
        },
    }


@st.cache_data(show_spinner=False)
def year_summary(year: int) -> dict:
    d = year_frame(year)
    return {
        "n": int(len(d)),
        "counts": d["quality"].value_counts().reindex(cfg.CLASS_NAMES, fill_value=0).to_dict(),
        "mean_all": d[cfg.FEATURES].mean().to_dict(),
        "mean_by_class": d.groupby("quality")[cfg.FEATURES].mean().to_dict("index"),
    }


def _balanced_sample(d: pd.DataFrame, target: int) -> pd.DataFrame:
    """Sample `target` rows from `d`:
    - Includes 100% of the lowest class (e.g. Great = 578)
    - Allocates the remaining quota across the other classes using square-root
      proportional weights so Average keeps the highest ratio while all classes
      remain well-represented (Great < Good < Bad < Serviceable < Average).
    """
    target = min(target, len(d))
    counts = d["quality"].value_counts()
    if counts.empty or target <= 0:
        return d.iloc[0:0]

    lowest_cls = str(counts.idxmin())
    quotas: dict[str, int] = {}
    take_lowest = min(int(counts[lowest_cls]), target)
    quotas[lowest_cls] = take_lowest
    remaining = target - take_lowest

    others = counts.drop(lowest_cls)
    if remaining > 0 and not others.empty:
        weights = (others ** 0.5) / (others ** 0.5).sum()
        raw = (weights * remaining).round().astype(int)
        for cls in others.index:
            quotas[str(cls)] = min(int(raw[cls]), int(others[cls]))
        diff = remaining - sum(quotas[str(c)] for c in others.index)
        if diff != 0:
            top_cls = str(others.idxmax())
            quotas[top_cls] = max(0, min(int(others[top_cls]), quotas[top_cls] + diff))

    parts = [
        grp.sample(n=quotas.get(str(cls), 0), random_state=cfg.RANDOM_STATE)
        for cls, grp in d.groupby("quality", sort=False)
        if quotas.get(str(cls), 0) > 0
    ]
    return pd.concat(parts, ignore_index=True) if parts else d.iloc[0:0]


@st.cache_data(show_spinner=False, max_entries=32)
def map_sample(
    year: int,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> pd.DataFrame:
    """Return 15k Indonesia tiles (or 5k local province/radius + 15k rest of Indonesia = 20k)."""
    d = year_frame(year)
    cols = ["tile_y", "tile_x", "quality", "Provinsi", "avg_d_kbps", "avg_u_kbps", "avg_lat_ms"]

    if user_lat is not None and user_lon is not None:
        dist = haversine_km(user_lat, user_lon, d["tile_y"].to_numpy(), d["tile_x"].to_numpy())
        nearest_idx = int(np.argmin(dist))
        local_prov = str(d.iloc[nearest_idx]["Provinsi"])

        # Prioritize tiles in the user's province ordered by distance, then closest nearby radius
        in_prov = (d["Provinsi"].to_numpy() == local_prov)
        order = np.lexsort((dist, ~in_prov))
        local_n = min(cfg.LOCAL_SAMPLE_SIZE, len(d))
        local_idx = order[:local_n]
        local_df = d.iloc[local_idx]

        rest_mask = np.ones(len(d), dtype=bool)
        rest_mask[local_idx] = False
        rest_df = d.iloc[np.where(rest_mask)[0]]
        indo_df = _balanced_sample(rest_df, cfg.MAP_SAMPLE_PER_YEAR)
        out = pd.concat([indo_df, local_df], ignore_index=True)
    else:
        out = _balanced_sample(d, cfg.MAP_SAMPLE_PER_YEAR)

    return out.sample(frac=1.0, random_state=cfg.RANDOM_STATE).reset_index(drop=True)[cols]


# ══════════════════════════════════════════════════════════════════════════════
# One-shot pipeline & backend formatters used after a speedtest finishes
# ══════════════════════════════════════════════════════════════════════════════
def _safe_float(v, default: float = 0.0, lo: float | None = None, hi: float | None = None) -> float:
    try:
        val = float(v)
        if not np.isfinite(val):
            val = default
    except (TypeError, ValueError):
        val = default
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


# Known ASN / organization coordinates in Indonesia for high-accuracy network pinning
_KNOWN_ASN_COORDS: dict[int, tuple[float, float, str]] = {
    135487: (-6.16950, 106.78910, "UNTAR · Grogol, Jakarta Barat"),
}
_KNOWN_ORG_KEYWORDS: list[tuple[str, float, float, str]] = [
    ("TARUMANAGARA", -6.16950, 106.78910, "UNTAR · Grogol, Jakarta Barat"),
    ("UNTAR", -6.16950, 106.78910, "UNTAR · Grogol, Jakarta Barat"),
]


@st.cache_data(show_spinner=False, max_entries=128)
def _geocode_network_hint(org: str, postal: str, city: str, region: str) -> tuple[float, float, str] | None:
    """Resolve organization name or postal code in Indonesia via Nominatim (backend only)."""
    import json
    import urllib.parse
    import urllib.request

    org_up = (org or "").upper()
    for kw, lat, lon, label in _KNOWN_ORG_KEYWORDS:
        if kw in org_up:
            return (lat, lon, label)

    queries: list[tuple[str, str]] = []
    if org:
        # Strip common corporate prefixes/suffixes for cleaner geocoding
        clean_org = org.replace("YAYASAN", "").replace("PT.", "").replace("PT ", "").replace("-", " ").strip()
        if clean_org:
            queries.append((f"{clean_org}, {city or region or 'Indonesia'}", f"Network ({org})"))
    if postal and (city or region):
        queries.append((f"{postal}, {city or region}, Indonesia", f"Postal {postal} ({city or region})"))

    for q, label in queries:
        try:
            url = (
                "https://nominatim.openstreetmap.org/search?"
                + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "id"})
            )
            req = urllib.request.Request(url, headers={"User-Agent": "NetSpeedLightGBM/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and isinstance(data, list):
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    if -11.5 <= lat <= 6.5 and 94.5 <= lon <= 141.5:
                        return (lat, lon, label)
        except Exception:
            continue
    return None


def resolve_location(raw_loc: dict | None, meta: dict | None) -> dict:
    """Validate and resolve user coordinates on the backend:
    1) High-accuracy GPS (<= 500 m)
    2) Network ASN / Organization / Postal code geolocation (e.g. UNTAR AS135487)
    3) Browser Wi-Fi geolocation or Cloudflare IP coordinates
    4) Backend default coordinates
    """
    loc = raw_loc if isinstance(raw_loc, dict) else {}
    m = meta if isinstance(meta, dict) else {}

    lat = loc.get("lat")
    lon = loc.get("lon")
    source = str(loc.get("source") or "")
    accuracy = _safe_float(loc.get("accuracy"), 99999.0, 0.0) if loc.get("accuracy") is not None else None

    # 1) Fine hardware/Wi-Fi GPS fix (accuracy <= 500 m)
    if lat is not None and lon is not None and source == "gps" and accuracy is not None and accuracy <= 500:
        return {
            "lat": _safe_float(lat, cfg.DEFAULT_LAT, -90.0, 90.0),
            "lon": _safe_float(lon, cfg.DEFAULT_LON, -180.0, 180.0),
            "accuracy": accuracy,
            "source": "gps",
            "label": f"GPS (±{round(accuracy)} m)",
        }

    # 2) Check ASN / Organization / Postal Code from Cloudflare network metadata
    asn_val = int(_safe_float(m.get("asn"), 0)) if m.get("asn") else 0
    org = str(m.get("asOrganization") or "").strip()
    postal = str(m.get("postalCode") or "").strip()
    city = str(m.get("city") or "").strip()
    region = str(m.get("region") or "").strip()

    if asn_val in _KNOWN_ASN_COORDS:
        k_lat, k_lon, k_lbl = _KNOWN_ASN_COORDS[asn_val]
        return {
            "lat": k_lat,
            "lon": k_lon,
            "accuracy": None,
            "source": "network",
            "label": k_lbl,
        }

    hint = _geocode_network_hint(org, postal, city, region)
    if hint is not None:
        h_lat, h_lon, h_lbl = hint
        return {
            "lat": h_lat,
            "lon": h_lon,
            "accuracy": None,
            "source": "network",
            "label": h_lbl,
        }

    # 3) Coarse browser geolocation or Cloudflare IP coordinates
    if lat is not None and lon is not None:
        lat_f = _safe_float(lat, cfg.DEFAULT_LAT, -90.0, 90.0)
        lon_f = _safe_float(lon, cfg.DEFAULT_LON, -180.0, 180.0)
        return {
            "lat": lat_f,
            "lon": lon_f,
            "accuracy": accuracy,
            "source": source if source in ("gps", "ip", "network", "default") else "ip",
            "label": f"GPS (±{round(accuracy)} m)" if accuracy else f"IP-based ({city or 'Indonesia'})",
        }

    if m.get("lat") is not None and m.get("lon") is not None:
        return {
            "lat": _safe_float(m["lat"], cfg.DEFAULT_LAT, -90.0, 90.0),
            "lon": _safe_float(m["lon"], cfg.DEFAULT_LON, -180.0, 180.0),
            "accuracy": None,
            "source": "ip",
            "label": f"IP-based ({city or 'Indonesia'})",
        }

    return {
        "lat": cfg.DEFAULT_LAT,
        "lon": cfg.DEFAULT_LON,
        "accuracy": None,
        "source": "default",
        "label": "Indonesia (default)",
    }


def format_colo(colo) -> str:
    """Format Cloudflare `colo` whether it is an IATA string or a metadata dict."""
    if isinstance(colo, dict):
        iata = colo.get("iata") or ""
        city = colo.get("city") or ""
        if iata and city:
            return f"{iata} ({city})"
        return str(iata or city or "Edge")
    return str(colo) if colo else "Edge"


def process_speedtest(test: dict) -> dict:
    """Sanitize raw speedtest measurements, resolve location, and classify on backend."""
    raw_meta = test.get("meta") if isinstance(test.get("meta"), dict) else {}
    meta = dict(raw_meta)
    if isinstance(meta.get("colo"), dict):
        colo_dict = meta["colo"]
        if not meta.get("city") and colo_dict.get("city"):
            meta["city"] = colo_dict["city"]
        meta["colo"] = format_colo(colo_dict)
    conn_type = "data" if str(test.get("conn_type")).lower() == "data" else "wifi"
    clean_test = {
        "id": test.get("id"),
        "conn_type": conn_type,
        "download_kbps": round(_safe_float(test.get("download_kbps"), 0.0, 0.0)),
        "upload_kbps": round(_safe_float(test.get("upload_kbps"), 0.0, 0.0)),
        "latency_ms": round(_safe_float(test.get("latency_ms"), 1.0, 0.0)),
        "latency_down_ms": round(_safe_float(test.get("latency_down_ms") or test.get("latency_ms"), 1.0, 0.0)),
        "latency_up_ms": round(_safe_float(test.get("latency_up_ms") or test.get("latency_ms"), 1.0, 0.0)),
        "jitter_ms": round(_safe_float(test.get("jitter_ms"), 0.0, 0.0), 1),
        "bytes_down": int(_safe_float(test.get("bytes_down"), 0.0, 0.0)),
        "bytes_up": int(_safe_float(test.get("bytes_up"), 0.0, 0.0)),
        "duration_s": round(_safe_float(test.get("duration_s"), 0.0, 0.0), 1),
        "meta": meta,
    }
    location = resolve_location(test.get("location"), meta)
    clean_test["location"] = location
    pred = classify(clean_test)
    return {
        "id": clean_test["id"],
        "test": clean_test,
        "prediction": pred,
        "location": location,
        "timestamp": datetime.now().strftime("%d %b %Y, %H:%M:%S"),
    }


def format_widget_prediction(last: dict | None) -> dict | None:
    """Prepare the safe display payload sent back to the speedtest widget."""
    if not last:
        return None
    p, t = last["prediction"], last["test"]
    loc = last.get("location") or {}
    meta = t.get("meta") or {}
    city = meta.get("city")
    if not city and isinstance(meta.get("colo"), dict):
        city = meta["colo"].get("city")
    src = loc.get("label") or (
        f"GPS (±{round(loc.get('accuracy') or 0)} m)"
        if loc.get("source") == "gps"
        else f"IP-based ({city or 'Indonesia'})"
        if loc.get("source") == "ip"
        else "Indonesia (default)"
    )
    colo = format_colo(meta.get("colo"))
    server_city = meta.get("serverCity") or city or colo
    asn_str = f"AS{meta['asn']}" if meta.get("asn") else ""
    org_str = meta.get("asOrganization") or ""
    network_str = f"{org_str} ({asn_str})" if org_str and asn_str else (org_str or asn_str or "–")
    client_ip = meta.get("clientIp") or meta.get("ip") or "–"
    ip_ver = meta.get("ipVersion") or ("IPv6" if ":" in str(client_ip) else "IPv4")
    conn_lbl = "Mobile Data" if t.get("conn_type") == "data" else "Wi-Fi"
    used_mb = (t.get("bytes_down", 0) + t.get("bytes_up", 0)) / 1_000_000
    return {
        "id": last["id"],
        "conn_type": t.get("conn_type", "wifi"),
        "label": p["label"],
        "color": p["color"],
        "confidence": p["confidence"],
        "download": t["download_kbps"] / 1000,
        "upload": t["upload_kbps"] / 1000,
        "ping": t["latency_ms"],
        "speed_html": (
            f'<span class="sp-dl">&#8595; {t["download_kbps"] / 1000:.1f}</span>'
            f' / <span class="sp-ul">&#8593; {t["upload_kbps"] / 1000:.1f}</span> <small>Mbps</small>'
        ),
        "loaded_html": (
            f'Loaded latency <span class="sp-dl">&#8595; {t.get("latency_down_ms", t["latency_ms"])} ms</span>'
            f' · <span class="sp-ul">&#8593; {t.get("latency_up_ms", t["latency_ms"])} ms</span>'
            f' · <span class="sp-ping">jitter {t.get("jitter_ms", 0):.0f} ms</span>'
        ),
        "meta_text": f"{conn_lbl} ({used_mb:.1f} MB) · Location: {src}",
        "net_info": {
            "ip_version": ip_ver,
            "server_location": server_city,
            "network": network_str,
            "ip": client_ip,
            "location_label": src,
        },
    }


def format_pin_popup(last: dict, near: dict) -> str:
    """Build the HTML popup for the user's map pin on the backend."""
    p, t = last["prediction"], last["test"]
    nt = near["nearest"]
    return f"""
    <div class="pin-pop">
        <div class="pin-title">Your connection</div>
        <div class="pin-badge" style="--c:{p['color']}">{html.escape(p['label'])}</div>
        <div class="pin-row"><span>Download</span><b>{t['download_kbps'] / 1000:.1f} Mbps</b></div>
        <div class="pin-row"><span>Upload</span><b>{t['upload_kbps'] / 1000:.1f} Mbps</b></div>
        <div class="pin-row"><span>Latency</span><b>{t['latency_ms']} ms</b></div>
        <hr/>
        <div class="pin-row"><span>Nearest tile</span><b>{nt['quality']} · {nt['dist_km']:.2f} km</b></div>
        <div class="pin-row"><span>Province</span><b>{html.escape(nt['province'])}</b></div>
    </div>
    """


def _subset_ttf_b64(path) -> str:
    """Subset a TTF file to Latin + punctuation + arrows and return base64 string."""
    import base64

    try:
        import io
        from fontTools.subset import Options, Subsetter
        from fontTools.ttLib import TTFont

        font = TTFont(str(path))
        opt = Options()
        opt.layout_features = ["*"]
        subsetter = Subsetter(options=opt)
        subsetter.populate(
            unicodes=list(range(0x0020, 0x0250))
            + list(range(0x2000, 0x2070))
            + list(range(0x2190, 0x2200))
        )
        subsetter.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        raw = buf.getvalue()
    except Exception:
        raw = path.read_bytes()
    return base64.b64encode(raw).decode("ascii")


@st.cache_resource(show_spinner=False)
def font_face_css() -> str:
    """Build @font-face CSS for Font/fot-yuruka-std.ttf & Font/NotoSans*.ttf."""
    blocks: list[str] = []

    if cfg.FONT_PATH.exists():
        b64 = _subset_ttf_b64(cfg.FONT_PATH)
        blocks.append(
            "@font-face{"
            'font-family:"FOT-Yuruka Std";'
            'src:local("FOT-Yuruka Std UB"),local("FOT-Yuruka Std"),local("YurukaStd-UB"),'
            f'url("data:font/ttf;base64,{b64}") format("truetype");'
            "font-weight:100 900;font-style:normal;font-display:swap;"
            "}"
        )

    if cfg.FONT_NOTO_PATH.exists():
        b64_noto = _subset_ttf_b64(cfg.FONT_NOTO_PATH)
        blocks.append(
            "@font-face{"
            'font-family:"Noto Sans";'
            'src:local("Noto Sans"),'
            f'url("data:font/ttf;base64,{b64_noto}") format("truetype");'
            "font-weight:100 900;font-style:normal;font-display:swap;"
            "}"
        )

    if cfg.FONT_NOTO_ITALIC_PATH.exists():
        b64_noto_it = _subset_ttf_b64(cfg.FONT_NOTO_ITALIC_PATH)
        blocks.append(
            "@font-face{"
            'font-family:"Noto Sans";'
            'src:local("Noto Sans Italic"),'
            f'url("data:font/ttf;base64,{b64_noto_it}") format("truetype");'
            "font-weight:100 900;font-style:italic;font-display:swap;"
            "}"
        )

    return f"<style>{''.join(blocks)}</style>" if blocks else ""


def warm_up() -> None:
    """Populate the caches (called once at start-up)."""
    load_dataset()
    load_bundle()
    font_face_css()
