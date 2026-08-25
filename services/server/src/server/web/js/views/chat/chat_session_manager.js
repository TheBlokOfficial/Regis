import { renderSessionRowMarkup } from './chat_template.js';

/**
 * Zarządzanie listą sesji czatu i popoverem wyboru konwersacji — wydzielone z `ChatView`.
 * Trzyma własną listę sesji i lekki poll niskiej częstotliwości (WYŁĄCZNIE do wykrycia
 * nowych sesji utworzonych gdzie indziej — kanał watch jest per-sesja, nie widzi sesji
 * jeszcze nieobecnych w popoverze). Przełączenie aktywnej sesji (klik wiersza, usunięcie
 * aktywnej, nowa konwersacja) zgłasza przez `onSessionSwitch` zamiast samemu otwierać kanał
 * obserwujący/historię — to zostaje po stronie `ChatView` (`chat_watch_channel.js` +
 * `loadSessionHistory`), ta odpowiedzialność dotyczy wyłącznie listy/popoveru.
 *
 * Wzorzec: `initX({...})` przyjmuje już zamontowany DOM, trzyma stan w domknięciu, zwraca
 * mały publiczny interfejs (patrz `components/select.js`).
 */
export function initSessionManager({ apiClient, getActiveSessionId, setActiveSessionId, onSessionSwitch }) {
  let sessions = [];
  let watchInterval = null;
  // Nasłuch na `document` (klik poza popoverem) spinamy raz na zawsze tej instancji —
  // `bindPopoverEvents()` uruchamia się przy każdej wizycie na zakładce Chat (TabManager
  // zastępuje poddrzewo DOM przy każdym przełączeniu), więc element trigger/popover trzeba
  // bindować od nowa, ale document nigdy nie znika — bez tej ochrony każda wizyta dokładałaby
  // kolejny, nigdy niesprzątany listener (ten sam problem i rozwiązanie co
  // `select.js#_ensureGlobalListeners`).
  let documentClickBound = false;

  function formatSessionDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    if (isToday) {
      return `Dzisiaj, ${hours}:${minutes}`;
    }
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    return `${day}.${month}, ${hours}:${minutes}`;
  }

  // Ustawia aktywną sesję, odświeża listę (podświetlenie) i deleguje otwarcie kanału
  // obserwującego + wczytanie historii do ChatView przez `onSessionSwitch` — dokładnie ta
  // sama kolejność, jaka wcześniej powtarzała się osobno w trzech miejscach (klik wiersza,
  // usunięcie aktywnej sesji, nowa konwersacja).
  async function switchToSession(sessionId) {
    setActiveSessionId(sessionId);
    await loadSessionsList();
    await onSessionSwitch(sessionId);
  }

  async function loadSessionsList() {
    const list = document.getElementById('popover-session-list');
    const titleDisplay = document.getElementById('chat-session-title-display');
    const countBadge = document.getElementById('popover-session-count');
    if (!apiClient) return;

    try {
      const res = await apiClient.getChatSessions();
      if (res && res.sessions) {
        sessions = res.sessions;

        const activeSession = sessions.find((s) => s.session_id === getActiveSessionId());
        if (!activeSession && sessions.length > 0) {
          setActiveSessionId(sessions[0].session_id);
        }

        const currentActiveId = getActiveSessionId();
        const currentActive = sessions.find((s) => s.session_id === currentActiveId);
        if (titleDisplay) {
          titleDisplay.textContent = currentActive ? currentActive.title : 'Wybierz konwersację';
        }

        if (countBadge) {
          countBadge.textContent = sessions.length;
        }

        if (list) {
          list.innerHTML = sessions
            .map((s) => renderSessionRowMarkup(s, s.session_id === currentActiveId, formatSessionDate(s.updated_at || s.created_at)))
            .join('');

          list.querySelectorAll('.popover-session-row').forEach((row) => {
            row.addEventListener('click', async (e) => {
              if (e.target.closest('.session-delete-btn')) return;

              const sid = row.getAttribute('data-session-id');
              if (sid !== getActiveSessionId()) {
                await switchToSession(sid);
              }
              const popover = document.getElementById('chat-session-popover');
              const triggerBtn = document.getElementById('chat-session-trigger');
              if (popover) popover.classList.add('hidden');
              if (triggerBtn) triggerBtn.classList.remove('active');
            });
          });

          list.querySelectorAll('.session-delete-btn').forEach((btn) => {
            btn.addEventListener('click', async (e) => {
              e.stopPropagation();
              const sid = btn.getAttribute('data-session-id');
              const row = btn.closest('.popover-session-row');

              try {
                if (sid !== getActiveSessionId()) {
                  await apiClient.deleteChatSession(sid);
                  if (row) row.remove();
                  sessions = sessions.filter((s) => s.session_id !== sid);
                  const countBadgeEl = document.getElementById('popover-session-count');
                  if (countBadgeEl) countBadgeEl.textContent = sessions.length;
                } else {
                  await apiClient.deleteChatSession(sid);
                  sessions = sessions.filter((s) => s.session_id !== sid);
                  const fallbackId = sessions.length > 0 ? sessions[0].session_id : 'session_default';
                  await switchToSession(fallbackId);
                }
              } catch (err) {
                console.error('[ChatSessionManager] Błąd usuwania sesji:', err);
              }
            });
          });
        }
      }
    } catch (err) {
      console.error('[ChatSessionManager] Błąd wczytywania listy sesji:', err);
    }
  }

  async function checkForNewSessions() {
    if (!apiClient) return;
    try {
      const res = await apiClient.getChatSessions();
      if (!res || !res.sessions) return;

      const previousIds = new Set(sessions.map((s) => s.session_id));
      const incomingIds = new Set(res.sessions.map((s) => s.session_id));
      const sessionListChanged =
        previousIds.size !== incomingIds.size || [...incomingIds].some((id) => !previousIds.has(id));

      if (sessionListChanged) {
        await loadSessionsList();
      }
    } catch (err) {
      console.error('[ChatSessionManager] Błąd sprawdzania nowych sesji:', err);
    }
  }

  function startWatch() {
    stopWatch();
    watchInterval = setInterval(() => checkForNewSessions(), 4000);
  }

  function stopWatch() {
    if (watchInterval) {
      clearInterval(watchInterval);
      watchInterval = null;
    }
  }

  function bindPopoverEvents() {
    const triggerBtn = document.getElementById('chat-session-trigger');
    const popover = document.getElementById('chat-session-popover');
    const btnPopoverNew = document.getElementById('btn-popover-new-chat');

    if (triggerBtn && popover) {
      triggerBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        popover.classList.toggle('hidden');
        triggerBtn.classList.toggle('active', !popover.classList.contains('hidden'));
      });

      if (!documentClickBound) {
        documentClickBound = true;
        document.addEventListener('click', (e) => {
          const currentPopover = document.getElementById('chat-session-popover');
          const currentTrigger = document.getElementById('chat-session-trigger');
          if (!currentPopover || !currentTrigger) return;
          if (!currentPopover.classList.contains('hidden')) {
            if (!currentPopover.contains(e.target) && !currentTrigger.contains(e.target)) {
              currentPopover.classList.add('hidden');
              currentTrigger.classList.remove('active');
            }
          }
        });
      }
    }

    if (btnPopoverNew) {
      btnPopoverNew.addEventListener('click', async (e) => {
        e.stopPropagation();
        const title = 'Nowa konwersacja';
        const created = await apiClient.createChatSession(title);
        if (created && created.session_id) {
          await switchToSession(created.session_id);
          const currentPopover = document.getElementById('chat-session-popover');
          const currentTrigger = document.getElementById('chat-session-trigger');
          if (currentPopover) currentPopover.classList.add('hidden');
          if (currentTrigger) currentTrigger.classList.remove('active');
        }
      });
    }
  }

  return { loadSessionsList, startWatch, stopWatch, bindPopoverEvents };
}
