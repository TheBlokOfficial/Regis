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

  async sendChatMessage(sessionId = 'session_default', message = '') {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message }),
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
    onChunk = null,
    onError = null,
    onComplete = null,
    signal = null
  ) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message }),
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
              if (parsed.error) {
                if (onError) onError(new Error(parsed.error));
                return;
              }
              if (parsed.chunk && onChunk) {
                onChunk(parsed.chunk);
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
}
