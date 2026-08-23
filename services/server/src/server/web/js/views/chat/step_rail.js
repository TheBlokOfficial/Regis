import { Icons } from '../../icons.js';
import { escapeHtml, escapeAttr } from '../../utils/dom.js';

/**
 * Silnik renderowania kroków ReAct (myślenie + wywołania narzędzi) w czacie —
 * wydzielony z `ChatView` (dawniej ~600 linii w jednej klasie). Odpowiada za
 * dwie ścieżki: (1) przyrostowe renderowanie na żywo w trakcie strumieniowania
 * (`appendStreamingText`/`appendStepNode`/`updateStepNode`), operujące na
 * węźle DOM przekazanym przez `reset()`; (2) statyczny replay z historii
 * (`renderAssistantHistoryHtml`), używany też przy formatowaniu wiadomości
 * `user` (`formatRestContent`).
 *
 * `ChatView` trzyma jedną długożyjącą instancję (`this.stepRail`) i deleguje
 * do niej wywołania streamingu/historii zamiast trzymać ten stan sama.
 */
export class StepRailRenderer {
  constructor() {
    this.isGenerating = false;
    this.currentAssistantTextEl = null;
    this.currentTextRunEl = null;
    this.currentTextRunText = '';
    this.currentThinkEl = null;
    this.currentThinkRawText = '';
    this.currentRailEl = null;
    this.currentRailGroupEl = null;
    this.pendingRunText = '';
    this.stepElsByCallId = new Map();
    // Surowe dane kroku per call_id — potrzebne do "awansu" już-wyrenderowanego pojedynczego
    // node'a na klaster (trzeba przerenderować jego treść w nowym, skondensowanym kształcie).
    this.stepDataByCallId = new Map();
  }

  /** Wołane na początku każdej nowej tury asystenta — zeruje stan przebiegu na żywo. */
  reset(assistantTextEl) {
    this.currentAssistantTextEl = assistantTextEl;
    this.currentTextRunEl = null;
    this.currentTextRunText = '';
    this.currentThinkEl = null;
    this.currentThinkRawText = '';
    this.currentRailEl = null;
    this.currentRailGroupEl = null;
    this.pendingRunText = '';
    this.stepElsByCallId = new Map();
    this.stepDataByCallId = new Map();
  }

  setGenerating(isGenerating) {
    this.isGenerating = isGenerating;
  }

  // --- Renderowanie na żywo: mały automat stanu -----------------------------------------
  // Trzy wzajemnie wykluczające się "tryby" bieżącego przebiegu: zwykły tekst
  // (currentTextRunEl), otwarty blok myślenia (currentThinkEl), albo żaden z nich (między
  // krokami). Kroki narzędzi (appendStepNode) i myślenie dokładają się do wspólnej szyny
  // (currentRailEl) — zamykanej dopiero przez kolejny fragment zwykłego tekstu.

  /**
   * Fragment ROZUMOWANIA modelu (`kind: 'reasoning'` w strumieniu). Rodzaj tokena
   * przychodzi dziś z serwera jako osobne pole (patrz `server/agent/llm.py::ReasoningChunk`),
   * więc nie ma tu czego zgadywać — dawniej ta sama informacja była odzyskiwana przez
   * parsowanie znaczników `<think>` wewnątrz strumienia tekstu.
   */
  appendReasoningText(chunkText) {
    if (!this.currentAssistantTextEl || !chunkText) return;
    // Rozumowanie przerywa bieżący przebieg zwykłego tekstu — kolejny fragment odpowiedzi
    // otworzy nowy przebieg pod szyną, dokładnie jak po kroku narzędzia.
    if (this.currentTextRunEl) {
      this.renderPlainTextRun(this.currentTextRunEl, this.currentTextRunText, false);
      this.currentTextRunEl = null;
      this.currentTextRunText = '';
    }
    this.pendingRunText = '';
    if (!this.currentThinkEl) {
      this.currentThinkRawText = '';
      this.startThinkRailItem();
    }
    this.currentThinkRawText += chunkText;
    this.updateThinkRailItemDom(this.currentThinkEl, this.currentThinkRawText, true);
  }

  appendStreamingText(chunkText) {
    if (!this.currentAssistantTextEl) return;

    // Pierwszy fragment odpowiedzi domyka otwarty blok myślenia — od tego momentu
    // rozumowanie tego przebiegu jest kompletne.
    if (this.currentThinkEl) {
      this.updateThinkRailItemDom(this.currentThinkEl, this.currentThinkRawText, false);
      this.currentThinkEl = null;
      this.currentThinkRawText = '';
    }

    if (this.currentTextRunEl) {
      this.currentTextRunText += chunkText;
      this.renderPlainTextRun(this.currentTextRunEl, this.currentTextRunText, true);
      return;
    }

    // Świeża granica (po kroku/myśleniu albo na starcie tury) — buforujemy bez dotykania
    // DOM, dopóki nie rozstrzygniemy, czy to sam biały znak (model często wstawia
    // pojedynczy "\n" między krokami pętli ReAct — to trzeba zignorować, inaczej fałszywie
    // przerywa sekwencję rail i np. "Analiza" traci linię łączącą), czy realny tekst.
    this.pendingRunText = (this.pendingRunText || '') + chunkText;
    if (this.pendingRunText.replace(/^\s+/, '') === '') return;

    // Realny tekst przerywa sekwencję rail.
    this.closeCurrentRail();
    this.currentTextRunEl = document.createElement('div');
    this.currentTextRunEl.className = 'message-text-run';
    this.currentAssistantTextEl.appendChild(this.currentTextRunEl);
    this.currentTextRunText = this.pendingRunText;
    this.pendingRunText = '';
    this.renderPlainTextRun(this.currentTextRunEl, this.currentTextRunText, true);
  }

