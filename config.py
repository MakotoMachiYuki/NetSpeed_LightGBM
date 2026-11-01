"""Global backend configuration & constants.

Sensitive keys (such as CARTO_API_KEY) and environment overrides are loaded
strictly on the backend from `.env` / OS environment variables / `st.secrets`.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def _load_dotenv_file(path: Path) -> None:
    """Load key=value pairs from `.env` using python-dotenv with a native fallback."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=path, override=False)
    except Exception:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_dotenv_file(ENV_PATH)


def _get_env(key: str, default: str = "") -> str:
    """Read a variable from OS environment / `.env`, falling back to `st.secrets`."""
    val = os.environ.get(key)
    if val is not None and val != "":
        return val
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


def _resolve_data_path() -> Path:
    env_rel = _get_env("DATA_PATH", "")
    candidates = []
    if env_rel:
        p = Path(env_rel)
        candidates.append(p if p.is_absolute() else BASE_DIR / p)
    candidates.extend(
        [
            BASE_DIR / "Dataset" / "ookla_indonesia_only.parquet",
            BASE_DIR / "Dataset" / "ookla_indonesia_only.csv",
            BASE_DIR.parent / "Dataset" / "ookla_indonesia_only.csv",
            BASE_DIR.parent / "Dataset" / "ookla_indonesia_only.parquet",
        ]
    )
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _resolve_model_path() -> Path:
    env_rel = _get_env("MODEL_BUNDLE_PATH", "")
    candidates = []
    if env_rel:
        p = Path(env_rel)
        candidates.append(p if p.is_absolute() else BASE_DIR / p)
    candidates.extend(
        [
            BASE_DIR / "Dataset" / "lightgbm_ookla_bundle.pkl",
            BASE_DIR.parent / "Dataset" / "lightgbm_ookla_bundle.pkl",
        ]
    )
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


# ── App identity ──────────────────────────────────────────────────────────────
APP_NAME = "NetSpeed LightGBM"
APP_TAGLINE = "Speedtest & network-quality classification"
APP_ICON = "🛜"

# ── Paths ─────────────────────────────────────────────────────────────────────
DATASET_DIR = BASE_DIR / "Dataset"
FONT_DIR = BASE_DIR / "Font"
DATA_PATH = _resolve_data_path()
MODEL_BUNDLE_PATH = _resolve_model_path()
CSS_PATH = BASE_DIR / "style.css"
SPEEDTEST_JS_PATH = BASE_DIR / "speedtest.js"
FONT_PATH = (
    FONT_DIR / "fot-yuruka-std.ttf"
    if (FONT_DIR / "fot-yuruka-std.ttf").exists()
    else BASE_DIR / "fot-yuruka-std.ttf"
)
FONT_NOTO_PATH = FONT_DIR / "NotoSans-VariableFont_wdth,wght.ttf"
FONT_NOTO_ITALIC_PATH = FONT_DIR / "NotoSans-Italic-VariableFont_wdth,wght.ttf"

# ── Model (must match Dataset/model.ipynb) ────────────────────────────────────
FEATURES = [
    "avg_d_kbps",
    "avg_u_kbps",
    "avg_lat_ms",
    "avg_lat_down_ms",
    "avg_lat_up_ms",
    "tests",
    "devices",
]
LABEL_MAPPING = {"Bad": 0, "Serviceable": 1, "Average": 2, "Good": 3, "Great": 4}
CLASS_NAMES = list(LABEL_MAPPING.keys())
TEST_SIZE = float(_get_env("TEST_SIZE", "0.30"))
RANDOM_STATE = int(_get_env("RANDOM_STATE", "727"))

# A single browser speedtest = 1 test from 1 device
USER_TESTS = 1
USER_DEVICES = 1

# ── Speedtest client parameters (managed on backend) ──────────────────────────
CLOUDFLARE_SPEED_URL = _get_env("CLOUDFLARE_SPEED_URL", "https://speed.cloudflare.com")
SPEEDTEST_DOWNLOAD_S = int(_get_env("SPEEDTEST_DOWNLOAD_S", "10"))
SPEEDTEST_UPLOAD_S = int(_get_env("SPEEDTEST_UPLOAD_S", "10"))
SPEEDTEST_STREAMS = int(_get_env("SPEEDTEST_STREAMS", "4"))
SPEEDTEST_DATA_MAX_MB = int(_get_env("SPEEDTEST_DATA_MAX_MB", "60"))
SPEEDTEST_DL_MAX_MB = int(_get_env("SPEEDTEST_DL_MAX_MB", "30"))
SPEEDTEST_UL_MAX_MB = int(_get_env("SPEEDTEST_UL_MAX_MB", "30"))

# Default fallback location (resolved on backend when GPS & IP are unavailable)
DEFAULT_LAT = float(_get_env("DEFAULT_LAT", "-6.2088"))
DEFAULT_LON = float(_get_env("DEFAULT_LON", "106.8456"))

# ── Geospatial visualisation (based on Dataset/visualization.ipynb) ───────────
YEARS = [2023, 2024, 2025, 2026]
DEFAULT_YEAR = 2026
MAP_SAMPLE_PER_YEAR = int(_get_env("MAP_SAMPLE_PER_YEAR", "15000"))
LOCAL_SAMPLE_SIZE = int(_get_env("LOCAL_SAMPLE_SIZE", "5000"))
MAP_CENTER = [-2.5, 118.0]           # Indonesia
MAP_ZOOM = 5
MAP_HEIGHT = 560

# Private CARTO API key (loaded from .env / environment on the backend)
_CARTO_API_KEY = _get_env("CARTO_API_KEY", "")
_CARTO_BASEMAP_URL = _get_env(
    "CARTO_BASEMAP_URL",
    "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
)
CARTO_ATTR = "&copy; OpenStreetMap contributors, &copy; CARTO"

# Ookla tiles are zoom-16 web-mercator tiles (~610 m)
TILE_DEG = 360 / 2**16
USER_ZOOM = 15

# Colours follow the notebook palette (Bad=black, Serviceable=red, ...)
QUALITY_COLORS = {
    "Bad": "#212121",
    "Serviceable": "#e53935",
    "Average": "#fb8c00",
    "Good": "#1e88e5",
    "Great": "#43a047",
}
