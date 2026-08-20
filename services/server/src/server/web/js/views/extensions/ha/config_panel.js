import { Icons } from '../../../icons.js';
import { escapeAttr, escapeHtml } from '../../../utils/dom.js';

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
        <div class="ha-config-actions-left">
          <button type="button" class="btn btn-ghost" id="ha-btn-test-config">Testuj połączenie</button>
          <span id="ha-config-test-result"></span>
        </div>
        <button class="btn btn-primary" id="ha-btn-save-config">Zapisz</button>
      </div>
    </div>
  `;
}

export function bindConfigEvents(view) {
  document.getElementById('ha-btn-save-config')?.addEventListener('click', () => handleSaveConfig(view));
  document.getElementById('ha-btn-test-config')?.addEventListener('click', () => handleTestConnection(view));
  document.getElementById('ha-btn-toggle-token')?.addEventListener('click', () => handleToggleTokenVisibility());
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

async function handleTestConnection(view) {
  const baseUrl = document.getElementById('ha-input-base-url')?.value.trim() || '';
  const token = document.getElementById('ha-input-token')?.value || '';
  const resultEl = document.getElementById('ha-config-test-result');

  if (!baseUrl) {
    view.showToast('Adres serwera jest wymagany.', 'error');
    return;
  }

  const btn = document.getElementById('ha-btn-test-config');
  if (btn) btn.disabled = true;
  if (resultEl) resultEl.innerHTML = '';
  try {
    const result = await view.apiClient.testHAConnection({ base_url: baseUrl, access_token: token || null });
    if (resultEl) {
      resultEl.innerHTML = `<span class="badge badge-status ${result.ok ? 'badge-status--success' : 'badge-status--error'}">${escapeHtml(result.message)}</span>`;
    }
  } catch (error) {
    if (resultEl) {
      resultEl.innerHTML = `<span class="badge badge-status badge-status--error">${escapeHtml(error.message || 'Błąd sprawdzania połączenia.')}</span>`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
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
