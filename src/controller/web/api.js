/**
 * Regis — Panel Kontrolny | api.js
 *
 * Warstwa sieciowa — inicjalizacja stanu z REST, strumień SSE, komendy węzłów.
 * Nie manipuluje DOM bezpośrednio — deleguje do renderer.js.
 *
 * Zależności: state.js, renderer.js, events.js, utils.js
 */

import { upsertWorker, upsertSatellite, workers, satellites } from './state.js';
import { renderWorkerCard, renderSatelliteCard, updateHAStatus, appendLog } from './renderer.js';
import { handleEvent } from './events.js';
import { fmtUptime, fmtTime } from './utils.js';

// ── Inicjalizacja stanu z /api/status ──────────────────────────────────────

export async function init() {
    try {
        const resp = await fetch("/api/status");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const ctrl = data.controller || {};
        updateHAStatus(ctrl.ha_status || "unknown");
        if (ctrl.uptime_s !== undefined) {
            document.getElementById("uptime").textContent = fmtUptime(ctrl.uptime_s);
        }

        (data.workers || []).forEach(w => {
            upsertWorker({ ...w, status: "online" });
            renderWorkerCard(workers[w.id]);
        });

        (data.satellites || []).forEach(s => {
            upsertSatellite({ ...s });
            renderSatelliteCard(satellites[s.id]);
        });

        _startUptimePoller();

    } catch (e) {
        console.error("[Regis] Błąd ładowania /api/status:", e);
        appendLog(fmtTime(null), "[system]", `Błąd inicjalizacji: ${e.message}`, "error");
    }
}

// ── Polling uptime (prywatny — uruchamiany raz przez init) ─────────────────

function _startUptimePoller() {
    setInterval(async () => {
        try {
            const data = await fetch("/api/status").then(r => r.json());
            const ctrl = data.controller || {};
            if (ctrl.uptime_s !== undefined)
                document.getElementById("uptime").textContent = fmtUptime(ctrl.uptime_s);
            updateHAStatus(ctrl.ha_status || "unknown");
        } catch (_) {}
    }, 60_000);
}

// ── Połączenie SSE ─────────────────────────────────────────────────────────

export function connectSSE() {
    const sseDot    = document.getElementById("sse-dot");
    const sseStatus = document.getElementById("sse-status");

    const es = new EventSource("/api/events");

    es.onopen = () => {
        sseDot.style.background = "var(--online)";
        sseStatus.textContent   = "połączono";
    };

    es.onmessage = (e) => {
        try {
            handleEvent(JSON.parse(e.data));
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
 * Eksportowana na window.sendNodeCommand — wymagane dla event listenerów w renderer.js.
 *
 * @param {string} nodeId
 * @param {string} command  worker_start | worker_stop | satellite_start | satellite_stop
 */
export async function sendNodeCommand(nodeId, command) {
    const btnId = _commandToBtnId(nodeId, command);
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
            appendLog(fmtTime(null), `[${nodeId}]`,
                `Komenda ${command} nie powiodła się: ${err.error || resp.status}`,
                "error");
        }
        // Wynik pojawi się przez EventBus (node_command_result)
    } catch (e) {
        appendLog(fmtTime(null), `[${nodeId}]`, `Błąd sieci: ${e.message}`, "error");
        if (btn) btn.disabled = false;
    }
}

function _commandToBtnId(nodeId, command) {
    const map = {
        worker_start:    `btn-worker-start-${nodeId}`,
        worker_stop:     `btn-worker-stop-${nodeId}`,
        satellite_start: `btn-sat-start-${nodeId}`,
        satellite_stop:  `btn-sat-stop-${nodeId}`,
    };
    return map[command] || null;
}
