/* =============================================================================
 * Speedtest component (runs in the user's browser)
 * -----------------------------------------------------------------------------
 * Ookla-style speedtest against Cloudflare's public speed endpoints:
 *   GET  https://speed.cloudflare.com/__down?bytes=N   (download / ping)
 *   POST https://speed.cloudflare.com/__up             (upload)
 *
 * Measured metrics (mapped 1:1 to the LightGBM features):
 *   download_kbps   -> avg_d_kbps
 *   upload_kbps     -> avg_u_kbps
 *   latency_ms      -> avg_lat_ms        (idle latency)
 *   latency_down_ms -> avg_lat_down_ms   (latency while downloading)
 *   latency_up_ms   -> avg_lat_up_ms     (latency while uploading)
 *
 * Results go back to Python with setStateValue("result", payload); Python
 * answers through `data.prediction`. "View details" fires the "detail" trigger.
 * ========================================================================== */

let CF = "https://speed.cloudflare.com";
const SCALE = [0, 5, 10, 50, 100, 250, 500, 750, 1000];
const R = 118;
const CIRC = 2 * Math.PI * R;
const ARC = CIRC * 0.75;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const median = (arr) => {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const fmtMbps = (v) =>
  v == null
    ? "--"
    : v < 10
      ? v.toFixed(2)
      : v < 100
        ? v.toFixed(1)
        : v.toFixed(0);
const fmtMs = (v) => (v == null ? "--" : Math.round(v).toString());

function speedToFrac(mbps) {
  if (mbps <= 0) return 0;
  for (let i = 1; i < SCALE.length; i++) {
    if (mbps <= SCALE[i]) {
      const f = (mbps - SCALE[i - 1]) / (SCALE[i] - SCALE[i - 1]);
      return (i - 1 + f) / (SCALE.length - 1);
    }
  }
  return 1;
}

/* ───────────────────────────── Markup ───────────────────────────── */
function gaugeSvg() {
  const ticks = SCALE.map((v, i) => {
    const a = ((135 + (270 * i) / (SCALE.length - 1)) * Math.PI) / 180;
    const x = 150 + Math.cos(a) * (R - 30);
    const y = 150 + Math.sin(a) * (R - 30);
    return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" class="sp-tick">${v}</text>`;
  }).join("");
  return `
  <svg viewBox="0 0 300 300" class="sp-svg" aria-hidden="true">
    <defs>
      <linearGradient id="spGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="var(--sp-grad-a, #00c6ff)"/>
        <stop offset="100%" stop-color="var(--sp-grad-b, #7b2ff7)"/>
      </linearGradient>
    </defs>
    <circle cx="150" cy="150" r="${R}" class="sp-track"
      stroke-dasharray="${ARC} ${CIRC}" transform="rotate(135 150 150)"/>
    <circle cx="150" cy="150" r="${R}" class="sp-arc" stroke="url(#spGrad)"
      stroke-dasharray="0 ${CIRC}" transform="rotate(135 150 150)"/>
    <g class="sp-ticks">${ticks}</g>
    <g class="sp-needle" transform="rotate(135 150 150)">
      <polygon points="150,145 262,150 150,155" />
      <circle cx="150" cy="150" r="9"/>
    </g>
  </svg>`;
}

function markup() {
  return `
  <div class="sp-wrap">
    <div class="sp-col sp-title-col">
      <div class="sp-title">Speedtest</div>
      <div class="sp-sub">Download · Upload · Latency<br/>powered by Cloudflare</div>
      <div class="sp-mode-switch" role="group" aria-label="Connection mode">
        <button type="button" class="sp-mode-btn" data-mode="wifi" title="Wi-Fi: Unlimited data">
          &#128246; Wi-Fi <small>No Limit</small>
        </button>
        <button type="button" class="sp-mode-btn" data-mode="data" title="Mobile Data: Adaptive cap up to 60 MB (30 MB DL + 30 MB UL)">
          &#128241; Mobile Data <small>&le; 60 MB</small>
        </button>
      </div>
      <div class="sp-net-info" data-f="net-box">
        <div class="sp-net-row"><span>Connected via:</span><b data-f="net-ipv">IPv4</b></div>
        <div class="sp-net-row"><span>Server location:</span><b data-f="net-srv">Detecting…</b></div>
        <div class="sp-net-row"><span>Your network:</span><b data-f="net-isp">Detecting…</b></div>
        <div class="sp-net-row"><span>Your IP address:</span><b class="sp-net-ip" data-f="net-ip">---</b></div>
      </div>
    </div>

    <div class="sp-col sp-gauge-col">
      <div class="sp-gauge" data-state="idle">
        ${gaugeSvg()}
        <button class="sp-go" type="button" aria-label="Start speedtest"><span>GO</span></button>
        <div class="sp-conn-ask" aria-hidden="true">
          <div class="sp-conn-title">Wi-Fi or Mobile Data?</div>
          <div class="sp-conn-sub">Select connection to set data cap</div>
          <button type="button" class="sp-conn-choice is-wifi" data-pick="wifi">
            <b>&#128246; Wi-Fi</b> <span>No Limit</span>
          </button>
          <button type="button" class="sp-conn-choice is-data" data-pick="data">
            <b>&#128241; Mobile Data</b> <span>60 MB</span>
          </button>
        </div>
        <div class="sp-live">
          <div class="sp-live-phase">Ping</div>
          <div class="sp-live-val">0.00</div>
          <div class="sp-live-unit">Mbps</div>
        </div>
      </div>
      <div class="sp-progress"><div class="sp-progress-bar"></div></div>
      <button class="sp-cancel" type="button">Cancel</button>
    </div>

    <div class="sp-col sp-info-col">
      <div class="sp-line"><span class="sp-k">Speed:</span><span class="sp-v" data-f="speed">---</span></div>
      <div class="sp-line"><span class="sp-k">Result:</span><span class="sp-v" data-f="result">---</span></div>
      <div class="sp-stats">
        <div class="sp-stat" data-s="ping"><div class="sp-stat-l">Ping</div><div class="sp-stat-v" data-f="ping">--</div><div class="sp-stat-u">ms</div></div>
        <div class="sp-stat" data-s="download"><div class="sp-stat-l">&#8595; Download</div><div class="sp-stat-v" data-f="download">--</div><div class="sp-stat-u">Mbps</div></div>
        <div class="sp-stat" data-s="upload"><div class="sp-stat-l">&#8593; Upload</div><div class="sp-stat-v" data-f="upload">--</div><div class="sp-stat-u">Mbps</div></div>
      </div>
      <div class="sp-loaded" data-f="loaded">Loaded latency &#8595; -- ms · &#8593; -- ms</div>
      <div class="sp-meta" data-f="meta">Press GO to start. Location permission is requested to pin your result on the map.</div>
      <button class="sp-detail" type="button" disabled>View details</button>
    </div>
  </div>`;
}

/* ───────────────────────────── Engine ───────────────────────────── */
function bust(url) {
  return (
    url +
    (url.includes("?") ? "&" : "?") +
    "r=" +
    Math.random().toString(36).slice(2)
  );
}

async function ping(signal) {
  const url = bust(`${CF}/__down?bytes=0`);
  const t0 = performance.now();
  const res = await fetch(url, { cache: "no-store", signal });
  await res.arrayBuffer();
  let rtt = performance.now() - t0;
  const e = performance.getEntriesByName(url).pop();
  if (e && e.requestStart > 0 && e.responseStart > e.requestStart) {
    rtt = e.responseStart - e.requestStart;
    const edge = (e.serverTiming || []).find((s) => s.name === "cfSpeedEdge");
    if (edge && edge.duration < rtt) rtt -= edge.duration;
  }
  return { rtt: Math.max(rtt, 1), res };
}

async function fetchMeta(res, signal) {
  const h = (k) => res?.headers?.get?.(k);
  const hLat = parseFloat(h("cf-meta-latitude"));
  const hLon = parseFloat(h("cf-meta-longitude"));
  const baseIp = h("cf-meta-ip") || null;
  const base = {
    clientIp: baseIp,
    ipVersion: baseIp && baseIp.includes(":") ? "IPv6" : "IPv4",
    colo: h("cf-meta-colo") || null,
    serverCity: h("cf-meta-city") || null,
    city: h("cf-meta-city") || null,
    region: null,
    postalCode: null,
    country: h("cf-meta-country") || null,
    asn: h("cf-meta-asn") || null,
    asOrganization: null,
    lat: isFinite(hLat) ? hLat : null,
    lon: isFinite(hLon) ? hLon : null,
  };
  try {
    const r = await fetch(bust(`${CF}/meta`), { cache: "no-store", signal });
    if (r.ok) {
      const j = await r.json();
      const jLat = parseFloat(j.latitude);
      const jLon = parseFloat(j.longitude);
      const coloObj = j.colo && typeof j.colo === "object" ? j.colo : null;
      const coloStr = coloObj
        ? coloObj.iata && coloObj.city
          ? `${coloObj.iata} (${coloObj.city})`
          : coloObj.iata || coloObj.city || "Edge"
        : j.colo || base.colo;
      const clientIp = j.clientIp || base.clientIp;
      return {
        clientIp,
        ipVersion: clientIp && String(clientIp).includes(":") ? "IPv6" : "IPv4",
        colo: coloStr,
        serverCity: coloObj?.city || j.city || base.serverCity,
        city: j.city || coloObj?.city || base.city,
        region: j.region || coloObj?.region || null,
        postalCode: j.postalCode || null,
        country: j.country || coloObj?.cca2 || base.country,
        asn: j.asn || base.asn,
        asOrganization: j.asOrganization || null,
        lat: isFinite(jLat) ? jLat : base.lat,
        lon: isFinite(jLon) ? jLon : base.lon,
      };
    }
  } catch (_) {
    /* fallback to headers / backend resolution */
  }
  return base;
}

function startGpsTracker() {
  if (!navigator.geolocation) {
    return { finish: async () => null, stop: () => {} };
  }
  let best = null;
  let watchId = null;
  let fallbackTried = false;
  const waiters = new Set();

  const stop = () => {
    if (watchId != null) {
      try {
        navigator.geolocation.clearWatch(watchId);
      } catch (_) {}
      watchId = null;
    }
  };

  const notifyIfPinpoint = () => {
    if (best && best.accuracy != null && best.accuracy <= 15) {
      stop();
      for (const resolve of waiters) resolve(best);
      waiters.clear();
    }
  };

  const onPos = (p) => {
    if (!p || !p.coords) return;
    const acc = Number.isFinite(p.coords.accuracy) ? p.coords.accuracy : 999999;
    const candidate = {
      lat: p.coords.latitude,
      lon: p.coords.longitude,
      accuracy: acc,
      source: "gps",
    };
    if (!best || acc < best.accuracy) {
      best = candidate;
    }
    notifyIfPinpoint();
  };

  const onErr = () => {
    if (fallbackTried || best) return;
    fallbackTried = true;
    navigator.geolocation.getCurrentPosition(
      (p) => {
        onPos(p);
        for (const resolve of waiters) resolve(best);
        waiters.clear();
      },
      () => {
        for (const resolve of waiters) resolve(best);
        waiters.clear();
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 },
    );
  };

  try {
    watchId = navigator.geolocation.watchPosition(onPos, onErr, {
      enableHighAccuracy: true,
      timeout: 25000,
      maximumAge: 0,
    });
  } catch (_) {
    onErr();
  }

  const finish = (extraWaitMs = 4000) =>
    new Promise((resolve) => {
      if (best && best.accuracy <= 25) {
        stop();
        return resolve(best);
      }
      const done = (val) => {
        clearTimeout(t);
        waiters.delete(done);
        stop();
        resolve(val || best);
      };
      const t = setTimeout(() => done(best), extraWaitMs);
      waiters.add(done);
    });

  return { finish, stop };
}

let RANDOM_CHUNK = null;
function uploadBlob(size) {
  if (!RANDOM_CHUNK) {
    RANDOM_CHUNK = new Uint8Array(1 << 20);
    for (let i = 0; i < RANDOM_CHUNK.length; i += 65536) {
      crypto.getRandomValues(RANDOM_CHUNK.subarray(i, i + 65536));
    }
  }
  const full = Math.floor(size / RANDOM_CHUNK.length);
  const parts = new Array(full).fill(RANDOM_CHUNK);
  const rest = size - full * RANDOM_CHUNK.length;
  if (rest > 0) parts.push(RANDOM_CHUNK.subarray(0, rest));
  return new Blob(parts);
}

function flexibleCapBytes(liveMbps, isData, hardCapBytes) {
  if (!isData) return Infinity;
  // Adaptive lower cap when connection speed is slow / bad so it finishes smoothly without wasting data
  if (liveMbps <= 0) return hardCapBytes;
  if (liveMbps < 2) return Math.min(hardCapBytes, 2_500_000); // < 2 Mbps (Bad): ~2.5 MB
  if (liveMbps < 5) return Math.min(hardCapBytes, 5_000_000); // 2–5 Mbps (Bad): ~5 MB
  if (liveMbps < 15) return Math.min(hardCapBytes, 12_000_000); // 5–15 Mbps (Serviceable): ~12 MB
  if (liveMbps < 35) return Math.min(hardCapBytes, 20_000_000); // 15–35 Mbps (Average): ~20 MB
  return hardCapBytes; // >= 35 Mbps: full 30 MB cap
}

async function downloadStream(st, signal, onCapReached) {
  let size = st.isData ? 131072 : 262144; // start small (128 KB / 256 KB) for slow connections
  const maxChunk = st.isData ? 3_000_000 : 25_000_000;
  while (!signal.aborted) {
    const cap = st.dynamicCap;
    const rem = cap - st.reserved;
    if (rem <= 0) return;
    const reqSize = Number.isFinite(rem) ? Math.min(size, rem) : size;
    st.reserved += reqSize;

    const t0 = performance.now();
    let got = 0;
    try {
      const res = await fetch(bust(`${CF}/__down?bytes=${reqSize}`), {
        cache: "no-store",
        signal,
      });
      const reader = res.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        const allow = Math.max(0, st.dynamicCap - st.bytes);
        const take = Number.isFinite(allow)
          ? Math.min(value.length, allow)
          : value.length;
        got += take;
        st.bytes += take;
        if (st.bytes >= st.dynamicCap) {
          onCapReached?.();
          return;
        }
      }
    } catch (e) {
      if (reqSize > got) st.reserved -= reqSize - got;
      if (signal.aborted) return;
      st.errors++;
      if (st.errors > 12) throw e;
      await sleep(200);
      continue;
    }
    if (reqSize > got) st.reserved -= reqSize - got;
    const dt = Math.max((performance.now() - t0) / 1000, 0.05);
    const targetSec = st.isData ? 0.65 : 1.5;
    size = Math.round(clamp((got / dt) * targetSec, 65536, maxChunk));
  }
}

