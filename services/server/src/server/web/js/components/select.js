import { Icons } from '../icons.js';

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
        <span id="${idPrefix}-trigger-label">${escapeHtml(placeholder)}</span>
        <span class="select-chevron">${Icons.ChevronRight()}</span>
      </button>
      <div class="select-menu hidden" id="${idPrefix}-menu" role="listbox"></div>
      <input type="hidden" id="${idPrefix}-value" />
    </div>
  `;
}

/**
 * @param {string} idPrefix - musi odpowiadać prefiksowi użytemu w `renderSelectMarkup`.
 * @param {Array<{value:string, label:string}>} options
 * @param {string} value - początkowa wartość (musi być wśród `options`, inaczej placeholder).
 * @param {string} placeholder - tekst gdy nic nie wybrano.
 * @param {(value:string)=>void} onChange
 * @returns {{getValue():string, setValue(v:string):void}|null}
 */
export function initSelect({ idPrefix, options, value = '', placeholder = '', onChange }) {
  const trigger = document.getElementById(`${idPrefix}-trigger`);
  const triggerLabel = document.getElementById(`${idPrefix}-trigger-label`);
  const menu = document.getElementById(`${idPrefix}-menu`);
  const hiddenInput = document.getElementById(`${idPrefix}-value`);
  if (!trigger || !triggerLabel || !menu || !hiddenInput) return null;

  _ensureGlobalListeners();

  let api;

  function renderOptions() {
    menu.innerHTML = options
      .map((opt) => `<div class="select-option" role="option" data-value="${escapeAttr(opt.value)}" tabindex="-1">${escapeHtml(opt.label)}</div>`)
      .join('');

    menu.querySelectorAll('.select-option').forEach((el) => {
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
          el.previousElementSibling?.focus();
        } else if (e.key === 'Escape') {
          close();
          trigger.focus();
        }
      });
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
    triggerLabel.textContent = spec?.label ?? placeholder;
    menu.querySelectorAll('.select-option').forEach((el) => {
      const isSelected = el.getAttribute('data-value') === v;
      el.classList.toggle('is-selected', isSelected);
      el.setAttribute('aria-selected', String(isSelected));
    });
    if (!silent) onChange?.(v);
  }

  function open() {
    if (_openInstance && _openInstance !== api) _openInstance.close();
    menu.classList.remove('hidden');
    trigger.classList.add('active');
    trigger.setAttribute('aria-expanded', 'true');
    _openInstance = api;
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

  renderOptions();
  setValue(value, { silent: true });

  return api;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}
