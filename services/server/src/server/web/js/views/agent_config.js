import { showToast } from '../utils/toast.js';

/**
 * Sekcja Agent (Ustawienia) — wyłącznie system prompt (fallback bez CRUD,
 * używany tylko gdy żaden silnik świata nie jest podłączony — patrz
 * `world_prompts_view.js` dla właściwej tożsamości agenta). CRUD dostawców
 * LLM przeniesiony do zakładki Dostawcy (`views/providers_config.js`).
 */
export class AgentConfigView {
  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">System Prompt</h3>
        <p class="section-hint">Używany tylko bez podłączonego świata.</p>
        <div class="chat-floating-box agent-prompt-box">
          <textarea id="agent-default-prompt-textarea" class="chat-textarea agent-prompt-textarea" placeholder="Ładowanie..."></textarea>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this._initDefaultPrompt();
  }

  async _initDefaultPrompt() {
    const textarea = document.getElementById('agent-default-prompt-textarea');
    if (!textarea) return;

    const data = await this.apiClient.getAgentDefaultPrompt();
    textarea.value = data?.content ?? '';
    this._defaultPromptSaved = textarea.value;

    let debounceTimer = null;
    const scheduleSave = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => this._saveDefaultPrompt(textarea), 1500);
    };

    textarea.addEventListener('input', scheduleSave);
    textarea.addEventListener('blur', () => {
      clearTimeout(debounceTimer);
      this._saveDefaultPrompt(textarea);
    });
  }

  async _saveDefaultPrompt(textarea) {
    if (textarea.value === this._defaultPromptSaved) return;
    try {
      await this.apiClient.setAgentDefaultPrompt(textarea.value);
      this._defaultPromptSaved = textarea.value;
      showToast('Zapisano.', 'success');
    } catch (err) {
      showToast(`Błąd zapisu: ${err.message}`, 'error');
    }
  }
}