function uploadOnce(size, st, signal, onCapReached) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    let last = 0;
    const t0 = performance.now();
    const done = (ok) => {
      signal.removeEventListener("abort", onAbort);
      resolve({ bytes: last, dt: (performance.now() - t0) / 1000, ok });
    };
    const onAbort = () => xhr.abort();
    signal.addEventListener("abort", onAbort, { once: true });
    xhr.upload.onprogress = (e) => {
      const allow = Math.max(0, st.dynamicCap - st.bytes);
      const delta = Math.max(
        0,
        Number.isFinite(allow)
          ? Math.min(e.loaded - last, allow)
          : e.loaded - last,
      );
      st.bytes += delta;
      last = e.loaded;
      if (st.bytes >= st.dynamicCap) {
        onCapReached?.();
      }
    };
    xhr.onload = () => {
      if (size > last) {
        const allow = Math.max(0, st.dynamicCap - st.bytes);
        const delta = Math.max(
          0,
          Number.isFinite(allow) ? Math.min(size - last, allow) : size - last,
        );
        st.bytes += delta;
      }
      last = size;
      done(true);
    };
    xhr.onerror = () => done(false);
    xhr.onabort = () => done(false);
    xhr.open("POST", bust(`${CF}/__up`));
    xhr.send(uploadBlob(size));
  });
}

