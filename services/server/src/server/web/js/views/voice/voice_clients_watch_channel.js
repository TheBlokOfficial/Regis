/**
 * Kanał obserwujący WSZYSTKICH klientów naraz (GET .../clients/watch, SSE) — wydzielony
 * z `VoiceConfigView`, mirror `chat/chat_watch_channel.js`: odpowiada wyłącznie za cykl
 * życia połączenia (AbortController, reconnect po zerwaniu), nie dotyka DOM ani stanu.
 *
 * Różnica względem `chat_watch_channel.js`: to jeden GLOBALNY strumień (wszyscy klienci
 * naraz), nie per-sesja — `open()` nie przyjmuje żadnego identyfikatora, a callbacki
 * przechodzą do `apiClient.watchClients()` bez owijania (nie ma czego wstrzykiwać jako
 * "dla kogo był ten callback", w odróżnieniu od `sessionId` w kanale czatu).
 */
export function createClientsWatchChannel(apiClient, callbacks) {
  let controller = null;

  async function runLoop(ctrl) {
    while (!ctrl.signal.aborted) {
      try {
        await apiClient.watchClients(callbacks, ctrl.signal);
      } catch (err) {
        if (ctrl.signal.aborted) return;
        console.error('[VoiceClientsWatchChannel] Kanał klientów przerwany, ponawiam za chwilę:', err);
      }
      if (ctrl.signal.aborted) return;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  function open() {
    close();
    const ctrl = new AbortController();
    controller = ctrl;
    runLoop(ctrl);
  }

  function close() {
    if (controller) {
      controller.abort();
      controller = null;
    }
  }

  return { open, close };
}
