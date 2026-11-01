"""Entry point for the Streamlit application.

Run with:
    streamlit run main.py
"""

from __future__ import annotations

import streamlit as st

import api
import config as cfg
import documentation
import header
import homepage

st.set_page_config(
    page_title=cfg.APP_NAME,
    page_icon=cfg.APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _init_state() -> None:
    st.session_state.setdefault("view", "home")
    st.session_state.setdefault("year", cfg.DEFAULT_YEAR)
    st.session_state.setdefault("last", None)
    st.session_state.setdefault("open_detail", False)


def main() -> None:
    _init_state()

    # Pre-warm cached dataset, LightGBM bundle & font face once per server process
    api.warm_up()

    # Load embedded fot-yuruka-std.ttf @font-face + global stylesheet (style.css)
    font_css = api.font_face_css()
    if font_css:
        st.html(font_css)
    if cfg.CSS_PATH.exists():
        st.html(cfg.CSS_PATH)

    # Top header bar (Website Name + '!' / 'Go' button)
    header.render()

    # Single-page view router (no redundant page transition)
    if st.session_state.get("view") == "doc":
        documentation.render()
    else:
        homepage.render()


if __name__ == "__main__":
    main()