async function uploadStream(st, signal, onCapReached) {
  let size = st.isData ? 65536 : 131072; // start small (64 KB / 128 KB) so bad upload speeds don't stall
  const maxChunk = st.isData ? 3_000_000 : 20_000_000;
  while (!signal.aborted) {
    const cap = st.dynamicCap;
    const rem = cap - st.reserved;
    if (rem <= 0) return;
    const reqSize = Number.isFinite(rem) ? Math.min(size, rem) : size;
    st.reserved += reqSize;

    const r = await uploadOnce(reqSize, st, signal, onCapReached);
    if (reqSize > r.bytes) st.reserved -= reqSize - r.bytes;
    if (signal.aborted || st.bytes >= st.dynamicCap) return;
    if (!r.ok) {
      st.errors++;
      if (st.errors > 12) throw new Error("Upload failed");
      await sleep(200);
      continue;
    }
    const targetSec = st.isData ? 0.65 : 1.5;
    size = Math.round(
      clamp((r.bytes / Math.max(r.dt, 0.05)) * targetSec, 65536, maxChunk),
    );
  }
}

async function pingLoop(list, signal, t0, warmMs) {
  while (!signal.aborted) {
    try {
      const { rtt } = await ping(signal);
      if (performance.now() - t0 > warmMs) list.push(rtt);
    } catch (_) {
      /* ignore while loaded */
    }
    await sleep(250);
  }
}

