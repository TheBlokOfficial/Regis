/**
 * Regis — Panel Kontrolny | app.js
 *
 * Logika reaktywna: inicjalizacja stanu z /api/status,
 * subskrypcja strumienia SSE /api/events,
 * renderowanie kart węzłów i satelit,
 * dziennik zdarzeń na żywo,
 * sterowanie węzłami przez /api/node/{id}/command.
 */

"use strict";

// ── Stan aplikacji ──────────────────────────────────────────────────────────

/** @type {Object.<string, Object>} id → dane węzła */
const workers = {};

/** @type {Object.<string, Object>} id → dane satelity */
const satellites = {};

// Max wpisów w dzienniku (zapobiega rosnącemu DOM bez końca)
const LOG_MAX = 300;

// ── Zegar ──────────────────────────────────────────────────────────────────

function updateClock() {
    const now = new Date();
    document.getElementById("clock").textContent =
        now.toLocaleTimeString("pl-PL", { hour12: false });
}

setInterval(updateClock, 1000);
updateClock();

// ── Formatowanie czasu ─────────────────────────────────────────────────────

function fmtUptime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function fmtTime(ts) {
    // ts może być ISO string lub HH:MM:SS
    if (!ts) {
        const now = new Date();
        return now.toLocaleTimeString("pl-PL", { hour12: false });
    }
    if (ts.includes("T")) {
        return new Date(ts).toLocaleTimeString("pl-PL", { hour12: false });
    }
    return ts;
}

// ── Renderowanie kart węzłów ───────────────────────────────────────────────

function renderWorkerCard(worker) {
    const id = worker.id;
    const existing = document.getElementById(`worker-${id}`);
    const card = existing || document.createElement("div");

    const status = worker.status || "online";
    const model  = worker.model_name || "—";
    const tier   = worker.tier || "—";
    const host   = worker.host ? `${worker.host}:${worker.port || "?"}` : "—";

    card.id = `worker-${id}`;
    card.className = "node-card";
    card.innerHTML = `
        <div class="card-title">
            <span class="dot ${status === "online" ? "online" : "offline"}"></span>
            ${escHtml(id)}
        </div>
        <div class="card-meta">
            <span><span class="key">Model:</span>${escHtml(model)}</span>
            <span><span class="key">Tier:</span>${escHtml(tier)}</span>
            <span><span class="key">Host:</span>${escHtml(host)}</span>
            <span><span class="key">Status:</span><span class="badge ${status}">${status}</span></span>
        </div>
        <div class="card-actions">
            <button class="btn"
                    id="btn-worker-start-${id}"
                    onclick="sendNodeCommand('${escAttr(id)}', 'worker_start')"
                    ${status === "online" ? "disabled" : ""}>
                Uruchom Worker
            </button>
            <button class="btn danger"
                    id="btn-worker-stop-${id}"
                    onclick="sendNodeCommand('${escAttr(id)}', 'worker_stop')"
                    ${status !== "online" ? "disabled" : ""}>
                Zatrzymaj Worker
            </button>
            <button class="btn"
                    id="btn-sat-start-${id}"
                    onclick="sendNodeCommand('${escAttr(id)}', 'satellite_start')">
                Uruchom Satelitę
            </button>
            <button class="btn danger"
                    id="btn-sat-stop-${id}"
                    onclick="sendNodeCommand('${escAttr(id)}', 'satellite_stop')">
                Zatrzymaj Satelitę
            </button>
        </div>
    `;

    const body = document.getElementById("workers-body");
    const empty = body.querySelector(".empty-state");
    if (empty) empty.remove();

    if (!existing) body.appendChild(card);

    document.getElementById("worker-count").textContent = Object.keys(workers).length;
}

function markWorkerOffline(id) {
    const card = document.getElementById(`worker-${id}`);
    if (!card) return;

    const dot   = card.querySelector(".dot");
    const badge = card.querySelector(".badge");
    if (dot)   { dot.className   = "dot offline"; }
    if (badge) { badge.className = "badge offline"; badge.textContent = "offline"; }

    // Dezaktywuj przyciski stopu, aktywuj start
    const startBtn = document.getElementById(`btn-worker-start-${id}`);
    const stopBtn  = document.getElementById(`btn-worker-stop-${id}`);
    if (startBtn) startBtn.disabled = false;
    if (stopBtn)  stopBtn.disabled  = true;

    document.getElementById("worker-count").textContent = Object.keys(workers).length;
}

// ── Renderowanie kart satelit ──────────────────────────────────────────────

