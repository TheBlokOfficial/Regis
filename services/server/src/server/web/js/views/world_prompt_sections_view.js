import { Icons } from '../icons.js';
import { flashButtonResult, lockButtonForAction } from '../utils/button_flash.js';
import { escapeAttr, escapeHtml } from '../utils/dom.js';
import { showToast } from '../utils/toast.js';

/**
 * Panel "Kontekst tury" — edycja tekstu faktów wstrzykiwanych agentowi przed
 * każdym pytaniem (`server/world/prompt_sections.py`).
 *
 * Do tej pory te zdania były literałami w Pythonie, więc zmiana instrukcji typu
 * "odpowiadaj krótko, bo to pójdzie na głos" wymagała edycji kodu źródłowego.
 *
 * Sekcje renderowane są w kolejności zwróconej przez serwer — **tej samej, w
 * jakiej trafiają do promptu** — więc panel czyta się jak podgląd wyniku.
 *
 * Świadomie NIE ma tu edycji formatu wiersza urządzenia ani nagłówków pokoi:
 * użytkownik edytuje to, co agent ma *usłyszeć*, silnik renderuje *dane*.
 * Zepsuty szablon wiersza po cichu zamieniłby całą listę urządzeń w śmieci.
 *
 * Zapis jest per sekcja (jawny przycisk przy każdej), nie globalny — pozwala
 * zapisać jedną zmianę bez ryzyka nadpisania pozostałych pól tym, co akurat
 * wisi w DOM. Wynik pokazywany na przycisku (`utils/button_flash.js`), tak jak
 * przy teście połączenia HA i konfiguracji klienta.
 */
export class WorldPromptSectionsView {
  constructor() {
    this.apiClient = null;
    this._sections = [];
  }

  render() {
    return `<div id="world-prompt-sections-list"></div>`;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    this._sections = await this.apiClient.getPromptSections();
    this._renderList();
  }

  _renderList() {
    const container = document.getElementById('world-prompt-sections-list');
    if (!container) return;

    if (!this._sections.length) {
      container.innerHTML = `<p class="section-hint">Nie udało się wczytać sekcji kontekstu tury.</p>`;
      return;
    }

    container.innerHTML = `
      <p class="section-hint wps-intro">
        Tekst wstrzykiwany agentowi tuż przed każdym pytaniem. Silnik decyduje, które
        sekcje się pojawią; tutaj decydujesz, co dokładnie mówią. Puste pole wycisza
        sekcję całkowicie.
      </p>
      ${this._sections.map((s) => this._renderSection(s)).join('')}
    `;

    container.querySelectorAll('[data-save-section]').forEach((btn) => {
      btn.addEventListener('click', () => this._save(btn.getAttribute('data-save-section')));
    });
    container.querySelectorAll('[data-reset-section]').forEach((btn) => {
      btn.addEventListener('click', () => this._reset(btn.getAttribute('data-reset-section')));
    });
  }

  _renderSection(section) {
    const placeholders = section.placeholders.length
      ? section.placeholders.map((p) => `<code class="wps-placeholder">${escapeHtml(p)}</code>`).join(' ')
      : '<span class="wps-placeholder-none">brak podstawień</span>';

    return `
      <div class="wps-section" data-section-key="${escapeAttr(section.key)}">
        <div class="wps-section-header">
          <span class="wps-section-label">${escapeHtml(section.label)}</span>
          <span class="badge-chip wps-condition">${escapeHtml(section.condition)}</span>
          ${section.is_overridden ? '<span class="badge-chip wps-overridden">zmienione</span>' : ''}
        </div>
        <div class="wps-box">
          <textarea
            class="wps-textarea"
            data-section-input="${escapeAttr(section.key)}"
            rows="3"
            placeholder="(puste — sekcja nie trafi do promptu)"
          >${escapeHtml(section.value)}</textarea>
        </div>
        <div class="wps-section-footer">
          <span class="wps-placeholders">${placeholders}</span>
          <span class="wps-section-actions">
            <button type="button" class="btn btn-sm btn-ghost" data-reset-section="${escapeAttr(section.key)}">
              Przywróć domyślne
            </button>
            <button type="button" class="btn btn-sm" data-save-section="${escapeAttr(section.key)}">Zapisz</button>
          </span>
        </div>
      </div>
    `;
  }

  async _save(key) {
    const input = document.querySelector(`[data-section-input="${CSS.escape(key)}"]`);
    const btn = document.querySelector(`[data-save-section="${CSS.escape(key)}"]`);
    if (!input || !btn) return;

    lockButtonForAction(btn);
    let ok = false;
    try {
      this._sections = await this.apiClient.updatePromptSections({ [key]: input.value });
      ok = true;
    } catch (error) {
      showToast(error.message || 'Błąd zapisu sekcji.', 'error');
    }
    flashButtonResult(btn, ok, { successHtml: Icons.Check(), errorHtml: Icons.X() });
    // Re-render dopiero PO rozbłysku — inaczej przycisk zniknąłby z DOM w trakcie
    // animacji i użytkownik nie zobaczyłby potwierdzenia zapisu.
    if (ok) setTimeout(() => this._renderList(), 2100);
  }

  /** `null` (a nie pusty string) — serwer odróżnia "przywróć domyślną" od "wycisz". */
  async _reset(key) {
    try {
      this._sections = await this.apiClient.updatePromptSections({ [key]: null });
      this._renderList();
      showToast('Przywrócono domyślną treść sekcji.', 'success');
    } catch (error) {
      showToast(error.message || 'Błąd przywracania domyślnej treści.', 'error');
    }
  }
}
