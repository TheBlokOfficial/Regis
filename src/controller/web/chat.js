/**
 * Regis — Panel Kontrolny | chat.js
 *
 * Moduł czatu i zarządzania konwersacjami z wirtualną emulacją Satelity.
 */

import { escHtml } from './utils.js';
import { showToast, withLoadingState } from './renderer.js';

let _activeSatelliteId = "web_ui";
let _activeRoom = "";

export function initChat() {
    _bindTabs();
    _bindChatForm();
    _bindClearButton();
    _bindSatelliteSelect();
    loadSatellitesForSelect();
    loadSessionHistory(_activeSatelliteId);
}

function _bindTabs() {
    const btnDashboard = document.getElementById("tab-btn-dashboard");
    const btnChat      = document.getElementById("tab-btn-chat");
    const viewDash     = document.getElementById("view-dashboard");
    const viewChat     = document.getElementById("view-chat");

    if (btnDashboard && btnChat) {
        btnDashboard.addEventListener("click", () => {
            btnDashboard.classList.add("active");
            btnChat.classList.remove("active");
            viewDash.style.display = "flex";
            viewChat.style.display = "none";
        });

        btnChat.addEventListener("click", () => {
            btnChat.classList.add("active");
            btnDashboard.classList.remove("active");
            viewDash.style.display = "none";
            viewChat.style.display = "flex";
            loadSatellitesForSelect();
            loadSessionHistory(_activeSatelliteId);
        });
    }
}

function _bindSatelliteSelect() {
    const select = document.getElementById("chat-satellite-select");
    if (!select) return;

    select.addEventListener("change", (e) => {
        _activeSatelliteId = e.target.value;
        const opt = select.options[select.selectedIndex];
        _activeRoom = opt ? opt.getAttribute("data-room") || "" : "";
        loadSessionHistory(_activeSatelliteId);
    });
}

export async function loadSatellitesForSelect() {
    const select = document.getElementById("chat-satellite-select");
    if (!select) return;

    try {
        const resp = await fetch("/api/status");
        if (!resp.ok) return;
        const data = await resp.json();
        const sats = data.satellites || [];

        const currentVal = select.value;
        select.innerHTML = `<option value="web_ui" data-room="">Wirtualna Satelita — Web UI (Klawiatura)</option>`;

        sats.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.setAttribute("data-room", s.room || "");
            opt.textContent = `Satelita: ${s.id}${s.room ? ` (${s.room})` : ''}`;
            select.appendChild(opt);
        });

        select.value = currentVal;
    } catch (_) {}
}

export async function loadSessionHistory(satelliteId) {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    try {
        const resp = await fetch(`/v1/chat/history?satellite_id=${encodeURIComponent(satelliteId)}`);
        if (!resp.ok) return;
        const data = await resp.json();
        const history = data.history || [];

        container.innerHTML = "";
        if (history.length === 0) {
            container.innerHTML = `<p class="empty-state" style="text-align:center; padding:30px 0;">Brak historii konwersacji w tej sesji.</p>`;
            return;
        }

        history.forEach(turn => appendTurnToChat(turn));
        _scrollToBottom();
    } catch (e) {
        console.error("Błąd ładowania historii:", e);
    }
}

function _formatDuration(ms) {
    if (!ms || ms <= 0) return "";
    return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : ms + "ms";
}

export function formatAssistantMeta(turn) {
    const parts = [];

    // 1. Tożsamość + Model
    const modelStr = turn.model ? ` (${turn.model})` : "";
    parts.push(`Regis${modelStr}`);

    // 2. Liczba narzędzi
    const toolCount = turn.tools ? turn.tools.length : (turn.tool_count || 0);
    if (toolCount > 0) {
        const label = toolCount === 1 ? "narzędzie" : (toolCount < 5 ? "narzędzia" : "narzędzi");
        parts.push(`${toolCount} ${label}`);
    }

    // 3. Łączny czas wykonania
    if (turn.elapsed_ms) {
        parts.push(_formatDuration(turn.elapsed_ms));
    }

    // 4. Szczegóły telemetrii z Profilera
    const profiler = turn.profiler || {};
    const profParts = [];
    if (profiler.stt) profParts.push(`STT: ${_formatDuration(profiler.stt)}`);
    if (profiler.llm_ttft) profParts.push(`TTFT: ${_formatDuration(profiler.llm_ttft)}`);
    if (profiler.llm_gen) profParts.push(`Gen: ${_formatDuration(profiler.llm_gen)}`);
    if (profiler.tools) profParts.push(`Narzędzia: ${_formatDuration(profiler.tools)}`);

    if (profParts.length > 0) {
        parts.push(`[${profParts.join(" | ")}]`);
    }

    // 5. Timestamp
    if (turn.timestamp) {
        parts.push(turn.timestamp);
    }

    return parts.join(" · ");
}

