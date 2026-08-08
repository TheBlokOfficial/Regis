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

        case "client_registered":
        case "client_updated": {
            const node = event.client || event;
            renderNodeCard(node);
            if (event.type === "client_registered" && !event.is_history) {
                appendLog(now, "[INFO]", `Zarejestrowano klienta RegisDesktop: ${node.name || node.id}`, "online");
            }
            break;
        }

        case "client_unregistered": {
            if (workers[event.id]) {
                setWorkerStatus(event.id, "offline");
                markWorkerOffline(event.id);
            }
            if (satellites[event.id]) {
                removeSatellite(event.id);
                markSatelliteOffline(event.id);
            }
            if (!event.is_history) appendLog(now, "[OFFLINE]", `RegisDesktop ${event.id} został odłączony`, "offline");
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

        case "client_command_result": {
            // Logujemy tylko niepowodzenia komend (błędy)
            if (!event.success) {
                const err = event.error || "brak szczegółów";
                appendLog(now, "[ERROR]",
                    `Błąd wykonania komendy '${event.command}' na kliencie ${event.client_id}: ${err}`,
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
