"""Homepage: speedtest widget + geospatial map with year selector."""

from __future__ import annotations

import html

import streamlit as st

import api
import config as cfg
import detail
import maps
from speedtest import speedtest


# ── Speedtest result handling ────────────────────────────────────────────────
def _state_result():
    """Latest finished test sent by the browser (persistent widget state)."""
    try:
        state = st.session_state.get("speedtest")
        return state.get("result") if hasattr(state, "get") else None
    except Exception:
        return None


def _handle(test) -> bool:
    """Classify a new speedtest once. Returns True when something changed."""
    if not isinstance(test, dict) or test.get("id") is None:
        return False
    last = st.session_state.get("last")
    if last and last.get("id") == test["id"]:
        return False
    try:
        st.session_state.last = api.process_speedtest(test)
        st.session_state.pop("st_error", None)
    except Exception as exc:  # keep the UI alive
        st.session_state.st_error = f"Classification failed: {exc}"
    return True


# ── Map section (fragment → changing the year reruns only this part) ─────────
@st.fragment
def map_section() -> None:
    year = st.session_state.get("year") or cfg.DEFAULT_YEAR
    last = st.session_state.get("last")
    loc = (last or {}).get("location")

    with st.container(key="map-card"):
        if loc:
            lat, lon = round(float(loc["lat"]), 5), round(float(loc["lon"]), 5)
            near = api.nearby(year, lat, lon)
            map_html = maps.build_map_html(
                year, lat, lon, last["prediction"]["label"], api.format_pin_popup(last, near)
            )
        else:
            map_html = maps.build_map_html(year)

        st.iframe(map_html, height=cfg.MAP_HEIGHT)

        with st.container(key="year-bar", horizontal=True, horizontal_alignment="center"):
            st.segmented_control(
                "Data year",
                options=cfg.YEARS,
                key="year",
                required=True,
                label_visibility="collapsed",
            )


# ── Page ──────────────────────────────────────────────────────────────────────
def render() -> None:
    _handle(_state_result())  # classify on backend before mounting -> widget gets the answer now
    last = st.session_state.get("last")

    with st.container(key="speedtest-card"):
        result = speedtest(
            prediction=api.format_widget_prediction(last),
            error=st.session_state.get("st_error"),
        )

    # Fallback if the widget state wasn't readable before mounting
    if _handle(result.get("result")):
        st.rerun()

    if result.get("detail") and st.session_state.get("last"):
        detail.show(st.session_state.last, st.session_state.get("year") or cfg.DEFAULT_YEAR)

    map_section()
