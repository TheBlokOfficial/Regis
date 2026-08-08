/**
 * Regis — Panel Kontrolny | app.js
 *
 * Punkt startowy — orchestruje inicjalizację modułów.
 * Nie zawiera logiki biznesowej.
 */

import { initClock, renderCloudProvidersList } from './renderer.js';
import { init, connectSSE, sendNodeCommand } from './api.js';
import { initChat } from './chat.js';
import { initModals } from './modals.js';

window.sendNodeCommand = sendNodeCommand;

function initRouting() {
    const navButtons = document.querySelectorAll('.sidebar-nav .nav-btn');
    const viewSections = document.querySelectorAll('.view-section');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetView = btn.getAttribute('data-view');

            navButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            viewSections.forEach(section => {
                if (section.id === `view-${targetView}`) {
                    section.style.display = (targetView === 'chat' || targetView === 'logs') ? 'flex' : 'block';
                    section.classList.add('active');
                } else {
                    section.style.display = 'none';
                    section.classList.remove('active');
                }
            });
        });
    });
}

// ── Inicjalizacja Aplikacji ───────────────────────────────────────────────

initRouting();
initClock();
init();
connectSSE();
initChat();
initModals();
renderCloudProvidersList();
