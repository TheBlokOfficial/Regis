import { Icons } from '../../../icons.js';
import { flashButtonResult, lockButtonForAction } from '../../../utils/button_flash.js';
import { escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Konfiguracja" — singleton Home Assistant (`base_url`/`access_token`).
 * Operuje na współdzielonym stanie koordynatora (`view` = `HomeAssistantExtensionView`).
 *
 * Wzorzec formularza tokenu/klucza API (jawny "Zapisz", brak auto-save na
 * blur, placeholder zamiast wartości, pole hasła z przełącznikiem
 * pokaż/ukryj, pasek akcji "Testuj połączenie"+"Zapisz" pod polami z
 * plakietką wyniku) — świadoma decyzja, nie domysł, patrz historia sesji.
 */
export function renderConfigForm(view) {
  const isConfigured = Boolean(view.config.base_url && view.config.access_token);
  const tokenPlaceholder = isConfigured ? truncateMaskedToken(view.config.access_token) : 'Wklej token dostępu...';
  return `
    <div class="form-card ha-config-form-card">
      <div class="form-row">
        <div class="form-group">
          <label for="ha-input-base-url">Adres serwera</label>
          <input type="text" id="ha-input-base-url" class="form-control" value="${escapeAttr(view.config.base_url)}" placeholder="http://homeassistant.local:8123" />
        </div>
        <div class="form-group">
          <label for="ha-input-token">Długoterminowy token dostępu</label>
          <div class="ha-token-field-wrap">
            <input type="password" id="ha-input-token" class="form-control" placeholder="${escapeAttr(tokenPlaceholder)}" />
            <button type="button" class="ha-token-toggle-eye" id="ha-btn-toggle-token" title="Pokaż token" aria-label="Pokaż token">${Icons.Eye()}</button>
          </div>
        </div>
      </div>
      <p class="section-hint ha-token-hint">
        Token wygenerujesz w profilu użytkownika Home Assistant → Bezpieczeństwo → Długoterminowe tokeny dostępu.
      </p>
      <div class="form-actions ha-config-actions">
        <button type="button" class="btn" id="ha-btn-test-config">Testuj połączenie</button>
        <button class="btn" id="ha-btn-save-config" disabled>Zapisz</button>
      </div>
    </div>
  `;
}

export function bindConfigEvents(view) {
  const saveBtn = document.getElementById('ha-btn-save-config');
  saveBtn?.addEventListener('click', () => handleSaveConfig(view));
  document.getElementById('ha-btn-test-config')?.addEventListener('click', () => handleTestConnection(view));
  document.getElementById('ha-btn-toggle-token')?.addEventListener('click', () => handleToggleTokenVisibility());

  // "Zapisz" zaczyna zablokowany (świeży render = zero niezapisanych zmian) i
  // odblokowuje się dopiero, gdy user faktycznie coś zmieni — nie jest to
  // stały, zawsze-klikalny przycisk. Po udanym zapisie `_loadAndRender()`
  // przerenderowuje cały panel od nowa (świeży `disabled` wraca sam).
  const markDirty = () => {
    if (saveBtn) saveBtn.disabled = false;
  };
  document.getElementById('ha-input-base-url')?.addEventListener('input', markDirty);
  document.getElementById('ha-input-token')?.addEventListener('input', markDirty);
}

function handleToggleTokenVisibility() {
  const input = document.getElementById('ha-input-token');
  const btn = document.getElementById('ha-btn-toggle-token');
  if (!input || !btn) return;
  const showing = input.type === 'text';
  input.type = showing ? 'password' : 'text';
  btn.innerHTML = showing ? Icons.Eye() : Icons.EyeOff();
  btn.title = showing ? 'Pokaż token' : 'Ukryj token';
  btn.setAttribute('aria-label', btn.title);
}

async function handleSaveConfig(view) {
  const baseUrl = document.getElementById('ha-input-base-url')?.value.trim() || '';
  const token = document.getElementById('ha-input-token')?.value || '';

  if (!baseUrl) {
    view.showToast('Adres serwera jest wymagany.', 'error');
    return;
  }

  try {
    // Puste pole tokenu NIE wysyła nic w `access_token` — backend wtedy zachowuje
    // obecnie zapisany token. Frontend nigdy nie zna jego prawdziwej wartości
    // (GET /config zwraca ją zawsze zamaskowaną), więc nie może go sam odesłać
    // z powrotem — wcześniejszy fallback na `view.config.access_token` nadpisywał
    // token ciągiem kropek zamiast go zachować.
    const payload = { base_url: baseUrl, ...(token ? { access_token: token } : {}) };
    await view.apiClient.updateHAConfig(payload);
    view.showToast('Zapisano konfigurację.', 'success');
    await view._loadAndRender();
  } catch (error) {
    view.showToast(error.message || 'Błąd zapisu konfiguracji.', 'error');
  }
}

/** Wynik testu jest pokazywany BEZPOŚREDNIO na przycisku (kolor + ikona na
 * 2s, `flashButtonResult`), nie osobną plakietką obok — jeden spójny element
 * zamiast dwóch różnych stylistyk w tym samym wierszu. Bez fazy spinnera —
 * na szybkim połączeniu odpowiedź przychodzi w <200ms, co zmienia spinner w
 * nieprzyjemny błysk; przycisk zostaje z oryginalnym tekstem "Testuj
 * połączenie" (zablokowany przez `lockButtonForAction`) aż do przyjścia
 * wyniku. Wynik nie idzie też do toastu — kolor+ikona na przycisku już w
 * pełni go niesie, drugi kanał informacji byłby redundantny.
 */
async function handleTestConnection(view) {
  const baseUrl = document.getElementById('ha-input-base-url')?.value.trim() || '';
  const token = document.getElementById('ha-input-token')?.value || '';

  if (!baseUrl) {
    view.showToast('Adres serwera jest wymagany.', 'error');
    return;
  }

  const btn = document.getElementById('ha-btn-test-config');
  if (!btn) return;
  lockButtonForAction(btn);

  let ok = false;
  try {
    const result = await view.apiClient.testHAConnection({ base_url: baseUrl, access_token: token || null });
    ok = Boolean(result?.ok);
  } catch {
    ok = false;
  }

  flashButtonResult(btn, ok, { successHtml: Icons.Check(), errorHtml: Icons.X() });
}

function truncateMaskedToken(masked) {
  // Backend maskuje token do jego pełnej długości kropkami (z ostatnimi 4 znakami
  // widocznymi) — dla długich tokenów (JWT) to ściana kropek wychodząca poza kartę.
  // Wizualnie ograniczamy do stałej liczby kropek, sens (zamaskowane + końcówka) zostaje.
  const MAX_DOTS = 24;
  const visibleSuffix = masked.replace(/^•+/, '');
  const dotsCount = masked.length - visibleSuffix.length;
  if (dotsCount <= MAX_DOTS) return masked;
  return `${'•'.repeat(MAX_DOTS)}${visibleSuffix}`;
}
