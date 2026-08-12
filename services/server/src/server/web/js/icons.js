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

  CheckCircle2: () => createSvg(`
    <circle cx="12" cy="12" r="10"></circle>
    <path d="m9 12 2 2 4-4"></path>
  `),

  AlertCircle: () => createSvg(`
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  `),

  RefreshCw: () => createSvg(`
    <polyline points="23 4 23 10 17 10"></polyline>
    <polyline points="1 20 1 14 7 14"></polyline>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
  `),

  ChevronRight: () => createSvg(`
    <polyline points="9 18 15 12 9 6"></polyline>
  `, "0 0 24 24", 'width="16" height="16"'),
};
