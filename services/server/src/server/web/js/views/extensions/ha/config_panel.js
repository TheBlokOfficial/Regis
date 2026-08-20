import { Icons } from '../../../icons.js';
import { escapeAttr } from '../../../utils/dom.js';

/**
 * Panel "Konfiguracja" — singleton Home Assistant (`base_url`/`access_token`).
 * Operuje na współdzielonym stanie koordynatora (`view` = `HomeAssistantExtensionView`).
 */
export function renderConfigForm(view) {
  const isConfigured = Boolean(view.config.base_url && view.config.access_token);
  const tokenPlaceholder = isConfigured ? truncateMaskedToken(view.config.access_token) : 'eyJhbGciOi...';
  return `
    <div class="form-card ha-config-form-card">
      <div class="form-row">
        <div class="form-group">
          <label for="ha-input-base-url">Adres serwera</label>
          <input type="text" id="ha-input-base-url" class="form-control" value="${escapeAttr(view.config.base_url)}" placeholder="http://homeassistant.local:8123" />
        </div>
        <div class="form-group">
          <label for="ha-input-token">Długoterminowy token dostępu</label>
          <input type="password" id="ha-input-token" class="form-control" placeholder="${escapeAttr(tokenPlaceholder)}" />
        </div>
        <div class="form-group form-group--btn">
          <label class="form-group-btn-spacer" aria-hidden="true">&nbsp;</label>
          <div class="ha-config-actions">
            <button class="btn btn-ghost btn-icon-square ha-config-submit" id="ha-btn-test-config" title="Sprawdź połączenie" aria-label="Sprawdź połączenie">${Icons.Activity()}</button>
            <button class="btn btn-ghost btn-icon-square ha-config-submit" id="ha-btn-save-config" title="Zapisz połączenie" aria-label="Zapisz połączenie">${Icons.RefreshCw()}</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

export function bindConfigEvents(view) {
  document.getElementById('ha-btn-save-config')?.addEventListener('click', () => handleSaveConfig(view));
  document.getElementById('ha-btn-test-config')?.addEventListener('click', () => handleTestConnection(view));
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

  if (!baseUrl) {
    view.showToast('Adres serwera jest wymagany.', 'error');
    return;
  }

  const btn = document.getElementById('ha-btn-test-config');
  const originalHtml = btn?.innerHTML;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = Icons.CircleLoader();
  }
  try {
    const result = await view.apiClient.testHAConnection({ base_url: baseUrl, access_token: token || null });
    if (result?.ok) {
      view.showToast('Połączenie z Home Assistant działa poprawnie.', 'success');
    } else {
      view.showToast('Nie udało się połączyć — sprawdź adres i token.', 'error');
    }
  } catch (error) {
    view.showToast(error.message || 'Błąd sprawdzania połączenia.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
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
