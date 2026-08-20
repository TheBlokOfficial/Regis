/**
 * Klient REST domeny World (`server/world`, WorldEngine) — prompty Świata,
 * Home Assistant (config/katalog/zadeklarowane urządzenia/grupy), pokoje,
 * nadawcy.
 */
export class WorldClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  // --- Prompty Świata (profile tożsamości, do 3 przełączalnych) ---

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

  // --- Home Assistant ---

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

  // --- Pokoje (pełnoprawny byt World, niezależny od HA Areas) ---

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

  // --- Nadawcy (sender_id -> pokój) ---

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