/** Runs a timed transfer phase with N parallel streams, flexible byte cap, and live reporting. */
async function transferPhase(kind, cfg, onTick, outerSignal) {
  const ctrl = new AbortController();
  const abortAll = () => ctrl.abort();
  outerSignal.addEventListener("abort", abortAll, { once: true });

  const isData = Boolean(cfg.isData);
  const hardCap = isData ? Math.max(1e6, cfg.maxBytes || 30_000_000) : Infinity;
  const st = {
    bytes: 0,
    reserved: 0,
    isData,
    hardCap,
    dynamicCap: hardCap,
    errors: 0,
  };
  const durMs = cfg.seconds * 1000;
  const t0 = performance.now();
  const samples = [{ t: 0, b: 0 }];
  const loaded = [];

  const onCapReached = () => {
    const tNow = performance.now() - t0;
    samples.push({ t: tNow, b: st.bytes });
    ctrl.abort();
  };

  const workers = [];
  for (let i = 0; i < cfg.streams; i++) {
    workers.push(
      (kind === "download" ? downloadStream : uploadStream)(
        st,
        ctrl.signal,
        onCapReached,
      ),
    );
  }
  const pinger = pingLoop(loaded, ctrl.signal, t0, 300);

  let failed = null;
  Promise.all(workers).catch((e) => {
    failed = e;
    ctrl.abort();
  });

  while (!ctrl.signal.aborted) {
    await sleep(100);
    const t = performance.now() - t0;
    samples.push({ t, b: st.bytes });
    // live speed over a sliding ~1 s window
    let j = samples.length - 1;
    while (j > 0 && t - samples[j].t < 1000) j--;
    const win = samples[samples.length - 1];
    const live =
      ((win.b - samples[j].b) * 8) / Math.max(win.t - samples[j].t, 1) / 1000; // Mbps

    // After 1.5s of measurement, adapt the flexible cap to the user's real speed
    if (isData && t >= 1500) {
      st.dynamicCap = flexibleCapBytes(live, true, hardCap);
    }

    const byteFrac = Number.isFinite(st.dynamicCap)
      ? st.bytes / st.dynamicCap
      : 0;
    const prog = Math.min(1, Math.max(t / durMs, byteFrac));
    onTick(live, prog);
    if (t >= durMs || st.bytes >= st.dynamicCap) break;
  }
  ctrl.abort();
  outerSignal.removeEventListener("abort", abortAll);
  await Promise.allSettled([...workers, pinger]);
  if (outerSignal.aborted) throw new DOMException("Cancelled", "AbortError");
  if (failed && st.bytes === 0) throw failed;

  // final speed: bytes after the TCP slow-start warm-up
  const end = samples[samples.length - 1];
  const warmMs = Math.min(1200, end.t * 0.25);
  let k = 0;
  while (k < samples.length - 1 && samples[k].t < warmMs) k++;
  const base = samples[k];
  const mbps =
    end.t > base.t ? ((end.b - base.b) * 8) / (end.t - base.t) / 1000 : 0;
  return {
    mbps,
    loadedLatency: loaded.length ? median(loaded) : null,
    bytes: st.bytes,
  };
}

