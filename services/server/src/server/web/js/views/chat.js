import { Icons } from '../icons.js';
import { getSenderId } from '../sender_id.js';
import { escapeHtml, escapeAttr } from '../utils/dom.js';
import { StepRailRenderer } from './chat/step_rail.js';

/**
 * Moduł widoku "Czat z Agentem" - interfejs kontrolno-debugujący w Web Console Regis OS.
 */
export class ChatView {
  constructor() {
    this.apiClient = null;
    this.activeSessionId = 'session_default';
    this.sessions = [];
    this.isGenerating = false;
    this.currentAssistantMessageEl = null;
    this.currentAssistantTextEl = null;
    this.accumulatedText = '';
    // Renderowanie na żywo drzewka kroków ReAct (tekst/COT przeplecione z wywołaniami
    // narzędzi) — wydzielone do StepRailRenderer (`./chat/step_rail.js`), które trzyma
    // własny stan przebiegu i dokłada węzły do DOM w kolejności faktycznego przyjścia
    // zdarzeń SSE, bez pełnego przerenderowania na każdy token.
    this.stepRail = new StepRailRenderer();
    this.userHasScrolledUp = false;
    this._documentClickBound = false;
    // Kanał obserwujący aktywną sesję w czasie rzeczywistym (GET .../watch, SSE) — jedno
    // długożyjące połączenie, niezależne od tego, kto zainicjował turę (Web/satelita/cron/
    // inna karta). Jedyne źródło renderowania wiadomości/streamingu — Web UI nie ma już
    // żadnej "własnej", uprzywilejowanej ścieżki (patrz handleSendMessage/openWatch).
    this.watchController = null;
    // Lekki poll niskiej częstotliwości — WYŁĄCZNIE do wykrycia nowych sesji utworzonych
    // gdzie indziej (kanał watch jest per-sesja, nie widzi sesji jeszcze nieobecnych w
    // popoverze). Treść/tokeny nie idą już tą ścieżką.
    this.sessionListWatchInterval = null;
  }

