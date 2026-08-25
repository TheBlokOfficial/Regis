import { Icons } from '../../icons.js';
import { flashButtonResult, lockButtonForAction } from '../../utils/button_flash.js';
import { showToast } from '../../utils/toast.js';
import { renderClientConfigErrorMarkup, renderClientConfigFormMarkup } from './voice_client_template.js';

/**
 * Formularz "Konfiguracja klienta" — próg wake-worda (100% serwerowa detekcja, patrz
 * `voice/wakeword.py`) + parametry VAD satelity (algorytm lokalny, próg centralnie
 * skonfigurowany tutaj i wysyłany satelicie przy handshake — `ServerMessageType.CLIENT_CONFIG`).
 * Pojedynczy globalny config, nie kolekcja instancji jak dostawcy LLM/STT/TTS — prosty
 * formularz, jawny "Zapisz" (mirror wzorca z `extensions/ha/config_panel.js`).
 *
 * Wydzielone z `VoiceConfigView` — druga, niezależna odpowiedzialność tego widoku obok
 * dashboardu klientów (`voice_clients_dashboard.js`), wzorzec `initX` z `components/select.js`.
 */
export function initClientConfigForm({ apiClient }) {
  async function load() {
    const [config, status] = await Promise.all([apiClient.getClientConfig(), apiClient.getVoiceStatus()]);
    render(config, status);
  }

  function render(config, status) {
    const container = document.getElementById('voice-client-config-section');
    if (!container) return;

    if (!config) {
      container.innerHTML = renderClientConfigErrorMarkup();
      return;
    }

    container.innerHTML = renderClientConfigFormMarkup(config, status);
    document.getElementById('voice-btn-save-client-config')?.addEventListener('click', () => save());
  }

  // Wynik zapisu jest pokazywany BEZPOŚREDNIO na przycisku (checkmark/X, mirror
  // `config_panel.js::handleTestConnection` via `utils/button_flash.js`) — jeden
  // kanał informacji zamiast koloru na przycisku + osobnego toastu. Walidacja NaN
  // to jedyny wyjątek: to pre-flight przed wywołaniem API, przycisk jeszcze nic nie
  // "wie" o wyniku, więc zostaje jako toast.
  async function save() {
    const thresholdInput = document.getElementById('voice-input-threshold');
    const silenceInput = document.getElementById('voice-input-vad-silence');
    const amplitudeInput = document.getElementById('voice-input-vad-amplitude');
    const btn = document.getElementById('voice-btn-save-client-config');
    if (!thresholdInput || !silenceInput || !amplitudeInput || !btn) return;

    const thresholdPct = Number(thresholdInput.value);
    const silenceMs = Number(silenceInput.value);
    const amplitude = Number(amplitudeInput.value);
    if (Number.isNaN(thresholdPct) || Number.isNaN(silenceMs) || Number.isNaN(amplitude)) {
      showToast('Wszystkie pola muszą być liczbami.', 'error');
      return;
    }

    lockButtonForAction(btn);
    let ok = false;
    try {
      await apiClient.updateClientConfig({
        wakeword_threshold: thresholdPct / 100,
        vad_silence_duration_ms: silenceMs,
        vad_amplitude_threshold: amplitude,
      });
      ok = true;
    } catch {
      ok = false;
    }
    flashButtonResult(btn, ok, { successHtml: Icons.Check(), errorHtml: Icons.X() });
  }

  return { load };
}
