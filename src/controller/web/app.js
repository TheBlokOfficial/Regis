/**
 * Regis — Panel Kontrolny | app.js
 *
 * Punkt startowy — orchestruje inicjalizację modułów.
 * Nie zawiera logiki biznesowej.
 *
 * Graf zależności:
 *   app.js → renderer.js → state.js
 *                        → utils.js
 *          → api.js     → state.js
 *                        → renderer.js
 *                        → events.js → state.js
 *                                    → renderer.js
 *                                    → utils.js
 *                        → utils.js
 */

import { initClock, appendLog } from './renderer.js';
import { init, connectSSE, sendNodeCommand, fetchSupportedModels, fetchNodeConfig, saveNodeConfig } from './api.js';
import { initChat } from './chat.js';
import { fmtTime } from './utils.js';

window.sendNodeCommand = sendNodeCommand;

function initRouting() {
    const navButtons = document.querySelectorAll('.sidebar-nav .nav-btn');
    const viewSections = document.querySelectorAll('.view-section');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetView = btn.getAttribute('data-view');
            
            navButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            viewSections.forEach(section => {
                if (section.id === `view-${targetView}`) {
                    section.style.display = (targetView === 'chat' || targetView === 'logs') ? 'flex' : 'block';
                    section.classList.add('active');
                } else {
                    section.style.display = 'none';
                    section.classList.remove('active');
                }
            });
        });
    });
}


let supportedModelsCache = [];

async function openNodeConfigModal(nodeId) {
    const modal = document.getElementById("node-config-modal");
    if (!modal) return;

    document.getElementById("modal-node-id").value = nodeId;
    document.getElementById("modal-node-title").textContent = `Konfiguracja Węzła: ${nodeId}`;

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

    // Worker
    const workerCfg = services.worker;
    const hasWorker = !!workerCfg;
    document.getElementById("modal-enable-worker").checked = hasWorker;
    document.getElementById("worker-config-fields").style.display = hasWorker ? "block" : "none";
    if (workerCfg) {
        if (workerCfg.model_name) selectEl.value = workerCfg.model_name;
        document.getElementById("modal-worker-priority").value = workerCfg.priority ?? 100;
    }

    // Satelita
    const satCfg = services.satellite;
    const hasSat = !!satCfg;
    document.getElementById("modal-enable-satellite").checked = hasSat;
    document.getElementById("satellite-config-fields").style.display = hasSat ? "block" : "none";
    if (satCfg) {
        document.getElementById("modal-satellite-room").value = satCfg.room || "";
    }

    modal.style.display = "flex";
}

function initNodeConfigModal() {
    const modal = document.getElementById("node-config-modal");
    if (!modal) return;

    const closeBtn = document.getElementById("modal-close-btn");
    const cancelBtn = document.getElementById("modal-cancel-btn");
    const form = document.getElementById("node-config-form");

    const enableWorkerCb = document.getElementById("modal-enable-worker");
    const enableSatCb = document.getElementById("modal-enable-satellite");

    enableWorkerCb.addEventListener("change", (e) => {
        document.getElementById("worker-config-fields").style.display = e.target.checked ? "block" : "none";
    });

    enableSatCb.addEventListener("change", (e) => {
        document.getElementById("satellite-config-fields").style.display = e.target.checked ? "block" : "none";
    });

    const closeModal = () => { modal.style.display = "none"; };
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const nodeId = document.getElementById("modal-node-id").value;
        const name = document.getElementById("modal-node-name").value;

        const services = {};
        if (enableWorkerCb.checked) {
            services.worker = {
                model_name: document.getElementById("modal-worker-model").value,
                priority: parseInt(document.getElementById("modal-worker-priority").value, 10) || 100,
            };
        }
        if (enableSatCb.checked) {
            services.satellite = {
                room: document.getElementById("modal-satellite-room").value || "brak",
                node_type: "desktop",
                capabilities: ["audio_input", "tts_output", "wakeword"],
                wakeword_local: true,
            };
        }

        try {
            await saveNodeConfig(nodeId, { name, services });
            appendLog(fmtTime(null), `[${nodeId}]`, "Zaktualizowano profil konfiguracji Węzła z poziomu Web UI.", "node_registered");
            closeModal();
        } catch (err) {
            alert(`Błąd zapisu konfiguracji: ${err.message}`);
        }
    });
}

