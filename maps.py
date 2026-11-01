"""Folium map builder (geospatial visualisation, CARTO Voyager basemap).

The notebook (Dataset/visualization.ipynb) draws every point as an individual
``folium.CircleMarker``. That produces an ~18 MB HTML file which is far too
slow for a web app, so here the points are shipped as one compact JSON array
and drawn by Leaflet's canvas renderer — same look, a fraction of the size.
"""

from __future__ import annotations

import json
import math

import folium
import streamlit as st
from folium.elements import MacroElement
from folium.template import Template

import api
import config as cfg

_CLASS_IDX = {c: i for i, c in enumerate(cfg.CLASS_NAMES)}


class CanvasPoints(MacroElement):
    """Draws thousands of points / Ookla tiles on a single Leaflet canvas."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
            var map = {{ this._parent.get_name() }};
            var cfg = {{ this.payload }};
            var renderer = L.canvas({ padding: 0.5, tolerance: 4 });
            var group = L.featureGroup();
            var half = cfg.tile / 2;

            cfg.points.forEach(function (p) {
                // p = [lat, lon, classIdx, provinceIdx, dl_mbps, ul_mbps, lat_ms]
                var c = cfg.colors[p[2]], layer;
                if (cfg.mode === "tile") {
                    var h = half * Math.cos(p[0] * Math.PI / 180);
                    layer = L.rectangle([[p[0] - h, p[1] - half], [p[0] + h, p[1] + half]], {
                        renderer: renderer, color: c, weight: 1, opacity: 0.9,
                        fillColor: c, fillOpacity: cfg.opacity
                    });
                } else {
                    layer = L.circleMarker([p[0], p[1]], {
                        renderer: renderer, radius: cfg.radius, color: c, weight: 0,
                        fillColor: c, fillOpacity: cfg.opacity
                    });
                }
                layer._p = p;
                group.addLayer(layer);
            });

            group.bindTooltip(function (layer) {
                var p = layer._p;
                return "<b>Quality:</b> " + cfg.classes[p[2]] +
                       " &nbsp;|&nbsp; <b>Province:</b> " + cfg.provinces[p[3]] +
                       "<br><b>DL:</b> " + p[4].toFixed(1) + " Mbps &nbsp; <b>UL:</b> " +
                       p[5].toFixed(1) + " Mbps &nbsp; <b>Latency:</b> " + p[6] + " ms";
            }, { sticky: true, className: "map-tooltip" });
            group.addTo(map);
        })();
        {% endmacro %}
        """
    )

    def __init__(self, df, mode: str = "point", radius: float = 3, opacity: float = 0.7):
        super().__init__()
        self._name = "CanvasPoints"
        provinces = sorted(df["Provinsi"].astype(str).unique().tolist())
        prov_idx = {p: i for i, p in enumerate(provinces)}
        points = [
            [
                round(float(r.tile_y), 4),
                round(float(r.tile_x), 4),
                _CLASS_IDX[r.quality],
                prov_idx[str(r.Provinsi)],
                round(r.avg_d_kbps / 1000, 1),
                round(r.avg_u_kbps / 1000, 1),
                int(r.avg_lat_ms),
            ]
            for r in df.itertuples(index=False)
        ]
        self.payload = json.dumps(
            {
                "points": points,
                "provinces": provinces,
                "classes": cfg.CLASS_NAMES,
                "colors": [cfg.QUALITY_COLORS[c] for c in cfg.CLASS_NAMES],
                "mode": mode,
                "radius": radius,
                "opacity": opacity,
                "tile": cfg.TILE_DEG,
            },
            separators=(",", ":"),
        )


class MapChrome(MacroElement):
    """Legend + 'click to enable scroll-zoom' behaviour."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
            var map = {{ this._parent.get_name() }};
            var legend = L.control({ position: "topright" });
            legend.onAdd = function () {
                var div = L.DomUtil.create("div", "map-legend");
                div.innerHTML = {{ this.legend_html }};
                L.DomEvent.disableClickPropagation(div);
                return div;
            };
            legend.addTo(map);

            // Avoid hijacking page scroll: wheel-zoom only after a click on the map
            map.scrollWheelZoom.disable();
            map.on("click focus", function () { map.scrollWheelZoom.enable(); });
            map.getContainer().addEventListener("mouseleave", function () {
                map.scrollWheelZoom.disable();
            });
        })();
        {% endmacro %}
        """
    )

    def __init__(self, legend_html: str):
        super().__init__()
        self._name = "MapChrome"
        self.legend_html = json.dumps(legend_html)