  // Domyka cokolwiek jest aktualnie otwarte (zwykły tekst lub blok myślenia) — wołane przed
  // dołożeniem node'a kroku i na końcu całej tury.
  finalizeCurrentTextRun() {
    if (this.currentThinkEl) {
      this.updateThinkRailItemDom(this.currentThinkEl, this.currentThinkRawText, false);
      this.currentThinkEl = null;
      this.currentThinkRawText = '';
    }
    if (this.currentTextRunEl) {
      this.renderPlainTextRun(this.currentTextRunEl, this.currentTextRunText, false);
    }
    // Bufor oczekujący na rozstrzygnięcie (sam biały znak na granicy przebiegu) nigdy nie
    // trafił do DOM — po prostu go porzucamy.
    this.pendingRunText = '';
  }

  renderPlainTextRun(element, text, isStreaming) {
    const formatted = this.formatRestContent(text);
    const cursorHtml = isStreaming ? '<span class="streaming-cursor"></span>' : '';
    element.innerHTML = `<div class="message-rest-content">${formatted}${cursorHtml}</div>`;
  }

  // Leniwie tworzy zbiorczy, zwijalny nagłówek wraz z wewnętrzną kolumną-osią (.step-rail)
  // dla kolejnych node'ów myślenia/kroków. Zawsze startuje ZWINIĘTA (spójnie z resztą
  // drzewka, patrz renderRailGroupShell) — postęp w trakcie pracy widać w samym tekście
  // nagłówka ("Agent pracuje... · N kroków"), nie przez domyślne rozwinięcie.
  ensureRailWrapper() {
    if (!this.currentRailEl) {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = this.renderRailGroupShell();
      this.currentRailGroupEl = wrapper.firstElementChild;
      this.currentAssistantTextEl.appendChild(this.currentRailGroupEl);
      this.currentRailEl = this.currentRailGroupEl.querySelector('.step-rail');
    }
    return this.currentRailEl;
  }

  // Liczy SUROWE wywołania w szynie — klaster liczy się jako liczba wywołań w środku, nie
  // jako 1 — współdzielone przez updateRailGroupSummary (w toku) i closeCurrentRail (finał).
  computeRailCount(rail) {
    let count = 0;
    for (const child of rail.children) {
      count += child.classList.contains('rail-item-cluster') ? child.querySelectorAll('.cluster-call').length : 1;
    }
    return count;
  }

  // Zamyka bieżącą szynę — wołane, gdy realny tekst przerywa sekwencję albo tura się
  // kończy. Dwie rzeczy: (1) jeśli w szynie została dokładnie jedna jednostka (pojedynczy
  // node albo jeden klaster) — owijający nagłówek "N kroków" to zbędna ceremonia, więc
  // rozpakowujemy: zastępujemy .rail-group samym jej jedynym dzieckiem; (2) w przeciwnym
  // razie przełącza nagłówek z "Agent pracuje..." na finalny statyczny licznik (explicite,
  // nie przez `isGenerating` — w momencie wywołania z finishStreaming flaga jeszcze nie
  // spadła, patrz kolejność w finishStreaming). Nie wymusza już zwinięcia niezależnie od
  // stanu — grupa zostaje taka, jaką zostawił user (rozwinięta, jeśli zerknął w trakcie
  // pracy; nic nie znika mu spod ręki po zakończeniu, feedback: "chamsko zwijamy").
  closeCurrentRail() {
    if (this.currentRailGroupEl && this.currentRailEl) {
      if (this.currentRailEl.children.length === 1) {
        this.currentRailGroupEl.replaceWith(this.currentRailEl.children[0]);
      } else {
        const titleEl = this.currentRailGroupEl.querySelector('.thinking-title-text');
        if (titleEl) {
          const count = this.computeRailCount(this.currentRailEl);
          titleEl.textContent = `${count} ${this.pluralizeKroki(count)}`;
        }
      }
    }
    this.currentRailEl = null;
    this.currentRailGroupEl = null;
  }

  // Znajduje właściwy kontener treści zwijanego bloku — .rail-group-content-wrapper dla
  // grupy, .thinking-content-wrapper (zagnieżdżony w .rail-content) dla pojedynczego node'a
  // myślenia. Oba typy mają dokładnie jeden taki kontener na blok.
  getCollapsibleWrapper(block) {
    return (
      block.querySelector(':scope > .rail-group-content-wrapper') ||
      block.querySelector(':scope > .rail-content > .thinking-content-wrapper')
    );
  }

