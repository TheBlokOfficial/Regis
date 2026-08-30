import { Icons } from '../../icons.js';
import { renderSelectMarkup } from '../select.js';
import { escapeAttr, escapeHtml } from '../../utils/dom.js';
import { SECRET_REF_PREFIX, isSecretRef } from '../../utils/secrets.js';

/**
 * Czyste funkcje renderujące HTML sekcji presetów dostawcy — wydzielone z
 * `ProviderCrudSection` (wzorzec `renderXMarkup` z `components/select.js`, ten sam co
 * `chat/chat_template.js`/`voice/voice_client_template.js`/`world_prompts_template.js`).
 * Zero dostępu do `this`/DOM, tylko stringi. Podobnie jak `world_prompts_template.js` —
 * brak kanału SSE i drugiej niezależnej odpowiedzialności, więc reszta (stan
 * rozwinięcia/draftu, wiązanie zdarzeń, zapis/usuwanie) zostaje w jednej klasie.
 */

export function renderProviderSectionMarkup(idPrefix) {
  return `
    <form id="${idPrefix}-form-create-provider" class="agent-composer">
      <div class="agent-composer-row">
        ${renderSelectMarkup(`${idPrefix}-provider-type`, { placeholder: 'Ładowanie...' })}
        <input type="text" id="${idPrefix}-new-name" class="form-control agent-composer-name"
          placeholder="Nazwa presetu (np. Dom)" aria-label="Nazwa presetu" />
        <button type="submit" class="agent-composer-submit" title="Dodaj preset" aria-label="Dodaj preset">${Icons.Plus()}</button>
      </div>
      <p class="section-hint">Model i parametry ustawisz po utworzeniu — rozwiń preset na liście.</p>
    </form>

    <div class="agent-provider-list" id="${idPrefix}-providers-list">
      ${renderListSkeletonMarkup()}
    </div>
  `;
}

export function renderListSkeletonMarkup() {
  return `
    <div class="skeleton-stack">
      <div class="skeleton-block skeleton-block--card"></div>
      <div class="skeleton-block skeleton-block--card"></div>
    </div>
  `;
}

export function renderEditorSkeletonMarkup() {
  return '<div class="skeleton-stack"><div class="skeleton-block skeleton-block--field"></div></div>';
}

export function renderEmptyListMarkup(emptyLabel) {
  return `<div class="card card-sm">${escapeHtml(emptyLabel)}</div>`;
}

export function renderProviderCardMarkup(provider, schemas, { idPrefix, expandedId, hasFallbackChain, fallbackPriority }) {
  const isActive = provider.is_active;
  const isExpanded = provider.id === expandedId;
  const typeSpec = schemas?.provider_types?.find((t) => t.type === provider.type);
  const model = provider.options?.model || provider.options?.model_id || '';

  return `
    <div class="agent-provider-card ${isActive ? 'is-active' : ''} ${isExpanded ? 'is-expanded' : ''}"
      data-id="${escapeAttr(provider.id)}">
      <div class="agent-provider-card-head" role="button" tabindex="0"
        aria-expanded="${isExpanded}" data-toggle="${escapeAttr(provider.id)}">
        <span class="agent-provider-card-chevron">${Icons.ChevronRight()}</span>
        <div class="agent-provider-card-main">
          <div class="agent-provider-card-title-row">
            <span class="agent-provider-card-name" title="${escapeAttr(provider.name)}">${escapeHtml(provider.name)}</span>
            <span class="badge badge-chip">${escapeHtml((typeSpec?.label || provider.type || '').toUpperCase())}</span>
          </div>
          <div class="agent-provider-card-meta">${escapeHtml(model || 'model nieustawiony')}</div>
        </div>
        ${
          !isActive && hasFallbackChain
            ? `<input type="number" min="1" step="1" class="form-control agent-provider-card-priority-input"
                 data-priority-for="${escapeAttr(provider.id)}" placeholder="—"
                 title="Priorytet w łańcuchu fallbacku (puste = poza automatycznym routingiem)"
                 value="${fallbackPriority ?? ''}" />`
            : ''
        }
        ${
          isActive
            ? `<span class="agent-provider-card-check" title="Aktywny preset (Priorytet 0)">${Icons.CheckCircle2()}</span>`
            : `<button type="button" class="btn btn-sm btn-subtle agent-provider-card-activate"
                 data-activate="${escapeAttr(provider.id)}">Aktywuj</button>`
        }
      </div>
      <div class="agent-provider-card-editor" id="${idPrefix}-editor-${escapeAttr(provider.id)}"></div>
    </div>
  `;
}

