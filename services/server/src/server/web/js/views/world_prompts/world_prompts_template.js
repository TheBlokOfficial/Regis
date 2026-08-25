import { Icons } from '../../icons.js';
import { escapeAttr, escapeHtml } from '../../utils/dom.js';

/**
 * Czyste funkcje renderujące HTML widoku profili promptu Świata — wydzielone z
 * `WorldPromptsView` (wzorzec `renderXMarkup` z `components/select.js`, ten sam co
 * `chat/chat_template.js`/`voice/voice_client_template.js`). Zero dostępu do `this`/DOM,
 * tylko stringi. W odróżnieniu od Czatu/Klientów ten widok nie ma kanału SSE ani drugiej
 * niezależnej odpowiedzialności — to jeden spójny edytor CRUD, więc jedynym wydzieleniem
 * jest szablon; reszta (stan listy/edytora, wiązanie zdarzeń, akcje) zostaje w klasie.
 */

export function renderWorldPromptsLayoutMarkup() {
  return `
    <div class="wp-layout" id="wp-layout">
      <nav class="pill-tabs wp-profile-tabs" id="wp-list"></nav>
      <div class="wp-panel-editor" id="wp-panel-editor">
        <div class="skeleton-stack">
          <div class="skeleton-block skeleton-block--field"></div>
          <div class="skeleton-block skeleton-block--section"></div>
        </div>
      </div>
    </div>
  `;
}

export function renderListErrorMarkup() {
  return `<div class="wp-list-error">Błąd ładowania listy profili promptu.</div>`;
}

/** Przełącznik profili — pill-taby, bo pozycji jest najwyżej `MAX_PROFILES`.
 * Kropka aktywności siedzi w samym tabie, więc widać ją bez wchodzenia w profil. */
export function renderProfileTabMarkup(prompt, { isActive, isSelected }) {
  return `
    <button type="button" class="pill-tab wp-profile-tab ${isSelected ? 'active' : ''}"
      data-id="${escapeAttr(prompt.id)}" title="${escapeAttr(prompt.description || prompt.name)}"
      ${isSelected ? 'aria-current="true"' : ''}>
      ${isActive ? '<span class="wp-profile-tab-dot" title="Aktywny profil"></span>' : ''}
      <span class="wp-profile-tab-name">${escapeHtml(prompt.name)}</span>
    </button>
  `;
}

export function renderNewProfileTabMarkup({ atLimit, isNewMode, maxProfiles }) {
  return `
    <button type="button" class="pill-tab wp-profile-tab wp-profile-tab--new ${isNewMode ? 'active' : ''}"
      id="wp-btn-new" ${atLimit ? 'disabled' : ''}
      title="${atLimit ? `Osiągnięto limit ${maxProfiles} profili` : 'Nowy profil'}">
      ${Icons.Plus()} Nowy
    </button>
  `;
}

export function renderEmptyEditorMarkup() {
  return `
    <div class="wp-editor-empty">
      <div class="wp-editor-empty-icon">${Icons.Cpu()}</div>
      <p>Wybierz prompt z listy lub utwórz nowy.</p>
    </div>
  `;
}

/**
 * Jeden szablon edytora dla obu trybów (edycja istniejącego / nowy profil) — wcześniej
 * były to dwa niemal identyczne bloki HTML, rozjeżdżające się przy każdej zmianie.
 * Różnią się wyłącznie zawartością stopki i paska akcji.
 */
export function renderEditorMarkup({ name, description, content, footerLeft, actionsRight, activateButton = '', namePlaceholder = '' }) {
  return `
    <div class="wp-editor">
      <div class="wp-editor-topline">
        <div class="wp-editor-identity">
          <input type="text" id="wp-input-name" class="form-control wp-input-name"
            value="${escapeAttr(name)}" placeholder="${escapeAttr(namePlaceholder || 'Nazwa profilu')}"
            aria-label="Nazwa profilu" />
          <input type="text" id="wp-input-desc" class="form-control wp-input-desc"
            value="${escapeAttr(description)}" placeholder="Opis (opcjonalny)" aria-label="Opis profilu" />
        </div>
        <div class="wp-editor-topline-right">
          <span class="wp-dirty-badge hidden" id="wp-dirty-badge">Niezapisane zmiany</span>
          ${activateButton}
        </div>
      </div>

      <div class="wp-editor-content-wrap">
        <div class="wp-line-gutter" id="wp-line-gutter">1</div>
        <textarea id="wp-input-content" class="form-control wp-editor-textarea"
          placeholder="Treść instrukcji systemowej... (może być pusta)"
          aria-label="Treść profilu">${escapeHtml(content)}</textarea>
      </div>

      <div class="wp-editor-actions">
        <div class="wp-editor-actions-left">${footerLeft}</div>
        <div class="wp-editor-actions-right" id="wp-delete-zone">${actionsRight}</div>
      </div>
    </div>
  `;
}

export function renderCopyIdButtonMarkup(promptId) {
  return `<button class="wp-btn-copy-id" id="wp-btn-copy-id" title="Skopiuj ID profilu: ${escapeAttr(promptId)}"
    aria-label="Skopiuj ID profilu">${Icons.Copy()}<span>${escapeHtml(promptId)}</span></button>`;
}

// Ten sam przycisk pojawia się w dwóch miejscach: jako domyślny stan paska akcji
// (`renderEditorMarkup`'s actionsRight) i jako powrót po "Anuluj" w inline-potwierdzeniu
// usuwania (`_handleDeleteClick`) — dawniej ten sam string HTML był zduplikowany w obu.
export function renderDeleteButtonMarkup() {
  return '<button class="btn wp-btn-delete" id="wp-btn-delete">Usuń</button>';
}

export function renderDeleteConfirmMarkup() {
  return `
    <div class="delete-confirm-inline">
      <span class="delete-confirm-text">Usunąć profil?</span>
      <button class="btn-confirm-yes" id="wp-btn-delete-yes">Tak</button>
      <button class="btn-confirm-no" id="wp-btn-delete-no">Anuluj</button>
    </div>
  `;
}
