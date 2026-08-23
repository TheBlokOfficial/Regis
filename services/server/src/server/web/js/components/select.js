import { Icons } from '../icons.js';
import { escapeHtml, escapeAttr } from '../utils/dom.js';

/**
 * Wspólny, dostępny (ARIA listbox) custom dropdown — zastępuje natywny
 * <select>, którego popup nie da się dopasować do ciemnego, zaokrąglonego
 * designu żadną ilością CSS. Wzorowany na `.chat-session-trigger`/
 * `.chat-session-popover` (chat.js/chat.css) i `.thinking-chevron` (rotacja
 * 90°, nie 180°).
 *
 * Dwa konsumenci uzasadniają wydzielenie: `agent_config.js` (typ dostawcy)
 * i `home_assistant_view.js` (picker pokoju, wiele instancji naraz).
 *
 * Użycie: wstrzyknij `renderSelectMarkup(idPrefix)` w szablon HTML, potem
 * po wstawieniu do DOM wywołaj `initSelect({ idPrefix, options, value, onChange })`.
 */

// Stan globalny (nie per-instancja) — naraz może być otwarty tylko jeden
// dropdown; klik poza nim / Escape zamyka aktualnie otwarty, niezależnie od
// tego, który widok go utworzył. Nasłuch na `document` spinamy raz na
// zawsze (moduł ładowany raz), nie per inicjalizacja instancji.
let _openInstance = null;
let _globalListenersBound = false;

function _ensureGlobalListeners() {
  if (_globalListenersBound) return;
  _globalListenersBound = true;

  document.addEventListener('click', (e) => {
    if (!_openInstance) return;
    if (!_openInstance.menuEl.isConnected) {
      _openInstance = null;
      return;
    }
    if (!_openInstance.menuEl.contains(e.target) && !_openInstance.triggerEl.contains(e.target)) {
      _openInstance.close();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _openInstance) _openInstance.close();
  });
}

export function renderSelectMarkup(idPrefix, { placeholder = '', className = '' } = {}) {
  return `
    <div class="select ${className}" id="${idPrefix}-select">
      <button type="button" class="select-trigger" id="${idPrefix}-trigger" aria-haspopup="listbox" aria-expanded="false">
        <span class="select-trigger-text" id="${idPrefix}-trigger-label">${escapeHtml(placeholder)}</span>
        <span class="select-chevron">${Icons.ChevronRight()}</span>
      </button>
      <div class="select-menu hidden" id="${idPrefix}-menu" role="listbox">
        <input type="text" class="select-search hidden" id="${idPrefix}-search" placeholder="Szukaj..." aria-label="Filtruj liste" />
        <div class="select-options" id="${idPrefix}-options"></div>
      </div>
      <input type="hidden" id="${idPrefix}-value" />
    </div>
  `;
}

/* Od ilu pozycji lista dostaje pole filtrowania. Nie jest to prog estetyczny: katalog
   modeli OpenRoutera to setki wpisow i bez filtra jest bezuzyteczny, a przy kilkunastu
   pozycjach dodatkowe pole tylko przeszkadza. */
const SEARCH_THRESHOLD = 12;

/**
 * @param {string} idPrefix - musi odpowiadać prefiksowi użytemu w `renderSelectMarkup`.
 * @param {Array<{value:string, label:string, hint?:string}>} options - `hint` renderuje
 *   sie jako mniejszy, wyszarzony tekst obok etykiety (np. identyfikator modelu obok
 *   nazwy presetu). Osobne pole, nie HTML w `label` - escapowanie zostaje po tej
 *   stronie i wywolujacy nie moze wstrzyknac znacznikow.
 * @param {string} value - początkowa wartość (musi być wśród `options`, inaczej placeholder).
 * @param {string} placeholder - tekst gdy nic nie wybrano.
 * @param {(value:string)=>void} onChange
 * @returns {{getValue():string, setValue(v:string):void}|null}
 */