export function renderProviderEditorMarkup({ idPrefix, providerId, provider, typeSpec, modelsData, selectedModel, paramSchema, draftOptions }) {
  return `
    <div class="provider-editor">
      <div class="provider-editor-group">
        <div class="provider-field-grid">
          <div class="provider-field">
            <label for="${idPrefix}-name-${providerId}">Nazwa presetu</label>
            <input type="text" class="form-control" id="${idPrefix}-name-${providerId}"
              value="${escapeAttr(provider.name || '')}" placeholder="np. Dom" />
            <p class="provider-field-hint">Twoja etykieta, nie nazwa modelu — to ona pojawia się w czacie.</p>
          </div>
        </div>
      </div>
      ${renderFieldGridMarkup(`${idPrefix}-base-${providerId}`, typeSpec?.options_schema || [], draftOptions)}
      ${modelsData ? renderModelPickerMarkup(idPrefix, providerId, modelsData, selectedModel) : ''}
      <div id="${idPrefix}-params-${providerId}">
        ${renderFieldGridMarkup(`${idPrefix}-param-${providerId}`, paramSchema, draftOptions, 'Parametry generacji')}
      </div>
      <div class="provider-editor-actions">
        <button type="button" class="btn btn-primary btn-sm" data-save="${escapeAttr(providerId)}">Zapisz</button>
        <button type="button" class="btn btn-ghost-danger btn-sm" data-delete="${escapeAttr(providerId)}">Usuń preset</button>
      </div>
    </div>
  `;
}

export function renderModelPickerMarkup(idPrefix, providerId, modelsData, selectedModel) {
  const hasList = (modelsData.models || []).length > 0;
  return `
    <div class="provider-editor-group">
      <h5 class="provider-editor-group-title">Model</h5>
      ${
        hasList
          ? `<div class="provider-field">
               <label>Wybierz z listy</label>
               ${renderSelectMarkup(`${idPrefix}-model-${providerId}`, { placeholder: 'Wybierz model' })}
             </div>`
          : ''
      }
      <div class="provider-field">
        <label for="${idPrefix}-model-custom-${providerId}">Identyfikator modelu</label>
        <input type="text" class="form-control" id="${idPrefix}-model-custom-${providerId}"
          value="${escapeAttr(selectedModel)}" placeholder="np. openai/gpt-oss-120b" />
        <p class="provider-field-hint">Lista nigdy nie zamyka wyboru — model spoza niej wpisz tutaj.</p>
      </div>
      ${modelsData.detail ? `<p class="provider-field-warning">${Icons.AlertCircle()} ${escapeHtml(modelsData.detail)}</p>` : ''}
    </div>
  `;
}

export function renderFieldGridMarkup(idPrefix, schema, draftOptions, title = '') {
  if (!schema || schema.length === 0) return '';
  const fields = schema.map((opt) => renderFieldMarkup(idPrefix, opt, draftOptions[opt.name])).join('');
  return `
    <div class="provider-editor-group">
      ${title ? `<h5 class="provider-editor-group-title">${escapeHtml(title)}</h5>` : ''}
      <div class="provider-field-grid">${fields}</div>
    </div>
  `;
}

export function renderFieldMarkup(idPrefix, opt, value) {
  const id = `${idPrefix}-${opt.name}`;
  const hint = opt.hint ? `<p class="provider-field-hint">${escapeHtml(opt.hint)}</p>` : '';

  if (opt.type === 'enum') {
    return `
      <div class="provider-field" data-opt-name="${escapeAttr(opt.name)}" data-opt-kind="enum">
        <label>${escapeHtml(opt.label)}</label>
        ${renderSelectMarkup(id, { placeholder: 'Domyślne modelu', className: 'select--compact' })}
        ${hint}
      </div>
    `;
  }

  // `type="number"` odpada świadomie — natywne strzałki góra/dół przeglądarki są
  // jednym z domyślnych kontrolek, których ten projekt nie używa.
  const shown = value === undefined || value === null ? '' : String(value);
  // Referencja `env:NAZWA` to nazwa zmiennej środowiskowej, nie sekret — serwer nie
  // maskuje jej w odpowiedzi (`ai/provider_crud.py`), więc i tutaj pokazujemy ją
  // wprost. Ukrycie jej za kropkami odebrałoby jedyny sygnał, że ta instancja bierze
  // klucz ze środowiska, a nie z pliku.
  const valueIsSecretRef = isSecretRef(shown);
  const inputType = opt.type === 'password' && !valueIsSecretRef ? 'password' : 'text';
  // Podpowiedź dokładana ZAWSZE dla pól sekretnych, obok ewentualnej podpowiedzi ze
  // schematu — inaczej dostawcy, którzy mają własny opis pola (a mają go wszyscy
  // z kluczem API), nigdy by o referencjach nie powiedzieli.
  const secretHint =
    opt.type === 'password'
      ? `<p class="provider-field-hint">Możesz wpisać <code>${SECRET_REF_PREFIX}NAZWA_ZMIENNEJ</code>, żeby wziąć klucz ze środowiska zamiast zapisywać go w pliku.</p>`
      : '';
  return `
    <div class="provider-field" data-opt-name="${escapeAttr(opt.name)}" data-opt-kind="input">
      <label for="${id}">${escapeHtml(opt.label)}</label>
      <input type="${inputType}" id="${id}" class="form-control provider-field-input"
        data-opt-name="${escapeAttr(opt.name)}"
        value="${escapeAttr(shown)}" placeholder="${escapeHtml(opt.placeholder || '')}" />
      ${hint}${secretHint}
    </div>
  `;
}