export function renderToolsBlock(tools) {
    if (!tools || tools.length === 0) return "";

    let html = `<div class="tool-calls-container">`;
    tools.forEach(t => {
        if (!t) return;
        const name = t.name || "tool";
        const thought = t.thought || "";
        let argsStr = "";
        if (t.arguments) {
            if (typeof t.arguments === "object") {
                argsStr = Object.entries(t.arguments).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
            } else {
                argsStr = String(t.arguments);
            }
        }
        const resultStr = t.result !== undefined ? (typeof t.result === "object" ? JSON.stringify(t.result, null, 2) : String(t.result)) : "";

        let thoughtHtml = "";
        if (thought) {
            thoughtHtml = `
                <div class="tool-call-thought">
                    <div><strong>Monolog (Myśl):</strong></div>
                    <pre class="thought-content">${escHtml(thought)}</pre>
                </div>
            `;
        }

        html += `
            <details class="tool-call-block">
                <summary class="tool-call-summary">
                    <span>🛠️</span>
                    <span class="tool-call-name">${escHtml(name)}</span>
                    <span class="tool-call-args">(${escHtml(argsStr)})</span>
                </summary>
                ${thoughtHtml}
                <div class="tool-call-result">
                    <div><strong>Wynik Kontrolera:</strong></div>
                    <pre class="result-content">${escHtml(resultStr)}</pre>
                </div>
            </details>
        `;
    });
    html += `</div>`;
    return html;
}

export function getActiveSatelliteId() {
    return _activeSatelliteId;
}

export function appendTurnToChat(turn) {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    const empty = container.querySelector(".empty-state");
    if (empty) empty.remove();

    if (turn.user) {
        const uMsg = document.createElement("div");
        uMsg.className = "msg-wrapper user";
        uMsg.innerHTML = `
            <div class="msg-bubble">${escHtml(turn.user)}</div>
            <div class="msg-meta">${escHtml(turn.timestamp || "")}</div>
        `;
        container.appendChild(uMsg);
    }

    if (turn.assistant) {
        const aMsg = document.createElement("div");
        aMsg.className = "msg-wrapper assistant";
        const toolsHtml = renderToolsBlock(turn.tools);
        const metaStr = formatAssistantMeta(turn);
        aMsg.innerHTML = `
            ${toolsHtml}
            <div class="msg-bubble">${escHtml(turn.assistant)}</div>
            <div class="msg-meta">${escHtml(metaStr)}</div>
        `;
        container.appendChild(aMsg);
    }

    _scrollToBottom();
}

