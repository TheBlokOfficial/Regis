/**
 * Regis — Panel Kontrolny | state.js
 *
 * Centralny store — jedyne źródło prawdy dla stanu aplikacji.
 * Eksportuje niemutowalne przez zewnątrz dane i kontrolowane funkcje mutacji.
 * Zero zależności od innych modułów.
 */

/** @type {Object.<string, Object>} id → dane węzła roboczego */
export const workers = {};

/** @type {Object.<string, Object>} id → dane satelity */
export const satellites = {};

// ── Mutacje węzłów ────────────────────────────────────────────────────────

export function upsertWorker(data) {
    workers[data.id] = { ...data };
}

export function setWorkerStatus(id, status) {
    if (workers[id]) workers[id].status = status;
}

// ── Mutacje satelit ───────────────────────────────────────────────────────

export function upsertSatellite(data) {
    satellites[data.id] = { ...data };
}

export function removeSatellite(id) {
    delete satellites[id];
}

// ── Gettery ───────────────────────────────────────────────────────────────

export function workerCount() {
    return Object.keys(workers).length;
}

export function satelliteCount() {
    return Object.keys(satellites).length;
}