  render() {
    return `
      <div class="chat-layout">
        <!-- Górny Pasek Nagłówka Czatu (Top Center Custom Popover Trigger) -->
        <div class="chat-top-bar">
          <div class="chat-session-trigger-wrapper">
            <button class="chat-session-trigger" id="chat-session-trigger" title="Zmień konwersację">
              <span class="chat-session-trigger-icon" id="icon-chat-session-msg"></span>
              <span class="chat-session-trigger-title" id="chat-session-title-display">Główny Czat Debugujący</span>
              <span class="chat-session-trigger-chevron" id="icon-chat-session-chevron"></span>
            </button>

            <!-- Pływające Popover Menu Konwersacji -->
            <div class="chat-session-popover hidden" id="chat-session-popover">
              <div class="popover-header">
                <div class="popover-title-box">
                  <span class="popover-title">Konwersacje</span>
                  <span class="popover-badge" id="popover-session-count">0</span>
                </div>
                <button class="btn btn-primary btn-sm btn-popover-new" id="btn-popover-new-chat">
                  <span id="icon-popover-plus"></span>
                  <span>+ Nowa konwersacja</span>
                </button>
              </div>
              <div class="popover-session-list" id="popover-session-list"></div>
            </div>
          </div>
        </div>

        <!-- Główny Kontener Wiadomości -->
        <div class="chat-messages-container" id="chat-messages-container">
          <div class="chat-empty-state" id="chat-empty-state">
            <div class="empty-state-icon" id="chat-empty-icon"></div>
            <div class="empty-state-title">Jak mogę pomóc?</div>
            <div class="empty-state-desc">Jestem Agentem Regis OS. O co chcesz zapytać?</div>
          </div>
        </div>

        <div class="chat-bottom-area">
          <!-- Pływający Pasek Wprowadzania -->
          <div class="chat-floating-input-wrapper">
            <div class="chat-floating-box">
              <textarea
                id="chat-textarea"
                class="chat-textarea"
                placeholder="Napisz wiadomość do Agenta..."
                rows="1"
              ></textarea>
              
              <div class="chat-input-bottom-bar">
                <div class="chat-input-actions-left">
                  <div class="chat-model-indicator">
                    <span class="status-dot-pulse"></span>
                    <span id="chat-active-model-name">Ładowanie...</span>
                  </div>
                </div>
                <button class="btn-chat-send" id="btn-chat-send" title="Wyślij">
                  <span id="icon-btn-chat-send"></span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    this.mountIcons();
    this.bindEvents();
    await this.loadActiveProviderInfo();
    await this.loadSessionsList();
    // Otwieramy kanał obserwujący PRZED wczytaniem historii, żeby zminimalizować okno,
    // w którym ewentualny token/zdarzenie mogłyby przepaść między snapshotem a subskrypcją.
    this.openWatch(this.activeSessionId);
    await this.loadSessionHistory(this.activeSessionId);
    this.startSessionListWatch();
  }

  mountIcons() {
    const triggerMsg = document.getElementById('icon-chat-session-msg');
    if (triggerMsg) triggerMsg.innerHTML = Icons.MessageSquare();

    const triggerChevron = document.getElementById('icon-chat-session-chevron');
    if (triggerChevron) triggerChevron.innerHTML = Icons.ChevronDown();

    const popoverPlus = document.getElementById('icon-popover-plus');
    if (popoverPlus) popoverPlus.innerHTML = Icons.Plus();

    const emptyIcon = document.getElementById('chat-empty-icon');
    if (emptyIcon) emptyIcon.innerHTML = Icons.MessageSquare();

    const btnSend = document.getElementById('icon-btn-chat-send');
    if (btnSend) btnSend.innerHTML = Icons.Send();
  }

  bindEvents() {
    const textarea = document.getElementById('chat-textarea');
    const btnSend = document.getElementById('btn-chat-send');
    const triggerBtn = document.getElementById('chat-session-trigger');
    const popover = document.getElementById('chat-session-popover');
    const btnPopoverNew = document.getElementById('btn-popover-new-chat');
    const container = document.getElementById('chat-messages-container');

    if (container) {
      container.addEventListener('scroll', () => {
        const threshold = 60;
        const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
        this.userHasScrolledUp = !isAtBottom;
      });

      // Delegowany toggle dla zwijanych nagłówków (.rail-group i bloki "Analiza") —
      // animacja wysokości jest sterowana z JS (setCollapsibleOpen), nie czystym CSS,
      // bo transition na sztywnym dużym limicie (max-height) dawał nieliniowe, "tnące"
      // rozwijanie i opóźnione zwijanie (animacja proporcjonalna do limitu, nie realnej
      // treści). Zmierzona wysokość (scrollHeight) daje animację 1:1 z rzeczywistą treścią.
      container.addEventListener('click', (e) => {
        const summary = e.target.closest('.thinking-summary');
        if (!summary) return;
        const block = summary.closest('.chat-collapsible');
        if (!block) return;
        this.stepRail.setCollapsibleOpen(block, block.dataset.open !== 'true');
      });
    }

    if (textarea) {
      textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
      });

      textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.handleSendMessage();
        }
      });
    }

    if (btnSend) {
      btnSend.addEventListener('click', () => {
        if (this.isGenerating) {
          this.stopGeneration();
        } else {
          this.handleSendMessage();
        }
      });
    }

    if (triggerBtn && popover) {
      triggerBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        popover.classList.toggle('hidden');
        triggerBtn.classList.toggle('active', !popover.classList.contains('hidden'));
      });

      // TabManager zastępuje cały poddrzewo DOM widoku Chat przy każdej wizycie na zakładce
      // (patrz tab_manager.js#switchTab), a ChatView jest instancją długożyjącą — bindEvents()
      // uruchamia się więc wielokrotnie. Nasłuch na `document` musi zostać spięty tylko RAZ,
      // inaczej każda wizyta na zakładce Chat dokłada kolejny, nigdy niesprzątany listener.
      // Wewnątrz handlera odpytujemy DOM na żywo, by zawsze operować na aktualnie
      // wyrenderowanym popoverze/triggerze, a nie na (potencjalnie odłączonych) referencjach
      // z chwili pierwszego wywołania bindEvents().
      if (!this._documentClickBound) {
        this._documentClickBound = true;
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
        const created = await this.apiClient.createChatSession(title);
        if (created && created.session_id) {
          this.activeSessionId = created.session_id;
          await this.loadSessionsList();
          this.openWatch(this.activeSessionId);
          await this.loadSessionHistory(this.activeSessionId);
          if (popover) {
            popover.classList.add('hidden');
            if (triggerBtn) triggerBtn.classList.remove('active');
          }
        }
      });
    }
  }

  async loadActiveProviderInfo() {
    const modelNameEl = document.getElementById('chat-active-model-name');
    if (!modelNameEl || !this.apiClient) return;

    try {
      const providersData = await this.apiClient.getLLMProviders();
      if (providersData && providersData.providers) {
        const active = providersData.providers.find((p) => p.is_active) || providersData.providers[0];
        if (active) {
          const model = active.options?.model || 'domyślny';
          modelNameEl.textContent = `${active.name} (${model})`;
          return;
        }
      }
      modelNameEl.textContent = 'Brak aktywnego dostawcy';
    } catch {
      modelNameEl.textContent = 'Nieznany model';
    }
  }

  async loadSessionsList() {
    const list = document.getElementById('popover-session-list');
    const titleDisplay = document.getElementById('chat-session-title-display');
    const countBadge = document.getElementById('popover-session-count');
    if (!this.apiClient) return;

    try {
      const res = await this.apiClient.getChatSessions();
      if (res && res.sessions) {
        this.sessions = res.sessions;

        const activeSession = this.sessions.find((s) => s.session_id === this.activeSessionId);
        if (!activeSession && this.sessions.length > 0) {
          this.activeSessionId = this.sessions[0].session_id;
        }

        const currentActive = this.sessions.find((s) => s.session_id === this.activeSessionId);
        if (titleDisplay) {
          titleDisplay.textContent = currentActive ? currentActive.title : 'Wybierz konwersację';
        }

        if (countBadge) {
          countBadge.textContent = this.sessions.length;
        }

        if (list) {
          list.innerHTML = this.sessions
            .map((s) => {
              const isActive = s.session_id === this.activeSessionId;
              const dateStr = this.formatSessionDate(s.updated_at || s.created_at);
              return `
                <div class="popover-session-row ${isActive ? 'active' : ''}" data-session-id="${escapeAttr(s.session_id)}">
                  <div class="session-info">
                    <span class="session-title" title="${escapeAttr(s.title)}">${escapeHtml(s.title)}</span>
                    <span class="session-time">${dateStr ? dateStr : ''}</span>
                  </div>
                  <button class="session-delete-btn" data-session-id="${escapeAttr(s.session_id)}" title="Usuń konwersację">
                    ${Icons.Trash2()}
                  </button>
                </div>
              `;
            })
            .join('');

          list.querySelectorAll('.popover-session-row').forEach((row) => {
            row.addEventListener('click', async (e) => {
              if (e.target.closest('.session-delete-btn')) return;

              const sid = row.getAttribute('data-session-id');
              if (sid !== this.activeSessionId) {
                this.activeSessionId = sid;
                await this.loadSessionsList();
                this.openWatch(this.activeSessionId);
                await this.loadSessionHistory(this.activeSessionId);
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
                if (sid !== this.activeSessionId) {
                  await this.apiClient.deleteChatSession(sid);
                  if (row) row.remove();
                  this.sessions = this.sessions.filter((s) => s.session_id !== sid);
                  const countBadgeEl = document.getElementById('popover-session-count');
                  if (countBadgeEl) countBadgeEl.textContent = this.sessions.length;
                } else {
                  await this.apiClient.deleteChatSession(sid);
                  this.sessions = this.sessions.filter((s) => s.session_id !== sid);
                  if (this.sessions.length > 0) {
                    this.activeSessionId = this.sessions[0].session_id;
                  } else {
                    this.activeSessionId = 'session_default';
                  }
                  await this.loadSessionsList();
                  this.openWatch(this.activeSessionId);
                  await this.loadSessionHistory(this.activeSessionId);
                }
              } catch (err) {
                console.error('[ChatView] Błąd usuwania sesji:', err);
              }
            });
          });
        }
      }
    } catch (err) {
      console.error('[ChatView] Błąd wczytywania listy sesji:', err);
    }
  }

  formatSessionDate(timestamp) {
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

  startSessionListWatch() {
    this.stopSessionListWatch();
    this.sessionListWatchInterval = setInterval(() => this.checkForNewSessions(), 4000);
  }

  stopSessionListWatch() {
    if (this.sessionListWatchInterval) {
      clearInterval(this.sessionListWatchInterval);
      this.sessionListWatchInterval = null;
    }
  }

  async checkForNewSessions() {
    if (!this.apiClient) return;
    try {
      const res = await this.apiClient.getChatSessions();
      if (!res || !res.sessions) return;

      const previousIds = new Set(this.sessions.map((s) => s.session_id));
      const incomingIds = new Set(res.sessions.map((s) => s.session_id));
      const sessionListChanged =
        previousIds.size !== incomingIds.size || [...incomingIds].some((id) => !previousIds.has(id));

      if (sessionListChanged) {
        await this.loadSessionsList();
      }
    } catch (err) {
      console.error('[ChatView] Błąd sprawdzania nowych sesji:', err);
    }
  }

  // --------------------------------------------------------------------------------------
  // Kanał obserwujący (GET .../watch, SSE) — jedyne źródło renderowania treści/streamingu.
  // Otwierany raz per aktywna sesja (init/przełączenie sesji), niezależnie od tego, kto
  // odpalił turę: satelita/cron/Web UI/inna karta wyglądają dla tego kodu identycznie.
  // --------------------------------------------------------------------------------------

  openWatch(sessionId) {
    this.closeWatch();
    const controller = new AbortController();
    this.watchController = controller;
    this._runWatchLoop(sessionId, controller);
  }

  closeWatch() {
    if (this.watchController) {
      this.watchController.abort();
      this.watchController = null;
    }
  }

  async _runWatchLoop(sessionId, controller) {
    while (!controller.signal.aborted) {
      try {
        await this.apiClient.watchSession(
          sessionId,
          {
            onUserMessage: (content) => this._onWatchUserMessage(sessionId, content),
            onChunk: (chunk) => this._onWatchChunk(sessionId, chunk),
            onToolStart: (evt) => this._onWatchToolStart(sessionId, evt),
            onToolResult: (evt) => this._onWatchToolResult(sessionId, evt),
            onDone: () => this._onWatchDone(sessionId),
            onError: (err) => this._onWatchError(sessionId, err),
            onCancelled: () => this._onWatchCancelled(sessionId),
          },
          controller.signal
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error('[ChatView] Kanał obserwujący przerwany, ponawiam za chwilę:', err);
      }
      if (controller.signal.aborted) return;
      // Połączenie zakończyło się z jakiegoś powodu (restart serwera, sieć) — krótka
      // przerwa i reconnect na tę samą sesję, zamiast zostawiać kartę bez żywego kanału.
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  _onWatchUserMessage(sessionId, content) {
    if (sessionId !== this.activeSessionId) return;
    const emptyState = document.getElementById('chat-empty-state');
    if (emptyState) emptyState.remove();

    this.appendMessageElement('user', content, Date.now() / 1000);
    this.userHasScrolledUp = false;
    this.scrollToBottom(true);

    this.setGeneratingState(true);
    this.accumulatedText = '';
    this.currentAssistantMessageEl = this.appendMessageElement('assistant', '', Date.now() / 1000, true);
    this.currentAssistantTextEl = this.currentAssistantMessageEl.querySelector('.message-text');
    if (this.currentAssistantTextEl) this.currentAssistantTextEl.innerHTML = '';
    this.stepRail.reset(this.currentAssistantTextEl);
  }

  _onWatchChunk(sessionId, chunk) {
    if (sessionId !== this.activeSessionId) return;
    this.accumulatedText += chunk;
    this.stepRail.appendStreamingText(chunk);
    this.scrollToBottom();
  }

  _onWatchToolStart(sessionId, evt) {
    if (sessionId !== this.activeSessionId) return;
    this.stepRail.appendStepNode(evt);
    this.scrollToBottom();
  }

  _onWatchToolResult(sessionId, evt) {
    if (sessionId !== this.activeSessionId) return;
    this.stepRail.updateStepNode(evt);
    this.scrollToBottom();
  }

  _onWatchDone(sessionId) {
    if (sessionId !== this.activeSessionId) return;
    this.stepRail.finalizeCurrentTextRun();
    this.stepRail.closeCurrentRail();
    this.setGeneratingState(false);
    this.loadSessionsList();
  }

  _onWatchError(sessionId, error) {
    if (sessionId !== this.activeSessionId) return;
    console.error('[ChatView] Błąd generowania:', error);
    this.stepRail.appendStreamingText(`\n\n[Błąd: ${error.message}]`);
    this._onWatchDone(sessionId);
  }

  _onWatchCancelled(sessionId) {
    if (sessionId !== this.activeSessionId) return;
    this.stepRail.appendStreamingText('\n\n[Przerwano]');
    this._onWatchDone(sessionId);
  }

  async loadSessionHistory(sessionId) {
    this.userHasScrolledUp = false;
    const container = document.getElementById('chat-messages-container');
    if (!container || !this.apiClient) return;

    try {
      const res = await this.apiClient.getChatHistory(sessionId);
      container.innerHTML = '';

      if (!res || !res.messages || res.messages.length === 0) {
        container.innerHTML = `
          <div class="chat-empty-state" id="chat-empty-state">
            <div class="empty-state-icon" id="chat-empty-icon">${Icons.MessageSquare()}</div>
            <div class="empty-state-title">Jak mogę pomóc?</div>
            <div class="empty-state-desc">Jestem Agentem Regis OS. O co chcesz zapytać?</div>
          </div>
        `;
        this.setGeneratingState(!!(res && res.is_generating));
        return;
      }

      let lastAssistantRow = null;
      let lastAssistantContent = '';

      res.messages.forEach((msg, idx) => {
        const isLast = idx === res.messages.length - 1;
        const isStreamingMsg = isLast && res.is_generating && msg.role === 'assistant';
        const row = this.appendMessageElement(msg.role, msg.content, msg.timestamp, isStreamingMsg, msg.metadata);
        if (msg.role === 'assistant') {
          lastAssistantRow = row;
          lastAssistantContent = msg.content || '';
        }
      });

      this.scrollToBottom(true);

      if (res.is_generating) {
        this.setGeneratingState(true);
        const lastMsg = res.messages[res.messages.length - 1];
        if (!lastAssistantRow || lastMsg.role !== 'assistant') {
          lastAssistantRow = this.appendMessageElement('assistant', '', Date.now() / 1000, true);
          lastAssistantContent = '';
        }
        this.currentAssistantMessageEl = lastAssistantRow;
        this.currentAssistantTextEl = lastAssistantRow ? lastAssistantRow.querySelector('.message-text') : null;
        this.accumulatedText = lastAssistantContent;
        // Usuwamy statyczny kursor replayu — dalsze tokeny dokłada już kanał obserwujący
        // (appendStreamingText), który zarządza własnym kursorem na końcu bieżącego przebiegu.
        this.currentAssistantTextEl?.querySelector('.streaming-cursor')?.remove();
        this.stepRail.reset(this.currentAssistantTextEl);
        // Kroki narzędzi SPRZED tego przeładowania nie są tu widoczne (metadata.steps trafia
        // do historii dopiero po zakończeniu tury) — te, które nastąpią OD TERAZ, kanał
        // obserwujący doda już na żywo (patrz docs/manifest.md).
      } else {
        this.setGeneratingState(false);
      }
    } catch (err) {
      console.error('[ChatView] Błąd wczytywania historii sesji:', err);
    }
  }

  async handleSendMessage() {
    const textarea = document.getElementById('chat-textarea');
    if (!textarea) return;

    if (this.isGenerating) {
      await this.stopGeneration();
      return;
    }

    const message = textarea.value.trim();
    if (!message) return;

    textarea.value = '';
    textarea.style.height = 'auto';

    // "Wyślij i zapomnij" — mirror `AgentEngine.start_interaction()`, ten sam kontrakt co
    // satelita głosowa. Renderowanie (bąbelek usera, potem odpowiedź agenta) przychodzi
    // wyłącznie przez już otwarty kanał obserwujący (patrz _onWatchUserMessage/_onWatchChunk
    // powyżej) — dokładnie tak samo, jakby tę turę odpaliła satelita/cron/inna karta.
    try {
      await this.apiClient.sendChatMessageAsync(this.activeSessionId, message, getSenderId());
    } catch (err) {
      console.error('[ChatView] Błąd wysyłania wiadomości:', err);
      textarea.value = message;
    }
  }

  async stopGeneration() {
    // Anulowanie NIE zamyka kanału obserwującego — zdarzenie `cancelled`, które opublikuje
    // backend, dotrze przez ten sam, zawsze otwarty kanał (_onWatchCancelled) i sfinalizuje
    // UI dokładnie tak samo, jak zrobiłaby to dowolna inna przyczyna zakończenia tury.
    await this.apiClient.cancelChatSession(this.activeSessionId);
  }

  setGeneratingState(isGenerating) {
    this.isGenerating = isGenerating;
    this.stepRail.setGenerating(isGenerating);
    const btnSend = document.getElementById('btn-chat-send');
    const textarea = document.getElementById('chat-textarea');

    if (textarea) {
      textarea.disabled = isGenerating;
    }

    if (btnSend) {
      if (isGenerating) {
        btnSend.innerHTML = Icons.Square();
        btnSend.classList.add('btn-danger');
        btnSend.title = 'Zatrzymaj generowanie';
      } else {
        btnSend.innerHTML = Icons.Send();
        btnSend.classList.remove('btn-danger');
        btnSend.title = 'Wyślij wiadomość (Enter)';
      }
    }
  }

  appendMessageElement(role, content, timestamp, isStreaming = false, metadata = null) {
    const container = document.getElementById('chat-messages-container');
    if (!container) return null;

    const row = document.createElement('div');
    row.className = `chat-message-row ${role === 'user' ? 'row-user' : 'row-agent'}`;

    const isUser = role === 'user';

    const cursorHtml = isStreaming ? '<span class="streaming-cursor"></span>' : '';
    const formattedContent = isUser
      ? this.formatMessageText(content) + cursorHtml
      : this.stepRail.renderAssistantHistoryHtml(content, (metadata && metadata.steps) || []) + cursorHtml;

    if (isUser) {
      row.innerHTML = `
        <div class="message-bubble bubble-user">
          <div class="message-text">${formattedContent}</div>
        </div>
      `;
    } else {
      // Bez awatara/nazwy nadawcy — jedyny agent w systemie, powtarzanie "Regis OS" przy
      // każdej turze nie niesie informacji (lewe wyrównanie już jednoznacznie odróżnia
      // agenta od usera, którego bąbelki są po prawej).
      row.innerHTML = `
        <div class="message-body">
          <div class="message-bubble bubble-agent">
            <div class="message-text">${formattedContent}</div>
          </div>
        </div>
      `;
    }

    container.appendChild(row);
    return row;
  }

  // Proste formatowanie tekstu bez obsługi <think>/kroków — używane wyłącznie dla wiadomości
  // `user` (obsługa <think> i kroków ReAct żyje w renderAssistantHistoryHtml, jedynej ścieżce
  // renderowania wiadomości `assistant`).
  formatMessageText(text) {
    if (!text) return '';
    return `<div class="message-rest-content">${this.stepRail.formatRestContent(text)}</div>`;
  }

  scrollToBottom(force = false) {
    if (force || !this.userHasScrolledUp) {
      const container = document.getElementById('chat-messages-container');
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }

}
