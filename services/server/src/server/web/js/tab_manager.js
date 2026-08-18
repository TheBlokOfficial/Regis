import { DashboardView } from './views/dashboard.js';
import { SettingsView } from './views/settings.js';
import { ChatView } from './views/chat.js';
import { AgentsView } from './views/agents.js';
import { ExtensionsView } from './views/extensions.js';
import { KernelConfigView } from './views/kernel_config.js';
import { VoiceConfigView } from './views/voice_config.js';
import { confirmModal } from './modal_confirm.js';

/**
 * Zarządza przełączaniem zakładek i renderowaniem widoków w obszarze roboczym.
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
      agents: new AgentsView(),
      extensions: new ExtensionsView(),
      kernel_config: new KernelConfigView(),
      voice_config: new VoiceConfigView(),
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

  async switchTab(tabId) {
    if (!this.views[tabId]) {
      console.warn(`[TabManager] Widok '${tabId}' jest w przygotowaniu.`);
      return;
    }

    if (this.activeTabId === 'agents' && tabId !== 'agents' && this.views.agents.hasUnsavedChanges?.()) {
      const confirmed = await confirmModal({
        title: 'Niezapisane zmiany',
        message: 'Masz niezapisane zmiany w edytorze promptów. Zmiana zakładki je odrzuci. Kontynuować?',
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
      const titles = {
        dashboard: 'Dashboard',
        chat: 'Czat',
        settings: 'Ustawienia',
        agents: 'Prompty',
        extensions: 'Świat',
        kernel_config: 'Kernel',
        voice_config: 'Głos',
      };
      this.breadcrumb.textContent = titles[tabId] || tabId;
    }

    // Renderowanie widoku w kontenerze roboczym
    if (this.container) {
      if (tabId === 'agents' || tabId === 'extensions' || tabId === 'kernel_config') {
        this.container.classList.add('workspace-content--full');
      } else {
        this.container.classList.remove('workspace-content--full');
      }

      this.container.innerHTML = this.views[tabId].render();

      // Inicjalizacja dynamiczna wyrenderowanego widoku
      if (tabId === 'dashboard') {
        this.views.dashboard.init();
        this.views.dashboard.updateStatus(this.latestHealthData);
      } else if (tabId === 'chat') {
        await this.views.chat.init(this.apiClient);
      } else if (tabId === 'agents') {
        await this.views.agents.init(this.apiClient);
      } else if (tabId === 'extensions') {
        await this.views.extensions.init(this.apiClient);
      } else if (tabId === 'kernel_config') {
        await this.views.kernel_config.init(this.apiClient);
      } else if (tabId === 'voice_config') {
        await this.views.voice_config.init(this.apiClient);
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
