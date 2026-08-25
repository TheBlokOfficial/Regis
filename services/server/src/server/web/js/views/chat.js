import { Icons } from '../icons.js';
import { initSelect } from '../components/select.js';
import { getSenderId } from '../sender_id.js';
import { showToast } from '../utils/toast.js';
import { StepRailRenderer } from './chat/step_rail.js';
import { renderChatLayoutMarkup, renderEmptyStateMarkup, renderUserMessageMarkup, renderAgentMessageMarkup } from './chat/chat_template.js';
import { createWatchChannel } from './chat/chat_watch_channel.js';
import { initSessionManager } from './chat/chat_session_manager.js';

/**
 * Moduł widoku "Czat z Agentem" - interfejs kontrolno-debugujący w Web Console Regis OS.
 *
 * Cienki "klej" spinający trzy wydzielone moduły: szablon HTML (`chat_template.js`), kanał
 * SSE obserwujący aktywną sesję (`chat_watch_channel.js`) i zarządzanie listą sesji/popoverem
 * (`chat_session_manager.js`). ChatView trzyma tylko stan bieżącej tury (streaming) i deleguje
 * resztę — dokładnie tak samo, jak renderowanie kroków ReAct już wcześniej zostało wydzielone
 * do `StepRailRenderer` (`./chat/step_rail.js`).
 */
export class ChatView {
  constructor() {
    this.apiClient = null;
    this.activeSessionId = 'session_default';
    this.isGenerating = false;
    this.currentAssistantMessageEl = null;
    this.currentAssistantTextEl = null;
    this.accumulatedText = '';
    this.stepRail = new StepRailRenderer();
    this.userHasScrolledUp = false;
    // Kanał obserwujący i menedżer sesji są tworzone raz (patrz `_ensureChannels`) i
    // przetrwają wielokrotne wizyty na zakładce Chat — ChatView jest instancją długożyjącą,
    // ale `render()`/`init()` uruchamiają się przy każdym przełączeniu (patrz tab_manager.js).
    this.watchChannel = null;
    this.sessionManager = null;
  }

  render() {
    return renderChatLayoutMarkup();
  }

  async init(apiClient) {
    this.apiClient = apiClient;
    this._ensureChannels();
    this.mountIcons();
    this.bindEvents();
    await this.loadActiveProviderInfo();
    await this.sessionManager.loadSessionsList();
    // Otwieramy kanał obserwujący PRZED wczytaniem historii, żeby zminimalizować okno,
    // w którym ewentualny token/zdarzenie mogłyby przepaść między snapshotem a subskrypcją.
    this.watchChannel.open(this.activeSessionId);
    await this.loadSessionHistory(this.activeSessionId);
    this.sessionManager.startWatch();
  }

  // Leniwa inicjalizacja "raz na zawsze" — apiClient nie jest znany w konstruktorze
  // (TabManager wstrzykuje go dopiero w init()), a oba moduły muszą przetrwać kolejne
  // wizyty na zakładce (patrz komentarz w konstruktorze).
  _ensureChannels() {
    if (!this.watchChannel) {
      this.watchChannel = createWatchChannel(this.apiClient, {
        onUserMessage: (sessionId, content) => this._onWatchUserMessage(sessionId, content),
        onChunk: (sessionId, chunk, kind) => this._onWatchChunk(sessionId, chunk, kind),
        onToolStart: (sessionId, evt) => this._onWatchToolStart(sessionId, evt),
        onToolResult: (sessionId, evt) => this._onWatchToolResult(sessionId, evt),
        onDone: (sessionId) => this._onWatchDone(sessionId),
        onError: (sessionId, err) => this._onWatchError(sessionId, err),
        onCancelled: (sessionId) => this._onWatchCancelled(sessionId),
      });
    }
    if (!this.sessionManager) {
      this.sessionManager = initSessionManager({
        apiClient: this.apiClient,
        getActiveSessionId: () => this.activeSessionId,
        setActiveSessionId: (id) => {
          this.activeSessionId = id;
        },
        onSessionSwitch: async (sessionId) => {
          this.watchChannel.open(sessionId);
          await this.loadSessionHistory(sessionId);
        },
      });
    }
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

    this.sessionManager.bindPopoverEvents();
  }

