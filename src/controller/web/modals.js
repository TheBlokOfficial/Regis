/**
 * Regis — Panel Kontrolny | modals.js
 *
 * Moduł obsługi okien modalnych (konfiguracja klientów RegisDesktop oraz dostawców chmurowych LLM).
 */

import { fetchSupportedModels, fetchNodeConfig, saveNodeConfig, fetchCloudProviders, addCloudProvider, patchCloudProvider, deleteCloudProvider } from './api.js';
import { appendLog, renderCloudProvidersList, showToast, withLoadingState } from './renderer.js';
import { fmtTime } from './utils.js';

let supportedModelsCache = [];
let cloudProvidersCache = [];

export function getCloudProvidersCache() {
    return cloudProvidersCache;
}

export function setCloudProvidersCache(cache) {
    cloudProvidersCache = cache;
}

// ── Modal Konfiguracji Klienta RegisDesktop ───────────────────────────────

export async function openClientConfigModal(nodeId) {
    const modal = document.getElementById("node-config-modal");
    if (!modal) return;

    document.getElementById("modal-node-id").value = nodeId;
    document.getElementById("modal-node-title").textContent = `Konfiguracja RegisDesktop: ${nodeId}`;

    if (supportedModelsCache.length === 0) {
        supportedModelsCache = await fetchSupportedModels();
    }

    const selectEl = document.getElementById("modal-worker-model");
    selectEl.innerHTML = supportedModelsCache.map(m =>
        `<option value="${m.id}">${m.name} (${m.id})</option>`
    ).join('');

    const cfg = await fetchNodeConfig(nodeId);
    const services = (cfg && cfg.services) || {};

    document.getElementById("modal-node-name").value = (cfg && cfg.name) || nodeId;

    // 1. Ollama LLM Worker
    const ollamaCfg = services.ollama_worker || services.worker;
    const hasOllama = !!ollamaCfg;
    document.getElementById("modal-enable-ollama").checked = hasOllama;
    document.getElementById("ollama-config-fields").style.display = hasOllama ? "block" : "none";
    if (ollamaCfg) {
        if (ollamaCfg.model_name) selectEl.value = ollamaCfg.model_name;
        document.getElementById("modal-worker-priority").value = ollamaCfg.priority ?? 100;
    }

    // 2. STT Worker
    const sttCfg = services.stt_worker;
    const hasStt = !!sttCfg;
    document.getElementById("modal-enable-stt").checked = hasStt;
    document.getElementById("stt-config-fields").style.display = hasStt ? "block" : "none";
    if (sttCfg) {
        if (sttCfg.stt_model_size) document.getElementById("modal-stt-size").value = sttCfg.stt_model_size;
        if (sttCfg.stt_language) document.getElementById("modal-stt-lang").value = sttCfg.stt_language;
    }

    // 3. TTS Worker
    const ttsCfg = services.tts_worker;
    const hasTts = !!ttsCfg;
    document.getElementById("modal-enable-tts").checked = hasTts;
    document.getElementById("tts-config-fields").style.display = hasTts ? "block" : "none";
    if (ttsCfg) {
        if (ttsCfg.tts_model_name) document.getElementById("modal-tts-model").value = ttsCfg.tts_model_name;
    }

    // 4. Satelita
    const satCfg = services.satellite;
    const hasSat = !!satCfg;
    document.getElementById("modal-enable-satellite").checked = hasSat;
    document.getElementById("satellite-config-fields").style.display = hasSat ? "block" : "none";
    if (satCfg || cfg.room) {
        document.getElementById("modal-satellite-room").value = (cfg && cfg.room) || (satCfg && satCfg.room) || "";
    }

    modal.style.display = "flex";
}

export function initNodeConfigModal() {
    const modal = document.getElementById("node-config-modal");
    if (!modal) return;

    const closeBtn = document.getElementById("modal-close-btn");
    const cancelBtn = document.getElementById("modal-cancel-btn");
    const form = document.getElementById("node-config-form");

    const enableOllamaCb = document.getElementById("modal-enable-ollama");
    const enableSttCb = document.getElementById("modal-enable-stt");
    const enableTtsCb = document.getElementById("modal-enable-tts");
    const enableSatCb = document.getElementById("modal-enable-satellite");

    enableOllamaCb.addEventListener("change", (e) => {
        document.getElementById("ollama-config-fields").style.display = e.target.checked ? "block" : "none";
    });
    enableSttCb.addEventListener("change", (e) => {
        document.getElementById("stt-config-fields").style.display = e.target.checked ? "block" : "none";
    });
    enableTtsCb.addEventListener("change", (e) => {
        document.getElementById("tts-config-fields").style.display = e.target.checked ? "block" : "none";
    });
    enableSatCb.addEventListener("change", (e) => {
        document.getElementById("satellite-config-fields").style.display = e.target.checked ? "block" : "none";
    });

    const closeModal = () => { modal.style.display = "none"; };
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const submitBtn = form.querySelector('button[type="submit"]');
        await withLoadingState(submitBtn, async () => {
            const nodeId = document.getElementById("modal-node-id").value;
            const name = document.getElementById("modal-node-name").value;
            const room = document.getElementById("modal-satellite-room").value.trim();

            const services = {};
            if (enableOllamaCb.checked) {
                services.ollama_worker = {
                    model_name: document.getElementById("modal-worker-model").value,
                    priority: parseInt(document.getElementById("modal-worker-priority").value, 10) || 100,
                };
            }
            if (enableSttCb.checked) {
                services.stt_worker = {
                    stt_model_size: document.getElementById("modal-stt-size").value || "small",
                    stt_language: document.getElementById("modal-stt-lang").value || "pl",
                };
            }
            if (enableTtsCb.checked) {
                services.tts_worker = {
                    tts_model_name: document.getElementById("modal-tts-model").value || "pl_PL-darkman-medium",
                };
            }
            if (enableSatCb.checked) {
                services.satellite = {
                    node_type: "desktop",
                    capabilities: ["audio_input", "tts_output", "wakeword"],
                    wakeword_local: true,
                };
            }

            try {
                await saveNodeConfig(nodeId, { name, room, services });
                appendLog(fmtTime(null), `[${nodeId}]`, "Zaktualizowano profil konfiguracji RegisDesktop z poziomu Web UI.", "node_registered");
                showToast("Zapisano konfigurację klienta.", "success");
                closeModal();
            } catch (err) {
                showToast(`Błąd zapisu konfiguracji: ${err.message}`, "error");
            }
        });
    });
}

