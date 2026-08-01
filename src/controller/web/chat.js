/**
 * Regis — Panel Kontrolny | chat.js
 *
 * Moduł czatu i zarządzania konwersacjami z wirtualną emulacją Satelity.
 */

import { escHtml } from './utils.js';

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
        const toolsText = turn.tools && turn.tools.length > 0 ? ` · ${turn.tools.length} narzędzi` : "";
        aMsg.innerHTML = `
            <div class="msg-bubble">${escHtml(turn.assistant)}</div>
            <div class="msg-meta">Regis ${toolsText} · ${escHtml(turn.timestamp || "")}</div>
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

        input.value = "";
        const now = new Date().toLocaleTimeString();

        // 1. Pokaż dymek użytkownika
        appendTurnToChat({ user: text, timestamp: now });

        // 2. Przygotuj dymek odpowiedzi do strumieniowania
        const container = document.getElementById("chat-messages");
        const aMsg = document.createElement("div");
        aMsg.className = "msg-wrapper assistant";
        aMsg.innerHTML = `
            <div class="msg-bubble" id="streaming-bubble">...</div>
            <div class="msg-meta" id="streaming-meta">Regis · generowanie...</div>
        `;
        container.appendChild(aMsg);
        _scrollToBottom();

        const bubble = document.getElementById("streaming-bubble");
        const meta   = document.getElementById("streaming-meta");
        let fullText = "";

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
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split("\n");

                for (let line of lines) {
                    line = line.trim();
                    if (line.startswith("data: ")) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === "content") {
                                fullText += data.content;
                                if (bubble) bubble.textContent = fullText;
                                _scrollToBottom();
                            } else if (data.type === "done") {
                                if (meta) meta.textContent = `Regis · ${now}`;
                                if (bubble && !fullText) bubble.textContent = data.content;
                            }
                        } catch (_) {}
                    }
                }
            }
        } catch (e) {
            if (bubble) bubble.textContent = `[Błąd: ${e.message}]`;
        } finally {
            if (bubble) bubble.removeAttribute("id");
            if (meta) meta.removeAttribute("id");
        }
    });
}

function _bindClearButton() {
    const btn = document.getElementById("clear-chat-btn");
    if (!btn) return;

    btn.addEventListener("click", async () => {
        if (!confirm("Czy na pewno chcesz wyczyścić historię tej sesji?")) return;
        try {
            await fetch(`/v1/clear_history?satellite_id=${encodeURIComponent(_activeSatelliteId)}`, { method: "POST" });
            loadSessionHistory(_activeSatelliteId);
        } catch (_) {}
    });
}

function _scrollToBottom() {
    const container = document.getElementById("chat-messages");
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}
