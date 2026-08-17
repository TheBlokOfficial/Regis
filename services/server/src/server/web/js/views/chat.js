import { Icons } from '../icons.js';

/**
 * Moduł widoku "Czat z Agentem" - interfejs kontrolno-debugujący w Web Console Regis OS.
 */
export class ChatView {
  constructor() {
    this.apiClient = null;
    this.activeSessionId = 'session_default';
    this.sessions = [];
    this.isGenerating = false;
    this.abortController = null;
    this.currentAssistantMessageEl = null;
    this.currentAssistantTextEl = null;
    this.accumulatedText = '';
    // Stan renderowania na żywo drzewka kroków ReAct (tekst/COT przeplecione z wywołaniami
    // narzędzi) — kroki i przebiegi tekstu dokładane są przyrostowo do DOM w kolejności
    // faktycznego przyjścia zdarzeń SSE, bez pełnego przerenderowania na każdy token
    // (zachowuje stan rozwinięcia node'ów, które użytkownik otworzył w trakcie streamu).
    this.currentTextRunEl = null;
    this.currentTextRunText = '';
    this.stepElsByCallId = new Map();
    this.userHasScrolledUp = false;
    this.pollInterval = null;
    this._documentClickBound = false;
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
    await this.loadSessionHistory(this.activeSessionId);
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

      // Delegowany toggle dla zwijanych node'ów (blok myślenia + kroki ReAct) —
      // wspólna klasa bazowa .chat-collapsible, żeby jeden listener obsłużył oba warianty
      container.addEventListener('click', (e) => {
        const summary = e.target.closest('.thinking-summary');
        if (!summary) return;
        const block = summary.closest('.chat-collapsible');
        if (!block) return;
        const isOpen = block.dataset.open === 'true';
        block.dataset.open = isOpen ? 'false' : 'true';
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
                <div class="popover-session-row ${isActive ? 'active' : ''}" data-session-id="${this.escapeHtml(s.session_id)}">
                  <div class="session-info">
                    <span class="session-title" title="${this.escapeHtml(s.title)}">${this.escapeHtml(s.title)}</span>
                    <span class="session-time">${dateStr ? dateStr : ''}</span>
                  </div>
                  <button class="session-delete-btn" data-session-id="${this.escapeHtml(s.session_id)}" title="Usuń konwersację">
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

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  startPolling(sessionId) {
    this.stopPolling();
    this.pollInterval = setInterval(async () => {
      if (this.activeSessionId !== sessionId || !this.isGenerating) {
        this.stopPolling();
        return;
      }

      try {
        const res = await this.apiClient.getChatHistory(sessionId);
        if (!res || this.activeSessionId !== sessionId) {
          this.stopPolling();
          return;
        }

        const messages = res.messages || [];
        const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;

        if (lastMsg && lastMsg.role === 'assistant') {
          this.accumulatedText = lastMsg.content || '';
          // Fallback pollingu (SSE nieaktywne, np. po odświeżeniu strony w trakcie generowania)
          // nie ma dostępu do kroków pośrednich w toku — pokazuje tylko narastający tekst,
          // całe drzewko kroków pojawi się dopiero po zakończeniu tury (metadata.steps
          // trafi do historii). Świadomy gap, patrz docs/manifest.md.
          if (this.currentAssistantTextEl) {
            this.renderTextRunIncremental(this.currentAssistantTextEl, this.accumulatedText, res.is_generating);
          }
          this.scrollToBottom();
        }

        if (!res.is_generating) {
          this.stopPolling();
          this.finishStreaming();
        }
      } catch (err) {
        console.error('[ChatView] Błąd w pollingu historii:', err);
      }
    }, 1500);
  }

  async loadSessionHistory(sessionId) {
    this.stopPolling();
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
        if (res && res.is_generating) {
          this.setGeneratingState(true);
          this.startPolling(sessionId);
        } else {
          this.setGeneratingState(false);
        }
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
        this.startPolling(sessionId);
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

    this.stopPolling();

    // Usunięcie empty state jeśli istnieje
    const emptyState = document.getElementById('chat-empty-state');
    if (emptyState) emptyState.remove();

    // 1. Dodanie wiadomości użytkownika do interfejsu
    this.appendMessageElement('user', message, Date.now() / 1000);
    textarea.value = '';
    textarea.style.height = 'auto';

    this.userHasScrolledUp = false;
    this.scrollToBottom(true);

    // 2. Przygotowanie stanu strumieniowania odpowiedzi Agenta
    this.setGeneratingState(true);
    this.accumulatedText = '';
    this.currentAssistantMessageEl = this.appendMessageElement('assistant', '', Date.now() / 1000, true);
    this.currentAssistantTextEl = this.currentAssistantMessageEl.querySelector('.message-text');
    // Zawartość budowana jest przyrostowo (appendStreamingText/appendStepNode), nie przez
    // jednorazowy formatMessageText — startujemy od pustego kontenera.
    if (this.currentAssistantTextEl) this.currentAssistantTextEl.innerHTML = '';
    this.currentTextRunEl = null;
    this.currentTextRunText = '';
    this.stepElsByCallId = new Map();

    this.abortController = new AbortController();

    // Zapamiętujemy sesję, dla której ten strumień faktycznie został rozpoczęty —
    // użytkownik może przełączyć się na inną konwersację zanim strumień się zakończy,
    // a callbacki poniżej nie mogą wtedy nadpisywać stanu UI aktywnej w danej chwili sesji.
    const streamSessionId = this.activeSessionId;

    // 3. Strumieniowanie via SSE — tekst i kroki tool-callingu przychodzą w faktycznej
    // kolejności chronologicznej, więc dokładamy je do DOM w tej samej kolejności zamiast
    // rekonstruować przeplot po text_offset (to potrzebne tylko przy replayu z historii).
    await this.apiClient.streamChatMessage(
      streamSessionId,
      message,
      {
        onChunk: (chunk) => {
          if (this.activeSessionId !== streamSessionId) return;
          this.accumulatedText += chunk;
          this.appendStreamingText(chunk);
          this.scrollToBottom();
        },
        onToolStart: (evt) => {
          if (this.activeSessionId !== streamSessionId) return;
          this.appendStepNode(evt);
          this.scrollToBottom();
        },
        onToolResult: (evt) => {
          if (this.activeSessionId !== streamSessionId) return;
          this.updateStepNode(evt);
          this.scrollToBottom();
        },
        onError: (error) => {
          console.error('[ChatView] Błąd strumieniowania:', error);
          if (this.activeSessionId === streamSessionId) {
            this.accumulatedText += `\n\n[Błąd: ${error.message}]`;
            this.appendStreamingText(`\n\n[Błąd: ${error.message}]`);
          }
          this.finishStreaming(streamSessionId);
        },
        onComplete: () => {
          this.finishStreaming(streamSessionId);
        },
      },
      this.abortController.signal
    );
  }

  finishStreaming(streamSessionId = this.activeSessionId) {
    // Strumień mógł dobiec końca dla sesji, z której użytkownik już się przełączył —
    // wtedy nie dotykamy stanu UI aktualnie wyświetlanej sesji, jedynie odświeżamy listę.
    if (this.activeSessionId !== streamSessionId) {
      this.loadSessionsList();
      return;
    }
    this.stopPolling();
    this.finalizeCurrentTextRun();
    this.setGeneratingState(false);
    this.loadSessionsList();
  }

  // Dokłada fragment tekstu do bieżącego "przebiegu" tekstu (ciągłego odcinka tekstu/COT
  // między dwoma wywołaniami narzędzi, albo od początku tury do pierwszego wywołania).
  // Nowy przebieg tworzony jest leniwie — po `appendStepNode` bieżący przebieg jest
  // sfinalizowany i wyzerowany, więc kolejny chunk tekstu automatycznie zacznie nowy.
  appendStreamingText(chunkText) {
    if (!this.currentAssistantTextEl) return;
    if (!this.currentTextRunEl) {
      this.currentTextRunEl = document.createElement('div');
      this.currentTextRunEl.className = 'message-text-run';
      this.currentAssistantTextEl.appendChild(this.currentTextRunEl);
      this.currentTextRunText = '';
    }
    this.currentTextRunText += chunkText;
    this.renderTextRunIncremental(this.currentTextRunEl, this.currentTextRunText, true);
  }

  // Zamyka bieżący przebieg tekstu (usuwa kursor streamowania, domyka blok myślenia jeśli
  // otwarty) — wołane przed dołożeniem node'a kroku i na końcu całej tury.
  finalizeCurrentTextRun() {
    if (this.currentTextRunEl) {
      this.renderTextRunIncremental(this.currentTextRunEl, this.currentTextRunText, false);
    }
  }

  // Renderuje pojedynczy przebieg tekstu przyrostowo do już istniejącego elementu DOM,
  // zachowując stan rozwinięcia bloku myślenia (`data-open`) między wywołaniami zamiast
  // resetować go przy każdym tokenie — identyczna logika jak dawne `updateAssistantStreamingText`,
  // tylko skopowana do jednego przebiegu zamiast całej wiadomości.
  renderTextRunIncremental(element, text, isStreaming) {
    const thinkStart = text.indexOf('<think>');
    let thinkHtml = '';
    let restText = text;

    if (thinkStart !== -1) {
      const thinkEnd = text.indexOf('</think>');
      let rawThink = '';
      if (thinkEnd !== -1) {
        rawThink = text.substring(thinkStart + 7, thinkEnd);
        restText = text.substring(thinkEnd + 8);
      } else {
        rawThink = text.substring(thinkStart + 7);
        restText = '';
      }

      const escapedThink = this.escapeHtml(rawThink.trim()).replace(/\n/g, '<br/>');
      const isThinkingDone = thinkEnd !== -1;
      const statusTitle = !isThinkingDone ? 'Regis myśli...' : 'Przemyślenia Agenta';

      const existingBlock = element.querySelector('.chat-thinking-block');
      if (existingBlock) {
        const contentEl = existingBlock.querySelector('.thinking-content');
        const titleEl = existingBlock.querySelector('.thinking-title-text');

        if (contentEl && contentEl.innerHTML !== escapedThink) {
          contentEl.innerHTML = escapedThink;
        }
        if (titleEl && titleEl.textContent !== statusTitle) {
          titleEl.textContent = statusTitle;
        }
        if (isThinkingDone && existingBlock.dataset.open === 'true') {
          existingBlock.dataset.open = 'false';
        }
      } else {
        thinkHtml = `<div class="chat-collapsible chat-thinking-block" data-open="true"><div class="thinking-summary">${Icons.Sparkles()}<span class="thinking-title-text">${statusTitle}</span><span class="thinking-chevron">${Icons.ChevronRight()}</span></div><div class="thinking-content-wrapper"><div class="thinking-content-inner"><div class="thinking-content">${escapedThink}</div></div></div></div>`;
      }
    }

    const formattedRest = this.formatRestContent(restText);
    const cursorHtml = isStreaming ? '<span class="streaming-cursor"></span>' : '';

    const existingBlock = element.querySelector('.chat-thinking-block');
    if (existingBlock) {
      let restContainer = element.querySelector('.message-rest-content');
      if (!restContainer) {
        restContainer = document.createElement('div');
        restContainer.className = 'message-rest-content';
        element.appendChild(restContainer);
      }
      restContainer.innerHTML = formattedRest + cursorHtml;
    } else {
      element.innerHTML = thinkHtml + `<div class="message-rest-content">${formattedRest}${cursorHtml}</div>`;
    }
  }

  // Dołącza node kroku wywołania narzędzia na koniec bieżącej wiadomości assistant, w stanie
  // "running" — finalizuje wcześniejszy przebieg tekstu, żeby kolejność DOM odzwierciedlała
  // faktyczną kolejność zdarzeń SSE.
  appendStepNode(evt) {
    if (!this.currentAssistantTextEl) return;
    this.finalizeCurrentTextRun();

    const step = { callId: evt.call_id, name: evt.name, arguments: evt.arguments, content: null, isError: null };
    const wrapper = document.createElement('div');
    wrapper.innerHTML = this.renderStepNode(step);
    const stepEl = wrapper.firstElementChild;
    this.currentAssistantTextEl.appendChild(stepEl);
    this.stepElsByCallId.set(evt.call_id, stepEl);

    this.currentTextRunEl = null;
    this.currentTextRunText = '';
  }

  // Aktualizuje istniejący node kroku po nadejściu wyniku (status running -> done/error).
  updateStepNode(evt) {
    const stepEl = this.stepElsByCallId.get(evt.call_id);
    if (!stepEl) return;

    const status = evt.is_error ? 'error' : 'done';
    stepEl.classList.remove('step-running');
    stepEl.classList.add(`step-${status}`);

    const iconEl = stepEl.querySelector('.step-icon');
    if (iconEl) iconEl.innerHTML = evt.is_error ? Icons.AlertCircle() : Icons.CheckCircle2();

    const contentEl = stepEl.querySelector('.thinking-content');
    if (contentEl && evt.content) {
      const argsEl = contentEl.querySelector('.step-args');
      const argsHtml = argsEl ? argsEl.outerHTML : '';
      contentEl.innerHTML = `${argsHtml}<div class="step-result">${this.escapeHtml(evt.content)}</div>`;
    }
  }

  // Buduje HTML pojedynczego node'a kroku — reużywana zarówno przy dokładaniu na żywo
  // (appendStepNode, status zawsze "running" bo isError jeszcze null), jak i przy replayu
  // z historii (status wynika wprost z zapisanego isError).
  renderStepNode(step) {
    const status = step.isError === null || step.isError === undefined ? 'running' : step.isError ? 'error' : 'done';
    const icon = status === 'running' ? Icons.Puzzle() : status === 'error' ? Icons.AlertCircle() : Icons.CheckCircle2();
    const title = this.humanizeToolName(step.name);
    const argsHtml =
      step.arguments && Object.keys(step.arguments).length
        ? `<pre class="step-args">${this.escapeHtml(JSON.stringify(step.arguments, null, 2))}</pre>`
        : '';
    const contentHtml = step.content ? `<div class="step-result">${this.escapeHtml(step.content)}</div>` : '';

    return `<div class="chat-collapsible chat-collapsible-step step-${status}" data-open="false" data-call-id="${this.escapeHtml(step.callId || '')}">
      <div class="thinking-summary step-summary"><span class="step-icon">${icon}</span><span class="thinking-title-text">${this.escapeHtml(title)}</span><span class="thinking-chevron">${Icons.ChevronRight()}</span></div>
      <div class="thinking-content-wrapper"><div class="thinking-content-inner"><div class="thinking-content">${argsHtml}${contentHtml}</div></div></div>
    </div>`;
  }

  // Mapuje nazwę narzędzia na czytelny tytuł node'a ("get_time" -> "Get time").
  humanizeToolName(name) {
    if (!name) return 'Narzędzie';
    const short = name.includes('.') ? name.split('.').pop() : name;
    return short.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  }

  // Łączy płaskie pary wpisów `tool_call`+`tool_result` (ten sam call_id) z
  // `metadata.steps` historii w jeden obiekt kroku — ścieżka live tego nie potrzebuje,
  // bo `stepElsByCallId` już buduje się scalone przez appendStepNode/updateStepNode.
  mergeStepPairs(rawSteps) {
    const byId = new Map();
    for (const s of rawSteps) {
      const existing = byId.get(s.call_id) || {
        callId: s.call_id,
        name: s.name,
        textOffset: s.text_offset,
        arguments: null,
        content: null,
        isError: null,
      };
      if (s.type === 'tool_call') {
        existing.arguments = s.arguments;
        existing.textOffset = s.text_offset;
      } else if (s.type === 'tool_result') {
        existing.content = s.content;
        existing.isError = s.is_error;
      }
      byId.set(s.call_id, existing);
    }
    return [...byId.values()];
  }

  // Dzieli pełny tekst finalnej odpowiedzi na segmenty tekst/krok wg `textOffset` zapisanego
  // przy każdym kroku — potrzebne tylko przy replayu z historii, gdzie nie mamy naturalnej
  // kolejności zdarzeń SSE, tylko płaski tekst + listę kroków.
  buildSegments(text, steps) {
    const sorted = [...steps].sort((a, b) => a.textOffset - b.textOffset);
    const segments = [];
    let cursor = 0;
    for (const step of sorted) {
      const offset = Math.min(Math.max(step.textOffset, 0), text.length);
      if (offset > cursor) {
        segments.push({ kind: 'text', content: text.slice(cursor, offset) });
        cursor = offset;
      }
      segments.push({ kind: 'step', step });
    }
    if (cursor < text.length) {
      segments.push({ kind: 'text', content: text.slice(cursor) });
    }
    return segments;
  }

  // Buduje statyczny HTML całej wiadomości assistant z historii, przeplatając segmenty
  // tekstu (przez formatMessageText — obsługa <think>) z node'ami kroków.
  renderAssistantHistoryHtml(content, rawSteps) {
    const steps = this.mergeStepPairs(rawSteps || []);
    if (!steps.length) return this.formatMessageText(content);
    const segments = this.buildSegments(content, steps);
    return segments
      .map((seg) => {
        if (seg.kind === 'step') return this.renderStepNode(seg.step);
        return `<div class="message-text-run">${this.formatMessageText(seg.content)}</div>`;
      })
      .join('');
  }

  formatRestContent(restText) {
    if (!restText) return '';
    const escapedContent = this.escapeHtml(restText.trim()).replace(/\n/g, '<br/>');
    return escapedContent
      .replace(/```([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
      .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
  }

  async stopGeneration() {
    this.stopPolling();
    if (this.abortController) {
      this.abortController.abort();
    }
    await this.apiClient.cancelChatSession(this.activeSessionId);
    this.finishStreaming();
  }

  setGeneratingState(isGenerating) {
    this.isGenerating = isGenerating;
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
    const avatarHtml = isUser ? Icons.User() : Icons.Bot();
    const authorName = isUser ? 'Ty' : 'Regis OS';

    const hasSteps = !isUser && metadata && Array.isArray(metadata.steps) && metadata.steps.length > 0;
    const formattedContent = hasSteps
      ? this.renderAssistantHistoryHtml(content, metadata.steps)
      : this.formatMessageText(content) + (isStreaming ? '<span class="streaming-cursor"></span>' : '');

    if (isUser) {
      row.innerHTML = `
        <div class="message-bubble bubble-user">
          <div class="message-text">${formattedContent}</div>
        </div>
      `;
    } else {
      row.innerHTML = `
        <div class="message-avatar avatar-agent">${avatarHtml}</div>
        <div class="message-body">
          <div class="message-author">${authorName}</div>
          <div class="message-bubble bubble-agent">
            <div class="message-text">${formattedContent}</div>
          </div>
        </div>
      `;
    }

    container.appendChild(row);
    return row;
  }

  formatMessageText(text) {
    if (!text) return '';

    let content = text;
    let thinkHtml = '';

    // Sprawdzamy czy w tekście znajduje się tag <think>
    const thinkStart = content.indexOf('<think>');
    if (thinkStart !== -1) {
      const thinkEnd = content.indexOf('</think>');
      let rawThink = '';
      let restText = '';

      if (thinkEnd !== -1) {
        rawThink = content.substring(thinkStart + 7, thinkEnd);
        restText = content.substring(thinkEnd + 8);
      } else {
        // Strumieniowany, niezamknięty blok <think>
        rawThink = content.substring(thinkStart + 7);
        restText = '';
      }

      const escapedThink = this.escapeHtml(rawThink.trim()).replace(/\n/g, '<br/>');
      const isStreaming = thinkEnd === -1;
      const statusTitle = isStreaming ? 'Regis myśli...' : 'Przemyślenia Agenta';

      thinkHtml = `<div class="chat-collapsible chat-thinking-block" data-open="${isStreaming ? 'true' : 'false'}"><div class="thinking-summary">${Icons.Sparkles()}<span class="thinking-title-text">${statusTitle}</span><span class="thinking-chevron">${Icons.ChevronRight()}</span></div><div class="thinking-content-wrapper"><div class="thinking-content-inner"><div class="thinking-content">${escapedThink}</div></div></div></div>`;
      content = restText;
    }

    const formattedContent = this.formatRestContent(content);
    return thinkHtml + `<div class="message-rest-content">${formattedContent}</div>`;
  }

  scrollToBottom(force = false) {
    if (force || !this.userHasScrolledUp) {
      const container = document.getElementById('chat-messages-container');
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}
