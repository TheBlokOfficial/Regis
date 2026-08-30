import { Icons } from '../../icons.js';
import { renderSelectMarkup } from '../../components/select.js';
import { escapeHtml, escapeAttr } from '../../utils/dom.js';

/**
 * Czyste funkcje renderujące HTML widoku Czatu — wydzielone z `ChatView`, żeby oddzielić
 * szablon od logiki zdarzeń/sieci/stanu (wzorzec `renderXMarkup` z `components/select.js`).
 * Zero dostępu do `this`, zero side-effectów — tylko stringi.
 */

export function renderChatLayoutMarkup() {
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
        ${renderEmptyStateMarkup()}
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
                ${renderSelectMarkup('chat-model-switch', { placeholder: 'Ładowanie...', className: 'select--compact chat-model-select' })}
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

export function renderEmptyStateMarkup() {
  return `
    <div class="chat-empty-state" id="chat-empty-state">
      <div class="empty-state-icon" id="chat-empty-icon">${Icons.MessageSquare()}</div>
      <div class="empty-state-title">Jak mogę pomóc?</div>
      <div class="empty-state-desc">Jestem Regis. O co chcesz zapytać?</div>
    </div>
  `;
}

export function renderSessionRowMarkup(session, isActive, dateStr) {
  return `
    <div class="popover-session-row ${isActive ? 'active' : ''}" data-session-id="${escapeAttr(session.session_id)}">
      <div class="session-info">
        <span class="session-title" title="${escapeAttr(session.title)}">${escapeHtml(session.title)}</span>
        <span class="session-time">${dateStr ? dateStr : ''}</span>
      </div>
      <button class="session-delete-btn" data-session-id="${escapeAttr(session.session_id)}" title="Usuń konwersację">
        ${Icons.Trash2()}
      </button>
    </div>
  `;
}

export function renderUserMessageMarkup(formattedContent) {
  return `
    <div class="message-bubble bubble-user">
      <div class="message-text">${formattedContent}</div>
    </div>
  `;
}

export function renderAgentMessageMarkup(formattedContent) {
  // Bez awatara/nazwy nadawcy — jedyny agent w systemie, powtarzanie "Regis" przy
  // każdej turze nie niesie informacji (lewe wyrównanie już jednoznacznie odróżnia
  // agenta od usera, którego bąbelki są po prawej).
  return `
    <div class="message-body">
      <div class="message-bubble bubble-agent">
        <div class="message-text">${formattedContent}</div>
      </div>
    </div>
  `;
}