function renderSatelliteCard(sat) {
    const id = sat.id;
    const existing = document.getElementById(`satellite-${id}`);
    const card = existing || document.createElement("div");

    const room = sat.room || "—";
    const type = sat.type || "—";
    const caps = Array.isArray(sat.capabilities) ? sat.capabilities.join(", ") : (sat.capabilities || "—");

    card.id = `satellite-${id}`;
    card.className = "satellite-card";
    card.innerHTML = `
        <div class="card-title">
            <span class="dot online"></span>
            ${escHtml(id)}
        </div>
        <div class="card-meta">
            <span><span class="key">Pomieszczenie:</span>${escHtml(room)}</span>
            <span><span class="key">Typ:</span>${escHtml(type)}</span>
            <span><span class="key">Możliwości:</span>${escHtml(caps)}</span>
            <span><span class="key">VAD:</span><span class="vad-status" id="vad-${id}">cisza</span></span>
        </div>
    `;

    const body = document.getElementById("satellites-body");
    const empty = body.querySelector(".empty-state");
    if (empty) empty.remove();

    if (!existing) body.appendChild(card);

    document.getElementById("satellite-count").textContent = Object.keys(satellites).length;
}

function markSatelliteOffline(id) {
    const card = document.getElementById(`satellite-${id}`);
    if (!card) return;

    const dot = card.querySelector(".dot");
    if (dot) dot.className = "dot offline";

    document.getElementById("satellite-count").textContent = Object.keys(satellites).length;
}

function updateSatelliteVAD(satId, eventType, data) {
    const el = document.getElementById(`vad-${satId}`);
    if (!el) return;

    if (eventType === "vad_speech") {
        el.textContent = "mowa";
        el.className = "vad-status active";
    } else if (eventType === "wakeword") {
        el.textContent = "WakeWord!";
        el.className = "vad-status active";
    } else if (eventType === "vad_silence") {
        el.textContent = "cisza";
        el.className = "vad-status";
    }
}

// ── Dziennik zdarzeń ───────────────────────────────────────────────────────

function appendLog(timeStr, source, message, typeClass) {
    const list = document.getElementById("log-list");

    const entry = document.createElement("div");
    entry.className = `log-entry type-${typeClass || "info"}`;
    entry.innerHTML = `
        <span class="log-time">${escHtml(timeStr)}</span>
        <span class="log-source">${escHtml(source)}</span>
        <span class="log-msg">${escHtml(message)}</span>
    `;

    list.appendChild(entry);

    // Usuń najstarsze wpisy gdy przekroczono limit
    while (list.children.length > LOG_MAX) {
        list.removeChild(list.firstChild);
    }

    // Auto-scroll na dół tylko jeśli użytkownik jest blisko dołu
    const threshold = 60;
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < threshold;
    if (atBottom) list.scrollTop = list.scrollHeight;
}

// ── Obsługa zdarzeń SSE ────────────────────────────────────────────────────

function handleEvent(event) {
    const now = fmtTime(event.timestamp || null);

    switch (event.type) {
        case "worker_registered": {
            workers[event.id] = { ...event, status: "online" };
            renderWorkerCard(workers[event.id]);
            appendLog(now, `[${event.id}]`, `Worker zarejestrowany — ${event.model_name || ""} (${event.tier || ""})`, "worker_registered");
            break;
        }
        case "worker_unregistered": {
            if (workers[event.id]) workers[event.id].status = "offline";
            markWorkerOffline(event.id);
            appendLog(now, `[${event.id}]`, "Worker wyrejestrowany", "worker_unregistered");
            break;
        }
        case "satellite_registered": {
            satellites[event.id] = { ...event };
            renderSatelliteCard(satellites[event.id]);
            appendLog(now, `[${event.id}]`, `Satelita zarejestrowana — ${event.room || ""} (${event.type || ""})`, "satellite_registered");
            break;
        }
        case "satellite_unregistered": {
            if (satellites[event.id]) delete satellites[event.id];
            markSatelliteOffline(event.id);
            appendLog(now, `[${event.id}]`, "Satelita wyrejestrowana", "satellite_unregistered");
            break;
        }
        case "satellite_event": {
            const satId  = event.satellite_id || event.id;
            const evType = event.data?.type || event.event_type || "";
            updateSatelliteVAD(satId, evType, event.data);

            const labels = {
                "vad_speech": "VAD: mowa wykryta",
                "vad_silence": "VAD: cisza",
                "wakeword": "WakeWord wykryty",
            };
            const label = labels[evType] || evType;
            if (label) appendLog(now, `[${satId}]`, label, "satellite_event");
            break;
        }
        case "routing_decision": {
            const msg = `Routing → ${event.worker_id || "?"} | ${event.model_name || event.model || ""}`;
            appendLog(now, "[routing]", msg, "routing_decision");
            break;
        }
        case "conversation_turn": {
            const wid = event.worker_id ? ` (${event.worker_id})` : "";
            const tools = event.tool_count ? ` · ${event.tool_count} narzędzi` : "";
            appendLog(now, `[Ty]`, truncate(event.user_text, 120), "conversation_turn");
            appendLog(now, `[Regis${wid}]`, truncate(event.assistant_text, 200) + tools, "conversation_turn");
            break;
        }
        case "node_command_result": {
            const ok = event.success ? "OK" : "BŁĄD";
            const err = event.error ? ` — ${event.error}` : "";
            appendLog(now, `[${event.node_id}]`, `Komenda: ${event.command} → ${ok}${err}`, "node_command_result");
            break;
        }
        case "heartbeat": {
            // Wewnętrzny heartbeat SSE — cichy, bez wpisu w dzienniku
            break;
        }
        default:
            break;
    }
}