function _bindChatForm() {
    const form  = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    if (!form || !input) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        const sendBtn = document.getElementById("chat-send-btn");
        
        await withLoadingState(sendBtn, async () => {
            input.disabled = true;
            input.value = "";
            const now = new Date().toLocaleTimeString();

            // 1. Pokaż dymek użytkownika
            appendTurnToChat({ user: text, timestamp: now });

        // 2. Przygotuj dymek odpowiedzi do strumieniowania
        const container = document.getElementById("chat-messages");
        const aMsg = document.createElement("div");
        aMsg.className = "msg-wrapper assistant";
        aMsg.innerHTML = `
            <div id="streaming-tools"></div>
            <div class="msg-bubble" id="streaming-bubble">...</div>
            <div class="msg-meta" id="streaming-meta">Regis · generowanie...</div>
        `;
        container.appendChild(aMsg);
        _scrollToBottom();

        const bubble = document.getElementById("streaming-bubble");
        const meta   = document.getElementById("streaming-meta");
        const toolsContainer = document.getElementById("streaming-tools");
        let fullText = "";
        let currentModel = "";
        let usedTools = [];
        let profilerData = {};
        let elapsedMs = null;

        try {
            const resp = await fetch("/v1/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: text,
                    satellite_id: _activeSatelliteId,
                    room: _activeRoom || null
                })
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    if (buffer.trim()) {
                        // Process any remaining complete or incomplete line
                        let line = buffer.trim();
                        if (line.startsWith("data: ")) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === "done") {
                                    elapsedMs = data.elapsed_ms || null;
                                    if (bubble && !fullText) bubble.textContent = data.content;
                                    const finalMetaStr = formatAssistantMeta({
                                        model: currentModel,
                                        tools: usedTools,
                                        elapsed_ms: elapsedMs,
                                        profiler: profilerData,
                                        timestamp: now
                                    });
                                    if (meta) meta.textContent = finalMetaStr;
                                }
                            } catch (_) {}
                        }
                    }
                    break;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop(); // Keep the last, incomplete line in the buffer

                for (let line of lines) {
                    line = line.trim();
                    if (line.startsWith("data: ")) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === "routing_info") {
                                currentModel = data.model || "";
                                if (meta) meta.textContent = formatAssistantMeta({ model: currentModel, timestamp: "generowanie..." });
                            } else if (data.type === "content") {
                                fullText += data.content;
                                if (bubble) bubble.textContent = fullText;
                                _scrollToBottom();
                            } else if (data.type === "tool_dict" || data.type === "tool_call_raw") {
                                const toolInfo = typeof data.content === "string" ? data.content : JSON.stringify(data.content);
                                usedTools.push(toolInfo);
                                if (toolsContainer) toolsContainer.innerHTML = renderToolsBlock(usedTools);
                                _scrollToBottom();
                            } else if (data.type === "error") {
                                if (bubble) bubble.textContent = `[Błąd: ${data.content}]`;
                                showToast(`Błąd: ${data.content}`, "error");
                            } else if (data.type === "profiler") {
                                const m = data.content;
                                if (m && m.metric) {
                                    profilerData[m.metric] = (profilerData[m.metric] || 0) + (m.value || 0);
                                }
                            } else if (data.type === "done") {
                                elapsedMs = data.elapsed_ms || null;
                                if (bubble && !fullText) bubble.textContent = data.content || fullText;
                                const finalMetaStr = formatAssistantMeta({
                                    model: currentModel,
                                    tools: usedTools,
                                    elapsed_ms: elapsedMs,
                                    profiler: profilerData,
                                    timestamp: now
                                });
                                if (meta) meta.textContent = finalMetaStr;
                            }
                        } catch (_) {}
                    }
                }
            }
        } catch (e) {
            if (bubble) bubble.textContent = `[Błąd: ${e.message}]`;
            showToast(`Błąd generowania odpowiedzi: ${e.message}`, "error");
        } finally {
            if (bubble) bubble.removeAttribute("id");
            if (meta) meta.removeAttribute("id");
            if (toolsContainer) toolsContainer.removeAttribute("id");
            input.disabled = false;
            input.focus();
        }
        });
    });
}

function _bindClearButton() {
    const btn = document.getElementById("clear-chat-btn");
    if (!btn) return;

    btn.addEventListener("click", async () => {
        if (!confirm("Czy na pewno chcesz wyczyścić historię tej sesji?")) return;
        await withLoadingState(btn, async () => {
            try {
                const resp = await fetch(`/v1/clear_history?satellite_id=${encodeURIComponent(_activeSatelliteId)}`, { method: "POST" });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                showToast("Historia sesji została wyczyszczona.", "success");
                await loadSessionHistory(_activeSatelliteId);
            } catch (e) {
                showToast(`Błąd czyszczenia historii: ${e.message}`, "error");
            }
        });
    });
}

function _scrollToBottom() {
    const container = document.getElementById("chat-messages");
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}
