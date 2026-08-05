/**
 * Regis — Panel Kontrolny | api.js
 *
 * Warstwa sieciowa — inicjalizacja stanu z REST, strumień SSE, komendy węzłów.
 * Nie manipuluje DOM bezpośrednio — deleguje do renderer.js.
 *
 * Zależności: state.js, renderer.js, events.js, utils.js
 */

import { upsertWorker, upsertSatellite, workers, satellites } from './state.js';
import { renderWorkerCard, renderSatelliteCard, renderIntegrationsList, updateHAStatus, appendLog } from './renderer.js';
import { handleEvent } from './events.js';
import { fmtUptime, fmtTime } from './utils.js';

// ── Inicjalizacja stanu z /api/status ──────────────────────────────────────

let _currentUptimeS = 0;

export async function init() {
    try {
        const resp = await fetch("/api/status");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const ctrl = data.controller || {};
        if (data.integrations && data.integrations.length > 0) {
            renderIntegrationsList(data.integrations);
        } else {
            updateHAStatus(ctrl.ha_status || "unknown");
        }

        if (ctrl.uptime_s !== undefined) {
            _currentUptimeS = ctrl.uptime_s;
            document.getElementById("uptime").textContent = fmtUptime(_currentUptimeS);
        }

        (data.workers || []).forEach(w => {
            upsertWorker({ ...w, status: "online" });
            renderWorkerCard(workers[w.id]);
        });

        (data.satellites || []).forEach(s => {
            upsertSatellite({ ...s });
            renderSatelliteCard(satellites[s.id]);
        });

        _startUptimeTicker();

    } catch (e) {
        console.error("[Regis] Błąd ładowania /api/status:", e);
        appendLog(fmtTime(null), "[system]", `Błąd inicjalizacji: ${e.message}`, "error");
    }
}

// ── Ticker & Sync Uptime (inkrementacja co 1s + sync z REST co 15s) ──────────

function _startUptimeTicker() {
    // Lokalny zegar 1-sekundowy
    setInterval(() => {
        if (_currentUptimeS > 0) {
            _currentUptimeS++;
            document.getElementById("uptime").textContent = fmtUptime(_currentUptimeS);
        }
    }, 1000);

    // Synchronizacja z serwerem co 15 sekund
    setInterval(async () => {
        try {
            const data = await fetch("/api/status").then(r => r.json());
            const ctrl = data.controller || {};
            if (ctrl.uptime_s !== undefined) {
                _currentUptimeS = ctrl.uptime_s;
                document.getElementById("uptime").textContent = fmtUptime(_currentUptimeS);
            }
            if (data.integrations && data.integrations.length > 0) {
                renderIntegrationsList(data.integrations);
            } else {
                updateHAStatus(ctrl.ha_status || "unknown");
            }
        } catch (_) {}
    }, 15_000);
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
 * @param {string} command  Komenda do wykonania np. "service_control", "config"
 * @param {object} payload  Opcjonalne dane, np. {service: "worker", action: "start"}
 */
export async function sendNodeCommand(nodeId, command, payload = {}) {
    try {
        const resp = await fetch(`/api/node/${encodeURIComponent(nodeId)}/command`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ command, data: payload }),
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
    }
}

// ── Konfiguracja Węzłów ───────────────────────────────────────────────────

export async function fetchSupportedModels() {
    try {
        const resp = await fetch("/v1/clients/supported_models");
        if (!resp.ok) return [];
        const data = await resp.json();
        return data.models || [];
    } catch (e) {
        console.error("Błąd pobierania wspieranych modeli:", e);
        return [];
    }
}

export async function fetchNodeConfig(nodeId) {
    try {
        const resp = await fetch(`/v1/clients/${encodeURIComponent(nodeId)}/config`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.error(`Błąd pobierania konfiguracji węzła ${nodeId}:`, e);
        return null;
    }
}

export async function saveNodeConfig(nodeId, configData) {
    try {
        const resp = await fetch(`/v1/clients/${encodeURIComponent(nodeId)}/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(configData),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        return await resp.json();
    } catch (e) {
        console.error(`Błąd zapisu konfiguracji węzła ${nodeId}:`, e);
        throw e;
    }
}

// ── Cloud Providers API ───────────────────────────────────────────────────

export async function fetchCloudProviders() {
    try {
        const resp = await fetch("/api/cloud-providers");
        if (!resp.ok) return [];
        return await resp.json();
    } catch (e) {
        console.error("Błąd pobierania cloud providers:", e);
        return [];
    }
}

export async function addCloudProvider(providerData) {
    try {
        const resp = await fetch("/api/cloud-providers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(providerData),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        return await resp.json();
    } catch (e) {
        console.error("Błąd dodawania cloud providera:", e);
        throw e;
    }
}

export async function patchCloudProvider(providerId, updates) {
    try {
        const resp = await fetch(`/api/cloud-providers/${encodeURIComponent(providerId)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(updates),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        return await resp.json();
    } catch (e) {
        console.error(`Błąd aktualizacji providera ${providerId}:`, e);
        throw e;
    }
}

export async function deleteCloudProvider(providerId) {
    try {
        const resp = await fetch(`/api/cloud-providers/${encodeURIComponent(providerId)}`, {
            method: "DELETE"
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        return true;
    } catch (e) {
        console.error(`Błąd usuwania providera ${providerId}:`, e);
        throw e;
    }
}
