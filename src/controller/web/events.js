/**
 * Regis — Panel Kontrolny | events.js
 *
 * Obsługa zdarzeń SSE — mapowanie typów zdarzeń na mutacje stanu i aktualizacje DOM.
 * Jedyne miejsce, które łączy state.js z renderer.js w odpowiedzi na zdarzenia sieciowe.
 *
 * Zależności: state.js, renderer.js, utils.js
 */

import {
    upsertWorker, setWorkerStatus,
    upsertSatellite, removeSatellite,
    workers, satellites,
} from './state.js';
import {
    renderWorkerCard, markWorkerOffline,
    renderSatelliteCard, markSatelliteOffline,
    updateSatelliteVAD, appendLog,
} from './renderer.js';
import { fmtTime, truncate } from './utils.js';

export function handleEvent(event) {
    const now = fmtTime(event.timestamp || null);

    switch (event.type) {

        case "worker_registered": {
            upsertWorker({ ...event, status: "online" });
            renderWorkerCard(workers[event.id]);
            appendLog(now, `[${event.id}]`,
                `Worker zarejestrowany — ${event.model_name || ""} (${event.tier || ""})`,
                "worker_registered");
            break;
        }

        case "worker_unregistered": {
            setWorkerStatus(event.id, "offline");
            markWorkerOffline(event.id);
            appendLog(now, `[${event.id}]`, "Worker wyrejestrowany", "worker_unregistered");
            break;
        }

        case "satellite_registered": {
            upsertSatellite({ ...event });
            renderSatelliteCard(satellites[event.id]);
            appendLog(now, `[${event.id}]`,
                `Satelita zarejestrowana — ${event.room || ""} (${event.type || ""})`,
                "satellite_registered");
            break;
        }

        case "satellite_unregistered": {
            removeSatellite(event.id);
            markSatelliteOffline(event.id);
            appendLog(now, `[${event.id}]`, "Satelita wyrejestrowana", "satellite_unregistered");
            break;
        }

        case "satellite_event": {
            const satId  = event.satellite_id || event.id;
            const evType = event.data?.type || event.event_type || "";
            updateSatelliteVAD(satId, evType);

            const labels = {
                "vad_speech":  "VAD: mowa wykryta",
                "vad_silence": "VAD: cisza",
                "wakeword":    "WakeWord wykryty",
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
            const wid   = event.worker_id ? ` (${event.worker_id})` : "";
            const tools = event.tool_count ? ` · ${event.tool_count} narzędzi` : "";
            appendLog(now, "[Ty]",          truncate(event.user_text, 120),                "conversation_turn");
            appendLog(now, `[Regis${wid}]`, truncate(event.assistant_text, 200) + tools,   "conversation_turn");
            break;
        }

        case "node_command_result": {
            const ok  = event.success ? "OK" : "BŁĄD";
            const err = event.error ? ` — ${event.error}` : "";
            appendLog(now, `[${event.node_id}]`,
                `Komenda: ${event.command} → ${ok}${err}`,
                "node_command_result");
            break;
        }

        case "heartbeat":
            // Wewnętrzny heartbeat SSE — cichy, bez wpisu w dzienniku
            break;

        default:
            break;
    }
}
