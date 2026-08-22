/**
 * Zbiór wektorowych, monochromatycznych ikonek SVG (Antigravity Style - 150% Scale).
 * Wykorzystują stroke="currentColor" oraz stroke-width="1.75".
 */

function createSvg(content, viewBox = "0 0 24 24", extraAttrs = "") {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="${viewBox}" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="icon-svg" ${extraAttrs}>${content}</svg>`;
}

export const Icons = {
  // Nawigacja
  LayoutGrid: () => createSvg(`
    <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
    <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
    <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
    <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
  `),

  Cpu: () => createSvg(`
    <rect x="4" y="4" width="16" height="16" rx="2"></rect>
    <rect x="9" y="9" width="6" height="6" rx="1"></rect>
    <path d="M15 2v2M15 20v2M2 15h2M20 15h2M2 9h2M20 9h2M9 2v2M9 20v2"></path>
  `),

  Server: () => createSvg(`
    <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
    <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
    <line x1="6" y1="6" x2="6.01" y2="6"></line>
    <line x1="6" y1="18" x2="6.01" y2="18"></line>
  `),

  FileText: () => createSvg(`
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
    <polyline points="14 2 14 8 20 8"></polyline>
    <line x1="16" y1="13" x2="8" y2="13"></line>
    <line x1="16" y1="17" x2="8" y2="17"></line>
    <polyline points="10 9 9 9 8 9"></polyline>
  `),

  Sliders: () => createSvg(`
    <line x1="4" y1="21" x2="4" y2="14"></line>
    <line x1="4" y1="10" x2="4" y2="3"></line>
    <line x1="12" y1="21" x2="12" y2="12"></line>
    <line x1="12" y1="8" x2="12" y2="3"></line>
    <line x1="20" y1="21" x2="20" y2="16"></line>
    <line x1="20" y1="12" x2="20" y2="3"></line>
    <line x1="1" y1="14" x2="7" y2="14"></line>
    <line x1="9" y1="8" x2="15" y2="8"></line>
    <line x1="17" y1="16" x2="23" y2="16"></line>
  `),

  // Status & Akcje
  Activity: () => createSvg(`
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
  `, "0 0 24 24", 'width="24" height="24"'),

  Radio: () => createSvg(`
    <circle cx="12" cy="12" r="2"></circle>
    <path d="M16.2 7.8a6 6 0 0 1 0 8.4m-8.4 0a6 6 0 0 1 0-8.4"></path>
    <path d="M19.1 4.9a10 10 0 0 1 0 14.2m-14.2 0a10 10 0 0 1 0-14.2"></path>
  `),

  Mic: () => createSvg(`
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
    <line x1="12" y1="19" x2="12" y2="23"></line>
    <line x1="8" y1="23" x2="16" y2="23"></line>
  `),

  Check: () => createSvg(`
    <path d="M20 6 9 17l-5-5"></path>
  `),

  X: () => createSvg(`
    <path d="M18 6 6 18"></path>
    <path d="m6 6 12 12"></path>
  `),

  CheckCircle2: () => createSvg(`
    <circle cx="12" cy="12" r="10"></circle>
    <path d="m9 12 2 2 4-4"></path>
  `),

  AlertCircle: () => createSvg(`
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  `),

  // Kółko z trzema kropkami — "w toku analizowania", spójne stylistycznie z CheckCircle2/AlertCircle
  CircleEllipsis: () => createSvg(`
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="8" y1="12" x2="8.01" y2="12"></line>
    <line x1="12" y1="12" x2="12.01" y2="12"></line>
    <line x1="16" y1="12" x2="16.01" y2="12"></line>
  `),

  // Kółko ze spinnerem — status "w toku" narzędzia, obracane w CSS (.rail-icon-spin)
  CircleLoader: () => createSvg(`
    <circle cx="12" cy="12" r="10" opacity="0.3"></circle>
    <path d="M12 2a10 10 0 0 1 10 10"></path>
  `),

  // Kółko z poziomą kreską (konwencja "stanu pośredniego", jak indeterminate checkbox) —
  // klaster wywołań narzędzi z mieszanymi wynikami (część sukces, część fail)
  CircleMinus: () => createSvg(`
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="8" y1="12" x2="16" y2="12"></line>
  `),

  RefreshCw: () => createSvg(`
    <polyline points="23 4 23 10 17 10"></polyline>
    <polyline points="1 20 1 14 7 14"></polyline>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
  `),

  ChevronRight: () => createSvg(`
    <polyline points="9 18 15 12 9 6"></polyline>
  `, "0 0 24 24", 'width="16" height="16"'),

  ChevronDown: () => createSvg(`
    <polyline points="6 9 12 15 18 9"></polyline>
  `, "0 0 24 24", 'width="16" height="16"'),

  // Czat i Komunikacja
  MessageSquare: () => createSvg(`
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
  `),

  Send: () => createSvg(`
    <line x1="22" y1="2" x2="11" y2="13"></line>
    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
  `),

  Bot: () => createSvg(`
    <rect x="3" y="11" width="18" height="10" rx="2"></rect>
    <circle cx="12" cy="5" r="2"></circle>
    <path d="M12 7v4"></path>
    <line x1="8" y1="16" x2="8.01" y2="16"></line>
    <line x1="16" y1="16" x2="16.01" y2="16"></line>
  `),

  User: () => createSvg(`
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  `),

  Trash2: () => createSvg(`
    <polyline points="3 6 5 6 21 6"></polyline>
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
    <line x1="10" y1="11" x2="10" y2="17"></line>
    <line x1="14" y1="11" x2="14" y2="17"></line>
  `),

  Plus: () => createSvg(`
    <line x1="12" y1="5" x2="12" y2="19"></line>
    <line x1="5" y1="12" x2="19" y2="12"></line>
  `),

  Sparkles: () => createSvg(`
    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"></path>
  `),

  Square: () => createSvg(`
    <rect x="5" y="5" width="14" height="14" rx="2"></rect>
  `),

  Copy: () => createSvg(`
    <rect x="9" y="9" width="13" height="13" rx="2"></rect>
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
  `),

  Eye: () => createSvg(`
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"></path>
    <circle cx="12" cy="12" r="3"></circle>
  `),

  EyeOff: () => createSvg(`
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"></path>
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c6.5 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"></path>
    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3.5 7 10 7a9.74 9.74 0 0 0 5.39-1.61"></path>
    <line x1="2" y1="2" x2="22" y2="22"></line>
  `),

  Puzzle: () => createSvg(`
    <path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.61a2.404 2.404 0 0 1-1.705.707 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.23 8.77c.256-.257.6-.35.877-.29.493.074.84.504 1.02.968a2.5 2.5 0 1 0 3.237-3.237c-.464-.18-.894-.527-.967-1.02a1.026 1.026 0 0 1 .289-.877l1.568-1.568A2.402 2.402 0 0 1 12 2c.617 0 1.234.236 1.704.706l1.611 1.611c.257.256.35.6.29.877-.075.493-.504.84-.968 1.02a2.5 2.5 0 1 0 3.237 3.237c.18-.464.527-.894 1.02-.967.278-.041.62.033.877.29z"></path>
  `),
};
