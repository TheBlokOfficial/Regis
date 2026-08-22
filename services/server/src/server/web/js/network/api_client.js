import { getConfig } from '../config.js';
import { AgentClient } from './clients/agent_client.js';
import { ChatClient } from './clients/chat_client.js';
import { WorldClient } from './clients/world_client.js';
import { VoiceClient } from './clients/voice_client.js';

/**
 * Klient REST API do komunikacji z serwerem Regis OS (Same-Origin).
 *
 * Fasada nad czterema klientami domenowymi (`network/clients/`), mirrorująca
 * podział backendu (`agent/`, `world/`, `voice/`, `network/routes/chat`) —
 * każda publiczna metoda deleguje 1:1 do właściwego klienta, więc żaden
 * z konsumentów (`apiClient.getXxx()`) nie musiał się zmienić.
 */
export class ApiClient {
  constructor(baseUrl = getConfig().SERVER_HOST) {
    this.baseUrl = baseUrl;
    this._agent = new AgentClient(baseUrl);
    this._chat = new ChatClient(baseUrl);
    this._world = new WorldClient(baseUrl);
    this._voice = new VoiceClient(baseUrl);
  }

  // --- Agent (health, dostawcy LLM, prompt domyślny) ---
  getHealth(...args) {
    return this._agent.getHealth(...args);
  }
  getProviderSchemas(...args) {
    return this._agent.getProviderSchemas(...args);
  }
  getLLMProviders(...args) {
    return this._agent.getLLMProviders(...args);
  }
  setActiveLLMProvider(...args) {
    return this._agent.setActiveLLMProvider(...args);
  }
  createLLMProvider(...args) {
    return this._agent.createLLMProvider(...args);
  }
  deleteLLMProvider(...args) {
    return this._agent.deleteLLMProvider(...args);
  }
  getAgentDefaultPrompt(...args) {
    return this._agent.getAgentDefaultPrompt(...args);
  }
  setAgentDefaultPrompt(...args) {
    return this._agent.setAgentDefaultPrompt(...args);
  }

  // --- Chat (sesje, historia, wysyłka/streaming) ---
  getChatSessions(...args) {
    return this._chat.getChatSessions(...args);
  }
  createChatSession(...args) {
    return this._chat.createChatSession(...args);
  }
  getChatHistory(...args) {
    return this._chat.getChatHistory(...args);
  }
  deleteChatSession(...args) {
    return this._chat.deleteChatSession(...args);
  }
  cancelChatSession(...args) {
    return this._chat.cancelChatSession(...args);
  }
  sendChatMessage(...args) {
    return this._chat.sendChatMessage(...args);
  }
  sendChatMessageAsync(...args) {
    return this._chat.sendChatMessageAsync(...args);
  }
  streamChatMessage(...args) {
    return this._chat.streamChatMessage(...args);
  }
  watchSession(...args) {
    return this._chat.watchSession(...args);
  }

  // --- World (prompty, Home Assistant, pokoje, nadawcy) ---
  getWorldPrompts(...args) {
    return this._world.getWorldPrompts(...args);
  }
  createWorldPrompt(...args) {
    return this._world.createWorldPrompt(...args);
  }
  updateWorldPrompt(...args) {
    return this._world.updateWorldPrompt(...args);
  }
  deleteWorldPrompt(...args) {
    return this._world.deleteWorldPrompt(...args);
  }
  activateWorldPrompt(...args) {
    return this._world.activateWorldPrompt(...args);
  }
  getHAConfig(...args) {
    return this._world.getHAConfig(...args);
  }
  updateHAConfig(...args) {
    return this._world.updateHAConfig(...args);
  }
  testHAConnection(...args) {
    return this._world.testHAConnection(...args);
  }
  getHACatalog(...args) {
    return this._world.getHACatalog(...args);
  }
  getHADeclaredDevices(...args) {
    return this._world.getHADeclaredDevices(...args);
  }
  addHADeclaredDevice(...args) {
    return this._world.addHADeclaredDevice(...args);
  }
  updateHADeclaredDevice(...args) {
    return this._world.updateHADeclaredDevice(...args);
  }
  deleteHADeclaredDevice(...args) {
    return this._world.deleteHADeclaredDevice(...args);
  }
  getHAGroups(...args) {
    return this._world.getHAGroups(...args);
  }
  createHAGroup(...args) {
    return this._world.createHAGroup(...args);
  }
  updateHAGroup(...args) {
    return this._world.updateHAGroup(...args);
  }
  deleteHAGroup(...args) {
    return this._world.deleteHAGroup(...args);
  }
  getRooms(...args) {
    return this._world.getRooms(...args);
  }
  createRoom(...args) {
    return this._world.createRoom(...args);
  }
  updateRoom(...args) {
    return this._world.updateRoom(...args);
  }
  deleteRoom(...args) {
    return this._world.deleteRoom(...args);
  }
  getSenders(...args) {
    return this._world.getSenders(...args);
  }
  registerSender(...args) {
    return this._world.registerSender(...args);
  }
  deleteSender(...args) {
    return this._world.deleteSender(...args);
  }

  // --- Voice (rejestr klientów, wake-word/VAD, CRUD dostawców STT/TTS) ---
  getConnectedSenders(...args) {
    return this._voice.getConnectedSenders(...args);
  }
  getClientConfig(...args) {
    return this._voice.getClientConfig(...args);
  }
  updateClientConfig(...args) {
    return this._voice.updateClientConfig(...args);
  }
  getClientsStatus(...args) {
    return this._voice.getClientsStatus(...args);
  }
  watchClients(...args) {
    return this._voice.watchClients(...args);
  }
  getSttProviderSchemas(...args) {
    return this._voice.getSttProviderSchemas(...args);
  }
  getSttProviders(...args) {
    return this._voice.getSttProviders(...args);
  }
  setActiveSttProvider(...args) {
    return this._voice.setActiveSttProvider(...args);
  }
  createSttProvider(...args) {
    return this._voice.createSttProvider(...args);
  }
  deleteSttProvider(...args) {
    return this._voice.deleteSttProvider(...args);
  }
  getTtsProviderSchemas(...args) {
    return this._voice.getTtsProviderSchemas(...args);
  }
  getTtsProviders(...args) {
    return this._voice.getTtsProviders(...args);
  }
  setActiveTtsProvider(...args) {
    return this._voice.setActiveTtsProvider(...args);
  }
  createTtsProvider(...args) {
    return this._voice.createTtsProvider(...args);
  }
  deleteTtsProvider(...args) {
    return this._voice.deleteTtsProvider(...args);
  }
}