  // Otwiera/zamyka zwijany blok animując ZMIERZONĄ wysokość (scrollHeight), nie sztywny
  // limit (max-height: 2000px) — ten dawał nieliniową animację: rozwijanie "przecinało"
  // realną wysokość treści w ułamku czasu trwania przejścia (bo 100px z limitu 2000px to
  // 5% drogi), a zwijanie z 2000px w dół wyglądało na "opóźniony zapłon" (ruch widoczny
  // dopiero pod koniec animacji, gdy limit spadnie poniżej realnej wysokości). Zmierzona
  // wysokość animuje się proporcjonalnie 1:1 do rzeczywistej treści, niezależnie od jej
  // długości — i działa niezależnie od zagnieżdżonego flex w środku (w przeciwieństwie do
  // triku grid-template-rows:1fr, który się na tym wywracał).
  setCollapsibleOpen(block, open, { animate = true } = {}) {
    const wrapper = this.getCollapsibleWrapper(block);
    if (!wrapper) {
      block.dataset.open = open ? 'true' : 'false';
      return;
    }
    const isCurrentlyOpen = block.dataset.open === 'true';
    if (open === isCurrentlyOpen) return;

    // Sprząta nasłuch z ewentualnego POPRZEDNIEGO, przerwanego przejścia (np. szybkie
    // kolejne kliknięcia zanim animacja się skończyła) — CSS nie emituje `transitionend`
    // dla przerwanego przejścia, więc bez tego stary listener zostawałby zawieszony i
    // odpaliłby się przy okazji NASTĘPNEGO przejścia na tym elemencie, cofając jego efekt
    // (obserwowany objaw: zwinięcie animuje się poprawnie, po czym natychmiast "teleportuje"
    // z powrotem na `auto`, bo to stary listener z przerwanego wcześniej otwarcia).
    if (wrapper._collapsibleTransitionHandler) {
      wrapper.removeEventListener('transitionend', wrapper._collapsibleTransitionHandler);
      wrapper._collapsibleTransitionHandler = null;
    }

    if (open) {
      // Zmierz PRZED zmianą data-open — inaczej reguła CSS [data-open="true"]{height:auto}
      // zdąży się aktywować, a odczyt scrollHeight (który wymusza synchroniczny layout)
      // "zamrozi" element już na pełnej wysokości, zanim JS ustawi punkt startowy animacji.
      // Docelowa wysokość w px wyszłaby wtedy identyczna z tym, co element już renderuje —
      // brak realnej zmiany, więc przejście w ogóle by się nie odpaliło (obserwowany objaw:
      // pierwsze rozwinięcie bez żadnej animacji, natychmiastowe).
      const target = wrapper.scrollHeight;
      block.dataset.open = 'true';
      if (!animate) {
        wrapper.style.height = 'auto';
        return;
      }
      wrapper.style.height = `${target}px`;
      const onEnd = (ev) => {
        if (ev.propertyName !== 'height' || ev.target !== wrapper) return;
        wrapper.style.height = 'auto';
        wrapper.removeEventListener('transitionend', onEnd);
        wrapper._collapsibleTransitionHandler = null;
      };
      wrapper._collapsibleTransitionHandler = onEnd;
      wrapper.addEventListener('transitionend', onEnd);
    } else {
      if (!animate) {
        wrapper.style.height = '0px';
        block.dataset.open = 'false';
        return;
      }
      const current = wrapper.scrollHeight;
      wrapper.style.height = `${current}px`;
      // Wymuś reflow, żeby przeglądarka zarejestrowała jawną wysokość PRZED zmianą na 0 —
      // bez tego przejście nie miałoby od czego animować (nie da się animować z "auto").
      void wrapper.offsetHeight;
      wrapper.style.height = '0px';
      block.dataset.open = 'false';
    }
  }

  // Bez ikony — sam tekst + chevron, celowo stonowany (ciemniejszy niż node'y w środku),
  // żeby nagłówek grupy nie wyglądał jak "kolejny node" tej samej rangi co elementy, które
  // owija (feedback: ikonka na headerze myliła hierarchię).
  // Zawsze startuje ZWINIĘTA (spójnie z resztą drzewka) — nagłówek w trakcie pracy pokazuje
  // status zamiast rozwijać szczegóły (feedback: "pokazujemy w trakcie pracy, potem chamsko
  // zwijamy" — usuwamy niekonsekwencję u źródła, nie pokazując nic domyślnie od początku).
  renderRailGroupShell() {
    return `<div class="rail-group chat-collapsible" data-open="false">
      <div class="thinking-summary rail-group-summary">
        <span class="thinking-title-text">Agent pracuje...</span>
        <span class="thinking-chevron">${Icons.ChevronRight()}</span>
      </div>
      <div class="rail-group-content-wrapper"><div class="thinking-content-inner">
        <div class="step-rail"></div>
      </div></div>
    </div>`;
  }

