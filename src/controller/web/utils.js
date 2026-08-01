/**
 * Regis — Panel Kontrolny | utils.js
 *
 * Czyste funkcje pomocnicze — zero zależności, zero efektów ubocznych.
 * Bezpieczne do importu z dowolnego modułu bez ryzyka cyklicznych zależności.
 */

/** Formatuje sekundy jako czytelny czas (np. 1h 5m / 3m 20s / 45s) */
export function fmtUptime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

/** Formatuje timestamp (ISO string lub HH:MM:SS) do lokalnego czasu */
export function fmtTime(ts) {
    if (!ts) {
        return new Date().toLocaleTimeString("pl-PL", { hour12: false });
    }
    if (ts.includes("T")) {
        return new Date(ts).toLocaleTimeString("pl-PL", { hour12: false });
    }
    return ts;
}

/** Bezpieczne escapowanie HTML — zapobiega XSS w innerHTML */
export function escHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/** Skraca tekst do max znaków z wielokropkiem */
export function truncate(str, max) {
    if (!str) return "";
    return str.length > max ? str.slice(0, max) + "…" : str;
}
