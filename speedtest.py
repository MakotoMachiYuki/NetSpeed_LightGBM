"""Streamlit wrapper for the in-browser Cloudflare speedtest (speedtest.js).

Uses ``st.components.v2`` (no iframe, no build step) so the widget is
bidirectional: the browser sends the measured metrics back to Python and
Python sends the LightGBM classification back to the widget.
"""

from __future__ import annotations

import streamlit as st

import api
import config as cfg


def _read(path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


_cached_mtime: float | None = None
_cached_component = None


def _get_component():
    """Return the component callable, re-registering when speedtest.js is saved."""
    global _cached_mtime, _cached_component
    mtime = cfg.SPEEDTEST_JS_PATH.stat().st_mtime if cfg.SPEEDTEST_JS_PATH.exists() else 0.0
    if _cached_component is None or _cached_mtime != mtime:
        # isolate_styles=False -> the widget lives in the page DOM, so it is styled by
        # the global style.css (all classes are prefixed with `sp-`).
        _cached_component = st.components.v2.component(
            "cloudflare_speedtest",
            js=_read(cfg.SPEEDTEST_JS_PATH),
            isolate_styles=False,
        )
        _cached_mtime = mtime
    return _cached_component


def speedtest(prediction: dict | None = None, error: str | None = None, key: str = "speedtest"):
    """Mount the widget.

    Returns a ComponentResult with:
      * ``result`` – persistent state: last finished test payload (dict) or None
      * ``detail`` – transient trigger: set when "View details" is clicked
    """
    comp = _get_component()
    return comp(
        key=key,
        data={"prediction": prediction, "error": error, "config": api.get_client_test_config()},
        default={"result": None},
        on_result_change=lambda: None,
        on_detail_change=lambda: None,
    )
