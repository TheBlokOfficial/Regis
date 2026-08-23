import { ProviderCrudSection } from '../components/provider_crud_section.js';

/**
 * Zakładka Dostawcy — CRUD LLM/STT/TTS w jednym miejscu, trzy instancje
 * `ProviderCrudSection` (ten sam design, wcześniej tylko w zakładce Agent
 * dla LLM). STT/TTS przeniesione tu z zakładki Głos (dawny płaski,
 * jednosslotowy formularz zastąpiony pełnym CRUD, mirror LLM).
 */
export class ProvidersView {
  constructor() {
    this.llm = new ProviderCrudSection({
      idPrefix: 'llm',
      emptyLabel: 'Brak skonfigurowanych dostawców LLM.',
      api: {
        getSchemas: 'getProviderSchemas',
        getList: 'getLLMProviders',
        setActive: 'setActiveLLMProvider',
        create: 'createLLMProvider',
        update: 'updateLLMProvider',
        delete_: 'deleteLLMProvider',
        getModels: 'getLLMProviderModels',
      },
    });
    this.stt = new ProviderCrudSection({
      idPrefix: 'stt',
      emptyLabel: 'Brak skonfigurowanych dostawców STT.',
      api: {
        getSchemas: 'getSttProviderSchemas',
        getList: 'getSttProviders',
        setActive: 'setActiveSttProvider',
        create: 'createSttProvider',
        update: 'updateSttProvider',
        delete_: 'deleteSttProvider',
      },
    });
    this.tts = new ProviderCrudSection({
      idPrefix: 'tts',
      emptyLabel: 'Brak skonfigurowanych dostawców TTS.',
      api: {
        getSchemas: 'getTtsProviderSchemas',
        getList: 'getTtsProviders',
        setActive: 'setActiveTtsProvider',
        create: 'createTtsProvider',
        update: 'updateTtsProvider',
        delete_: 'deleteTtsProvider',
      },
    });
  }

  render() {
    return `
      <div class="view-shell">
        <h3 class="section-heading">LLM</h3>
        ${this.llm.render()}

        <h3 class="section-heading section-heading--spaced">STT</h3>
        ${this.stt.render()}

        <h3 class="section-heading section-heading--spaced">TTS</h3>
        ${this.tts.render()}
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    await this.llm.init(apiClient);
    await this.stt.init(apiClient);
    await this.tts.init(apiClient);
  }
}
