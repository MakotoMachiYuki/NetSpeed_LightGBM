"""Documentation view (populated with the thesis proposal & system specifications)."""

from __future__ import annotations

import streamlit as st

import config as cfg


def _doc_html() -> str:
    return f"""
    <div class="doc">
        <div class="doc-head">
            <h1>Documentation</h1>
            <p class="doc-subtitle">
                <b>Klasifikasi Kualitas Jaringan Internet Seluler di Indonesia Menggunakan Algoritma LightGBM</b>
            </p>
            <p class="doc-dataset">
                Dataset based on:
                <a href="https://registry.opendata.aws/speedtest-global-performance/" target="_blank" rel="noopener noreferrer">
                    <b>Speedtest&reg; by Ookla&reg; Global Fixed and Mobile Network Performance Maps</b>
                </a>
                <span>(2023 Q1 – 2026 Q1 · <b>608,990</b> sampel bersih di <b>38 Provinsi Indonesia</b> dari 13,976,613 observasi global)</span>
            </p>
        </div>

        <div class="doc-grid">
            <section class="doc-card">
                <h3>Latar Belakang &amp; Dataset:</h3>
                <p>
                    Infrastruktur jaringan seluler berperan penting dalam transformasi digital di Indonesia, namun
                    kondisi geografis kepulauan menyebabkan ketimpangan kualitas akses (<i>digital divide</i>) antara
                    wilayah perkotaan dan pedesaan. Sistem ini dirancang untuk mengevaluasi dan memetakan kelayakan
                    kualitas jaringan internet di seluruh wilayah administratif Indonesia secara objektif menggunakan
                    data <i>crowdsourced</i> nyata di lapangan (mendukung <b>SDG Poin 9: Industri, Inovasi, dan Infrastruktur</b>).
                </p>

                <h4>Tahapan Prapemrosesan &amp; Atribut Data</h4>
                <p>
                    Data mentah berformat <i>Apache Parquet</i> dari repositori AWS S3 Ookla disaring secara spasial
                    menggunakan batas poligon Kabupaten/Kota &amp; Provinsi Indonesia (proyeksi <code>EPSG:4326</code>,
                    Geodatabase Peta Bumi Indonesia) untuk mengeliminasi titik di laut lepas dan negara tetangga,
                    dilanjutkan penghapusan baris <i>missing values</i> (<code>NaN</code>) serta kolom <code>quadkey</code>
                    dan WKT <code>tile</code>. Ketujuh fitur prediktor utama yang digunakan model meliputi:
                </p>
                <ul class="doc-list">
                    <li><span class="doc-tag dl">avg_d_kbps</span> Rata-rata kecepatan unduh (<i>download throughput</i>, kbps)</li>
                    <li><span class="doc-tag ul">avg_u_kbps</span> Rata-rata kecepatan unggah (<i>upload throughput</i>, kbps)</li>
                    <li><span class="doc-tag pg">avg_lat_ms</span> Waktu tunda rata-rata kondisi <i>idle</i> (<i>idle latency</i>, ms)</li>
                    <li><span class="doc-tag dl">avg_lat_down_ms</span> Waktu tunda rata-rata saat jaringan dibebani proses unduhan (ms)</li>
                    <li><span class="doc-tag ul">avg_lat_up_ms</span> Waktu tunda rata-rata saat jaringan dibebani pengiriman data (ms)</li>
                    <li><span class="doc-tag">tests</span> &amp; <span class="doc-tag">devices</span> Akumulasi jumlah pengujian dan perangkat pada satu titik koordinat spasial (<code>tile_x</code>, <code>tile_y</code>)</li>
                </ul>

                <h4>Standarisasi 5 Kelas Target Kualitas Layanan</h4>
                <div class="doc-classes">
                    <div class="doc-class-item">
                        <span class="doc-cls-pill" style="--c:{cfg.QUALITY_COLORS['Bad']}">0 · Bad (Buruk)</span>
                        <span>Degradasi transmisi sangat berat; hanya mendukung transmisi data ringan dan belum mampu memfasilitasi multimedia interaktif (<b>36,281</b> sampel).</span>
                    </div>
                    <div class="doc-class-item">
                        <span class="doc-cls-pill" style="--c:{cfg.QUALITY_COLORS['Serviceable']}">1 · Serviceable (Layak Dasar)</span>
                        <span>Fungsional minimum untuk penelusuran situs web, media sosial, dan komunikasi teks, namun terkendala pada aliran multimedia berkelanjutan (<b>59,761</b> sampel).</span>
                    </div>
                    <div class="doc-class-item">
                        <span class="doc-cls-pill" style="--c:{cfg.QUALITY_COLORS['Average']}">2 · Average (Rata-Rata)</span>
                        <span>Stabilitas konektivitas standar untuk produktivitas digital harian, <i>e-learning</i>, dan video daring tanpa gangguan signifikan (<b>501,941</b> sampel).</span>
                    </div>
                    <div class="doc-class-item">
                        <span class="doc-cls-pill" style="--c:{cfg.QUALITY_COLORS['Good']}">3 · Good (Baik)</span>
                        <span>Performa jaringan berkapasitas tinggi yang stabil untuk <i>video streaming</i> resolusi tinggi (YouTube/Twitch) tanpa jeda pemuatan (<b>9,701</b> sampel).</span>
                    </div>
                    <div class="doc-class-item">
                        <span class="doc-cls-pill" style="--c:{cfg.QUALITY_COLORS['Great']}">4 · Great (Sangat Baik)</span>
                        <span>Konektivitas paling optimal dengan <i>delay</i> dan <i>jitter</i> terendah untuk komunikasi waktu nyata, video kualitas maksimal, dan unduhan besar tanpa <i>buffering</i> (<b>1,306</b> sampel).</span>
                    </div>
                </div>
            </section>

            <section class="doc-card">
                <h3>Metodologi LightGBM &amp; Sistem:</h3>
                <p>
                    <b>Light Gradient Boosting Machine (LightGBM)</b> merupakan algoritma <i>ensemble</i> berbasis
                    <i>Gradient Boosting Decision Tree</i> (GBDT) yang membangun pohon keputusan secara
                    <b>leaf-wise (best-first)</b> dengan memprioritaskan pemisahan daun yang menghasilkan reduksi
                    kerugian (<i>Gain</i>) paling maksimal berdasarkan ekspansi deret Taylor orde kedua (Gradien
                    <i>g<sub>i</sub></i> dan Hessian <i>h<sub>i</sub></i>).
                </p>
                <ul class="doc-list">
                    <li>
                        <b>GOSS (<i>Gradient-based One-Side Sampling</i>):</b> Mempertahankan seluruh instans data
                        bergradien besar dan mengambil sampel acak pada instans bergradien kecil untuk mempercepat
                        perhitungan <i>information gain</i> dengan akurasi tinggi.
                    </li>
                    <li>
                        <b>EFB (<i>Exclusive Feature Bundling</i>):</b> Mengikat fitur-fitur yang saling eksklusif ke
                        dalam bundel berdimensi tunggal untuk mereduksi kompleksitas pencarian cabang pohon.
                    </li>
                    <li>
                        <b>Evaluasi Model:</b> Menggunakan skema pembagian data <b>70:30 Stratified Split</b>,
                        <b>Multi-Class Confusion Matrix (5&times;5, One-vs-Rest)</b> dengan metrik <i>Precision</i>,
                        <i>Recall</i>, <i>F1-Score</i>, <i>Macro/Weighted F1</i>, dan <i>Overall Accuracy</i> mencapai
                        <b>98.81%</b>, serta validasi ketahanan model dengan <b>K-Fold Cross Validation</b>.
                    </li>
                    <li>
                        <b>Arsitektur Aplikasi (SPA &amp; RAD):</b> Dikembangkan dengan metode <i>Rapid Application
                        Development</i> (RAD) dalam arsitektur <i>Single Page Application</i> (SPA) yang memadukan
                        uji kecepatan mandiri (Cloudflare Speedtest API), inferensi model LightGBM di sisi
                        <i>back-end</i>, dan pemetaan geospasial interaktif (Folium &amp; CARTO Voyager) periode 2023–2026.
                    </li>
                </ul>

                <h3>Credits:</h3>
                <div class="doc-credits">
                    <div class="doc-credit-row">
                        <span>Dataset</span>
                        <b>Speedtest&reg; by Ookla&reg; Open Data (AWS S3)</b>
                    </div>
                    <div class="doc-credit-row">
                        <span>Speedtest API</span>
                        <b>Cloudflare Speedtest API</b>
                    </div>
                    <div class="doc-credit-row">
                        <span>Web Framework</span>
                        <b>Streamlit (Python SPA)</b>
                    </div>
                    <div class="doc-credit-row">
                        <span>Machine Learning &amp; Data</span>
                        <b>LightGBM · Scikit-Learn · Pandas · NumPy · PyArrow</b>
                    </div>
                    <div class="doc-credit-row">
                        <span>Geospatial &amp; Mapping</span>
                        <b>Folium · Leaflet.js · GeoPandas · CARTO Voyager &amp; OpenStreetMap</b>
                    </div>
                    <div class="doc-credit-row">
                        <span>Typography &amp; Font</span>
                        <b>FOT-Yuruka Std · Noto Sans · FontTools</b>
                    </div>
                </div>
            </section>
        </div>

        <p class="doc-foot">{cfg.APP_NAME} · Documentation</p>
    </div>
    """


def render() -> None:
    """Render Documentation in the single-page view."""
    with st.container(key="doc-card-wrap"):
        st.html(_doc_html())


@st.dialog("Documentation", width="large")
def show() -> None:
    """Optional modal dialog version of Documentation."""
    st.html(_doc_html())
    if st.button("Close", key="doc-close", type="primary"):
        st.rerun()