export function initSelect({ idPrefix, options, value = '', placeholder = '', onChange }) {
  const trigger = document.getElementById(`${idPrefix}-trigger`);
  const triggerLabel = document.getElementById(`${idPrefix}-trigger-label`);
  const menu = document.getElementById(`${idPrefix}-menu`);
  const search = document.getElementById(`${idPrefix}-search`);
  const optionsEl = document.getElementById(`${idPrefix}-options`);
  const hiddenInput = document.getElementById(`${idPrefix}-value`);
  if (!trigger || !triggerLabel || !menu || !optionsEl || !hiddenInput) return null;

  _ensureGlobalListeners();

  let api;

  function optionMarkup(opt) {
    const hint = opt.hint ? `<span class="select-option-hint">${escapeHtml(opt.hint)}</span>` : '';
    return `<div class="select-option" role="option" data-value="${escapeAttr(opt.value)}" tabindex="-1">` +
      `<span class="select-option-label">${escapeHtml(opt.label)}</span>${hint}</div>`;
  }

  function renderOptions(filter = '') {
    const needle = filter.trim().toLowerCase();
    const visible = needle
      ? options.filter((o) => `${o.label} ${o.hint || ''} ${o.value}`.toLowerCase().includes(needle))
      : options;

    optionsEl.innerHTML = visible.length
      ? visible.map(optionMarkup).join('')
      : '<div class="select-empty">Brak pasujacych pozycji</div>';

    optionsEl.querySelectorAll('.select-option').forEach((el) => {
      const choose = () => {
        setValue(el.getAttribute('data-value'));
        close();
        trigger.focus();
      };
      el.addEventListener('click', choose);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          choose();
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          el.nextElementSibling?.focus();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          // Nad pierwsza opcja jest pole filtrowania (gdy widoczne) - wracamy do niego,
          // zeby dalo sie poprawic fraze bez siegania po mysz.
          if (el.previousElementSibling) el.previousElementSibling.focus();
          else if (search && !search.classList.contains('hidden')) search.focus();
        } else if (e.key === 'Escape') {
          close();
          trigger.focus();
        }
      });
    });
    markSelected(hiddenInput.value);
  }

  /* Zaznaczenie jest przeliczane po kazdym renderze listy - po odfiltrowaniu wpisy
     powstaja od nowa i stracilyby klase `is-selected`. */
  function markSelected(v) {
    optionsEl.querySelectorAll('.select-option').forEach((el) => {
      const isSelected = el.getAttribute('data-value') === v;
      el.classList.toggle('is-selected', isSelected);
      el.setAttribute('aria-selected', String(isSelected));
    });
  }

  /**
   * `silent`: pomija `onChange` — używane wyłącznie przy ustawianiu stanu
   * początkowego w `initSelect()`. Bez tego rozróżnienia inicjalizacja N
   * instancji na stronie (np. picker pokoju per wiersz w Świecie) odpalała N
   * zapisów do API przy każdym renderze, nawet bez żadnej realnej zmiany
   * użytkownika — potrafiło to zapętlić się w lawinę żądań (re-render ->
   * ponowna inicjalizacja -> kolejny "change" -> kolejny re-render...).
   */
  function setValue(v, { silent = false } = {}) {
    hiddenInput.value = v ?? '';
    const spec = options.find((o) => o.value === v);
    if (spec) {
      const hint = spec.hint ? `<span class="select-option-hint">${escapeHtml(spec.hint)}</span>` : '';
      triggerLabel.innerHTML = `<span class="select-option-label">${escapeHtml(spec.label)}</span>${hint}`;
    } else {
      triggerLabel.textContent = placeholder;
    }
    markSelected(v);
    if (!silent) onChange?.(v);
  }

  function open() {
    if (_openInstance && _openInstance !== api) _openInstance.close();
    menu.classList.remove('hidden');
    trigger.classList.add('active');
    trigger.setAttribute('aria-expanded', 'true');
    _openInstance = api;
    if (search && !search.classList.contains('hidden')) {
      search.value = '';
      renderOptions();
      search.focus();
    }
    // Zaznaczona pozycja bywa poza widokiem przy dlugiej liscie - bez tego otwarcie
    // katalogu modeli pokazuje jego poczatek, a nie to, co aktualnie wybrane.
    optionsEl.querySelector('.select-option.is-selected')?.scrollIntoView({ block: 'nearest' });
  }

  function close() {
    menu.classList.add('hidden');
    trigger.classList.remove('active');
    trigger.setAttribute('aria-expanded', 'false');
    if (_openInstance === api) _openInstance = null;
  }

  function toggle() {
    if (menu.classList.contains('hidden')) open();
    else close();
  }

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    toggle();
  });
  trigger.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      open();
      menu.querySelector('.select-option')?.focus();
    }
  });

  api = { getValue: () => hiddenInput.value, setValue, close, menuEl: menu, triggerEl: trigger };

  if (search) {
    search.classList.toggle('hidden', options.length < SEARCH_THRESHOLD);
    search.addEventListener('click', (e) => e.stopPropagation());
    search.addEventListener('input', () => renderOptions(search.value));
    search.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        optionsEl.querySelector('.select-option')?.focus();
      } else if (e.key === 'Escape') {
        close();
        trigger.focus();
      }
    });
  }

  renderOptions();
  setValue(value, { silent: true });

  return api;
}
