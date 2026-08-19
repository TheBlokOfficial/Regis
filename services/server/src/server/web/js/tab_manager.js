import { DashboardView } from './views/dashboard.js';
import { SettingsView } from './views/settings.js';
import { ChatView } from './views/chat.js';
import { confirmModal } from './modal_confirm.js';

/**
 * Zarządza przełączaniem zakładek top-level (Dashboard/Chat/Ustawienia) i renderowaniem
 * widoków w obszarze roboczym. Cała konfiguracja (dawne Kernel/Świat/Głos/Prompty) żyje
 * dziś wewnątrz `SettingsView` jako poziome sekcje (pills), nie jako osobne top-level taby.
 */
export class TabManager {
  constructor(apiClient, containerId = 'workspace-content', breadcrumbId = 'breadcrumb-active-tab') {
    this.apiClient = apiClient;
    this.container = document.getElementById(containerId);
    this.breadcrumb = document.getElementById(breadcrumbId);
    this.activeTabId = 'dashboard';

    // Inicjalizacja instancji widoków
    this.views = {
      dashboard: new DashboardView(),
      chat: new ChatView(),
      settings: new SettingsView(),
    };

    this.latestHealthData = null;
  }

  init() {
    this.bindEvents();
    this.switchTab('dashboard');
  }

  bindEvents() {
    const navItems = document.querySelectorAll('.nav-item[data-tab]');
    navItems.forEach((item) => {
      if (item.classList.contains('disabled')) return;
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const tabId = item.getAttribute('data-tab');
        this.switchTab(tabId);
      });
    });
  }

  async switchTab(tabId, options = {}) {
    if (!this.views[tabId]) {
      console.warn(`[TabManager] Widok '${tabId}' jest w przygotowaniu.`);
      return;
    }

    const currentView = this.views[this.activeTabId];
    if (this.activeTabId !== tabId && currentView?.hasUnsavedChanges?.()) {
      const confirmed = await confirmModal({
        title: 'Niezapisane zmiany',
        message: 'Masz niezapisane zmiany, które zostaną odrzucone. Zmiana zakładki je odrzuci. Kontynuować?',
        confirmLabel: 'Odrzuć zmiany',
      });
      if (!confirmed) return;
    }

    this.activeTabId = tabId;

    // Aktualizacja podświetlenia w Sidebarze
    document.querySelectorAll('.nav-item').forEach((el) => {
      if (el.getAttribute('data-tab') === tabId) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    });

    // Aktualizacja Breadcrumbs
    if (this.breadcrumb) {
      const titles = { dashboard: 'Dashboard', chat: 'Czat', settings: 'Ustawienia' };
      this.breadcrumb.textContent = titles[tabId] || tabId;
    }

    // Renderowanie widoku w kontenerze roboczym
    if (this.container) {
      if (tabId === 'settings') {
        this.container.classList.add('workspace-content--full');
      } else {
        this.container.classList.remove('workspace-content--full');
      }

      this.container.innerHTML = this.views[tabId].render();

      // Inicjalizacja dynamiczna wyrenderowanego widoku
      if (tabId === 'dashboard') {
        this.views.dashboard.init((navTabId, navOptions) => this.switchTab(navTabId, navOptions));
        this.views.dashboard.updateStatus(this.latestHealthData);
      } else if (tabId === 'chat') {
        await this.views.chat.init(this.apiClient);
      } else if (tabId === 'settings') {
        await this.views.settings.init(this.apiClient);
        await this.views.settings.activateSection(options.section);
      }
    }
  }

  setHealthData(healthData) {
    this.latestHealthData = healthData;
    if (this.activeTabId === 'dashboard' && this.views.dashboard) {
      this.views.dashboard.updateStatus(healthData);
    }
  }
}