def _legend_html(year: int, shown: int, total: int, counts: dict, drawn: dict) -> str:
    rows = "".join(
        f'<div class="lg-row"><span class="lg-dot" style="background:{cfg.QUALITY_COLORS[c]}"></span>'
        f'<span>{c}</span><span class="lg-n"><b>{drawn.get(c, 0):,}</b> / {counts.get(c, 0):,}</span></div>'
        for c in cfg.CLASS_NAMES
    )
    return (
        f'<div class="lg-title">Quality tiles · {year}</div>{rows}'
        f'<div class="lg-foot">{shown:,} of {total:,} tiles drawn</div>'
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _build_map_html_cached(
    year: int,
    user_lat: float | None = None,
    user_lon: float | None = None,
    label: str | None = None,
    popup_html: str | None = None,
    css_mtime: float = 0.0,
) -> str:
    """Return the full map HTML for a year (optionally pinned to the user)."""
    _ = css_mtime  # part of the cache key so saving style.css refreshes the map
    has_user = user_lat is not None and user_lon is not None
    m = folium.Map(
        location=[user_lat, user_lon] if has_user else cfg.MAP_CENTER,
        zoom_start=cfg.USER_ZOOM if has_user else cfg.MAP_ZOOM,
        tiles=api.get_carto_tiles_url(),
        attr=cfg.CARTO_ATTR,
        prefer_canvas=False,
        control_scale=True,
        min_zoom=4,
    )

    font_css = api.font_face_css()
    if font_css:
        m.get_root().header.add_child(folium.Element(font_css))
    css = cfg.CSS_PATH.read_text(encoding="utf-8") if cfg.CSS_PATH.exists() else ""
    m.get_root().header.add_child(folium.Element(f"<style>{css}</style>"))

    sample = api.map_sample(year, user_lat, user_lon)
    summary = api.year_summary(year)

    if has_user:
        near = api.nearby(year, user_lat, user_lon)

        # Highlight the nearest Ookla tile (SVG layer with fill=False so it never blocks canvas hover)
        nt = near["nearest"]
        half = cfg.TILE_DEG / 2
        h = half * math.cos(math.radians(nt["lat"]))
        folium.Rectangle(
            bounds=[[nt["lat"] - h, nt["lon"] - half], [nt["lat"] + h, nt["lon"] + half]],
            color="#d500f9",
            weight=3,
            fill=False,
            tooltip=(
                f"Nearest tile ({nt['dist_km']:.2f} km) · {nt['quality']} · "
                f"DL {nt['avg_d_kbps'] / 1000:.1f} Mbps"
            ),
        ).add_to(m)
        folium.PolyLine(
            [[user_lat, user_lon], [nt["lat"], nt["lon"]]],
            color="#d500f9",
            weight=2,
            dash_array="4 6",
        ).add_to(m)

        color = cfg.QUALITY_COLORS.get(label or "", "#3949ab")
        icon = folium.DivIcon(
            html=(
                f'<div class="user-pin" style="--pin:{color}">'
                f'<span class="user-pin-pulse"></span><span class="user-pin-dot"></span></div>'
            ),
            icon_size=(28, 28),
            icon_anchor=(14, 14),
        )
        marker = folium.Marker([user_lat, user_lon], icon=icon)
        if popup_html:
            folium.Popup(popup_html, max_width=280, show=False).add_to(marker)
        folium.Tooltip(f"You · {label or '—'} (click for details)", permanent=False).add_to(marker)
        marker.add_to(m)

    CanvasPoints(sample, mode="point", radius=4 if has_user else 3, opacity=0.75).add_to(m)

    drawn_counts = sample["quality"].value_counts().to_dict()
    MapChrome(_legend_html(year, len(sample), summary["n"], summary["counts"], drawn_counts)).add_to(m)
    return m.get_root().render()


def build_map_html(
    year: int,
    user_lat: float | None = None,
    user_lon: float | None = None,
    label: str | None = None,
    popup_html: str | None = None,
) -> str:
    css_mtime = cfg.CSS_PATH.stat().st_mtime if cfg.CSS_PATH.exists() else 0.0
    return _build_map_html_cached(year, user_lat, user_lon, label, popup_html, css_mtime)
