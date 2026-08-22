import { Icons } from '../icons.js';
import { confirmModal } from '../modal_confirm.js';
import { AgentConfigView } from './agent_config.js';
import { ExtensionsView } from './extensions.js';
import { ProvidersView } from './providers_config.js';
import { VoiceConfigView } from './voice_config.js';

/**
 * Kontener sekcji Ustawień — poziome zakładki (pills): Agent / Dostawcy /
 * Świat / Klienci. Zastępuje dawny płaski sidebar (Kernel/Świat/Głos/Prompty
 * jako osobne top-level taby). Sekcja "Klienci" (dawniej "Głos", `data-section="voice"`
 * — id celowo bez zmian, wewnętrzny) to dziś nie tylko status pipeline'u głosowego, ale
 * centralna konfiguracja parametrów satelitów (próg wake-worda, VAD), stąd rename.
 */
export class SettingsView {
  constructor() {
    this.apiClient = null;
    this.activeSection = null;
    this.sections = {
      agent: new AgentConfigView(),
      providers: new ProvidersView(),
      world: new ExtensionsView(),
      voice: new VoiceConfigView(),
    };
  }

  render() {
    return `
      <div class="settings-shell">
        <div class="settings-shell-header">
          <nav class="pill-tabs" id="settings-pill-tabs">
            <button class="pill-tab" data-section="agent">${Icons.Activity()} Agent</button>
            <button class="pill-tab" data-section="providers">${Icons.Server()} Dostawcy</button>
            <button class="pill-tab" data-section="world">${Icons.Puzzle()} Świat</button>
            <button class="pill-tab" data-section="voice">${Icons.Radio()} Klienci</button>
          </nav>
        </div>
        <div class="settings-shell-content" id="settings-section-content"></div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    document.getElementById('settings-pill-tabs')?.querySelectorAll('.pill-tab').forEach((btn) => {
      btn.addEventListener('click', () => this.activateSection(btn.getAttribute('data-section')));
    });
  }

  hasUnsavedChanges() {
    return Boolean(this.sections[this.activeSection]?.hasUnsavedChanges?.());
  }

  async activateSection(id) {
    const targetId = id && this.sections[id] ? id : this.activeSection || 'agent';
    if (this.activeSection && this.activeSection !== targetId && this.hasUnsavedChanges()) {
      const confirmed = await confirmModal({
        title: 'Niezapisane zmiany',
        message: 'Masz niezapisane zmiany, które zostaną odrzucone. Zmiana sekcji je odrzuci. Kontynuować?',
        confirmLabel: 'Odrzuć zmiany',
      });
      if (!confirmed) return;
    }

    this.activeSection = targetId;

    document.getElementById('settings-pill-tabs')?.querySelectorAll('.pill-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-section') === targetId);
    });

    const content = document.getElementById('settings-section-content');
    if (!content) return;
    const section = this.sections[targetId];
    content.innerHTML = section.render();
    await section.init(this.apiClient, (navSectionId) => this.activateSection(navSectionId));
  }
}