// ── Modal Dostawców Chmurowych (Cloud Providers) ──────────────────────────

export function openCloudProviderModal(providerId = null) {
    const modal = document.getElementById("cloud-provider-modal");
    if (!modal) return;

    document.getElementById("cloud-provider-form")?.reset();

    const isEdit = !!providerId;
    document.getElementById("modal-cp-title").textContent = isEdit ? `Edycja: ${providerId}` : "Nowy Dostawca (Chmura)";
    document.getElementById("modal-cp-id").value = providerId || "";
    document.getElementById("modal-cp-delete-btn").style.display = isEdit ? "block" : "none";
    document.getElementById("modal-cp-type").disabled = isEdit;

    if (isEdit) {
        const cp = cloudProvidersCache.find(p => p.id === providerId);
        if (cp) {
            document.getElementById("modal-cp-type").value = cp.type;
            document.getElementById("modal-cp-model").value = cp.model;
            document.getElementById("modal-cp-priority").value = cp.priority || 50;
        }
    } else {
        document.getElementById("modal-cp-type").value = "openrouter";
        document.getElementById("modal-cp-model").value = "qwen/qwen-2.5-72b-instruct";
        document.getElementById("modal-cp-priority").value = "50";
    }

    modal.style.display = "flex";
}

export function initCloudProviderModal() {
    const modal = document.getElementById("cloud-provider-modal");
    if (!modal) return;

    const closeBtn = document.getElementById("modal-cp-close-btn");
    const cancelBtn = document.getElementById("modal-cp-cancel-btn");
    const delBtn = document.getElementById("modal-cp-delete-btn");
    const form = document.getElementById("cloud-provider-form");
    const addBtn = document.getElementById("add-cloud-provider-btn");

    const closeModal = () => { modal.style.display = "none"; form.reset(); };
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    if (addBtn) addBtn.addEventListener("click", () => openCloudProviderModal(null));

    if (delBtn) delBtn.addEventListener("click", async () => {
        const id = document.getElementById("modal-cp-id").value;
        if (!id || !confirm(`Na pewno usunąć providera ${id}?`)) return;
        await withLoadingState(delBtn, async () => {
            try {
                await deleteCloudProvider(id);
                showToast(`Usunięto providera ${id}.`, "success");
                closeModal();
                await renderCloudProvidersList();
            } catch (e) {
                showToast(`Błąd usuwania: ${e.message}`, "error");
            }
        });
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submitBtn = form.querySelector('button[type="submit"]');
        await withLoadingState(submitBtn, async () => {
            const id = document.getElementById("modal-cp-id").value;
            const isEdit = !!id;

            const payload = {
                id: isEdit ? id : `cp_${Date.now()}`,
                type: document.getElementById("modal-cp-type").value,
                api_key: document.getElementById("modal-cp-key").value,
                model: document.getElementById("modal-cp-model").value,
                priority: parseInt(document.getElementById("modal-cp-priority").value, 10) || 50,
            };

            try {
                if (isEdit) {
                    await patchCloudProvider(id, payload);
                    showToast("Zaktualizowano dostawcę chmurowego.", "success");
                } else {
                    if (!payload.api_key) {
                        showToast("Klucz API jest wymagany dla nowego providera!", "error");
                        return;
                    }
                    await addCloudProvider(payload);
                    showToast("Dodano nowego dostawcę chmurowego.", "success");
                }
                closeModal();
                await renderCloudProvidersList();
            } catch (err) {
                showToast(`Błąd zapisu: ${err.message}`, "error");
            }
        });
    });
}

// Globalne przypisania dla kompatybilności wstecznej z eventami inline
window.openClientConfigModal = openClientConfigModal;
window.openCloudProviderModal = openCloudProviderModal;

export function initModals() {
    initNodeConfigModal();
    initCloudProviderModal();
}