/* ───────────────────────────── App ───────────────────────────── */
function createApp(root) {
  const host = document.createElement("div");
  host.className = "sp-host";
  host.innerHTML = markup();
  root.appendChild(host);

  const $ = (s) => host.querySelector(s);
  const field = (f) => host.querySelector(`[data-f="${f}"]`);
  const gauge = $(".sp-gauge");
  const arc = $(".sp-arc");
  const needle = $(".sp-needle");
  const liveVal = $(".sp-live-val");
  const liveUnit = $(".sp-live-unit");
  const livePhase = $(".sp-live-phase");
  const bar = $(".sp-progress-bar");
  const goBtn = $(".sp-go");
  const cancelBtn = $(".sp-cancel");
  const detailBtn = $(".sp-detail");

  const app = {
    api: { setStateValue: null, setTriggerValue: null },
    config: {
      download_s: 10,
      upload_s: 10,
      streams: 4,
      data_max_mb: 60,
      dl_max_mb: 30,
      ul_max_mb: 30,
    },
    connType: null, // null until user selects 'wifi' or 'data'
    running: false,
    ctrl: null,
    lastId: null,
    target: 0,
    shown: 0,
    unit: "Mbps",
  };

  const setConnType = (mode) => {
    app.connType = mode === "data" ? "data" : "wifi";
    host.querySelectorAll(".sp-mode-btn").forEach((b) => {
      b.classList.toggle("is-selected", b.dataset.mode === app.connType);
    });
  };

  // smooth gauge animation
  const frame = () => {
    app.shown += (app.target - app.shown) * 0.18;
    if (Math.abs(app.target - app.shown) < 0.005) app.shown = app.target;
    const frac = app.unit === "Mbps" ? speedToFrac(app.shown) : 0;
    arc.setAttribute("stroke-dasharray", `${(ARC * frac).toFixed(2)} ${CIRC}`);
    needle.setAttribute(
      "transform",
      `rotate(${(135 + 270 * frac).toFixed(2)} 150 150)`,
    );
    liveVal.textContent =
      app.unit === "Mbps" ? fmtMbps(app.shown) : fmtMs(app.shown);
    app.raf = requestAnimationFrame(frame);
  };
  app.raf = requestAnimationFrame(frame);

  const setPhase = (phase, unit) => {
    livePhase.textContent = phase;
    liveUnit.textContent = unit;
    app.unit = unit;
    app.target = 0;
    app.shown = 0;
    host
      .querySelectorAll(".sp-stat")
      .forEach((s) => s.classList.remove("is-active"));
    const key = phase.toLowerCase().includes("down")
      ? "download"
      : phase.toLowerCase().includes("up")
        ? "upload"
        : "ping";
    gauge.dataset.phase = key;
    host.querySelector(`[data-s="${key}"]`)?.classList.add("is-active");
  };
  const setProgress = (p) =>
    (bar.style.width = `${(clamp(p, 0, 1) * 100).toFixed(1)}%`);

  const setResult = (html, cls) => {
    const el = field("result");
    el.innerHTML = html;
    el.className = "sp-v" + (cls ? " " + cls : "");
  };

  const renderNetInfo = (m) => {
    if (!m) return;
    const ipv =
      m.ipVersion ||
      (m.clientIp && String(m.clientIp).includes(":") ? "IPv6" : "IPv4");
    const srv = m.serverCity || m.colo || "Jakarta";
    const asnStr = m.asn ? `AS${m.asn}` : "";
    const orgStr = m.asOrganization || "";
    const isp =
      orgStr && asnStr
        ? `${orgStr} (<span class="sp-net-ip">${asnStr}</span>)`
        : orgStr || asnStr || "–";
    if (field("net-ipv")) field("net-ipv").textContent = ipv;
    if (field("net-srv")) field("net-srv").textContent = srv;
    if (field("net-isp")) field("net-isp").innerHTML = isp;
    if (field("net-ip")) field("net-ip").textContent = m.clientIp || "–";
  };

  // Pre-fetch Cloudflare /meta on mount so network, ASN & IP show immediately
  fetchMeta(null).then((m) => {
    app.cachedMeta = m;
    renderNetInfo(m);
  });

  const reset = () => {
    field("speed").textContent = "---";
    setResult("---");
    field("ping").textContent = "--";
    field("download").textContent = "--";
    field("upload").textContent = "--";
    field("loaded").innerHTML = "Loaded latency &#8595; -- ms · &#8593; -- ms";
    detailBtn.disabled = true;
  };

  async function run() {
    if (app.running) return;
    app.running = true;
    app.ctrl = new AbortController();
    const signal = app.ctrl.signal;
    reset();
    gauge.dataset.state = "running";
    host.classList.add("is-running");
    setProgress(0);
    const started = performance.now();
    performance.setResourceTimingBufferSize?.(5000);
    performance.clearResourceTimings?.();

    // 1) continuously track & refine high-accuracy GPS in parallel with the test
    const gpsTracker = startGpsTracker();
    field("meta").textContent =
      "Requesting precise GPS location & connecting to Cloudflare…";

    try {
      // 2) idle latency
      setPhase("Ping", "ms");
      const rtts = [];
      let meta = null;
      let metaPromise = null;
      const N = 16;
      for (let i = 0; i < N; i++) {
        const { rtt, res } = await ping(signal);
        if (i === 0) {
          metaPromise = fetchMeta(res, signal).then((m) => {
            meta = m;
            app.cachedMeta = m;
            renderNetInfo(m);
            field("meta").textContent =
              `Server: Cloudflare ${m.colo || "Edge"}${m.asOrganization ? " · " + m.asOrganization : ""}${m.asn ? " (AS" + m.asn + ")" : ""}`;
            return m;
          });
        } else {
          rtts.push(rtt);
          app.target = median(rtts);
          field("ping").textContent = fmtMs(app.target);
        }
        setProgress((0.1 * (i + 1)) / N);
      }
      if (metaPromise)
        meta = await Promise.race([
          metaPromise,
          sleep(800).then(() => meta || app.cachedMeta),
        ]);
      if (!meta && app.cachedMeta) meta = app.cachedMeta;
      const latency = median(rtts);
      const jitter =
        rtts.length > 1
          ? rtts.slice(1).reduce((s, v, i) => s + Math.abs(v - rtts[i]), 0) /
            (rtts.length - 1)
          : 0;
      field("ping").textContent = fmtMs(latency);

      // 3) download (Wi-Fi = Unlimited; Mobile Data = up to 30 MB with flexible lower cap for slow speeds)
      const isData = app.connType === "data";
      const dlCapBytes = (app.config.dl_max_mb || 30) * 1_000_000;
      const ulCapBytes = (app.config.ul_max_mb || 30) * 1_000_000;
      setPhase("Download", "Mbps");
      const dl = await transferPhase(
        "download",
        {
          seconds: app.config.download_s,
          streams: app.config.streams,
          isData,
          maxBytes: dlCapBytes,
        },
        (live, p) => {
          app.target = live;
          field("download").textContent = fmtMbps(live);
          field("speed").innerHTML =
            `<span class="sp-dl">&#8595; ${fmtMbps(live)}</span> <small>Mbps</small>`;
          setProgress(0.1 + 0.45 * p);
        },
        signal,
      );
      field("download").textContent = fmtMbps(dl.mbps);

      // 4) upload (Wi-Fi = Unlimited; Mobile Data = up to 30 MB with flexible lower cap for slow speeds)
      setPhase("Upload", "Mbps");
      const ul = await transferPhase(
        "upload",
        {
          seconds: app.config.upload_s,
          streams: app.config.streams,
          isData,
          maxBytes: ulCapBytes,
        },
        (live, p) => {
          app.target = live;
          field("upload").textContent = fmtMbps(live);
          field("speed").innerHTML =
            `<span class="sp-dl">&#8595; ${fmtMbps(dl.mbps)}</span> / <span class="sp-ul">&#8593; ${fmtMbps(live)}</span> <small>Mbps</small>`;
          setProgress(0.55 + 0.45 * p);
        },
        signal,
      );
      field("upload").textContent = fmtMbps(ul.mbps);
      setProgress(1);

      field("loaded").innerHTML =
        `Loaded latency <span class="sp-dl">&#8595; ${fmtMs(dl.loadedLatency)} ms</span> · <span class="sp-ul">&#8593; ${fmtMs(ul.loadedLatency)} ms</span> · <span class="sp-ping">jitter ${fmtMs(jitter)} ms</span>`;
      field("speed").innerHTML =
        `<span class="sp-dl">&#8595; ${fmtMbps(dl.mbps)}</span> / <span class="sp-ul">&#8593; ${fmtMbps(ul.mbps)}</span> <small>Mbps</small>`;

      // 5) location: refined GPS if allowed, otherwise backend resolves IP / default fallback
      field("meta").textContent =
        "Resolving precise GPS location & classifying on backend…";
      const gps = await gpsTracker.finish(4000);
      let location = gps;
      if (!location && meta && meta.lat != null && meta.lon != null) {
        location = {
          lat: meta.lat,
          lon: meta.lon,
          accuracy: null,
          source: "ip",
        };
      }

      const payload = {
        id: Date.now(),
        conn_type: app.connType || "wifi",
        download_kbps: Math.round(dl.mbps * 1000),
        upload_kbps: Math.round(ul.mbps * 1000),
        latency_ms: Math.round(latency),
        latency_down_ms: Math.round(dl.loadedLatency ?? latency),
        latency_up_ms: Math.round(ul.loadedLatency ?? latency),
        jitter_ms: Math.round(jitter * 10) / 10,
        bytes_down: dl.bytes,
        bytes_up: ul.bytes,
        duration_s: Math.round((performance.now() - started) / 100) / 10,
        location,
        meta,
      };
      app.lastId = payload.id;
      setResult('<span class="sp-pending">Classifying…</span>');
      app.api.setStateValue?.("result", payload);
    } catch (e) {
      const cancelled = e && e.name === "AbortError";
      field("meta").textContent = cancelled
        ? "Test cancelled."
        : `Test failed: ${e?.message || e}. Check your connection and try again.`;
      setResult("---");
      setProgress(0);
    } finally {
      gpsTracker.stop();
      app.running = false;
      app.ctrl = null;
      app.target = 0;
      gauge.dataset.state = "done";
      host.classList.remove("is-running");
      host
        .querySelectorAll(".sp-stat")
        .forEach((s) => s.classList.remove("is-active"));
    }
  }

  // Ask whether the user is on Wi-Fi or Mobile Data before starting (or let them switch anytime)
  goBtn.addEventListener("click", () => {
    if (app.running) return;
    if (!app.connType) {
      gauge.dataset.state = "asking";
      return;
    }
    run();
  });
  host.querySelectorAll(".sp-conn-choice").forEach((btn) => {
    btn.addEventListener("click", () => {
      setConnType(btn.dataset.pick);
      run();
    });
  });
  host.querySelectorAll(".sp-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (app.running) return;
      setConnType(btn.dataset.mode);
      if (gauge.dataset.state === "asking") {
        run();
      }
    });
  });
  cancelBtn.addEventListener("click", () => app.ctrl?.abort());
  detailBtn.addEventListener("click", () =>
    app.api.setTriggerValue?.("detail", Date.now()),
  );
  field("result").addEventListener("click", () => {
    if (!detailBtn.disabled) app.api.setTriggerValue?.("detail", Date.now());
  });

  app.update = (data) => {
    data = data || {};
    if (data.config) {
      Object.assign(app.config, data.config);
      if (data.config.cf_url) CF = data.config.cf_url;
    }
    const p = data.prediction;
    if (p && !app.running) {
      if (p.conn_type && !app.connType) setConnType(p.conn_type);
      if (p.speed_html) field("speed").innerHTML = p.speed_html;
      if (p.loaded_html) field("loaded").innerHTML = p.loaded_html;
      if (p.meta_text) field("meta").textContent = p.meta_text;
      if (app.lastId == null) {
        app.lastId = p.id;
        if (p.ping != null) field("ping").textContent = fmtMs(p.ping);
        if (p.download != null)
          field("download").textContent = fmtMbps(p.download);
        if (p.upload != null) field("upload").textContent = fmtMbps(p.upload);
      }
      if (p.id === app.lastId) {
        setResult(
          `<span class="sp-badge" style="--c:${p.color}">${p.label}</span><span class="sp-conf">${(p.confidence * 100).toFixed(1)}%</span>`,
          "has-badge",
        );
        detailBtn.disabled = false;
      }
    }
    if (data.error && !app.running) field("meta").textContent = data.error;
  };

  app.version = 11;
  return app;
}

