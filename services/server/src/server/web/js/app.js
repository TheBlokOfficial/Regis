import { getConfig } from './config.js';
import { ApiClient } from './network/api_client.js';

/**
 * Punkt wejścia aplikacji wbudowanej konsoli.
 */
document.addEventListener('DOMContentLoaded', async () => {
  const config = getConfig();
  console.log(`🚀 Uruchamianie ${config.APP_TITLE} (v${config.VERSION})...`);

  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');

  const apiClient = new ApiClient();
  const health = await apiClient.getHealth();

  if (health) {
    console.log('✅ Połączenie z serwerem Regis OS aktywne:', health);
    if (statusDot) statusDot.classList.add('online');
    if (statusText) statusText.textContent = `Połączono z ${health.system} (Port 8000)`;
  } else {
    console.warn('⚠️ Brak połączenia z serwerem Regis OS.');
    if (statusText) statusText.textContent = 'Rozłączono (Serwer niedostępny)';
  }
});
