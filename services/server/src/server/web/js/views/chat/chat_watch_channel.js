/**
 * Kanał obserwujący aktywną sesję czatu (GET .../watch, SSE) — wydzielony z `ChatView`.
 * Odpowiada wyłącznie za cykl życia połączenia (AbortController, reconnect po zerwaniu) i
 * przekazywanie zdarzeń dalej przez `callbacks` — nie dotyka DOM ani stanu czatu, dokładnie
 * jak wymaga tego oddzielenie mechaniki streamingu od renderowania (patrz `chat_template.js`
 * i `ChatView._onWatch*`, które faktycznie aktualizują UI).
 *
 * Każdy callback dostaje `sessionId`, dla którego dana pętla `open()` została wywołana —
 * to ten sam mechanizm co dawne domknięcia w `ChatView._runWatchLoop` (`sessionId` z
 * argumentu, NIE z aktualnego `this.activeSessionId`), bo zdarzenie z jednej (starej,
 * właśnie zamykanej) pętli obserwującej mogło się jeszcze pojawić chwilę po tym, jak
 * aktywna sesja się zmieniła — wywołujący porównuje `sessionId` z aktualnie aktywną sesją
 * i odrzuca spóźnione zdarzenia.
 */
export function createWatchChannel(apiClient, callbacks) {
  let controller = null;

  function wrapCallbacks(sessionId) {
    const wrap = (fn) => (fn ? (...args) => fn(sessionId, ...args) : undefined);
    return {
      onUserMessage: wrap(callbacks.onUserMessage),
      onChunk: wrap(callbacks.onChunk),
      onToolStart: wrap(callbacks.onToolStart),
      onToolResult: wrap(callbacks.onToolResult),
      onDone: wrap(callbacks.onDone),
      onError: wrap(callbacks.onError),
      onCancelled: wrap(callbacks.onCancelled),
    };
  }

  async function runLoop(sessionId, ctrl) {
    const wrapped = wrapCallbacks(sessionId);
    while (!ctrl.signal.aborted) {
      try {
        await apiClient.watchSession(sessionId, wrapped, ctrl.signal);
      } catch (err) {
        if (ctrl.signal.aborted) return;
        console.error('[ChatWatchChannel] Kanał obserwujący przerwany, ponawiam za chwilę:', err);
      }
      if (ctrl.signal.aborted) return;
      // Połączenie zakończyło się z jakiegoś powodu (restart serwera, sieć) — krótka
      // przerwa i reconnect na tę samą sesję, zamiast zostawiać kartę bez żywego kanału.
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  function open(sessionId) {
    close();
    const ctrl = new AbortController();
    controller = ctrl;
    runLoop(sessionId, ctrl);
  }

  function close() {
    if (controller) {
      controller.abort();
      controller = null;
    }
  }

  return { open, close };
}
