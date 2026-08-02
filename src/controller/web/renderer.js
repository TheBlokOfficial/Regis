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

// ── Karty integracji ────────────────────────────────────────────────────────

export function renderIntegrationCard(integration) {
    const id       = integration.id;
    const existing = document.getElementById(`integration-${id}`);
    const card     = existing || document.createElement("div");

    const status = integration.status || "unknown";
    const name   = integration.name || id;
    const type   = integration.type || "—";
    const detail = integration.detail || "—";

    const labels = { online: "ONLINE", offline: "OFFLINE", unknown: "—" };
    const badgeText = labels[status] || status.toUpperCase();

    card.id        = `integration-${id}`;
    card.className = "list-row";
    card.innerHTML = `
        <span class="dot ${status}"></span>
        <div class="list-info">
            <span class="list-title">${escHtml(name)}</span>
            <span class="list-meta">(${escHtml(type)}) ${escHtml(detail)}</span>
        </div>
        <div class="list-actions">
            <span class="badge ${status}">${badgeText}</span>
        </div>
    `;

    const body  = document.getElementById("integrations-tree-body");
    if (!body) return;
    const empty = body.querySelector(".empty-state");
    if (empty) empty.remove();

    if (!existing) body.appendChild(card);

    const countEl = document.getElementById("integration-count");
    if (countEl) {
        countEl.textContent = body.querySelectorAll(".list-row").length;
    }
}

export function renderIntegrationsList(integrations) {
    if (Array.isArray(integrations) && integrations.length > 0) {
        integrations.forEach(item => renderIntegrationCard(item));
    }
}

export function updateHAStatus(status) {
    renderIntegrationCard({
        id: "home_assistant",
        name: "Home Assistant",
        type: "Smart Home",
        detail: "Sterowanie urządzeniami & encjami",
        status: status || "unknown"
    });
}

// ── Zjednoczone Karty Węzłów Systemowych ─────────────────────────────────

export function renderNodeCard(node) {
    const id = node.id;
    const existing = document.getElementById(`node-${id}`);
    const card = existing || document.createElement("div");

    const name = node.name || id;
    const host = node.host ? (node.port ? `${node.host}:${node.port}` : node.host) : "—";
    const services = node.services || {};
    const isDict = typeof services === 'object' && !Array.isArray(services);

    let tagsHtml = '';

    const workerConfig = isDict ? services.worker : (Array.isArray(services) && services.includes("worker") ? node : null);
    if (workerConfig) {
        const model = workerConfig.model_name || node.model_name || "qwen3.5:9b";
        tagsHtml += `<span class="service-tag">WORKER (${escHtml(model)})</span> `;
    }

    const satConfig = isDict ? services.satellite : (Array.isArray(services) && services.includes("satellite") ? node : null);
    if (satConfig) {
        const room = satConfig.room || node.room || "brak";
        tagsHtml += `<span class="service-tag">SAT (${escHtml(room)})</span>`;
    }

    card.id = `node-${id}`;
    card.className = "list-row";
    card.innerHTML = `
        <span class="dot online"></span>
        <div class="list-info">
            <span class="list-title">${escHtml(name)}</span>
            <span class="list-meta">ID: ${escHtml(id)} | Host: ${escHtml(host)}</span>
            <div style="margin-top:6px;">${tagsHtml}</div>
        </div>
        <div class="list-actions">
            <button class="btn btn-configure-node" id="btn-config-${id}">
                KONFIGURUJ
            </button>
        </div>
    `;

    card.querySelector(`#btn-config-${id}`)
        .addEventListener("click", () => window.openNodeConfigModal(id));

    const body = document.getElementById("nodes-tree-body");
    if (!body) return;
    const empty = body.querySelector(".empty-state");
    if (empty) empty.remove();

    if (!existing) body.appendChild(card);

    const countEl = document.getElementById("worker-count");
    if (countEl) {
        countEl.textContent = body.children.length;
    }
}

export function renderWorkerCard(worker) {
    renderNodeCard(worker);
}

export function renderSatelliteCard(sat) {
    renderNodeCard(sat);
}

export function markWorkerOffline(id) {
    const card = document.getElementById(`node-${id}`);
    if (!card) return;
    const dot = card.querySelector(".dot");
    if (dot) dot.className = "dot offline";
}

export function markSatelliteOffline(id) {
    markWorkerOffline(id);
}

export function updateSatelliteVAD(satId, eventType) {
    let el = document.getElementById(`vad-${satId}`);
    if (!el) {
        el = document.querySelector(".satellite-card .vad-status") || document.querySelector(".vad-status");
    }
    if (!el) return;

    if (eventType === "vad_speech") {
        el.textContent = "MOWA";
        el.className   = "vad-status active";
    } else if (eventType === "wakeword") {
        el.textContent = "WAKEWORD";
        el.className   = "vad-status active";
    } else if (eventType === "vad_silence") {
        el.textContent = "CISZA";
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
