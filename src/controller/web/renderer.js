/**
 * Regis — Panel Kontrolny | renderer.js
 *
 * Warstwa DOM — jedyne miejsce modyfikujące interfejs użytkownika.
 * Nie zna sieci ani logiki zdarzeń biznesowych.
 *
 * Zależności: state.js (liczniki), utils.js (escapowanie)
 */

import { workerCount, satelliteCount } from './state.js';
import { escHtml } from './utils.js';

// Maksymalna liczba wpisów w dzienniku (zapobiega rosnącemu DOM bez końca)
const LOG_MAX = 300;

// ── Zegar ──────────────────────────────────────────────────────────────────

export function initClock() {
    function tick() {
        document.getElementById("clock").textContent =
            new Date().toLocaleTimeString("pl-PL", { hour12: false });
    }
    setInterval(tick, 1000);
    tick();
}

// ── Status Home Assistant ──────────────────────────────────────────────────

export function updateHAStatus(status) {
    const dot   = document.getElementById("ha-dot");
    const badge = document.getElementById("ha-status");
    if (!dot || !badge) return;

    const labels = { online: "ONLINE", offline: "OFFLINE", unknown: "—" };
    dot.className     = `dot ${status}`;
    badge.className   = `badge ${status}`;
    badge.textContent = labels[status] || status.toUpperCase();
}

// ── Karty węzłów roboczych ─────────────────────────────────────────────────

export function renderWorkerCard(worker) {
    const id       = worker.id;
    const existing = document.getElementById(`worker-${id}`);
    const card     = existing || document.createElement("div");

    const status = worker.status || "online";
    const model  = worker.model_name || "—";
    const tier   = worker.tier || "—";
    const host   = worker.host ? `${worker.host}:${worker.port || "?"}` : "—";

    card.id        = `worker-${id}`;
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
            <button class="btn" id="btn-worker-start-${id}" ${status === "online" ? "disabled" : ""}>
                Uruchom Worker
            </button>
            <button class="btn danger" id="btn-worker-stop-${id}" ${status !== "online" ? "disabled" : ""}>
                Zatrzymaj Worker
            </button>
            <button class="btn" id="btn-sat-start-${id}">
                Uruchom Satelitę
            </button>
            <button class="btn danger" id="btn-sat-stop-${id}">
                Zatrzymaj Satelitę
            </button>
        </div>
    `;

    // addEventListener zamiast inline onclick — poprawna obsługa modułów ES
    card.querySelector(`#btn-worker-start-${id}`)
        .addEventListener("click", () => window.sendNodeCommand(id, "worker_start"));
    card.querySelector(`#btn-worker-stop-${id}`)
        .addEventListener("click", () => window.sendNodeCommand(id, "worker_stop"));
    card.querySelector(`#btn-sat-start-${id}`)
        .addEventListener("click", () => window.sendNodeCommand(id, "satellite_start"));
    card.querySelector(`#btn-sat-stop-${id}`)
        .addEventListener("click", () => window.sendNodeCommand(id, "satellite_stop"));

    const body  = document.getElementById("workers-body");
    const empty = body.querySelector(".empty-state");
    if (empty) empty.remove();

    if (!existing) body.appendChild(card);

    document.getElementById("worker-count").textContent = workerCount();
}

export function markWorkerOffline(id) {
    const card = document.getElementById(`worker-${id}`);
    if (!card) return;

    const dot   = card.querySelector(".dot");
    const badge = card.querySelector(".badge");
    if (dot)   { dot.className   = "dot offline"; }
    if (badge) { badge.className = "badge offline"; badge.textContent = "offline"; }

    const startBtn = document.getElementById(`btn-worker-start-${id}`);
    const stopBtn  = document.getElementById(`btn-worker-stop-${id}`);
    if (startBtn) startBtn.disabled = false;
    if (stopBtn)  stopBtn.disabled  = true;

    document.getElementById("worker-count").textContent = workerCount();
}

// ── Karty satelit ──────────────────────────────────────────────────────────

export function renderSatelliteCard(sat) {
    const id       = sat.id;
    const existing = document.getElementById(`satellite-${id}`);
    const card     = existing || document.createElement("div");

    const room = sat.room || "—";
    const type = sat.type || "—";
    const caps = Array.isArray(sat.capabilities)
        ? sat.capabilities.join(", ")
        : (sat.capabilities || "—");

    card.id        = `satellite-${id}`;
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

    const body  = document.getElementById("satellites-body");
    const empty = body.querySelector(".empty-state");
    if (empty) empty.remove();

    if (!existing) body.appendChild(card);

    document.getElementById("satellite-count").textContent = satelliteCount();
}

export function markSatelliteOffline(id) {
    const card = document.getElementById(`satellite-${id}`);
    if (!card) return;

    const dot = card.querySelector(".dot");
    if (dot) dot.className = "dot offline";

    document.getElementById("satellite-count").textContent = satelliteCount();
}

export function updateSatelliteVAD(satId, eventType) {
    const el = document.getElementById(`vad-${satId}`);
    if (!el) return;

    if (eventType === "vad_speech") {
        el.textContent = "mowa";
        el.className   = "vad-status active";
    } else if (eventType === "wakeword") {
        el.textContent = "WakeWord!";
        el.className   = "vad-status active";
    } else if (eventType === "vad_silence") {
        el.textContent = "cisza";
        el.className   = "vad-status";
    }
}

// ── Dziennik zdarzeń ───────────────────────────────────────────────────────

export function appendLog(timeStr, source, message, typeClass) {
    const list  = document.getElementById("log-list");
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
    const atBottom  = list.scrollHeight - list.scrollTop - list.clientHeight < threshold;
    if (atBottom) list.scrollTop = list.scrollHeight;
}