// ── Inicjalizacja stanu z /api/status ─────────────────────────────────────

async function init() {
    try {
        const resp = await fetch("/api/status");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        // Kontroler
        const ctrl = data.controller || {};
        updateHAStatus(ctrl.ha_status || "unknown");
        if (ctrl.uptime_s !== undefined) {
            document.getElementById("uptime").textContent = fmtUptime(ctrl.uptime_s);
        }

        // Węzły
        (data.workers || []).forEach(w => {
            workers[w.id] = { ...w, status: "online" };
            renderWorkerCard(workers[w.id]);
        });

        // Satelity
        (data.satellites || []).forEach(s => {
            satellites[s.id] = { ...s };
            renderSatelliteCard(satellites[s.id]);
        });

    } catch (e) {
        console.error("[Regis] Błąd ładowania /api/status:", e);
        appendLog(fmtTime(null), "[system]", `Błąd inicjalizacji: ${e.message}`, "error");
    }
}

function updateHAStatus(status) {
    const dot   = document.getElementById("ha-dot");
    const badge = document.getElementById("ha-status");
    if (!dot || !badge) return;

    const labels = { online: "ONLINE", offline: "OFFLINE", unknown: "—" };
    dot.className   = `dot ${status}`;
    badge.className = `badge ${status}`;
    badge.textContent = labels[status] || status.toUpperCase();
}

// Odśwież uptime co minutę
setInterval(async () => {
    try {
        const data = await fetch("/api/status").then(r => r.json());
        const ctrl = data.controller || {};
        if (ctrl.uptime_s !== undefined)
            document.getElementById("uptime").textContent = fmtUptime(ctrl.uptime_s);
        updateHAStatus(ctrl.ha_status || "unknown");
    } catch (_) {}
}, 60_000);

// ── Połączenie SSE ─────────────────────────────────────────────────────────

function connectSSE() {
    const sseDot    = document.getElementById("sse-dot");
    const sseStatus = document.getElementById("sse-status");

    const es = new EventSource("/api/events");

    es.onopen = () => {
        sseDot.style.background    = "var(--online)";
        sseStatus.textContent      = "połączono";
    };

    es.onmessage = (e) => {
        try {
            const event = JSON.parse(e.data);
            handleEvent(event);
        } catch (err) {
            console.warn("[Regis] Błąd parsowania SSE:", err, e.data);
        }
    };

    es.onerror = () => {
        sseDot.style.background = "var(--offline)";
        sseStatus.textContent   = "brak połączenia";
        es.close();
        // Próba ponownego połączenia po 5 sekundach
        setTimeout(connectSSE, 5000);
    };
}

// ── Sterowanie węzłami ─────────────────────────────────────────────────────

/**
 * Wysyła komendę do węzła przez Kontroler (proxy).
 * @param {string} nodeId
 * @param {string} command  worker_start|worker_stop|satellite_start|satellite_stop|status
 */
async function sendNodeCommand(nodeId, command) {
    const btnId = commandToBtnId(nodeId, command);
    const btn   = btnId ? document.getElementById(btnId) : null;

    if (btn) btn.disabled = true;

    try {
        const resp = await fetch(`/api/node/${encodeURIComponent(nodeId)}/command`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ command }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            appendLog(fmtTime(null), `[${nodeId}]`, `Komenda ${command} nie powiodła się: ${err.error || resp.status}`, "error");
        }
        // Wynik pojawi się przez EventBus (node_command_result)
    } catch (e) {
        appendLog(fmtTime(null), `[${nodeId}]`, `Błąd sieci: ${e.message}`, "error");
        if (btn) btn.disabled = false;
    }
}

function commandToBtnId(nodeId, command) {
    const map = {
        worker_start:    `btn-worker-start-${nodeId}`,
        worker_stop:     `btn-worker-stop-${nodeId}`,
        satellite_start: `btn-sat-start-${nodeId}`,
        satellite_stop:  `btn-sat-stop-${nodeId}`,
    };
    return map[command] || null;
}

// ── Narzędzia pomocnicze ───────────────────────────────────────────────────

/** Bezpieczne escapowanie HTML */
function escHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/** Escapowanie wartości atrybutów HTML (dla onclick) */
function escAttr(str) {
    return String(str || "").replace(/'/g, "\\'");
}

/** Skraca tekst do max znaków */
function truncate(str, max) {
    if (!str) return "";
    return str.length > max ? str.slice(0, max) + "…" : str;
}

// ── Start ──────────────────────────────────────────────────────────────────

init();
connectSSE();
