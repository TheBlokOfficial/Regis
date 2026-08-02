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
    renderNodeCard, renderWorkerCard, markWorkerOffline,
    renderSatelliteCard, markSatelliteOffline,
    updateSatelliteVAD, appendLog,
} from './renderer.js';
import { fmtTime, truncate } from './utils.js';
import { getActiveSatelliteId, appendTurnToChat } from './chat.js';

export function handleEvent(event) {
    const now = fmtTime(event.timestamp || null);

    switch (event.type) {

        case "node_registered":
        case "node_updated": {
            const node = event.node || event;
            renderNodeCard(node);
            const services = node.services || {};
            const isDict = typeof services === 'object' && !Array.isArray(services);
            const serviceList = isDict ? Object.keys(services) : (Array.isArray(services) ? services : []);
            appendLog(now, `[${node.id}]`, `Zjednoczony Węzeł zaktualizowany — usługi: ${serviceList.join(", ")}`, "node_registered");
            break;
        }

        case "node_unregistered": {
            if (workers[event.id]) {
                setWorkerStatus(event.id, "offline");
                markWorkerOffline(event.id);
            }
            if (satellites[event.id]) {
                removeSatellite(event.id);
                markSatelliteOffline(event.id);
            }
            appendLog(now, `[${event.id}]`, "Zjednoczony Węzeł wyrejestrowany", "node_unregistered");
            break;
        }

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
            // VAD / audio nie zaśmiecają dziennika technicznego
            break;
        }

        case "routing_decision": {
            // Decyzje routingowe usunięte z dziennika głównego
            break;
        }

        case "conversation_turn": {
            // Szczegóły tury trafiają do czatu konwersacyjnego, nie do dziennika
            const activeSat = getActiveSatelliteId();
            const eventSat = event.satellite_id || "web_ui";
            if (activeSat === eventSat) {
                appendTurnToChat({
                    user: event.user_text,
                    assistant: event.assistant_text,
                    timestamp: now,
                    tools: event.tools || [],
                    tool_count: event.tool_count || 0,
                    model: event.model,
                    elapsed_ms: event.elapsed_ms,
                    profiler: event.profiler
                });
            }
            break;
        }

        case "node_command_result": {
            // Logujemy tylko niepowodzenia komend (błędy)
            if (!event.success) {
                const err = event.error ? ` — ${event.error}` : "";
                appendLog(now, `[${event.node_id}]`,
                    `Błąd wykonania komendy '${event.command}': ${err}`,
                    "error");
            }
            break;
        }

        case "heartbeat":
            // Wewnętrzny heartbeat SSE — cichy, bez wpisu w dzienniku
            break;

        default:
            break;
    }
}
