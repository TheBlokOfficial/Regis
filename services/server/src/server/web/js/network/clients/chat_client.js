/**
 * Klient REST/SSE domeny Chat — sesje, historia, wysyłka i strumieniowanie.
 */
export class ChatClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

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

  /**
   * "Wyślij i zapomnij" — mirror `AgentEngine.start_interaction()`, ten sam kontrakt, z
   * którego korzysta satelita głosowa: odpala turę w tle i od razu wraca (202), bez
   * czekania na odpowiedź. Renderowanie (własnej wiadomości i odpowiedzi) idzie wyłącznie
   * przez `watchSession()` — Web UI świadomie nie różni się już architektonicznie od
   * satelity/crona jako inicjator tury.
   */
  async sendChatMessageAsync(sessionId = 'session_default', message = '', senderId = null) {
    const response = await fetch(`${this.baseUrl}/api/v1/chat/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, sender_id: senderId }),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP Error: ${response.status}`);
    }
    return await response.json();
  }

  /**
   * Długożyjący kanał SSE obserwujący sesję (`GET .../watch`) — w odróżnieniu od
   * `streamChatMessage` NIE wysyła żadnej wiadomości i NIE kończy się na `[DONE]`/błędzie
   * pojedynczej tury: leci dalej, aż wywołujący przerwie `signal` (AbortController).
   * Zwraca się (bez rzucania), gdy strumień serwera się zakończy z jakiegokolwiek powodu —
   * wywołujący decyduje, czy i kiedy ponowić połączenie.
   */
  async watchSession(
    sessionId,
    { onUserMessage = null, onChunk = null, onToolStart = null, onToolResult = null, onDone = null, onError = null, onCancelled = null } = {},
    signal = null
  ) {
    const response = await fetch(`${this.baseUrl}/api/v1/chat/sessions/${sessionId}/watch`, { signal });
    if (!response.ok) {
      throw new Error(`HTTP Error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) return;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const rawData = trimmed.replace(/^data:\s*/, '');
        try {
          const parsed = JSON.parse(rawData);
          switch (parsed.type) {
            case 'user_message':
              if (onUserMessage) onUserMessage(parsed.content);
              break;
            case 'chunk':
              if (onChunk) onChunk(parsed.chunk);
              break;
            case 'tool_start':
              if (onToolStart) onToolStart(parsed);
              break;
            case 'tool_result':
              if (onToolResult) onToolResult(parsed);
              break;
            case 'done':
              if (onDone) onDone();
              break;
            case 'error':
              if (onError) onError(new Error(parsed.error));
              break;
            case 'cancelled':
              if (onCancelled) onCancelled();
              break;
            default:
              console.warn('[ApiClient] Nieznany typ ramki kanału obserwującego:', parsed);
          }
        } catch (e) {
          console.warn('[ApiClient] Błąd parsowania ramki kanału obserwującego:', rawData, e);
        }
      }
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
}
