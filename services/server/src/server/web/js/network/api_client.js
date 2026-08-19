import { getConfig } from '../config.js';

/**
 * Klient REST API do komunikacji z serwerem Regis OS (Same-Origin).
 */
export class ApiClient {
  constructor(baseUrl = getConfig().SERVER_HOST) {
    this.baseUrl = baseUrl;
  }

  async getHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/health`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd sprawdzania statusu serwera:', error);
      return null;
    }
  }

  async getProviderSchemas() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/schemas`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania schematów dostawców LLM:', error);
      return null;
    }
  }

  async getLLMProviders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy dostawców LLM:', error);
      return null;
    }
  }

  async setActiveLLMProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/active`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd aktywacji dostawcy LLM:', error);
      throw error;
    }
  }

  async createLLMProvider(providerData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(providerData),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd tworzenia dostawcy LLM:', error);
      throw error;
    }
  }

  async deleteLLMProvider(providerId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/llm/providers/${providerId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd usuwania dostawcy LLM:', error);
      throw error;
    }
  }

  // ==========================================================================
  // METODY CHAT & SESSIONS
  // ==========================================================================

  async getChatSessions() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/sessions`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy sesji:', error);
      return { sessions: [] };
    }
  }

  async createChatSession(title = 'Nowa konwersacja', customId = null) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, custom_id: customId }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd tworzenia nowej sesji:', error);
      throw error;
    }
  }

  async getChatHistory(sessionId = 'session_default') {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/sessions/${sessionId}/history`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd pobierania historii dla sesji '${sessionId}':`, error);
      return null;
    }
  }

  async deleteChatSession(sessionId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd usuwania sesji '${sessionId}':`, error);
      throw error;
    }
  }

  async cancelChatSession(sessionId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd anulowania generowania dla sesji '${sessionId}':`, error);
      return null;
    }
  }

  async sendChatMessage(sessionId = 'session_default', message = '', senderId = null) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message, sender_id: senderId }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd wysyłania wiadomości:', error);
      throw error;
    }
  }

  async streamChatMessage(
    sessionId = 'session_default',
    message = '',
    { onChunk = null, onToolStart = null, onToolResult = null, onError = null, onCancelled = null, onComplete = null } = {},
    signal = null,
    senderId = null
  ) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message, sender_id: senderId }),
        signal,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data:')) {
            const rawData = trimmed.replace(/^data:\s*/, '');
            if (rawData === '[DONE]') {
              if (onComplete) onComplete();
              return;
            }
            try {
              const parsed = JSON.parse(rawData);
              switch (parsed.type) {
                case 'chunk':
                  if (onChunk) onChunk(parsed.chunk);
                  break;
                case 'tool_start':
                  if (onToolStart) onToolStart(parsed);
                  break;
                case 'tool_result':
                  if (onToolResult) onToolResult(parsed);
                  break;
                case 'error':
                  if (onError) onError(new Error(parsed.error));
                  return;
                case 'cancelled':
                  if (onCancelled) onCancelled();
                  break;
                default:
                  console.warn('[ApiClient] Nieznany typ ramki SSE:', parsed);
              }
            } catch (e) {
              console.warn('[ApiClient] Błąd parsowania ramki SSE:', rawData, e);
            }
          }
        }
      }

      if (onComplete) onComplete();
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('[ApiClient] Strumieniowanie przerwane przez użytkownika.');
        if (onComplete) onComplete();
      } else {
        console.error('[ApiClient] Błąd strumieniowania odpowiedzi:', error);
        if (onError) onError(error);
      }
    }
  }

  // ==========================================================================
  // METODY WORLD PROMPTS (profile tożsamości Świata, do 3 przełączalnych)
  // ==========================================================================

  async getWorldPrompts() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/prompts`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy profili promptu Świata:', error);
      return null;
    }
  }

  async getWorldPrompt(promptId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/prompts/${promptId}`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd pobierania profilu promptu '${promptId}':`, error);
      return null;
    }
  }

  async createWorldPrompt(promptData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/prompts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(promptData),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd tworzenia profilu promptu:', error);
      throw error;
    }
  }

  async updateWorldPrompt(promptId, promptData) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/prompts/${promptId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(promptData),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd aktualizacji profilu promptu '${promptId}':`, error);
      throw error;
    }
  }

  async deleteWorldPrompt(promptId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/prompts/${promptId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd usuwania profilu promptu '${promptId}':`, error);
      throw error;
    }
  }

  async activateWorldPrompt(promptId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/prompts/${promptId}/activate`, {
        method: 'PUT',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd aktywacji profilu promptu '${promptId}':`, error);
      throw error;
    }
  }

  // ==========================================================================
  // METODY AGENT DEFAULT PROMPT (fallback, jedna wartość, bez CRUD)
  // ==========================================================================

  async getAgentDefaultPrompt() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/agent/prompt`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania promptu domyślnego agenta:', error);
      return null;
    }
  }

  async setAgentDefaultPrompt(content) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/agent/prompt`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd zapisu promptu domyślnego agenta:', error);
      throw error;
    }
  }

  // ==========================================================================
  // METODY SILNIKA ŚWIATA — HOME ASSISTANT
  // ==========================================================================

  async getHAConfig() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/config`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania konfiguracji Home Assistant:', error);
      return null;
    }
  }

  async updateHAConfig(data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd zapisu konfiguracji Home Assistant:', error);
      throw error;
    }
  }

  async getHACatalog() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/catalog`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania katalogu Home Assistant:', error);
      return null;
    }
  }

  async getHADeclaredDevices() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/declared`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania zadeklarowanych urządzeń Home Assistant:', error);
      return null;
    }
  }

  async addHADeclaredDevice(data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/declared`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd dodawania zadeklarowanego urządzenia Home Assistant:', error);
      throw error;
    }
  }

  async updateHADeclaredDevice(entityId, data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/declared/${encodeURIComponent(entityId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd aktualizacji zadeklarowanego urządzenia '${entityId}':`, error);
      throw error;
    }
  }

  async deleteHADeclaredDevice(entityId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/declared/${encodeURIComponent(entityId)}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd usuwania zadeklarowanego urządzenia '${entityId}':`, error);
      throw error;
    }
  }

  async getHAGroups() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/groups`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy grup Home Assistant:', error);
      return null;
    }
  }

  async createHAGroup(data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/groups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd tworzenia grupy Home Assistant:', error);
      throw error;
    }
  }

  async updateHAGroup(groupId, data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/groups/${groupId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd aktualizacji grupy '${groupId}':`, error);
      throw error;
    }
  }

  async deleteHAGroup(groupId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/groups/${groupId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd usuwania grupy '${groupId}':`, error);
      throw error;
    }
  }

  // ==========================================================================
  // METODY SILNIKA ŚWIATA — POKOJE (pełnoprawny byt World, niezależny od HA Areas)
  // ==========================================================================

  async getRooms() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/rooms`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy pokoi:', error);
      return null;
    }
  }

  async createRoom(data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/rooms`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd tworzenia pokoju:', error);
      throw error;
    }
  }

  async updateRoom(roomId, data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/rooms/${encodeURIComponent(roomId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd aktualizacji pokoju '${roomId}':`, error);
      throw error;
    }
  }

  async deleteRoom(roomId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/rooms/${encodeURIComponent(roomId)}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd usuwania pokoju '${roomId}':`, error);
      throw error;
    }
  }

  async importRoomsFromHA() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/rooms/import-from-ha`, { method: 'POST' });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd importu pokoi z Home Assistant:', error);
      throw error;
    }
  }

  // ==========================================================================
  // METODY server.voice — status pipeline'u głosowego (read-only)
  // ==========================================================================

  async getVoiceStatus() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/voice/status`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania statusu pipeline\'u głosowego:', error);
      return null;
    }
  }

  async getWorldAreas() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/areas`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy pokoi:', error);
      return [];
    }
  }

  // ==========================================================================
  // METODY SILNIKA ŚWIATA — NADAWCY (sender_id -> pokój)
  // ==========================================================================

  async getSenders() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/senders`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy nadawców:', error);
      return null;
    }
  }

  async registerSender(data) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/senders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd rejestracji nadawcy:', error);
      throw error;
    }
  }

  async deleteSender(senderId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/world/senders/${encodeURIComponent(senderId)}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd usuwania satelity '${senderId}':`, error);
      throw error;
    }
  }
}
