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
    this.userHasScrolledUp = false;
    this.pollInterval = null;
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

      container.addEventListener('click', (e) => {
        const summary = e.target.closest('.thinking-summary');
        if (!summary) return;

        const details = summary.closest('.chat-thinking-block');
        if (!details) return;

        if (details.open) {
          e.preventDefault();

          if (details._closingTimer) {
            clearTimeout(details._closingTimer);
            details._closingTimer = null;
          }

          if (details.classList.contains('is-closing')) {
            details.classList.remove('is-closing');
            return;
          }

          details.classList.add('is-closing');
          details._closingTimer = setTimeout(() => {
            details.removeAttribute('open');
            details.classList.remove('is-closing');
            details._closingTimer = null;
          }, 300);
        } else {
          if (details.classList.contains('is-closing')) {
            details.classList.remove('is-closing');
          }
        }
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

      document.addEventListener('click', (e) => {
        if (!popover.classList.contains('hidden')) {
          if (!popover.contains(e.target) && !triggerBtn.contains(e.target)) {
            popover.classList.add('hidden');
            triggerBtn.classList.remove('active');
          }
        }
      });
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

  showCustomConfirm(msg, onConfirm) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    if (!overlay || !content) return;
    
    content.innerHTML = `
      <div class="modal-header">
        <h3 class="modal-title">Potwierdzenie</h3>
        <button class="btn-close-corner" id="btn-close-modal">×</button>
      </div>
      <p style="margin-bottom: 20px; font-size: 0.95rem; color: var(--text-secondary);">${msg}</p>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-subtle" id="btn-cancel-modal">Anuluj</button>
        <button class="btn btn-primary" style="background-color: var(--accent-danger); border-color: var(--accent-danger);" id="btn-confirm-modal">Usuń</button>
      </div>
    `;
    
    overlay.classList.remove('hidden');
    
    const closeModal = () => {
      overlay.classList.add('hidden');
    };
    
    document.getElementById('btn-close-modal').addEventListener('click', closeModal);
    document.getElementById('btn-cancel-modal').addEventListener('click', closeModal);
    document.getElementById('btn-confirm-modal').addEventListener('click', () => {
      onConfirm();
      closeModal();
    });
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
          if (this.currentAssistantTextEl) {
            this.updateAssistantStreamingText(this.currentAssistantTextEl, this.accumulatedText, res.is_generating);
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
        const row = this.appendMessageElement(msg.role, msg.content, msg.timestamp, isStreamingMsg);
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

    this.abortController = new AbortController();

    // 3. Strumieniowanie via SSE
    await this.apiClient.streamChatMessage(
      this.activeSessionId,
      message,
      null,
      (chunk) => {
        this.accumulatedText += chunk;
        if (this.currentAssistantTextEl) {
          this.updateAssistantStreamingText(this.currentAssistantTextEl, this.accumulatedText, true);
        }
        this.scrollToBottom();
      },
      (error) => {
        console.error('[ChatView] Błąd strumieniowania:', error);
        if (this.currentAssistantTextEl) {
          this.updateAssistantStreamingText(this.currentAssistantTextEl, this.accumulatedText + `\n\n[Błąd: ${error.message}]`, false);
        }
        this.finishStreaming();
      },
      () => {
        this.finishStreaming();
      },
      this.abortController.signal
    );
  }

  finishStreaming() {
    this.stopPolling();
    if (this.currentAssistantTextEl) {
      this.updateAssistantStreamingText(this.currentAssistantTextEl, this.accumulatedText, false);
    }
    this.setGeneratingState(false);
    this.loadSessionsList();
  }

  updateAssistantStreamingText(element, text, isStreaming = false) {
    if (!element) return;

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
      } else {
        thinkHtml = `<details class="chat-thinking-block" ${!isThinkingDone ? 'open' : ''}><summary class="thinking-summary">${Icons.Sparkles()}<span class="thinking-title-text">${statusTitle}</span><span class="thinking-chevron">${Icons.ChevronRight()}</span></summary><div class="thinking-wrapper"><div class="thinking-content">${escapedThink}</div></div></details>`;
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

  appendMessageElement(role, content, timestamp, isStreaming = false) {
    const container = document.getElementById('chat-messages-container');
    if (!container) return null;

    const row = document.createElement('div');
    row.className = `chat-message-row ${role === 'user' ? 'row-user' : 'row-agent'}`;

    const isUser = role === 'user';
    const avatarHtml = isUser ? Icons.User() : Icons.Bot();
    const authorName = isUser ? 'Ty' : 'Regis OS';

    const formattedContent = this.formatMessageText(content) + (isStreaming ? '<span class="streaming-cursor"></span>' : '');

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

      thinkHtml = `<details class="chat-thinking-block" ${isStreaming ? 'open' : ''}><summary class="thinking-summary">${Icons.Sparkles()}<span class="thinking-title-text">${statusTitle}</span><span class="thinking-chevron">${Icons.ChevronRight()}</span></summary><div class="thinking-wrapper"><div class="thinking-content">${escapedThink}</div></div></details>`;
      content = restText;
    }

    const formattedRest = this.formatRestContent(content);
    return thinkHtml + `<div class="message-rest-content">${formattedRest}</div>`;
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