if (!window.__dialogCloseTransitionBound) {
  window.__dialogCloseTransitionBound = true;
  document.addEventListener(
    "click",
    (e) => {
      const dialog = document.querySelector(
        'div[role="dialog"], div[aria-modal="true"]',
      );
      if (!dialog || dialog.dataset.closingDone === "1") return;
      const closeBtn = e.target.closest?.(
        'div[role="dialog"] button[aria-label="Close"], div[aria-modal="true"] button[aria-label="Close"]',
      );
      const modalRoot = dialog.closest(
        '[data-testid="stDialog"], [data-baseweb="modal"]',
      );
      const clickedBackdrop =
        modalRoot && modalRoot.contains(e.target) && !dialog.contains(e.target);
      if (!closeBtn && !clickedBackdrop) return;

      const btn =
        closeBtn || dialog.querySelector('button[aria-label="Close"]');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      if (!dialog.classList.contains("is-closing")) {
        dialog.classList.add("is-closing");
        modalRoot?.classList.add("is-closing");
        setTimeout(() => {
          dialog.dataset.closingDone = "1";
          btn.click();
        }, 480);
      }
    },
    true,
  );
}

export default function (component) {
  const { parentElement, data, setStateValue, setTriggerValue } = component;
  let app = parentElement.__speedtestApp;
  if (!app || app.version !== 11) {
    parentElement.innerHTML = "";
    app = createApp(parentElement);
    parentElement.__speedtestApp = app;
  }
  app.api.setStateValue = setStateValue;
  app.api.setTriggerValue = setTriggerValue;
  app.update(data);
  // No cleanup on purpose: a running test must survive Streamlit reruns.
}
