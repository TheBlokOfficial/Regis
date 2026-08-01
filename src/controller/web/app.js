/**
 * Regis — Panel Kontrolny | app.js
 *
 * Punkt startowy — orchestruje inicjalizację modułów.
 * Nie zawiera logiki biznesowej.
 *
 * Graf zależności:
 *   app.js → renderer.js → state.js
 *                        → utils.js
 *          → api.js     → state.js
 *                        → renderer.js
 *                        → events.js → state.js
 *                                    → renderer.js
 *                                    → utils.js
 *                        → utils.js
 */

import { initClock }                       from './renderer.js';
import { init, connectSSE, sendNodeCommand } from './api.js';

// Eksponuj sendNodeCommand na window — wymagane przez event listenery kart węzłów w renderer.js
window.sendNodeCommand = sendNodeCommand;

initClock();
init();
connectSSE();
