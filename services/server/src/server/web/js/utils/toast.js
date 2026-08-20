import { escapeHtml } from './dom.js';

/**
 * Toast w prawym górnym rogu — wspólny dla wszystkich widoków (dawniej
 * zduplikowany niezależnie w kilku miejscach).
 */
export function showToast(message, type = 'success') {
  let toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement('div');
  toast.className = `toast-notification toast-${type}`;
  toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-leaving');
    setTimeout(() => toast.remove(), 200);
  }, 3000);
}
