import { escapeHtml } from './utils/dom.js';

/**
 * Współdzielony modal potwierdzenia (zastępuje natywne window.confirm/alert),
 * oparty o istniejący kontener #modal-overlay/#modal-content.
 */
export function confirmModal({ title = 'Potwierdź akcję', message, confirmLabel = 'Tak', cancelLabel = 'Anuluj' } = {}) {
  return new Promise((resolve) => {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    if (!overlay || !content) {
      resolve(window.confirm(message));
      return;
    }

    content.classList.add('modal-content-sm');
    content.innerHTML = `
      <div class="modal-header">
        <h3 class="modal-title">${escapeHtml(title)}</h3>
      </div>
      <p class="modal-confirm-message">${escapeHtml(message)}</p>
      <div class="form-actions modal-confirm-actions">
        <button class="btn btn-primary" id="modal-confirm-yes">${escapeHtml(confirmLabel)}</button>
        <button class="btn btn-ghost" id="modal-confirm-no">${escapeHtml(cancelLabel)}</button>
      </div>
    `;

    overlay.classList.add('modal-entering');
    overlay.classList.remove('hidden');
    requestAnimationFrame(() => {
      requestAnimationFrame(() => overlay.classList.remove('modal-entering'));
    });

    let settled = false;
    const cleanup = (result) => {
      if (settled) return;
      settled = true;
      overlay.classList.add('modal-closing');
      window.removeEventListener('keydown', handleEsc);
      setTimeout(() => {
        overlay.classList.remove('modal-closing');
        overlay.classList.add('hidden');
        content.classList.remove('modal-content-sm');
        content.innerHTML = '';
      }, 180);
      resolve(result);
    };

    const handleEsc = (e) => {
      if (e.key === 'Escape') cleanup(false);
    };
    window.addEventListener('keydown', handleEsc);

    document.getElementById('modal-confirm-yes')?.addEventListener('click', () => cleanup(true));
    document.getElementById('modal-confirm-no')?.addEventListener('click', () => cleanup(false));
    overlay.addEventListener(
      'click',
      (e) => {
        if (e.target === overlay) cleanup(false);
      },
      { once: true }
    );
  });
}
