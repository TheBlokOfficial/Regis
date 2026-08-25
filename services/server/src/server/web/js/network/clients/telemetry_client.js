/**
 * Klient REST domeny Telemetrii — zrzuty wywołań LLM (zakładka „Logi").
 *
 * Osobny klient, nie metody w `ChatClient`: telemetria opisuje wywołania modelu,
 * nie konwersację. Ta sama granica, którą backend trzyma między `server/telemetry`
 * a `network/routes/chat` (patrz `api_client.js` — fasada mirroruje podział backendu).
 */
export class TelemetryClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async getGenerations({ limit = 50, beforeId = null, sessionId = null, status = null } = {}) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (beforeId !== null) params.set('before_id', String(beforeId));
    if (sessionId) params.set('session_id', sessionId);
    if (status) params.set('status', status);

    try {
      const response = await fetch(`${this.baseUrl}/api/v1/telemetry/generations?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd pobierania listy wywołań LLM:', error);
      return { entries: [], next_before_id: null };
    }
  }

  async getGeneration(recordId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/telemetry/generations/${recordId}`);
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Błąd pobierania zrzutu wywołania '${recordId}':`, error);
      return null;
    }
  }

  async clearGenerations() {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/telemetry/generations`, { method: 'DELETE' });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP Error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('[ApiClient] Błąd czyszczenia telemetrii:', error);
      throw error;
    }
  }
}
