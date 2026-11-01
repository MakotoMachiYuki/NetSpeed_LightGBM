"""Header bar: website name on the left + '!' / 'Go' circular button on the right."""

from __future__ import annotations

import streamlit as st

import config as cfg


def _toggle_view() -> None:
    current = st.session_state.get("view", "home")
    st.session_state.view = "doc" if current == "home" else "home"


def render() -> None:
    in_doc = st.session_state.get("view") == "doc"
    btn_label = "Go" if in_doc else "!"
    btn_help = "Back to Speedtest" if in_doc else "Open Documentation"

    with st.container(
        key="app-header",
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        st.html(
            f"""
            <div class="hdr-brand">
                <span class="hdr-logo">{cfg.APP_ICON}</span>
                <div>
                    <div class="hdr-name">{cfg.APP_NAME}</div>
                    <div class="hdr-tag">{cfg.APP_TAGLINE}</div>
                </div>
            </div>
            """,
            width="content",
        )
        st.button(
            btn_label,
            key="btn-doc",
            help=btn_help,
            on_click=_toggle_view,
        )