  // Przelicza licznik nagłówka grupy na podstawie aktualnego stanu node'ów w szynie —
  // wołane po każdym dołożeniu/aktualizacji node'a. W trakcie generowania nagłówek pokazuje
  // "Agent pracuje... · N kroków" (finalny statyczny napis "N kroków" ustawia dopiero
  // closeCurrentRail). Kolor nagłówka zmienia się tylko przy błędzie/stanie mieszanym w
  // którymkolwiek elemencie (jedyny realny akcent koloru w całym drzewku).
  updateRailGroupSummary() {
    if (!this.currentRailGroupEl || !this.currentRailEl) return;
    const count = this.computeRailCount(this.currentRailEl);
    const hasError = [...this.currentRailEl.children].some(
      (child) => child.classList.contains('step-error') || child.classList.contains('cluster-error') || child.classList.contains('cluster-mixed')
    );
    const titleEl = this.currentRailGroupEl.querySelector('.thinking-title-text');
    if (titleEl) {
      const countLabel = `${count} ${this.pluralizeKroki(count)}`;
      titleEl.textContent = this.isGenerating ? `Agent pracuje... · ${countLabel}` : countLabel;
    }
    this.currentRailGroupEl.classList.toggle('group-error', hasError);
  }

  // Polska odmiana "krok": 1 krok, 2-4 kroki (poza 12-14), pozostałe kroków.
  pluralizeKroki(n) {
    if (n === 1) return 'krok';
    const lastDigit = n % 10;
    const lastTwo = n % 100;
    if (lastDigit >= 2 && lastDigit <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return 'kroki';
    return 'kroków';
  }

  startThinkRailItem() {
    const rail = this.ensureRailWrapper();
    const wrapper = document.createElement('div');
    wrapper.innerHTML = this.renderThinkRailItem('', true);
    this.currentThinkEl = wrapper.firstElementChild;
    rail.appendChild(this.currentThinkEl);
    this.updateRailGroupSummary();
  }

  // Aktualizuje istniejący node bloku myślenia w miejscu (zachowuje `data-open`, jaki by
  // nie był — jeśli user ręcznie rozwinął w trakcie myślenia, ma zostać rozwinięty, NIE
  // domykamy tego już automatycznie po zakończeniu, żeby nie zabierać spod ręki tego, co
  // user właśnie oglądał — feedback: "pokazujemy w trakcie pracy, potem chamsko zwijamy").
  updateThinkRailItemDom(el, content, isStreaming) {
    const escaped = escapeHtml(content.trim()).replace(/\n/g, '<br/>');
    const title = isStreaming ? 'Analizuję...' : 'Analiza';
    const contentEl = el.querySelector('.thinking-content');
    const titleEl = el.querySelector('.thinking-title-text');
    if (contentEl && contentEl.innerHTML !== escaped) contentEl.innerHTML = escaped;
    if (titleEl && titleEl.textContent !== title) titleEl.textContent = title;
  }

  // Dołącza node kroku wywołania narzędzia na koniec bieżącej szyny, w stanie "running" —
  // finalizuje wcześniejszy przebieg tekstu/myślenia, żeby kolejność DOM odzwierciedlała
  // faktyczną kolejność zdarzeń SSE. Nie zamyka szyny — kolejny krok/myślenie może dołączyć
  // do tej samej sekwencji.
  //
  // Jeśli poprzedni element szyny to TAKŻE krok narzędzia (bez przerwy w postaci myślenia/
  // tekstu) — zlepiamy w klaster zamiast dokładać kolejny pełny node (feedback: 7 osobnych
  // nagłówków+ikon dla 7 kolejnych wywołań było zbyt rozjechane wizualnie).
  appendStepNode(evt) {
    if (!this.currentAssistantTextEl) return;
    this.finalizeCurrentTextRun();
    this.currentTextRunEl = null;
    this.currentTextRunText = '';

    const rail = this.ensureRailWrapper();
    const step = { callId: evt.call_id, name: evt.name, arguments: evt.arguments, content: null, isError: null };
    this.stepDataByCallId.set(step.callId, step);

    const lastChild = rail.lastElementChild;
    if (lastChild && lastChild.classList.contains('rail-item-cluster')) {
      this.addCallToClusterDom(lastChild, step);
    } else if (lastChild && lastChild.classList.contains('rail-item-step')) {
      this.promoteStepToCluster(lastChild, step);
    } else {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = this.renderStepNode(step);
      const stepEl = wrapper.firstElementChild;
      rail.appendChild(stepEl);
      this.stepElsByCallId.set(step.callId, stepEl);
    }
    this.updateRailGroupSummary();
  }

  // Zamienia już-wyrenderowany pojedynczy node kroku (lastStepEl) na klaster dwuelementowy
  // zawierający jego dane + nowy krok — w tym samym miejscu w DOM (replaceWith).
  promoteStepToCluster(lastStepEl, newStep) {
    const priorCallId = lastStepEl.dataset.callId;
    const priorStep = this.stepDataByCallId.get(priorCallId) || { callId: priorCallId, name: '', arguments: null, content: null, isError: null };
    const wrapper = document.createElement('div');
    wrapper.innerHTML = this.renderClusterNode([priorStep, newStep]);
    const clusterEl = wrapper.firstElementChild;
    lastStepEl.replaceWith(clusterEl);
    this.stepElsByCallId.set(priorCallId, clusterEl.querySelector(`[data-call-id="${CSS.escape(priorCallId || '')}"]`));
    this.stepElsByCallId.set(newStep.callId, clusterEl.querySelector(`[data-call-id="${CSS.escape(newStep.callId || '')}"]`));
  }

  // Dokłada kolejne wywołanie do już istniejącego klastra i przelicza jego ikonę/tytuł.
  addCallToClusterDom(clusterEl, step) {
    const body = clusterEl.querySelector('.rail-item-body');
    const wrapper = document.createElement('div');
    wrapper.innerHTML = this.renderClusterCallHtml(step);
    const callEl = wrapper.firstElementChild;
    body.appendChild(callEl);
    this.stepElsByCallId.set(step.callId, callEl);
    this.updateClusterAggregate(clusterEl);
  }

  // Przelicza ikonę/tytuł klastra na podstawie aktualnego stanu wszystkich jego wywołań
  // (stepDataByCallId) — wołane po dołożeniu nowego wywołania i po nadejściu każdego wyniku.
  updateClusterAggregate(clusterEl) {
    const callIds = [...clusterEl.querySelectorAll('.cluster-call')].map((el) => el.dataset.callId);
    const calls = callIds.map((id) => this.stepDataByCallId.get(id)).filter(Boolean);
    const status = this.computeClusterStatus(calls);
    const iconEl = clusterEl.querySelector('.rail-icon');
    if (iconEl) iconEl.innerHTML = this.renderClusterIcon(status);
    clusterEl.className = `rail-item rail-item-cluster cluster-${status}`;
    const titleEl = clusterEl.querySelector('.thinking-title-text');
    if (titleEl) titleEl.textContent = `Wywołano ${this.pluralizeNarzedzia(calls.length)}: ${calls.length}`;
  }

  // Aktualizuje istniejący node/wpis kroku po nadejściu wyniku (status running -> done/error)
  // — rozgałęzia się po tym, czy zapisany element to pojedynczy .rail-item-step (jak dawniej)
  // czy .cluster-call wewnątrz klastra (bez własnej ikony — tylko kolor wyniku tej linii).
  updateStepNode(evt) {
    const el = this.stepElsByCallId.get(evt.call_id);
    if (!el) return;

    const stepData = this.stepDataByCallId.get(evt.call_id);
    if (stepData) {
      stepData.content = evt.content;
      stepData.isError = evt.is_error;
    }

    if (el.classList.contains('cluster-call')) {
      const resultEl = el.querySelector('.cluster-call-result');
      if (resultEl) {
        resultEl.textContent = evt.content;
        resultEl.classList.remove('step-result-pending');
        resultEl.classList.toggle('is-error', !!evt.is_error);
      }
      const clusterEl = el.closest('.rail-item-cluster');
      if (clusterEl) this.updateClusterAggregate(clusterEl);
    } else {
      const status = evt.is_error ? 'error' : 'done';
      el.classList.remove('step-running');
      el.classList.add(`step-${status}`);

      const iconEl = el.querySelector('.rail-icon');
      if (iconEl) iconEl.innerHTML = evt.is_error ? Icons.AlertCircle() : Icons.CheckCircle2();

      const contentEl = el.querySelector('.rail-item-body');
      if (contentEl) {
        contentEl.innerHTML = this.renderStepBody({ content: evt.content, isError: evt.is_error });
      }
    }
    this.updateRailGroupSummary();
  }

  // --- Budowniczy wspólnego szkieletu node'a rail (myślenie + kroki) --------------------

  // Kroki narzędzi (collapsible=false, domyślnie) są płaskie — wynik to zwykle jedna krótka
  // linijka, więc osobny poziom rozwijania byłby zbędnym tarciem (feedback: dwa poziomy
  // rozwijania, grupa + każdy node z osobna, były nieprzyjemne). Bloki "Analiza" bywają
  // długim, surowym CoT modelu (nie streszczonym jak w referencyjnym UI) — dla nich
  // `collapsible=true` zachowuje własny, niezależny od grupy collapse, żeby rozwinięcie
  // grupy nie wysypywało od razu ściany tekstu.
  renderRailItemShell({ extraClass, dataCallId, iconHtml, titleHtml, bodyHtml, collapsible = false, dataOpen = 'false' }) {
    const callIdAttr = dataCallId ? ` data-call-id="${escapeAttr(dataCallId)}"` : '';
    if (collapsible) {
      return `<div class="rail-item chat-collapsible ${extraClass}" data-open="${dataOpen}"${callIdAttr}>
        <div class="rail-icon-col"><span class="rail-icon">${iconHtml}</span></div>
        <div class="rail-content">
          <div class="thinking-summary rail-summary">
            <span class="thinking-title-text">${titleHtml}</span>
            <span class="thinking-chevron">${Icons.ChevronRight()}</span>
          </div>
          <div class="thinking-content-wrapper"><div class="thinking-content-inner"><div class="thinking-content">${bodyHtml}</div></div></div>
        </div>
      </div>`;
    }
    return `<div class="rail-item ${extraClass}"${callIdAttr}>
      <div class="rail-icon-col"><span class="rail-icon">${iconHtml}</span></div>
      <div class="rail-content">
        <div class="rail-item-header"><span class="thinking-title-text">${titleHtml}</span></div>
        <div class="rail-item-body">${bodyHtml}</div>
      </div>
    </div>`;
  }

  // Formatuje dosłowną sygnaturę wywołania narzędzia — interfejs jest konsolą techniczną/
  // debugującą, więc pokazujemy nazwę i argumenty 1:1, nie humanizowaną etykietę.
  formatToolCallSignature(name, args) {
    if (!args || Object.keys(args).length === 0) return `${name}()`;
    const parts = Object.entries(args).map(([k, v]) => `${k}: ${JSON.stringify(v)}`);
    return `${name}(${parts.join(', ')})`;
  }

  renderStepBody(step) {
    if (step.content === null || step.content === undefined) {
      return '<div class="step-result step-result-pending">W toku…</div>';
    }
    return `<div class="step-result">${escapeHtml(step.content)}</div>`;
  }

  // --- Klaster kolejnych wywołań narzędzi (bez przerwy w postaci myślenia/tekstu) --------
  // 2+ wywołań narzędzi bezpośrednio po sobie zlepiamy w jeden, PŁASKI (bez collapsible)
  // node z jedną ikoną zbiorczą — 7 osobnych nagłówków+ikon+wyników było zbyt "rozjechane"
  // wizualnie (feedback). Bez ikony sukcesu/porażki przy pojedynczym wywołaniu wewnątrz
  // klastra — fail sygnalizowany kolorem tekstu tej konkretnej linii wyniku.

  // Polska odmiana "narzędzie": 1 narzędzie, 2-4 narzędzia (poza 12-14), pozostałe narzędzi.
  pluralizeNarzedzia(n) {
    if (n === 1) return 'narzędzie';
    const lastDigit = n % 10;
    const lastTwo = n % 100;
    if (lastDigit >= 2 && lastDigit <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return 'narzędzia';
    return 'narzędzi';
  }

  // running: część wywołań jeszcze nie ma wyniku. done/error: wszystkie się zgadzają.
  // mixed: część sukces, część fail — jedyny przypadek, w którym potrzebna trzecia ikona.
  computeClusterStatus(calls) {
    if (calls.some((c) => c.isError === null || c.isError === undefined)) return 'running';
    const hasError = calls.some((c) => c.isError === true);
    const hasSuccess = calls.some((c) => c.isError === false);
    if (hasError && hasSuccess) return 'mixed';
    return hasError ? 'error' : 'done';
  }

  renderClusterIcon(status) {
    if (status === 'running') return Icons.CircleLoader();
    if (status === 'error') return Icons.AlertCircle();
    if (status === 'mixed') return Icons.CircleMinus();
    return Icons.CheckCircle2();
  }

  renderClusterCallHtml(step) {
    const signature = this.formatToolCallSignature(step.name, step.arguments);
    const isError = step.isError === true;
    const resultHtml =
      step.content === null || step.content === undefined
        ? '<div class="cluster-call-result step-result-pending">W toku…</div>'
        : `<div class="cluster-call-result${isError ? ' is-error' : ''}">${escapeHtml(step.content)}</div>`;
    return `<div class="cluster-call" data-call-id="${escapeAttr(step.callId || '')}">
      <div class="cluster-call-signature">${escapeHtml(signature)}</div>
      ${resultHtml}
    </div>`;
  }

  renderClusterNode(calls) {
    const status = this.computeClusterStatus(calls);
    const icon = this.renderClusterIcon(status);
    const bodyHtml = calls.map((c) => this.renderClusterCallHtml(c)).join('');
    return `<div class="rail-item rail-item-cluster cluster-${status}">
      <div class="rail-icon-col"><span class="rail-icon">${icon}</span></div>
      <div class="rail-content">
        <div class="rail-item-header"><span class="thinking-title-text">Wywołano ${this.pluralizeNarzedzia(calls.length)}: ${calls.length}</span></div>
        <div class="rail-item-body">${bodyHtml}</div>
      </div>
    </div>`;
  }

  // Zamienia płaską listę segmentów step/think na listę jednostek renderowania — przebieg
  // 2+ kolejnych 'step' staje się jedną jednostką {kind:'cluster'}, przebieg długości 1
  // zostaje pojedynczym 'step', 'think' bez zmian. Używane tylko przy replayu z historii
  // (ścieżka live buduje/awansuje klastry przyrostowo w appendStepNode).
  groupConsecutiveStepsForRender(segs) {
    const units = [];
    let run = [];
    const flushRun = () => {
      if (run.length === 1) units.push({ kind: 'step', step: run[0] });
      else if (run.length > 1) units.push({ kind: 'cluster', steps: run });
      run = [];
    };
    for (const seg of segs) {
      if (seg.kind === 'step') {
        run.push(seg.step);
      } else {
        flushRun();
        units.push(seg);
      }
    }
    flushRun();
    return units;
  }

  // Buduje HTML pojedynczego node'a kroku — reużywana zarówno przy dokładaniu na żywo
  // (appendStepNode, status zawsze "running" bo isError jeszcze null), jak i przy replayu
  // z historii (status wynika wprost z zapisanego isError).
  renderStepNode(step) {
    const status = step.isError === null || step.isError === undefined ? 'running' : step.isError ? 'error' : 'done';
    const icon = status === 'running' ? Icons.CircleLoader() : status === 'error' ? Icons.AlertCircle() : Icons.CheckCircle2();
    const signature = this.formatToolCallSignature(step.name, step.arguments);
    const titleHtml = `<span class="rail-title-label">Wywołanie narzędzia:</span> <span class="rail-title-code">${escapeHtml(signature)}</span>`;

    return this.renderRailItemShell({
      extraClass: `rail-item-step step-${status}`,
      dataCallId: step.callId,
      iconHtml: icon,
      titleHtml,
      bodyHtml: this.renderStepBody(step),
    });
  }

  // Zawsze domyślnie zwinięty (dataOpen: 'false'), także w trakcie aktywnego myślenia —
  // spójnie z resztą drzewka (feedback: "pokazujemy w trakcie pracy, potem chamsko
  // zwijamy"). Bez live-typing surowego CoT domyślnie; user może ręcznie rozwinąć, a
  // updateThinkRailItemDom już nigdy nie domyka tego automatycznie pod nim.
  renderThinkRailItem(content, isStreaming) {
    const escaped = escapeHtml(content.trim()).replace(/\n/g, '<br/>');
    const title = isStreaming ? 'Analizuję...' : 'Analiza';
    return this.renderRailItemShell({
      extraClass: 'rail-item-think',
      dataCallId: null,
      iconHtml: Icons.CircleEllipsis(),
      titleHtml: escapeHtml(title),
      bodyHtml: escaped,
      collapsible: true,
      dataOpen: 'false',
    });
  }

  // --- Replay z historii: statyczne grupowanie segmentów w rail --------------------------

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
        seq: s.seq || 0,
        arguments: null,
        content: null,
        isError: null,
      };
      if (s.type === 'tool_call') {
        existing.arguments = s.arguments;
        existing.textOffset = s.text_offset;
        existing.seq = s.seq || 0;
      } else if (s.type === 'tool_result') {
        existing.content = s.content;
        existing.isError = s.is_error;
      }
      byId.set(s.call_id, existing);
    }
    return [...byId.values()];
  }

  // Dzieli tekst na segmenty tekst/myślenie wg tagów <think>...</think> — używane zarówno
  // samodzielnie (wiadomość bez kroków), jak i wewnątrz buildSegments dla segmentów 'text'.
  splitThinkFromText(text) {
    if (!text) return [];
    const thinkStart = text.indexOf('<think>');
    if (thinkStart === -1) return [{ kind: 'text', content: text }];

    const parts = [];
    if (thinkStart > 0) parts.push({ kind: 'text', content: text.slice(0, thinkStart) });

    const thinkEnd = text.indexOf('</think>');
    if (thinkEnd !== -1) {
      parts.push({ kind: 'think', content: text.slice(thinkStart + 7, thinkEnd), done: true });
      const rest = text.slice(thinkEnd + 8);
      if (rest) parts.push(...this.splitThinkFromText(rest));
    } else {
      parts.push({ kind: 'think', content: text.slice(thinkStart + 7), done: false });
    }
    return parts;
  }

  // Dzieli pełny tekst finalnej odpowiedzi na segmenty tekst/krok/myślenie wg `textOffset`
  // zapisanego przy każdej pozycji szyny — potrzebne tylko przy replayu z historii, gdzie
  // nie mamy naturalnej kolejności zdarzeń SSE, tylko płaski tekst + listy pozycji.
  //
  // Sortowanie po `seq` (globalny licznik chronologiczny z serwera), nie po samym offsecie:
  // cała sekwencja myślenie -> narzędzie -> myślenie dzieje się przy TYM SAMYM offsecie,
  // dopóki model nie napisze pierwszego znaku odpowiedzi, więc offset by ich nie rozróżnił.
  // Wpisy legacy (bez `seq`) mają 0 i spadają na dawne sortowanie po offsecie — `sort` w JS
  // jest stabilny, więc zachowują kolejność zapisu.
  buildSegments(text, steps, reasoning = []) {
    const railItems = [
      ...steps.map((step) => ({ kind: 'step', step, seq: step.seq || 0, textOffset: step.textOffset })),
      ...reasoning,
    ].sort((a, b) => (a.seq || 0) - (b.seq || 0) || a.textOffset - b.textOffset);

    const rawSegments = [];
    let cursor = 0;
    for (const item of railItems) {
      const offset = Math.min(Math.max(item.textOffset, 0), text.length);
      if (offset > cursor) {
        rawSegments.push({ kind: 'text', content: text.slice(cursor, offset) });
      }
      rawSegments.push(item);
      cursor = offset;
    }
    if (cursor < text.length) {
      rawSegments.push({ kind: 'text', content: text.slice(cursor) });
    }

    const segments = [];
    for (const seg of rawSegments) {
      if (seg.kind === 'text') segments.push(...this.splitThinkFromText(seg.content));
      else segments.push(seg);
    }
    return segments;
  }

  // Grupuje kolejne segmenty 'think'/'step' we wspólną szynę (.step-rail), a segmenty
  // 'text' renderuje jako osobne przebiegi poza szyną — dokładnie odzwierciedla model
  // grupowania używany przy renderowaniu na żywo (appendStepNode/appendStreamingText).
  renderGroupedSegments(segments) {
    let html = '';
    let railSegBuffer = [];
    const flushRail = () => {
      if (railSegBuffer.length) {
        html += this.renderRailGroupFromSegments(railSegBuffer);
        railSegBuffer = [];
      }
    };
    for (const seg of segments) {
      if (seg.kind === 'step' || seg.kind === 'think') {
        railSegBuffer.push(seg);
      } else if (seg.content && seg.content.trim()) {
        flushRail();
        html += `<div class="message-text-run"><div class="message-rest-content">${this.formatRestContent(seg.content)}</div></div>`;
      }
      // Segmenty tekstowe złożone wyłącznie z białych znaków (np. pojedynczy "\n", który
      // model często wstawia między </think> a kolejną akcją, albo między wynikiem
      // narzędzia a kolejnym <think>) są całkowicie pomijane — nie przerywają sekwencji
      // rail ani nie dodają pustego akapitu. Bez tego pojedynczy "\n" fałszywie kończył
      // szynę, przez co np. blok "Analiza" tracił linię łączącą do kolejnego kroku.
    }
    flushRail();
    return html;
  }

  // Buduje zbiorczy, zwijalny nagłówek ("N kroków") + wewnętrzną szynę dla replayu z
  // historii — status/liczba wynikają wprost z zapisanych danych (w historii wszystko jest
  // już zakończone, więc "running" nigdy tu nie występuje).
  renderRailGroupFromSegments(segs) {
    const units = this.groupConsecutiveStepsForRender(segs);
    const renderUnit = (u) => {
      if (u.kind === 'cluster') return this.renderClusterNode(u.steps);
      if (u.kind === 'step') return this.renderStepNode(u.step);
      return this.renderThinkRailItem(u.content, !u.done);
    };

    // Owijanie pojedynczego node'a w zbiorczy nagłówek "1 krok" to zbędna ceremonia —
    // przy dokładnie jednej jednostce (nawet jeśli to klaster N wywołań) renderujemy ją
    // bezpośrednio, bez .rail-group wokół.
    if (units.length === 1) return renderUnit(units[0]);

    const itemsHtml = units.map(renderUnit).join('');
    const hasError = segs.some((seg) => seg.kind === 'step' && seg.step.isError === true);
    // Licznik nagłówka liczy SUROWE wywołania (niezależnie od wizualnego zlepienia w
    // klaster) — "N kroków" ma dawać prawdziwą skalę, klaster daje szczegół w środku.
    const count = segs.length;

    return `<div class="rail-group chat-collapsible${hasError ? ' group-error' : ''}" data-open="false">
      <div class="thinking-summary rail-group-summary">
        <span class="thinking-title-text">${count} ${this.pluralizeKroki(count)}</span>
        <span class="thinking-chevron">${Icons.ChevronRight()}</span>
      </div>
      <div class="rail-group-content-wrapper"><div class="thinking-content-inner">
        <div class="step-rail">${itemsHtml}</div>
      </div></div>
    </div>`;
  }

  // Buduje statyczny HTML całej wiadomości assistant z historii (albo z pollingu, gdzie
  // rawSteps zawsze jest puste).
  renderAssistantHistoryHtml(content, rawSteps, rawReasoning) {
    const steps = this.mergeStepPairs(rawSteps || []);
    const reasoning = (rawReasoning || []).map((run) => ({
      kind: 'think',
      content: run.content,
      done: true,
      seq: run.seq || 0,
      textOffset: run.text_offset || 0,
    }));

    // Ścieżka legacy: wiadomości sprzed rozdzielenia rozumowania nie mają
    // `metadata.reasoning`, tylko znaczniki `<think>` wprost w treści. Pliki w
    // `data/sessions/` to realne dane użytkownika — nie migrujemy ich, tylko nadal
    // umiemy je odczytać (`splitThinkFromText` jest dla nowych wiadomości martwe).
    if (!steps.length && !reasoning.length) {
      return this.renderGroupedSegments(this.splitThinkFromText(content));
    }
    return this.renderGroupedSegments(this.buildSegments(content, steps, reasoning));
  }

  formatRestContent(restText) {
    if (!restText) return '';
    const escapedContent = escapeHtml(restText.trim()).replace(/\n/g, '<br/>');
    return escapedContent
      .replace(/```([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
      .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
  }
}