// ── Cloud Providers ────────────────────────────────────────────────────────

import { fetchCloudProviders, addCloudProvider, patchCloudProvider, deleteCloudProvider } from './api.js';

let cloudProvidersCache = [];

async function renderCloudProviders() {
    cloudProvidersCache = await fetchCloudProviders();
    const container = document.getElementById("cloud-providers-tree-body");
    
    if (!cloudProvidersCache || cloudProvidersCache.length === 0) {
        container.innerHTML = '<div class="empty-state">Brak skonfigurowanych dostawców chmurowych.</div>';
        return;
    }
    
    container.innerHTML = cloudProvidersCache.map(cp => `
        <div class="list-row">
            <span class="list-icon">[EXT]</span>
            <div class="list-info">
                <span class="list-title">${cp.id}</span>
                <span class="list-meta">(${cp.type}) Model: ${cp.model} | Tryb: ${cp.mode} | Prio: ${cp.priority}</span>
            </div>
            <div class="list-actions">
                <button class="btn" onclick="openCloudProviderModal('${cp.id}')" style="font-size: 13px;">EDYTUJ</button>
            </div>
        </div>
    `).join('');
}

function openCloudProviderModal(providerId = null) {
    const modal = document.getElementById("cloud-provider-modal");
    if (!modal) return;
    
    document.getElementById("modal-cp-form")?.reset();
    
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
            document.getElementById("modal-cp-mode").value = cp.mode || "extended";
            document.getElementById("modal-cp-priority").value = cp.priority || 50;
        }
    } else {
        document.getElementById("modal-cp-type").value = "openrouter";
        document.getElementById("modal-cp-model").value = "qwen/qwen-2.5-72b-instruct";
        document.getElementById("modal-cp-mode").value = "extended";
        document.getElementById("modal-cp-priority").value = "50";
    }
    
    modal.style.display = "flex";
}

function initCloudProviderModal() {
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
    window.openCloudProviderModal = openCloudProviderModal;

    if (delBtn) delBtn.addEventListener("click", async () => {
        const id = document.getElementById("modal-cp-id").value;
        if (!id || !confirm(`Na pewno usunąć providera ${id}?`)) return;
        try {
            await deleteCloudProvider(id);
            closeModal();
            renderCloudProviders();
        } catch (e) {
            alert(`Błąd usuwania: ${e.message}`);
        }
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = document.getElementById("modal-cp-id").value;
        const isEdit = !!id;
        
        const payload = {
            id: isEdit ? id : `cp_${Date.now()}`,
            type: document.getElementById("modal-cp-type").value,
            api_key: document.getElementById("modal-cp-key").value,
            model: document.getElementById("modal-cp-model").value,
            mode: document.getElementById("modal-cp-mode").value,
            priority: parseInt(document.getElementById("modal-cp-priority").value, 10) || 50,
        };
        
        try {
            if (isEdit) {
                await patchCloudProvider(id, payload);
            } else {
                if (!payload.api_key) {
                    alert("Klucz API jest wymagany dla nowego providera!");
                    return;
                }
                await addCloudProvider(payload);
            }
            closeModal();
            renderCloudProviders();
        } catch (err) {
            alert(`Błąd zapisu: ${err.message}`);
        }
    });
}

window.openNodeConfigModal = openNodeConfigModal;

initRouting();
initClock();
init();
connectSSE();
initChat();
initNodeConfigModal();
initCloudProviderModal();
renderCloudProviders();