  /**
   * Szybka zmiana presetu LLM wprost z czatu — dotąd trzeba było wejść w Ustawienia.
   *
   * **Przełącza globalnie aktywny preset**, nie „model tej rozmowy": w systemie jest
   * dokładnie jeden aktywny backend (`LLMRouter`, `server/ai/llm/router.py`), z którego
   * korzystają też satelity głosowe. Model per sesja wymagałby rozwiązywania dostawcy
   * per turę w kernelu — osobna, dużo większa zmiana.
   *
   * Dawna zielona kropka obok tej etykiety **została usunięta**: była zawsze zielona,
   * niezależnie od czegokolwiek. Uczciwy wskaźnik stanu dostawcy wymagałby realnego
   * pingu (`check_health()` istnieje, ale dla dostawców chmurowych sprawdza wyłącznie,
   * czy klucz API jest niepusty), więc dekoracja udająca status poszła precz.
   */
  async loadActiveProviderInfo() {
    if (!this.apiClient) return;

    let providers = [];
    let activeId = null;
    try {
      const data = await this.apiClient.getLLMProviders();
      providers = data?.providers || [];
      activeId = providers.find((p) => p.is_active)?.id ?? null;
    } catch {
      // Brak połączenia z serwerem — pusty picker z czytelnym placeholderem.
    }

    // Nazwa presetu jest etykietą, identyfikator modelu doprecyzowaniem obok — stąd
    // `hint`, renderowany mniejszym, wyszarzonym krojem (`components/select.js`).
    // Presety utworzone przed wprowadzeniem edytowalnych nazw mają nazwę RÓWNĄ nazwie
    // modelu; wtedy hint jest pomijany, żeby nie pokazywać tego samego dwa razy.
    const toOption = (p) => {
      const model = p.options?.model || '';
      return { value: p.id, label: p.name, hint: model && model !== p.name ? model : '' };
    };

    this.modelSwitch = initSelect({
      idPrefix: 'chat-model-switch',
      options: providers.map(toOption),
      value: activeId ?? '',
      placeholder: providers.length ? 'Wybierz preset' : 'Brak presetów',
      onChange: async (providerId) => {
        if (!providerId || providerId === activeId) return;
        try {
          await this.apiClient.setActiveLLMProvider(providerId);
          activeId = providerId;
          showToast('Przełączono preset LLM.', 'success');
        } catch (err) {
          this.modelSwitch?.setValue(activeId ?? '');
          showToast(`Nie udało się przełączyć presetu: ${err.message}`, 'error');
        }
      },
    });
  }

  // --------------------------------------------------------------------------------------
  // Zdarzenia kanału obserwującego (GET .../watch, SSE) — jedyne źródło renderowania
  // treści/streamingu. Mechanika połączenia (AbortController, reconnect) żyje w
  // `chat_watch_channel.js`; tu zostaje wyłącznie logika dotykająca DOM/stan tury, bo to
  // ona wymaga dostępu do `this.stepRail`/`this.activeSessionId` itd.
  // --------------------------------------------------------------------------------------

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

  _onWatchChunk(sessionId, chunk, kind = 'answer') {
    if (sessionId !== this.activeSessionId) return;
    // Rozumowanie ma własną ścieżkę renderowania i NIE wchodzi do `accumulatedText` —
    // ten bufor odzwierciedla treść odpowiedzi, względem której liczone są `text_offset`
    // kroków ReAct (patrz `server/agent/engine.py`).
    if (kind === 'reasoning') {
      this.stepRail.appendReasoningText(chunk);
      this.scrollToBottom();
      return;
    }
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
    this.sessionManager.loadSessionsList();
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
        container.innerHTML = renderEmptyStateMarkup();
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
      // Treść wraca prosto z backendu — w typowym przypadku (403, ta przeglądarka nie
      // jest jeszcze zarejestrowanym klientem) mówi wprost, co zrobić. Bez tego odmowa
      // wyglądała jak zniknięcie wiadomości: tekst wracał do pola bez żadnego powodu.
      showToast(err.message || 'Nie udało się wysłać wiadomości.', 'error');
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
      : this.stepRail.renderAssistantHistoryHtml(
          content,
          (metadata && metadata.steps) || [],
          (metadata && metadata.reasoning) || []
        ) + cursorHtml;

    row.innerHTML = isUser ? renderUserMessageMarkup(formattedContent) : renderAgentMessageMarkup(formattedContent);

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
