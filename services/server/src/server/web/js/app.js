import { getConfig } from './config.js';
import { ApiClient } from './network/api_client.js';
import { TabManager } from './tab_manager.js';
import { Icons } from './icons.js';

/**
 * Punkt wejścia aplikacji konsoli roboczej Regis Agent OS.
 */
document.addEventListener('DOMContentLoaded', async () => {
  const config = getConfig();
  console.log(`🚀 Uruchamianie ${config.APP_TITLE} (v${config.VERSION})...`);

  // 1. Wstrzyknięcie monochromatycznych ikon SVG do elementów nawigacji
  mountIcons();

  // 2. Inicjalizacja Klienta API i Zarządcy zakładek
  const apiClient = new ApiClient();
  const tabManager = new TabManager(apiClient);
  tabManager.init();

  // 3. Połączenie API i weryfikacja statusu
  const checkHealth = async () => {
    const health = await apiClient.getHealth();
    
    // Aktualizacja wskaźnika w stopce sidebaru (tylko Online / Offline)
    const sidebarDot = document.getElementById('sidebar-status-dot');
    const sidebarText = document.getElementById('sidebar-status-text');

    if (health) {
      if (sidebarDot) sidebarDot.className = 'status-indicator-dot online';
      if (sidebarText) sidebarText.textContent = `Online`;
    } else {
      if (sidebarDot) sidebarDot.className = 'status-indicator-dot offline';
      if (sidebarText) sidebarText.textContent = `Offline`;
    }

    // Przekazanie danych do widoków
    tabManager.setHealthData(health);
  };

  // Pierwsze sprawdzanie statusu + interwał co 10s
  await checkHealth();
  setInterval(checkHealth, 10000);

  // Przycisk ręcznego odświeżania w nagłówku
  const btnRefresh = document.getElementById('btn-refresh');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      checkHealth();
    });
  }
});

/**
 * Montuje ikony wektorowe SVG w statycznych elementach interfejsu.
 */
function mountIcons() {
  const logoBox = document.getElementById('brand-logo-svg');
  if (logoBox) logoBox.innerHTML = Icons.Cpu();

  const iconDash = document.getElementById('icon-nav-dashboard');
  if (iconDash) iconDash.innerHTML = Icons.LayoutGrid();

  const iconChat = document.getElementById('icon-nav-chat');
  if (iconChat) iconChat.innerHTML = Icons.MessageSquare();

  const iconLogs = document.getElementById('icon-nav-logs');
  if (iconLogs) iconLogs.innerHTML = Icons.Activity();

  const iconSettings = document.getElementById('icon-nav-settings');
  if (iconSettings) iconSettings.innerHTML = Icons.Sliders();

  const chevron = document.getElementById('breadcrumb-chevron');
  if (chevron) chevron.innerHTML = Icons.ChevronRight();

  const btnRefresh = document.getElementById('btn-refresh');
  if (btnRefresh) btnRefresh.innerHTML = Icons.RefreshCw();
}
