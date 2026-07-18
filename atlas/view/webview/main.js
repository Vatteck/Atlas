// Polyfill localStorage if unavailable in webview sandbox (common in file:// contexts under WebKitGTK)
if (typeof localStorage === 'undefined' || !localStorage) {
    window.localStorage = {
        _data: {},
        setItem: function(id, val) { return this._data[id] = String(val); },
        getItem: function(id) { return this._data.hasOwnProperty(id) ? this._data[id] : null; },
        removeItem: function(id) { return delete this._data[id]; },
        clear: function() { return this._data = {}; }
    };
}

// Theme Management — two axes: palette (data-theme: light/dark/+presets) and accent
// (data-accent: indigo[default]/blue/teal/green/rose/amber). Both persist in localStorage (durable
// now that pywebview runs with persistent storage) and mirror the resolved window background to the
// backend so the native splash-flash color tracks the active theme. See
// plans/2026-06-20-theme-options.md.
const themeToggleBtn = document.getElementById('theme-toggle');
const rootElement = document.documentElement;

const THEME_PALETTES = ['light', 'dark', 'nord', 'solarized-dark', 'high-contrast'];
const ACCENT_COLORS = ['indigo', 'blue', 'teal', 'green', 'rose', 'amber'];

// Initialize from localStorage (defaults: dark palette, indigo accent) — applied synchronously
// before first paint to avoid a flash of the wrong theme.
rootElement.setAttribute('data-theme', localStorage.getItem('atlas-theme') || 'dark');
rootElement.setAttribute('data-accent', localStorage.getItem('atlas-accent') || 'indigo');

// Push the resolved base background to the backend so the next launch paints the native window in
// the right color before WebKit renders (kills the splash-flash for non-dark themes). Fire-and-
// forget; only meaningful once the backend is ready, so callers gate on that or just let it no-op.
function syncWindowBg() {
    try {
        const bg = getComputedStyle(rootElement).getPropertyValue('--bg-base').trim();
        if (bg && window.pywebview && window.pywebview.api && window.pywebview.api.set_window_bg) {
            window.pywebview.api.set_window_bg(bg);
        }
    } catch (e) { /* non-fatal: the flash color just won't update this run */ }
}

function setTheme(palette) {
    const next = THEME_PALETTES.includes(palette) ? palette : 'dark';
    rootElement.setAttribute('data-theme', next);
    localStorage.setItem('atlas-theme', next);
    syncWindowBg();
}

function setAccent(accent) {
    const next = ACCENT_COLORS.includes(accent) ? accent : 'indigo';
    rootElement.setAttribute('data-accent', next);
    localStorage.setItem('atlas-accent', next);
    syncWindowBg();  // accent doesn't change --bg-base, but harmless + keeps the mirror authoritative
}

// Topbar quick toggle: flip light/dark.
themeToggleBtn.addEventListener('click', () => {
    setTheme(rootElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
});

// Representative swatch color per accent (the dot shown in Settings; the live CSS lives in style.css).
const ACCENT_SWATCHES = {
    indigo: '#6366f1', blue: '#3b82f6', teal: '#14b8a6',
    green: '#22c55e', rose: '#f43f5e', amber: '#f59e0b'
};
const THEME_LABELS = {
    light: 'Light', dark: 'Dark', nord: 'Nord',
    'solarized-dark': 'Solarized Dark', 'high-contrast': 'High Contrast'
};

// Settings → Appearance rows (pure markup; handlers wired in the settings render).
function buildThemeRow() {
    const cur = localStorage.getItem('atlas-theme') || 'dark';
    const opts = THEME_PALETTES.map(p =>
        `<option value="${p}" ${cur === p ? 'selected' : ''}>${THEME_LABELS[p] || p}</option>`).join('');
    return `
        <label class="settings-row" title="Color theme - applies immediately">
            <span class="settings-row-label">Theme</span>
            <select id="settings-theme" class="styled-select">${opts}</select>
        </label>`;
}

function buildAccentRow() {
    const cur = localStorage.getItem('atlas-accent') || 'indigo';
    const dots = ACCENT_COLORS.map(a =>
        `<button type="button" class="accent-swatch${cur === a ? ' selected' : ''}" data-accent-pick="${a}"
                 title="${a.charAt(0).toUpperCase() + a.slice(1)}" aria-label="${a} accent"
                 style="--swatch:${ACCENT_SWATCHES[a]}"></button>`).join('');
    return `
        <div class="settings-row" title="Highlight color - applies immediately">
            <span class="settings-row-label">Accent color</span>
            <div class="accent-swatches" id="settings-accent">${dots}</div>
        </div>`;
}

// HTML escaping helper to prevent XSS / Local RCE
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function safeExternalUrl(url) {
    if (typeof url !== 'string') return '';
    if (!url || /[\u0000-\u0020\u007f]/.test(url)) return '';
    try {
        const parsed = new URL(url);
        if ((parsed.protocol === 'http:' || parsed.protocol === 'https:') && parsed.hostname) return url;
    } catch (e) {
        return '';
    }
    return '';
}

function externalLinkHTML(url, label, className = '') {
    const safe = safeExternalUrl(url);
    const text = label || url || '';
    if (!safe) return escapeHtml(text);
    const cls = className ? ` class="${escapeHtml(className)}"` : '';
    return `<a href="#"${cls} data-url="${escapeHtml(safe)}">${escapeHtml(text)} ↗</a>`;
}

function openExternalUrl(url) {
    const safe = safeExternalUrl(url);
    if (!safe) {
        showToast('Invalid URL', 'Atlas refused to open a non-http(s) URL.', 'error');
        return Promise.resolve(null);
    }
    return pyApiCall('open_url', safe);
}

// Toast Notifications
const toastContainer = document.getElementById('toast-container');

function showToast(title, message, type = 'info', copyText = null) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconSvg = '';
    if (type === 'success') {
        iconSvg = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`;
    } else if (type === 'error') {
        iconSvg = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
    } else {
        iconSvg = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
    }

    // An optional copyable command (e.g. the exact `flatpak override` a permission toggle ran):
    // nothing is hidden from CLI users — click the toast to copy it.
    const copyHint = copyText ? `<div class="toast-copy-hint">⧉ Click to copy command</div>` : '';
    toast.innerHTML = `
        ${iconSvg}
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
            ${copyHint}
        </div>
    `;
    if (copyText) {
        toast.classList.add('toast-copyable');
        toast.title = 'Click to copy command';
        toast.addEventListener('click', () => {
            const done = () => showToast('Copied command', copyText, 'success');
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(copyText).then(done).catch(() => {});
            } else { done(); }
        });
    }

    toastContainer.appendChild(toast);

    // Remove after 3.5 seconds
    setTimeout(() => {
        toast.classList.add('hiding');
        toast.addEventListener('animationend', () => {
            toast.remove();
        });
    }, 3500);
}

// App Logic Constants & Globals
const packagesGrid = document.getElementById('packages-grid');
const loadingState = document.getElementById('loading-state');
const emptyState = document.getElementById('empty-state');
const searchInput = document.getElementById('search-input');
const typeFilter = document.getElementById('type-filter');
const sortFilter = document.getElementById('sort-filter');
const navItems = document.querySelectorAll('.nav-item');
// The main column (.content) is the scroll container; the topbar is sticky inside it. Switching
// from a tall, scrolled-down view to a short one leaves scrollTop stranded past the new content,
// scrolling everything (sticky topbar included) out of view → a blank page. Reset it on view change.
const contentScroll = document.querySelector('.content');
function resetContentScroll() { if (contentScroll) contentScroll.scrollTop = 0; }

const selectModeBtn = document.getElementById('select-mode-btn');
const batchBar = document.getElementById('batch-bar');
const batchCount = document.getElementById('batch-count');
const batchInstallBtn = document.getElementById('batch-install-btn');
const batchUninstallBtn = document.getElementById('batch-uninstall-btn');
const batchCancelBtn = document.getElementById('batch-cancel-btn');
const updateAllBtn = document.getElementById('update-all-btn');
const cleanupOrphansBtn = document.getElementById('cleanup-orphans-btn');

const detailModal = document.getElementById('detail-modal');
const modalClose = document.getElementById('modal-close');
const modalBackdrop = detailModal.querySelector('.modal-backdrop');

let currentPackages = [];
let currentGroups = [];   // packages collapsed by app name; each card renders one group
let diskPackages = [];
let currentView = 'dashboard'; // 'dashboard', 'installed', 'updates', 'activity'
let activeBrowseCategory = null;
let packageFetchEpoch = 0;

// History / rollback center (Activity page): the last-fetched entries + the active filter, so
// filter/search changes re-render client-side without refetching. See
// docs/plans/2026-06-05-history-rollback-center.md.
let activityEntries = [];
let activityFilter = { action: 'all', type: 'all', query: '' };

// Grid vs list layout for the package views (persisted). Pure CSS — toggling the class on
// packagesGrid is enough, no re-render needed. Defaults to grid.
let viewMode = (localStorage.getItem('atlas_view_mode') === 'list') ? 'list' : 'grid';

// Sort order for the package lists (persisted). 'relevance' keeps the existing
// search-ranking / AUR-ranking behaviour; the rest are explicit comparators.
const SORT_MODES = ['relevance', 'votes', 'popularity', 'updated', 'name'];
let sortMode = SORT_MODES.includes(localStorage.getItem('atlas_sort_mode'))
    ? localStorage.getItem('atlas_sort_mode') : 'relevance';

let selectMode = false;
let selectedPackages = new Set();
let operationInProgress = false;

// Cross-view install queue (Theme 5): a persistent basket of not-installed packages collected while
// browsing, reviewed + installed together. Snapshots (not live pkg refs) so it survives view changes.
const QUEUE_STORAGE_KEY = 'atlas_install_queue';
let installQueue = [];

let packageCache = {};
let updatesInFlight = null;

function getCacheKey(view, type, query) {
    return `${view}\0${type}\0${query}`;
}

// The full, unfiltered list backing a finite local view (Installed / Updates) — reused from the
// session cache populated by the no-query load, so a search filters it without a fresh backend call.
async function localListFor(view) {
    const cached = packageCache[getCacheKey(view, 'all', '')];
    if (cached !== undefined) return cached;
    if (view === 'updates') return (await getUpdatesCached()) || [];
    return (await pyApiCall('get_installed', 'all')) || [];
}

function getUpdatesCached() {
    const updatesKey = getCacheKey('updates', 'all', '');
    if (packageCache[updatesKey] !== undefined) {
        return Promise.resolve(packageCache[updatesKey]);
    }
    if (!updatesInFlight) {
        updatesInFlight = pyApiCall('get_updates', 'all').then(
            updates => {
                if (Array.isArray(updates)) writeToCache(updatesKey, updates);
                updatesInFlight = null;
                return updates;
            },
            error => {
                updatesInFlight = null;
                throw error;
            }
        );
    }
    return updatesInFlight;
}

// --- Source types ----------------------------------------------------------
// Atlas is Arch-focused: the only sources are the official repo, the AUR, Flatpak and
// AppImage. Arch and AUR are always kept distinct (AUR is community-maintained / less
// vetted). normalizeType() maps a raw backend get_type() value to a canonical token used
// by both the filter and the card tag.
function normalizeType(type) {
    const t = (type || '').toString().trim().toLowerCase();
    if (t === 'arch_repo' || t === 'arch') return 'arch_repo';
    if (t === 'aur') return 'aur';
    if (t === 'flatpak') return 'flatpak';
    if (t === 'appimage') return 'appimage';
    return t || 'unknown';
}

const SOURCE_LABELS = {
    arch_repo: 'Arch',
    aur: 'AUR',
    flatpak: 'Flatpak',
    appimage: 'AppImage',
    snap: 'Snap',
    debian: 'Debian',
    web: 'Web',
};
function sourceLabel(type) {
    return SOURCE_LABELS[normalizeType(type)] || (type || 'Unknown');
}

// Web page for a package, derived from its source + name. AUR and the official Arch repo
// are reliable from the name; other sources return null (no link shown).
function packagePageUrl(pkg) {
    const name = (pkg && pkg.name || '').trim();
    if (!name) return null;
    const t = normalizeType(pkg.type);
    if (t === 'aur') return `https://aur.archlinux.org/packages/${encodeURIComponent(name)}`;
    if (t === 'arch_repo') return `https://archlinux.org/packages/?name=${encodeURIComponent(name)}`;
    // Flatpak's Flathub page is keyed by the appstream id (app_id), not the display name.
    if (t === 'flatpak' && pkg.app_id) return `https://flathub.org/apps/${encodeURIComponent(pkg.app_id)}`;
    return null;
}

// Client-side type filter: the backend returns every source, the dropdown narrows it here
// (instant, no refetch). 'all' shows everything.
function filterByType(packages, type) {
    if (!type || type === 'all') return packages;
    return (packages || []).filter(p => normalizeType(p.type) === type);
}

// --- AUR variants ----------------------------------------------------------
// AUR ships base / -bin / -git (and friends) as distinct packages. We keep them as
// separate cards (they're different build choices) but badge + rank them. We also compute
// the base name now so grouping these under one card later is cheap to switch on.
const AUR_VCS_SUFFIXES = ['-git', '-svn', '-hg', '-bzr', '-cvs', '-nightly'];
function aurVariant(name) {
    const raw = name || '';
    const n = raw.toLowerCase();
    for (const suf of AUR_VCS_SUFFIXES) {
        if (n.endsWith(suf)) return { kind: 'vcs', label: suf.slice(1), base: raw.slice(0, -suf.length) };
    }
    if (n.endsWith('-bin')) return { kind: 'binary', label: 'binary', base: raw.slice(0, -4) };
    if (n.endsWith('-debug')) return { kind: 'debug', label: 'debug', base: raw.slice(0, -6) };
    return { kind: 'source', label: 'source', base: raw };
}

// Rank AUR packages among themselves (decision: most-voted non-VCS first). Installed
// first, then non-VCS before VCS, then not-out-of-date, then by votes/popularity desc.
// Non-AUR items keep their position (AUR items are reordered only within their own slots),
// so this never disturbs the official-repo / Flatpak / AppImage ordering.
function _aurRankKey(p) {
    const v = aurVariant(p.name);
    const score = typeof p.votes === 'number' ? p.votes
                : (typeof p.popularity === 'number' ? p.popularity : -1);
    return [p.installed ? 0 : 1, v.kind === 'vcs' ? 1 : 0, p.out_of_date ? 1 : 0, -score];
}
function rankAur(packages) {
    const list = packages || [];
    const idxs = [], items = [];
    list.forEach((p, i) => { if (normalizeType(p.type) === 'aur') { idxs.push(i); items.push(p); } });
    if (items.length < 2) return list;
    items.sort((a, b) => {
        const ka = _aurRankKey(a), kb = _aurRankKey(b);
        for (let i = 0; i < ka.length; i++) { if (ka[i] !== kb[i]) return ka[i] - kb[i]; }
        return 0;
    });
    const out = list.slice();
    idxs.forEach((idx, k) => { out[idx] = items[k]; });
    return out;
}

// Per-source color used for the letter-avatar fallback icon (most AUR/repo packages have
// no icon_url, so a colored initial reads far better than identical gray squares).
const SOURCE_COLORS = {
    arch_repo: '#1793d1', aur: '#d97706', flatpak: '#4a86cf', appimage: '#5b6472', web: '#6366f1',
};
function letterAvatar(pkg) {
    const bg = SOURCE_COLORS[normalizeType(pkg.type)] || '#6366f1';
    let ch = ((pkg.name || '?').trim()[0] || '?').toUpperCase();
    if (!/[A-Z0-9]/.test(ch)) ch = '?';
    // A soft sheen (light top → faint dark bottom) over the source color reads as a polished tile
    // rather than a flat square; the letter is slightly translucent so it's less harsh.
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48">`
        + `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">`
        + `<stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>`
        + `<stop offset="1" stop-color="#000000" stop-opacity="0.14"/></linearGradient></defs>`
        + `<rect width="48" height="48" rx="12" fill="${bg}"/>`
        + `<rect width="48" height="48" rx="12" fill="url(#g)"/>`
        + `<text x="24" y="25" font-family="-apple-system,Segoe UI,Roboto,sans-serif" font-size="22" `
        + `font-weight="600" fill="#ffffff" fill-opacity="0.95" text-anchor="middle" `
        + `dominant-baseline="central">${ch}</text></svg>`;
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

// Best icon for a (possibly multi-source) card: an embedded data: icon wins, else any remote URL,
// so e.g. Steam (Arch installed + Flatpak) borrows the Flatpak's icon when the active source has
// none. '' means no source has an icon → the letter avatar is used.
function bestIconUrl(group) {
    const srcs = (group && group.sources) || [];
    const data = srcs.find(s => s.icon_url && s.icon_url.startsWith('data:'));
    if (data) return data.icon_url;
    const remote = srcs.find(s => s.icon_url && /^https?:\/\//.test(s.icon_url));
    return remote ? remote.icon_url : '';
}

// Name-relevance for search ranking: exact > prefix > name-contains > description-only.
function relevanceScore(name, q) {
    const n = (name || '').toLowerCase();
    if (!q) return 0;
    if (n === q) return 4;
    if (n.startsWith(q)) return 3;
    if (n.includes(q)) return 2;
    return 1; // only matched on description/other fields
}

// Sort search results so name matches lead, then installed, then AUR sanity (non-VCS,
// not-out-of-date, more votes). Reorders across sources, which is what you want for search.
function sortByRelevance(packages, query) {
    const q = (query || '').toLowerCase();
    return (packages || []).map((p, i) => [p, i]).sort((a, b) => {
        const pa = a[0], pb = b[0];
        const ra = relevanceScore(pa.name, q), rb = relevanceScore(pb.name, q);
        if (ra !== rb) return rb - ra;
        if (!!pa.installed !== !!pb.installed) return pa.installed ? -1 : 1;
        const va = aurVariant(pa.name).kind === 'vcs' ? 1 : 0;
        const vb = aurVariant(pb.name).kind === 'vcs' ? 1 : 0;
        if (va !== vb) return va - vb;
        const oa = pa.out_of_date ? 1 : 0, ob = pb.out_of_date ? 1 : 0;
        if (oa !== ob) return oa - ob;
        const sa = typeof pa.votes === 'number' ? pa.votes : -1;
        const sb = typeof pb.votes === 'number' ? pb.votes : -1;
        if (sa !== sb) return sb - sa;
        return a[1] - b[1]; // stable
    }).map(pair => pair[0]);
}

// Numeric sort key: treat missing/non-number as -Infinity so packages without the field
// (e.g. votes/popularity/last_modified on non-AUR sources) sink to the bottom.
function _numKey(v) { return typeof v === 'number' ? v : -Infinity; }

// Apply the chosen sort. 'relevance' preserves today's behaviour (search ranking, else AUR
// ranking); the explicit modes override and sort across all sources. Always stable.
function sortPackages(list, query) {
    const pkgs = list || [];
    if (sortMode === 'relevance') {
        return query ? sortByRelevance(pkgs, query) : rankAur(pkgs);
    }
    const cmp = {
        votes:      (a, b) => _numKey(b.votes) - _numKey(a.votes),
        popularity: (a, b) => _numKey(b.popularity) - _numKey(a.popularity),
        updated:    (a, b) => _numKey(b.last_modified) - _numKey(a.last_modified),
        name:       (a, b) => (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }),
    }[sortMode];
    if (!cmp) return pkgs;
    return pkgs.map((p, i) => [p, i]).sort((x, y) => cmp(x[0], y[0]) || (x[1] - y[1])).map(pair => pair[0]);
}

function renderFiltered() {
    const filtered = filterByType(currentPackages, typeFilter.value);
    const query = searchInput.value.trim();
    renderPackages(sortPackages(filtered, query));
    if (currentView === 'browse' && activeBrowseCategory && currentGroups.length > 0) {
        packagesGrid.insertBefore(browseCategoryHeader(activeBrowseCategory), packagesGrid.firstChild);
    }
}

function nextPackageFetchEpoch() {
    packageFetchEpoch += 1;
    return packageFetchEpoch;
}

function isCurrentPackageFetch(epoch, viewName) {
    return epoch === packageFetchEpoch && viewName === currentView;
}

// Reflect the current grid/list choice on the package grid + the toggle buttons. Layout is
// pure CSS (.view-list on .packages-grid), so this never needs a re-render.
function applyViewMode() {
    packagesGrid.classList.toggle('view-list', viewMode === 'list');
    packagesGrid.classList.toggle('view-grid', viewMode === 'grid');
    document.querySelectorAll('.view-toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.viewMode === viewMode);
    });
}

function setViewMode(mode) {
    viewMode = (mode === 'list') ? 'list' : 'grid';
    localStorage.setItem('atlas_view_mode', viewMode);
    applyViewMode();
}

// --- Display density (localStorage pref applied app-wide via a body class) ---
const DENSITY_MODES = ['comfortable', 'compact', 'dense'];
function densityClass(mode) {
    return 'density-' + (DENSITY_MODES.includes(mode) ? mode : 'comfortable');
}
function applyDensity() {
    if (!document.body) return;
    const cls = densityClass(localStorage.getItem('atlas_density') || 'comfortable');
    DENSITY_MODES.forEach(m => document.body.classList.remove('density-' + m));
    document.body.classList.add(cls);
}
function setDensity(mode) {
    localStorage.setItem('atlas_density', DENSITY_MODES.includes(mode) ? mode : 'comfortable');
    applyDensity();
}

// --- Contextual topbar: the package-list controls (type filter / sort / view-toggle / select)
// only make sense when the main grid is showing a package list. ---
const PACKAGE_LIST_VIEWS = new Set(['installed', 'updates']);
function shouldShowPackageControls(view, hasQuery, inBrowseCategory) {
    if (hasQuery) return true;                       // search results are a package list anywhere
    if (view === 'browse') return !!inBrowseCategory; // landing = categories; open category = packages
    return PACKAGE_LIST_VIEWS.has(view);
}
function applyTopbarContext() {
    const hasQuery = !!(searchInput && searchInput.value.trim());
    const show = shouldShowPackageControls(currentView, hasQuery, !!activeBrowseCategory);
    [typeFilter, sortFilter, document.getElementById('view-toggle'),
     document.getElementById('select-mode-btn')].forEach(el => {
        if (el) el.classList.toggle('hidden', !show);
    });
}

// --- View-render epoch: every navigation bumps this; an async utility-view renderer captures it
// and bails if it's superseded — and only shows a loading spinner if the load is slow *and* still
// current, so rapid page-switching never flashes intermediate spinners/content. ---
let navEpoch = 0;
function pendingSpinner(epoch, html, delay = 160) {
    return setTimeout(() => { if (epoch === navEpoch) packagesGrid.innerHTML = html; }, delay);
}

// --- Shared empty / error state (icon + sentence + optional action), used across views ---
function emptyStateHTML({ icon, title, hint, actionLabel, actionView }) {
    const action = (actionLabel && actionView)
        ? `<button class="empty-state-action" data-empty-view="${escapeHtml(actionView)}">${escapeHtml(actionLabel)}</button>`
        : '';
    return `<div class="empty-state-box">
        <div class="empty-state-icon">${icon || '📭'}</div>
        <div class="empty-state-title">${escapeHtml(title || '')}</div>
        ${hint ? `<div class="empty-state-hint">${escapeHtml(hint)}</div>` : ''}
        ${action}
    </div>`;
}

const MAX_CACHE_ENTRIES = 30;
function writeToCache(key, data) {
    const keys = Object.keys(packageCache);
    if (keys.length >= MAX_CACHE_ENTRIES) {
        delete packageCache[keys[0]]; // FIFO eviction
    }
    packageCache[key] = data;
}


// Function to call Python backend methods
async function pyApiCall(methodName, ...args) {
    if (window.pywebview && window.pywebview.api) {
        try {
            const response = await window.pywebview.api[methodName](...args);
            if (response && response.status === 'error') {
                showToast('Error', response.message, 'error');
                return null;
            }
            return (response && typeof response === 'object' && 'data' in response) ? response.data : response;
        } catch (error) {
            console.error(`Error calling ${methodName}:`, error);
            showToast('Error', `Failed to communicate with backend: ${error}`, 'error');
            return null;
        }
    } else {
        console.warn('pywebview not injected yet. Returning mock data.');
        return mockApi[methodName](...args);
    }
}

// Terminal Watcher Controls called from WebviewWatcher.
// The terminal shows a live "current activity" line, an optional raw log, and — on failure — a
// friendly summary of the likely cause. (A discrete step timeline was attempted but dropped: gems
// don't emit clean phase events — change_status is barely used and some gems blank the substatus —
// so the honest signal is the latest status/substatus/log line.) See
// docs/plans/2026-06-05-transaction-timeline.md.

// Pure: turn the accumulated raw log into a likely-cause summary, most-specific first. Returns
// {title, hint} or null when there's nothing to go on. Node-VM contract-tested.
function summarizeFailure(log) {
    const t = (log || '').toLowerCase();
    if (!t.trim()) return null;
    const has = (...subs) => subs.some(s => t.includes(s));
    if (has('incorrect password', 'authentication failure', 'a password is required', 'sorry, try again'))
        return { title: 'Authentication failed', hint: 'The root password was rejected. Try again and re-enter it.' };
    if (has('signature from', 'unknown trust', 'invalid or corrupted package (pgp', 'could not be looked up', 'corrupted (pgp', 'marginal trust'))
        return { title: 'PGP signature / keyring problem', hint: 'A package signature couldn’t be verified. Update the keyring (e.g. archlinux-keyring) and retry.' };
    if (has('failed retrieving file', ' 404', 'could not resolve host', 'connection timed out', 'unable to connect', 'temporary failure in name resolution', 'failed to download'))
        return { title: 'Download failed', hint: 'A file couldn’t be fetched - a mirror may be down or you’re offline. Refresh mirrors / check your connection and retry.' };
    if (has('conflicting files', 'exists in filesystem'))
        return { title: 'File conflict', hint: 'A package would overwrite files owned by another. The log lists the files - resolve the conflict before retrying.' };
    if (has('conflicting packages', 'are in conflict'))
        return { title: 'Package conflict', hint: 'Two packages conflict and can’t be installed together (see the log).' };
    if (has('unable to satisfy dependency', 'could not find all required packages', 'target not found', 'breaks dependency', 'cannot resolve'))
        return { title: 'Dependency problem', hint: 'A required dependency couldn’t be found or satisfied (see the log).' };
    if (has('==> error', 'build failed', 'a failure occurred in build', 'error: makepkg'))
        return { title: 'Build failed', hint: 'The AUR package failed to build - see the log for the makepkg/compiler error.' };
    return { title: 'The operation failed', hint: 'See the raw log below for details.' };
}

// Pure: strip textual progress-bar glyphs from a status line for clean display (some tools — e.g.
// Flatpak/OSTree — draw a bar out of block/box characters in their output). Only used for the
// activity line; the raw log keeps everything verbatim.
function stripProgressBar(s) {
    return (s || '')
        .replace(/[\u2500-\u25ff]+/g, ' ')  // box-drawing + block elements + geometric shapes
        .replace(/[#=|]{3,}/g, ' ')         // ASCII-style bars
        .replace(/\s{2,}/g, ' ')
        .trim();
}

// Pure: pull a 0–100 percentage out of a status line (e.g. "… 33% 82.7 MB/s") so a tool that reports
// progress as text can still drive the real progress bar. Returns a number or null.
function extractPercent(s) {
    const m = (s || '').match(/(\d{1,3})\s*%/);
    if (!m) return null;
    const v = parseInt(m[1], 10);
    return (v >= 0 && v <= 100) ? v : null;
}

// Pure: pick the line to show as the "current activity" from the latest signals. Prefer the gem's
// substatus, then its high-level status, then the last raw-log line (some gems — e.g. Flatpak —
// blank the substatus and only print), then a generic fallback. Progress-bar glyphs are stripped;
// never returns an empty string.
function pickActivityText({ substatus, status, lastLine } = {}) {
    return stripProgressBar(substatus) || stripProgressBar(status)
        || stripProgressBar(lastLine) || 'Working…';
}

// Pure: highlight one raw log line as HTML (input escaped). Regex-based, no external lib —
// same approach as highlightBashLine. Line classes mirror what pacman/makepkg print in a real
// color terminal (:: bold blue, ==> bold green, ERROR bold red, …); neutral lines get
// whitespace-token inline highlighting (URLs, paths, versions, sizes) — tokenizing on
// whitespace keeps replacements from overlapping each other's inserted markup.
function highlightLogLine(line) {
    line = String(line == null ? '' : line);
    if (/^==> ERROR/i.test(line)) return `<span class="tlog-error">${escapeHtml(line)}</span>`;
    if (/^==> WARNING/i.test(line)) return `<span class="tlog-warn">${escapeHtml(line)}</span>`;
    if (/^==>/.test(line)) return `<span class="tlog-header">${escapeHtml(line)}</span>`;
    if (/^::/.test(line)) return `<span class="tlog-notice">${escapeHtml(line)}</span>`;
    if (/^\s*(error|failed)[: ]/i.test(line)) return `<span class="tlog-error">${escapeHtml(line)}</span>`;
    if (/^\s*warning[: ]/i.test(line)) return `<span class="tlog-warn">${escapeHtml(line)}</span>`;
    const step = /^\s*->\s?/.test(line);
    const tokenClass = (t) => {
        if (/^(https?|ftp):\/\/\S+$/i.test(t)) return 'tlog-url';
        if (/^\/[^\s]+$/.test(t)) return 'tlog-path';
        if (/^[a-z][\w@.+-]*-\d[\w.:+~]*(-\d+)?$/.test(t)) return 'tlog-pkg';   // name-1.2.3-1
        if (/^\(?\d+(\.\d+)*([%)]|\/\d+\)?)?$/.test(t)) return 'tlog-num';      // 42, 3.14, 87%, (3/12)
        if (/^\d[\w.:+~-]*$/.test(t)) return 'tlog-num';                        // versions: 1:2.3-4
        if (/^[KMGT]i?B(\/s)?$/i.test(t)) return 'tlog-num';                    // size units
        return null;
    };
    const body = line.split(/(\s+)/).map(t => {
        if (!t || /^\s+$/.test(t)) return escapeHtml(t);
        const cls = tokenClass(t);
        return cls ? `<span class="${cls}">${escapeHtml(t)}</span>` : escapeHtml(t);
    }).join('');
    return step ? `<span class="tlog-step">${body}</span>` : body;
}

let terminalLogBuffer = '';
let terminalActivity = { substatus: '', status: '', lastLine: '' };

function renderTerminalActivity() {
    const el = document.getElementById('terminal-activity-text');
    if (el) el.textContent = pickActivityText(terminalActivity);
}

window.terminalOpen = (title) => {
    const panel = document.getElementById('terminal-panel');
    const overlay = document.getElementById('terminal-overlay');
    const output = document.getElementById('terminal-output');
    const titleEl = document.getElementById('terminal-title');
    const statusEl = document.getElementById('terminal-status');
    const progressFill = document.getElementById('terminal-progress-fill');
    const doneMsg = document.getElementById('terminal-done-msg');
    const failureEl = document.getElementById('terminal-failure');

    operationInProgress = true;
    terminalLogBuffer = '';
    terminalActivity = { substatus: '', status: '', lastLine: '' };
    titleEl.textContent = title;
    statusEl.textContent = 'Working…';
    statusEl.className = 'terminal-status running';
    progressFill.style.width = '0%';
    progressFill.style.background = 'var(--accent-color)';
    output.innerHTML = '';
    doneMsg.className = 'hidden';
    doneMsg.textContent = '';
    if (failureEl) { failureEl.className = 'terminal-failure hidden'; failureEl.innerHTML = ''; }
    const spinner = document.getElementById('terminal-activity-spinner');
    if (spinner) spinner.classList.remove('done');
    renderTerminalActivity();

    panel.classList.remove('hidden');
    overlay.classList.remove('hidden');

    // Hide close button during run
    document.getElementById('terminal-close').style.display = 'none';
};

function maybeDriveProgress(text) {
    // Tools that report progress as text (e.g. Flatpak/OSTree) can still move the real bar.
    const pct = extractPercent(text);
    if (pct != null) document.getElementById('terminal-progress-fill').style.width = `${pct}%`;
}

window.terminalAppend = (line) => {
    terminalLogBuffer += (line == null ? '' : line) + '\n';
    if (line && line.trim()) {
        terminalActivity.lastLine = line;
        maybeDriveProgress(line);
        renderTerminalActivity();
    }
    const output = document.getElementById('terminal-output');
    const lineEl = document.createElement('span');
    lineEl.className = 'line';
    lineEl.innerHTML = highlightLogLine(line);  // pure, escapes its own input
    output.appendChild(lineEl);
    output.scrollTop = output.scrollHeight;
};

window.terminalSetStatus = (status) => {
    terminalActivity.status = status || '';
    renderTerminalActivity();
};

window.terminalSetSubstatus = (substatus) => {
    terminalActivity.substatus = substatus || '';
    maybeDriveProgress(substatus);
    renderTerminalActivity();
};

window.terminalSetProgress = (val) => {
    document.getElementById('terminal-progress-fill').style.width = `${val}%`;
};

window.terminalSetDone = (success, warnings) => {
    operationInProgress = false;
    packageCache = {}; // Invalidate cache on terminal operation completion

    // Three outcomes: failed (red) / succeeded-with-warnings (amber) / succeeded (green). A warning
    // is a non-fatal advisory from an otherwise-successful transaction (e.g. an optional dependency
    // failed to build) — the main package still installed, so it's not a failure.
    warnings = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
    const warned = success && warnings.length > 0;

    // Stop the activity spinner and settle the line on a final message.
    const spinner = document.getElementById('terminal-activity-spinner');
    if (spinner) spinner.classList.add('done');

    // Settle the progress bar full, tinted by outcome (green / amber / red).
    const fill = document.getElementById('terminal-progress-fill');
    if (fill) {
        fill.style.width = '100%';
        fill.style.background = !success ? 'var(--status-danger)'
                              : warned ? 'var(--status-warning)'
                              : 'var(--status-success)';
    }

    terminalActivity.status = success ? 'Done' : 'Failed';
    terminalActivity.substatus = ''; terminalActivity.lastLine = '';
    renderTerminalActivity();

    const doneMsg = document.getElementById('terminal-done-msg');
    doneMsg.className = !success ? 'terminal-done-error'
                      : warned ? 'terminal-done-warning'
                      : 'terminal-done-success';
    doneMsg.textContent = !success ? '✗ Operation failed.'
                        : warned ? '⚠ Completed with warnings.'
                        : '✓ Operation completed successfully.';

    const statusEl = document.getElementById('terminal-status');
    statusEl.textContent = !success ? 'Failed' : warned ? 'Completed with warnings' : 'Success';
    statusEl.className = 'terminal-status ' + (!success ? 'failed' : warned ? 'warned' : 'ok');

    // Surface a friendly notice above the raw log: the likely failure cause (on failure), or the
    // non-fatal warnings (on success-with-warnings). Reuses the one notice slot, toned by outcome.
    const failureEl = document.getElementById('terminal-failure');
    if (failureEl) {
        if (warned) {
            failureEl.className = 'terminal-failure terminal-failure-warn';
            failureEl.innerHTML = `<div class="terminal-failure-title">The main package was installed</div>` +
                                  warnings.map(w => `<div class="terminal-failure-hint">${escapeHtml(w)}</div>`).join('');
        } else {
            const summary = success ? null : summarizeFailure(terminalLogBuffer);
            if (summary) {
                failureEl.className = 'terminal-failure';
                failureEl.innerHTML = `<div class="terminal-failure-title">${escapeHtml(summary.title)}</div>` +
                                      `<div class="terminal-failure-hint">${escapeHtml(summary.hint)}</div>`;
            } else {
                failureEl.className = 'terminal-failure hidden';
                failureEl.innerHTML = '';
            }
        }
    }

    // Show close button
    document.getElementById('terminal-close').style.display = 'block';

    // Reset any buttons loading spinner
    document.querySelectorAll('.btn.loading').forEach(b => b.classList.remove('loading'));
};

document.getElementById('terminal-close').addEventListener('click', () => {
    document.getElementById('terminal-panel').classList.add('hidden');
    document.getElementById('terminal-overlay').classList.add('hidden');
    refreshCurrentView(); // refresh whatever view is active (not just package lists)
});

// Copy the full raw log to the clipboard.
document.getElementById('terminal-copy').addEventListener('click', () => {
    const text = terminalLogBuffer.trim();
    if (!text) { showToast('Nothing to copy', 'The log is empty', 'info'); return; }
    const done = () => showToast('Copied', 'Full log copied to the clipboard', 'success');
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done, () => { fallbackCopy(text); });
            return;
        }
    } catch (e) { /* fall through */ }
    fallbackCopy(text);
});

// Collapse/expand the raw output (the timeline + status are the primary view).
document.getElementById('terminal-output-toggle').addEventListener('click', () => {
    const wrap = document.getElementById('terminal-output-wrap');
    const toggle = document.getElementById('terminal-output-toggle');
    const collapsed = wrap.classList.toggle('collapsed');
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.textContent = (collapsed ? '▸' : '▾') + ' Raw output';
});

// --- Root password modal ---------------------------------------------------
// Python (AtlasApi._prompt_root_password_once) calls showPasswordModal(); the user's
// answer is sent back via pyApiCall('submit_root_password', value | null), which
// unblocks the waiting worker thread. window.prompt is unsupported in WebKitGTK, so
// this HTML modal replaces it.
let passwordResolved = false;

function submitPassword(value) {
    if (passwordResolved) return;
    passwordResolved = true;
    document.getElementById('password-modal').classList.add('hidden');
    pyApiCall('submit_root_password', value);
}

window.showPasswordModal = (message) => {
    passwordResolved = false;
    const modal = document.getElementById('password-modal');
    const input = document.getElementById('password-input');
    document.getElementById('password-message').textContent = message || 'Enter your password:';
    input.value = '';
    modal.classList.remove('hidden');
    setTimeout(() => input.focus(), 50);
};

document.getElementById('password-submit-btn').addEventListener('click', () => {
    submitPassword(document.getElementById('password-input').value);
});
document.getElementById('password-cancel-btn').addEventListener('click', () => {
    submitPassword(null);
});
document.getElementById('password-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        submitPassword(document.getElementById('password-input').value);
    } else if (e.key === 'Escape') {
        submitPassword(null);
    }
});

// --- Confirmation modal ----------------------------------------------------
// Python (AtlasApi.prompt_confirmation) calls showConfirmModal(); the choice is sent
// back via submit_confirmation(bool, selections), unblocking the waiting worker thread.
// Replaces window.confirm, which WebKitGTK does not support. Input components (optdep
// checklists, missing-deps lists, provider choices) are rendered into #confirm-components
// and the per-component selections are returned for the gem code to read.
let confirmResolved = false;
let confirmComponents = [];

function resolveConfirm(value) {
    if (confirmResolved) return;
    confirmResolved = true;
    const selections = value ? collectComponentSelections(confirmComponents) : null;
    document.getElementById('confirm-modal').classList.add('hidden');
    pyApiCall('submit_confirmation', value, selections);
}

// Build the DOM for a serialized component and return its selection-reader closure.
function renderConfirmComponent(comp, container) {
    if (comp.kind === 'text') {
        const p = document.createElement('div');
        p.className = 'confirm-component-text';
        p.innerHTML = comp.html || '';
        container.appendChild(p);
        return () => null;
    }

    const wrap = document.createElement('div');
    wrap.className = 'confirm-component';
    if (comp.label) {
        const lbl = document.createElement('div');
        lbl.className = 'confirm-component-label';
        lbl.textContent = comp.label;
        wrap.appendChild(lbl);
    }

    if (comp.kind === 'form') {
        const childReaders = (comp.components || []).map(c => renderConfirmComponent(c, wrap));
        container.appendChild(wrap);
        return () => childReaders.map(r => r());
    }

    if (comp.kind === 'singleselect' && comp.selectType === 'combo') {
        const sel = document.createElement('select');
        sel.className = 'confirm-select';
        (comp.options || []).forEach(o => {
            const opt = document.createElement('option');
            opt.value = String(o.oi);
            opt.textContent = o.label;
            if (o.tooltip) opt.title = o.tooltip;
            if (o.selected) opt.selected = true;
            sel.appendChild(opt);
        });
        wrap.appendChild(sel);
        container.appendChild(wrap);
        return () => (sel.value === '' ? null : parseInt(sel.value, 10));
    }

    // checkbox list (multiselect) or radio list (singleselect)
    const isMulti = comp.kind === 'multiselect';
    const inputType = isMulti ? 'checkbox' : 'radio';
    const groupName = 'confirm-opt-' + Math.random().toString(36).slice(2);
    const inputs = [];
    (comp.options || []).forEach(o => {
        const row = document.createElement('label');
        row.className = 'confirm-option';
        if (o.tooltip) row.title = o.tooltip;
        const input = document.createElement('input');
        input.type = inputType;
        input.name = groupName;
        input.value = String(o.oi);
        input.checked = !!o.selected;
        if (o.readOnly) input.disabled = true;
        row.appendChild(input);
        if (o.icon) {
            const icon = document.createElement('img');
            icon.className = 'confirm-option-icon';
            icon.src = o.icon;
            icon.alt = '';
            row.appendChild(icon);
        }
        const span = document.createElement('span');
        span.textContent = o.label;
        row.appendChild(span);
        wrap.appendChild(row);
        inputs.push(input);
    });
    container.appendChild(wrap);

    if (isMulti) {
        return () => inputs.filter(i => i.checked).map(i => parseInt(i.value, 10));
    }
    return () => {
        const checked = inputs.find(i => i.checked);
        return checked ? parseInt(checked.value, 10) : null;
    };
}

function renderConfirmComponents(components) {
    const host = document.getElementById('confirm-components');
    host.innerHTML = '';
    confirmComponents = [];
    (components || []).forEach(comp => {
        const reader = renderConfirmComponent(comp, host);
        confirmComponents.push({ reader });
    });
    host.style.display = (components && components.length) ? 'block' : 'none';
}

function collectComponentSelections(comps) {
    return comps.map(c => c.reader());
}

// Rich PKGBUILD review block inside the confirm modal (advisory AUR safety helper). Renders the
// colored diff-since-last-build + severity-flagged lines. `review` is null for ordinary confirms.
function renderPkgbuildReview(review) {
    const host = document.getElementById('confirm-review');
    const content = document.querySelector('#confirm-modal .modal-content');
    if (!review) {
        host.style.display = 'none';
        host.innerHTML = '';
        if (content) content.classList.remove('has-review');
        return;
    }
    const s = review.summary || {};
    const banner = (s.warn || s.info)
        ? `<div class="review-banner ${s.warn ? 'warn' : 'info'}">⚠ ${s.warn || 0} line${s.warn === 1 ? '' : 's'} worth a look${s.info ? ` · ${s.info} minor` : ''} - a hint, not a safety check</div>`
        : '';

    let maintHtml = '';
    const mc = review.maintainer_change;
    if (mc) {
        const oldM = escapeHtml(mc.old || 'unknown');
        const newM = mc.new ? escapeHtml(mc.new) : '<em>orphaned (no maintainer)</em>';
        maintHtml = `<div class="review-banner warn">⚠ Maintainer changed since you installed: <strong>${oldM} → ${newM}</strong>. The package changed hands - worth a look before updating.</div>`;
    }

    let diffHtml = '';
    if ((review.diff || []).length) {
        const rows = review.diff.map(d =>
            `<div class="diff-line diff-${d.kind}">${escapeHtml(d.text)}</div>`).join('');
        diffHtml = `<h4 class="review-h">Changed since your last build</h4><div class="review-diff">${rows}</div>`;
    }

    let findHtml = '';
    if ((review.findings || []).length) {
        const items = review.findings.map(f => `
            <li class="review-finding sev-${escapeHtml(f.severity)}">
                <div class="finding-head"><span class="finding-line">L${f.line_no}</span>${escapeHtml(f.why)}</div>
                <code class="finding-code">${escapeHtml((f.line || '').slice(0, 200))}</code>
            </li>`).join('');
        findHtml = `<h4 class="review-h">Lines worth a look</h4><ul class="review-findings">${items}</ul>`;
    }

    // The actual files (PKGBUILD + .install scriptlets), collapsed — so "read the PKGBUILD"
    // is one click away instead of requiring the user to cancel and hunt the package down.
    let filesHtml = '';
    (review.files || []).forEach((f, i) => {
        if (!f || !f.text) return;
        const lineCount = String(f.text).split('\n').length;
        filesHtml += `
            <details class="review-pkgb-file">
                <summary>Read <span class="review-pkgb-name">${escapeHtml(f.name || 'PKGBUILD')}</span> · ${lineCount} lines</summary>
                <div class="pkgbuild-code review-code">${buildPkgbuildCodeHTML(f.text, f.findings, `crv-${i}-line-`)}</div>
            </details>`;
    });

    host.innerHTML = maintHtml + banner + diffHtml + findHtml + filesHtml;
    host.style.display = 'block';
    if (content) content.classList.add('has-review');
}

window.showConfirmModal = (opts) => {
    opts = opts || {};
    confirmResolved = false;
    document.getElementById('confirm-title').textContent = opts.title || 'Confirm';
    document.getElementById('confirm-message').textContent = opts.message || '';
    renderPkgbuildReview(opts.review);
    renderConfirmComponents(opts.components);
    const acceptBtn = document.getElementById('confirm-accept-btn');
    const denyBtn = document.getElementById('confirm-deny-btn');
    acceptBtn.textContent = opts.confirmLabel || 'Yes';
    denyBtn.textContent = opts.denyLabel || 'No';
    denyBtn.style.display = (opts.showDeny === false) ? 'none' : 'block';
    document.getElementById('confirm-modal').classList.remove('hidden');
    setTimeout(() => acceptBtn.focus(), 50);
};

document.getElementById('confirm-accept-btn').addEventListener('click', () => resolveConfirm(true));
document.getElementById('confirm-deny-btn').addEventListener('click', () => resolveConfirm(false));
document.getElementById('confirm-modal').addEventListener('keydown', (e) => {
    if (e.key === 'Escape') resolveConfirm(false);
});

// --- Message modal ---------------------------------------------------------
// Python (AtlasApi.prompt_message) calls showMessageModal(); OK acks via
// submit_message_ack(). Replaces window.alert.
let messageResolved = false;

function resolveMessage() {
    if (messageResolved) return;
    messageResolved = true;
    document.getElementById('message-modal').classList.add('hidden');
    pyApiCall('submit_message_ack');
}

// --- Arch news gate (client-side, before Update All) -----------------------
// Self-contained + promise-based: resolves true (proceed) / false (cancel). Not the confirm
// modal, which is wired to the Python watcher's submit_confirmation.
let newsGateResolver = null;

function resolveNewsGate(proceed) {
    document.getElementById('news-gate-modal').classList.add('hidden');
    const resolve = newsGateResolver;
    newsGateResolver = null;
    if (resolve) resolve(proceed);
}

function showNewsGate(items) {
    const list = document.getElementById('news-gate-list');
    list.innerHTML = (items || []).map(n => `
        <article class="news-card">
            <div class="news-card-head">
                <h3 class="news-title">${escapeHtml(n.title)}</h3>
                ${n.date ? `<span class="news-date">${escapeHtml(n.date)}</span>` : ''}
            </div>
            ${n.summary ? `<p class="news-summary">${escapeHtml(n.summary)}</p>` : ''}
            ${safeExternalUrl(n.url) ? `<a class="news-link" href="#" data-news-url="${escapeHtml(safeExternalUrl(n.url))}">Read on archlinux.org ↗</a>` : ''}
        </article>`).join('');
    list.querySelectorAll('a[data-news-url]').forEach(a => {
        a.addEventListener('click', (e) => { e.preventDefault(); openExternalUrl(a.dataset.newsUrl); });
    });
    document.getElementById('news-gate-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('news-gate-cancel-btn').focus(), 50);
    return new Promise(resolve => { newsGateResolver = resolve; });
}

document.getElementById('news-gate-proceed-btn').addEventListener('click', () => resolveNewsGate(true));
document.getElementById('news-gate-cancel-btn').addEventListener('click', () => resolveNewsGate(false));
document.getElementById('news-gate-modal').addEventListener('keydown', (e) => {
    if (e.key === 'Escape') resolveNewsGate(false);
});

// --- Transaction preview (pre-flight, before install) ----------------------
// Self-contained + promise-based like the news gate (the confirm modal is bound to the Python
// watcher and can't be reused). Resolves true (proceed) / false (cancel). buildTransactionPreviewHTML
// is pure (escapeHtml + formatBytes only) so it's unit-testable in the Node VM harness.
// See docs/plans/2026-06-04-transaction-preview.md.
// ---- Dependency tree renderer (AUR install preview) ----
// Renders a recursive tree of {name, source, warnings:[{label,level}], deps:[...]}.
// Row = caret/spacer + colored dot + mono name + chips. The dot carries the source color
// (green repo / amber AUR / red AUR-with-warnings); only AUR rows get a chip — labeling every
// repo row was noise. Nesting comes from the .dep-tree-children container alone (no per-node
// indent spans). Subtrees with children are collapsible.
function renderDepTree(nodes) {
    if (!nodes || !nodes.length) return '';
    return nodes.map(node => {
        const isAur = node.source === 'aur';
        const hasWarnings = node.warnings && node.warnings.length > 0;
        const hasChildren = node.deps && node.deps.length > 0;
        const cssClass = isAur ? (hasWarnings ? 'aur-danger' : 'aur-clean') : 'repo';
        const sourceBadge = isAur ? '<span class="dep-tree-source aur">AUR</span>' : '';
        const warnBadges = (node.warnings || []).map(w =>
            `<span class="dep-tree-warn dep-tree-warn-${escapeHtml(w.level)}" title="${escapeHtml(w.label)}">${escapeHtml(w.label)}</span>`
        ).join('');
        // Spacer keeps dots/names aligned between rows with and without a caret.
        const toggleIcon = hasChildren ? `<span class="dep-tree-toggle" onclick="this.parentElement.parentElement.querySelector('.dep-tree-children').classList.toggle('hidden');this.textContent=this.textContent==='▸'?'▾':'▸'">▾</span>`
                                       : '<span class="dep-tree-toggle-spacer"></span>';
        let html = `<div class="dep-tree-node ${cssClass}">${toggleIcon}<span class="dep-tree-dot"></span><span class="dep-tree-name">${escapeHtml(node.name)}</span>${sourceBadge}${warnBadges}</div>`;
        if (hasChildren) {
            html += `<div class="dep-tree-children">${renderDepTree(node.deps)}</div>`;
        }
        return html;
    }).join('');
}

function buildTransactionPreviewHTML(data) {
    data = data || {};
    const action = data.action || 'install';
    const sourceLabel = escapeHtml(data.source_label || '');
    const version = escapeHtml(data.version || '');
    const fromVersion = escapeHtml(data.from_version || '');
    const versionText = (action === 'update' && fromVersion && version)
        ? `v${fromVersion} → v${version}` : (version ? `v${version}` : '');
    const sizes = data.sizes || null;
    const deps = data.deps || { direct: [], optional: [] };
    const warnings = data.warnings || [];
    const perms = data.permissions || null;
    const notes = data.notes || [];

    let html = `<div class="txp-header">
        <div class="txp-title">${escapeHtml(data.name || 'package')}</div>
        <div class="txp-sub">
            ${sourceLabel ? `<span class="txp-source-pill">${sourceLabel}</span>` : ''}
            ${versionText ? `<span class="txp-version">${versionText}</span>` : ''}
        </div>
    </div>`;

    if (sizes && (sizes.download != null || sizes.installed != null)) {
        const installedLabel = action === 'uninstall' ? 'Frees' : 'Installed';
        html += `<div class="txp-sizes">`;
        if (sizes.download != null) html += `<span class="txp-size"><span class="txp-size-label">Download</span> ${formatBytes(sizes.download)}</span>`;
        if (sizes.installed != null) html += `<span class="txp-size"><span class="txp-size-label">${installedLabel}</span> ${formatBytes(sizes.installed)}</span>`;
        html += `</div>`;
    }

    // Update-All source chooser: tick which sources to include in this bulk upgrade. Lets the
    // user skip e.g. AUR (community-maintained, less vetted) without updating package-by-package.
    if (action === 'update-all' && Array.isArray(data.sources) && data.sources.length > 1) {
        html += `<div class="txp-sources"><div class="txp-sources-head">Sources to update</div>` +
            data.sources.map(s => `
            <label class="txp-source-toggle">
                <input type="checkbox" data-source="${escapeHtml(s.key)}" data-count="${s.count}"${s.checked ? ' checked' : ''}>
                <span class="txp-source-name tag ${escapeHtml(normalizeType(s.key))}">${escapeHtml(s.label)}</span>
                <span class="txp-source-count">${s.count}</span>
            </label>`).join('') + `</div>`;
    }

    if (data.aur_risk && data.aur_risk.score !== undefined) {
        const tierLabel = { trusted: 'Trusted', caution: 'Caution', risk: 'Risk' }[data.aur_risk.tier] || data.aur_risk.tier;
        html += `<div class="txp-risk-indicator risk-${escapeHtml(data.aur_risk.tier)}" title="Composite AUR trust score - heuristic only, not a safety check">
            <span class="material-symbols-outlined">shield</span>
            <span class="txp-risk-text">Reputation: ${data.aur_risk.score}/100 · ${escapeHtml(tierLabel)}</span>
        </div>`;
    }

    if (warnings.length) {
        const order = { danger: 0, warn: 1, info: 2 };
        const sorted = warnings.slice().sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3));
        html += `<div class="txp-warnings">` + sorted.map(w => {
            const level = w.level || 'info';
            const colorClass = level === 'danger' ? 'perm-icon-danger' : (level === 'warn' ? 'perm-icon-warn' : 'perm-icon-info');
            return `
            <div class="txp-warn txp-warn-${escapeHtml(level)}">
                <div class="rich-badge-icon ${colorClass}"><span class="material-symbols-outlined">${getWarningIcon(w.title, level)}</span></div>
                <div class="txp-warn-text">
                    <div class="txp-warn-title">${escapeHtml(w.title || '')}</div>
                    ${w.detail ? `<div class="txp-warn-detail">${escapeHtml(w.detail)}</div>` : ''}
                </div>
            </div>`;
        }).join('') + `</div>`;
    }

    if (perms && perms.length) {
        html += `<details class="txp-accordion"><summary>Permissions (${perms.length})</summary><div class="txp-acc-body">` +
            perms.map(p => {
                const level = p.level || 'safe';
                const colorClass = level === 'danger' ? 'perm-icon-danger' : (level === 'warn' ? 'perm-icon-warn' : 'perm-icon-safe');
                return `<div class="txp-perm txp-perm-${escapeHtml(level)}">
                <div class="rich-badge-icon ${colorClass}"><span class="material-symbols-outlined">${getPermissionIcon(p.title)}</span></div>
                <div class="txp-perm-text">
                    <span class="txp-perm-title">${escapeHtml(p.title || '')}</span>
                    ${p.detail ? `<span class="txp-perm-detail">${escapeHtml(p.detail)}</span>` : ''}
                </div>
            </div>`;
            }).join('') + `</div></details>`;
    }

    const direct = deps.direct || [];
    const optional = deps.optional || [];
    const depTree = data.dep_tree;
    if (depTree && depTree.length) {
        // Visual dependency tree — replaces the flat chip list for AUR installs where
        // we want the user to see what's getting pulled in, color-coded by risk.
        const treeHtml = renderDepTree(depTree);
        const treeLegend = `<div class="dep-tree-legend">
            <span class="dep-tree-legend-item repo">official repo</span>
            <span class="dep-tree-legend-item aur">AUR</span>
            <span class="dep-tree-legend-item warn">AUR with warnings</span>
        </div>`;
        html += `<details class="txp-accordion" open><summary>Dependency tree (${depTree.length} direct)</summary><div class="txp-acc-body">${treeHtml}${treeLegend}</div></details>`;
    } else if (direct.length || optional.length) {
        html += `<details class="txp-accordion"><summary>Dependencies (${direct.length} required${optional.length ? `, ${optional.length} optional` : ''})</summary><div class="txp-acc-body">`;
        if (direct.length) {
            html += `<div class="txp-dep-group"><div class="txp-dep-head">Direct requirements</div><div class="txp-dep-list">` +
                direct.map(d => `<span class="txp-dep-chip">${escapeHtml(d)}</span>`).join('') + `</div></div>`;
        }
        if (optional.length) {
            html += `<div class="txp-dep-group"><div class="txp-dep-head">Optional</div>` +
                optional.map(o => `<div class="txp-optdep"><span class="txp-dep-chip">${escapeHtml(o.name || '')}</span>${o.detail ? `<span class="txp-optdep-detail">${escapeHtml(o.detail)}</span>` : ''}</div>`).join('') + `</div>`;
        }
        html += `</div></details>`;
    }

    if (notes.length) {
        html += `<div class="txp-notes">` + notes.map(n => `<div class="txp-note">${escapeHtml(n)}</div>`).join('') + `</div>`;
    }
    return html;
}

let txPreviewResolver = null;

function resolveTxPreview(proceed) {
    document.getElementById('tx-preview-modal').classList.add('hidden');
    const resolve = txPreviewResolver;
    txPreviewResolver = null;
    if (resolve) resolve(proceed);
}

// Per-action copy for the shared preview modal. Keyed off data.action so install / uninstall /
// downgrade reuse one modal + one renderer.
const TX_PREVIEW_COPY = {
    install:      { title: n => `Install ${n}?`,    desc: "Here's what this will do. The full dependency set is resolved at install time.", btn: 'Install',    danger: false },
    uninstall:    { title: n => `Remove ${n}?`,     desc: "Here's what removing this will do.",                                            btn: 'Remove',     danger: true  },
    downgrade:    { title: n => `Downgrade ${n}?`,  desc: "Here's what rolling this back will do.",                                        btn: 'Downgrade',  danger: false },
    update:       { title: n => `Update ${n}?`,     desc: "Here's what updating this will do.",                                            btn: 'Update',     danger: false },
    'update-all': { title: n => `Update ${n}?`,     desc: "Here's everything that will be upgraded.",                                      btn: 'Update All', danger: false },
};

// Fetch the equivalent terminal command for a transaction and copy it to the clipboard. Shows the
// command (+ any note, e.g. the AUR-helper alternative) in a toast so the user sees what they got.
async function copyEquivalentCommand(pkgId, action, btn) {
    const data = await pyApiCall('get_command', pkgId, action);
    const command = data && data.command;
    if (!command) {
        showToast('No command', 'No equivalent one-liner for this action', 'info');
        return;
    }
    const finish = () => {
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = '✓ Copied';
            setTimeout(() => { btn.textContent = orig; }, 1500);
        }
        showToast('Copied command', data.note ? `${command}\n${data.note}` : command, 'success');
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(command).then(finish).catch(() =>
            showToast('Copied command', command, 'success'));
    } else {
        finish();
    }
}

function openTransactionPreview(data, pkgId) {
    const copy = TX_PREVIEW_COPY[(data && data.action) || 'install'] || TX_PREVIEW_COPY.install;
    const name = (data && data.name) || 'package';
    document.getElementById('tx-preview-body').innerHTML = buildTransactionPreviewHTML(data);

    // "View PKGBUILD" — the natural review moment for an AUR build. AUR only, and only when we have
    // a single package id to fetch (not the Update-All aggregate).
    const pkgbBtn = document.getElementById('tx-preview-pkgbuild-btn');
    if (pkgbBtn) {
        const isAur = data && data.source_label === 'AUR' && pkgId;
        pkgbBtn.classList.toggle('hidden', !isAur);
        pkgbBtn.onclick = isAur ? () => openPkgbuildViewer({ id: pkgId, name, type: 'aur' }) : null;
    }

    // "Copy command" — the equivalent terminal command for this transaction (CLI users; nothing
    // hidden). Single-package actions only (not the Update-All aggregate, which has no single id).
    const copyCmdBtn = document.getElementById('tx-preview-copy-cmd-btn');
    if (copyCmdBtn) {
        const act = (data && data.action) || 'install';
        const eligible = pkgId && ['install', 'update', 'uninstall'].includes(act);
        copyCmdBtn.classList.toggle('hidden', !eligible);
        copyCmdBtn.textContent = '⧉ Copy command';
        copyCmdBtn.onclick = eligible ? () => copyEquivalentCommand(pkgId, act, copyCmdBtn) : null;
    }
    const title = document.getElementById('tx-preview-title');
    if (title) title.textContent = copy.title(name);
    const desc = document.getElementById('tx-preview-desc');
    if (desc) desc.textContent = copy.desc;
    const proceed = document.getElementById('tx-preview-proceed-btn');
    if (proceed) {
        proceed.textContent = copy.btn;
        proceed.classList.toggle('btn-danger', !!copy.danger);
        proceed.classList.toggle('btn-primary', !copy.danger);
        proceed.disabled = false;
    }

    // Update-All source chooser: keep the proceed button's count in sync with the ticked sources
    // and disable it when nothing is selected (nothing to do).
    const sourceToggles = [...document.querySelectorAll('#tx-preview-body input[data-source]')];
    if (proceed && sourceToggles.length) {
        const syncProceed = () => {
            const n = sourceToggles.filter(t => t.checked)
                                   .reduce((sum, t) => sum + (parseInt(t.dataset.count, 10) || 0), 0);
            proceed.textContent = n > 0 ? `Update ${n}` : 'Nothing selected';
            proceed.disabled = n === 0;
        };
        sourceToggles.forEach(t => t.addEventListener('change', syncProceed));
        syncProceed();
    }

    document.getElementById('tx-preview-modal').classList.remove('hidden');
    setTimeout(() => proceed && proceed.focus(), 50);
    return new Promise(resolve => { txPreviewResolver = resolve; });
}

// Fetch a preview and show the modal; resolves whether to proceed. pyApiCall unwraps the
// {status,data} envelope, so `data` here is the preview payload itself. Backend fails open (always
// returns a payload with at least `name`); we only skip the gate if the bridge returns nothing
// (null on error / not injected) — never block the user.
const TX_PREVIEW_API = { install: 'get_install_preview', uninstall: 'get_uninstall_preview', downgrade: 'get_downgrade_preview', update: 'get_update_preview' };

async function showTransactionPreview(id, action = 'install') {
    const data = await pyApiCall(TX_PREVIEW_API[action] || TX_PREVIEW_API.install, id);
    if (!data || typeof data !== 'object' || !data.name) return true;
    return openTransactionPreview(data, id);
}

// Back-compat thin wrapper (install path + existing tests/command palette).
async function showInstallPreview(id) {
    return showTransactionPreview(id, 'install');
}

// Pure builder: shape an Update-All aggregate into a tx-preview `data` payload so it reuses the
// same modal + renderer. Built frontend-side from the already-loaded updates list (no second slow
// read_installed). `extras` carries the cheap news/.pacnew counts. Node-VM contract-tested.
function buildUpdateAllPreviewData(updates, extras) {
    updates = Array.isArray(updates) ? updates : [];
    extras = extras || {};
    const counts = { arch: 0, aur: 0, flatpak: 0, other: 0 };
    let totalDownload = 0, sizedCount = 0;
    for (const p of updates) {
        const t = normalizeType(p.type);
        if (t === 'aur') counts.aur++;
        else if (t === 'flatpak') counts.flatpak++;
        else if (t === 'arch' || t === 'arch_repo') counts.arch++;
        else counts.other++;
        if (typeof p.download_size === 'number') { totalDownload += p.download_size; sizedCount++; }
    }
    const n = updates.length;
    // Source toggles for the preview. Built from the actual update types so each distinct
    // source key (matching the serialized `type`, which the backend filter also uses) gets its
    // own toggle with a correct count — including any enabled-but-off-by-default source. Offered
    // in trust order. `extras.excluded` (remembered skip list) pre-unchecks a source so e.g. AUR
    // stays off between runs.
    const excluded = new Set(extras.excluded || []);
    const SRC_RANK = { arch_repo: 0, aur: 1, flatpak: 2, appimage: 3 };
    const byKey = new Map();
    for (const p of updates) {
        const key = normalizeType(p.type);
        byKey.set(key, (byKey.get(key) || 0) + 1);
    }
    const sources = [...byKey.entries()]
        .map(([key, count]) => ({ key, label: sourceLabel(key), count, checked: !excluded.has(key) }))
        .sort((a, b) => (SRC_RANK[a.key] ?? 9) - (SRC_RANK[b.key] ?? 9));
    const data = {
        action: 'update-all',
        name: `${n} package${n === 1 ? '' : 's'}`,
        source_label: '', version: '',
        sizes: sizedCount > 0 ? { download: totalDownload, installed: null } : null,
        deps: { direct: [], optional: [] }, permissions: null, warnings: [], notes: [],
        sources: sources.length > 1 ? sources : null,  // a single source needs no chooser
    };
    const parts = [];
    if (counts.arch) parts.push(`Arch: ${counts.arch}`);
    if (counts.aur) parts.push(`AUR: ${counts.aur}`);
    if (counts.flatpak) parts.push(`Flatpak: ${counts.flatpak}`);
    if (counts.other) parts.push(`Other: ${counts.other}`);
    if (parts.length) data.notes.push(parts.join(' · '));
    if (counts.aur) data.notes.push('AUR packages are rebuilt from source - their download size and build time are not included above.');
    if (sizedCount > 0 && sizedCount < n) data.notes.push('Download size shown covers only the packages that report one.');

    const newsCount = extras.news_count || 0;
    if (newsCount > 0) {
        data.warnings.push({ level: 'warn', title: `${newsCount} unread Arch news item${newsCount === 1 ? '' : 's'}`,
            detail: "Published since your last sync - review before upgrading (shown next)." });
    }
    const pacnewCount = extras.pacnew_count || 0;
    if (pacnewCount > 0) {
        data.warnings.push({ level: 'info', title: `${pacnewCount} config file${pacnewCount === 1 ? '' : 's'} to review`,
            detail: '.pacnew/.pacsave files from a previous upgrade are still pending in the Updates view.' });
    }

    // AUR reputation tiers (from a single batched get_update_risk_tiers call) — categorize, don't
    // gate: Update All still updates everything in one shot, this only surfaces what to look at.
    const tiers = extras.tiers;
    if (tiers && tiers.counts) {
        const c = tiers.counts;
        data.notes.push(`${c.safe || 0} safe to update · ${c.caution || 0} worth a review · ${c.risk || 0} high risk`);
        if (c.risk > 0 && tiers.tiers) {
            const riskyNames = updates
                .filter(p => (tiers.tiers[p.id] || {}).tier === 'risk')
                .map(p => p.name);
            if (riskyNames.length) {
                data.warnings.push({ level: 'warn', title: `${riskyNames.length} package${riskyNames.length === 1 ? '' : 's'} with a low reputation score`,
                    detail: `${riskyNames.join(', ')} - low AUR votes/age, orphaned, or a recent maintainer change. Worth a look before updating.` });
            }
        }
    }
    return data;
}

document.getElementById('tx-preview-proceed-btn').addEventListener('click', () => resolveTxPreview(true));
document.getElementById('tx-preview-cancel-btn').addEventListener('click', () => resolveTxPreview(false));
document.getElementById('tx-preview-modal').addEventListener('keydown', (e) => {
    if (e.key === 'Escape') resolveTxPreview(false);
});

window.showMessageModal = (opts) => {
    opts = opts || {};
    messageResolved = false;
    document.getElementById('message-title').textContent = opts.title || 'Notice';
    document.getElementById('message-body').textContent = opts.message || '';
    const okBtn = document.getElementById('message-ok-btn');
    document.getElementById('message-modal').classList.remove('hidden');
    setTimeout(() => okBtn.focus(), 50);
};

document.getElementById('message-ok-btn').addEventListener('click', resolveMessage);
document.getElementById('message-modal').addEventListener('keydown', (e) => {
    if (e.key === 'Escape' || e.key === 'Enter') resolveMessage();
});

// Fallback placeholder icon (Base64 encoded SVG)
const ICON_PLACEHOLDER = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iIzY0NzQ4YiIgdmlld0JveD0iMCAwIDI0IDI0Ij48cmVjdCB4PSIzIiB5PSIzIiB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHJ4PSIyIiByeT0iMiI+PC9yZWN0Pjwvc3ZnPg==';

// Determine whether an icon URL is safe to assign directly to src (won't 404)
// base64 data URIs are safe. Remote http(s) URLs are NOT safe (upstream repos delete icons).
// Bare filenames without paths are invalid.
function getIconSrc(iconUrl) {
    if (!iconUrl) return ICON_PLACEHOLDER;
    if (iconUrl.startsWith('data:')) return iconUrl; // base64 — always safe
    return ICON_PLACEHOLDER; // Everything else (remote URLs, bare filenames) gets placeholder
}

// Returns the original URL only if it's a remote URL worth probing, empty string otherwise
function getIconDataSrc(iconUrl) {
    if (!iconUrl) return '';
    if (iconUrl.startsWith('data:')) return ''; // already handled by getIconSrc
    if (iconUrl.startsWith('http://') || iconUrl.startsWith('https://')) return iconUrl;
    return ''; // bare filenames, file:// etc — already handled by backend base64 encoding
}

// --- Multi-source grouping (Phase 2a) --------------------------------------
// Collapse packages that are the same app offered by different sources (Arch / AUR /
// Flatpak / AppImage) into one card with a source switcher. Different *names* stay
// separate (so AUR -bin/-git variants and forks remain their own cards). Order is
// preserved from the already-ranked input (first occurrence sets the group's position).
const SOURCE_PREF = { arch_repo: 0, aur: 1, flatpak: 2, appimage: 3 };  // trust/preference order
// AUR build preference for the *default* option: prefer a stable build (binary/source) over a
// bleeding-edge VCS (-git) build, so a grouped card never defaults to -git.
function aurBuildRank(p) {
    if (normalizeType(p.type) !== 'aur') return 0;
    const k = aurVariant(p.name).kind;
    return k === 'vcs' ? 2 : (k === 'debug' ? 1 : 0);
}

function compareSourcePreference(a, b) {
    if (!!a.installed !== !!b.installed) return a.installed ? -1 : 1;  // installed source wins
    const pa = SOURCE_PREF[normalizeType(a.type)] ?? 9;
    const pb = SOURCE_PREF[normalizeType(b.type)] ?? 9;
    if (pa !== pb) return pa - pb;
    return aurBuildRank(a) - aurBuildRank(b);  // tie-break within a source: stable build first
}
// Build-method suffixes that mean "same app, different build" — stripped for grouping so
// foo / foo-bin / foo-git collapse into one card. Deliberately NOT channel suffixes
// (-beta/-dev/-nightly): those are genuinely different apps/channels and must stay separate.
const AUR_BUILD_SUFFIXES = ['-bin', '-git', '-svn', '-hg', '-bzr', '-cvs', '-darcs'];

function stripBuildSuffix(name) {
    let n = String(name == null ? '' : name).trim();
    let changed = true;
    while (changed) {                  // handles the rare chained case (e.g. foo-git-bin)
        changed = false;
        for (const suf of AUR_BUILD_SUFFIXES) {
            if (n.length > suf.length && n.toLowerCase().endsWith(suf)) {
                n = n.slice(0, -suf.length); changed = true; break;
            }
        }
    }
    return n;
}

// Group key for cross-source collapsing: drop the build-method suffix, lowercase, and strip
// separators so a Flatpak's display name and an AUR/repo package name for the same app line up —
// "Google Chrome" ≙ "google-chrome", "Brave" ≙ "brave-bin" ≙ "brave-git". Conservative: it bridges
// punctuation/casing/build-method without token-matching that could merge genuinely distinct apps.
function groupKey(name) {
    return stripBuildSuffix(name).toLowerCase().replace(/[\s._-]+/g, '');
}

// A source's "option" identity inside a group: the source type, plus the AUR build variant so
// foo-bin and foo-git read as two distinct *options* (not same-source dupes). Two sources sharing
// a signature (e.g. two Flatpaks with the same display name) are genuinely different packages and
// must NOT be folded into a fake switcher.
function sourceOptionSig(p) {
    const t = normalizeType(p.type);
    return t === 'aur' ? `aur:${aurVariant(p.name).label}` : t;
}

// Short plain-text label for a source — for AUR it names the build variant so multiple AUR options
// in one group are tellable apart ("AUR bin" / "AUR git" / "AUR"). Used for titles/aria.
function sourcePillLabel(s) {
    if (normalizeType(s.type) !== 'aur') return sourceLabel(s.type);
    const v = aurVariant(s.name);
    if (v.kind === 'source') return 'AUR';
    return `AUR ${v.kind === 'binary' ? 'bin' : v.label}`;
}

// CSS modifier for an AUR build variant (drives the coloured chip): bin / vcs / other.
function aurKindClass(s) {
    const v = aurVariant(s.name);
    return v.kind === 'binary' ? 'bin' : (v.kind === 'vcs' ? 'vcs' : 'other');
}

// Display HTML for a source pill — same as the label, but the AUR build variant is a distinct
// coloured chip after "AUR" so "AUR" (source) and "AUR bin"/"AUR git" don't read as duplicates.
function sourcePillHTML(s) {
    if (normalizeType(s.type) !== 'aur') return escapeHtml(sourceLabel(s.type));
    const v = aurVariant(s.name);
    if (v.kind === 'source') return 'AUR';
    const short = v.kind === 'binary' ? 'bin' : v.label;
    return `AUR<span class="aur-kind aur-kind-${aurKindClass(s)}">${escapeHtml(short)}</span>`;
}

function collapseByName(packages) {
    const order = [], map = new Map();
    (packages || []).forEach(p => {
        const key = groupKey(p.name);
        if (!map.has(key)) { map.set(key, []); order.push(key); }
        map.get(key).push(p);
    });
    const groups = [];
    order.forEach(key => {
        const items = map.get(key);
        const sigs = items.map(sourceOptionSig);
        // The switcher is for ONE app available from DIFFERENT options (source, or AUR build
        // variant). Two items sharing an option signature — same source + same AUR build, e.g.
        // several Flatpaks with the display name "Adwaita theme" — are genuinely different
        // packages; don't fake a multi-source switcher, keep them apart. (foo-bin vs foo-git have
        // distinct signatures, so they DO collapse into one card.)
        if (new Set(sigs).size !== sigs.length) {
            items.forEach(p => groups.push({ key, name: p.name, sources: [p] }));
        } else {
            const sources = items.slice().sort(compareSourcePreference);
            groups.push({ key, name: sources[0].name, sources });
        }
    });
    return groups;
}

// The footer tags/switcher for the active source of a group.
function sourceBadges(group, activeIdx) {
    const pkg = group.sources[activeIdx];
    // Single source: keep the plain tag (with the condensed AUR badge from phase 2b).
    if (group.sources.length === 1) {
        const src = normalizeType(pkg.type);
        if (src !== 'aur') {
            return `<span class="tag ${escapeHtml(src)}" title="${escapeHtml(sourceLabel(pkg.type))}">${escapeHtml(sourceLabel(pkg.type))}</span>`;
        }
        // Build variant rides in the chip (sourcePillHTML); no redundant "· source/binary" word.
        const votesStr = (typeof pkg.votes === 'number') ? ` · ▲${pkg.votes}` : '';
        let out = `<span class="tag aur" title="AUR - community-maintained, less vetted than the official repo. Build: ${escapeHtml(aurVariant(pkg.name).label)}">${sourcePillHTML(pkg)}${escapeHtml(votesStr)}</span>`;
        if (pkg.out_of_date) out += `<span class="tag ood" title="Flagged out-of-date on the AUR">out of date</span>`;
        return out;
    }
    // Multiple sources: clickable switcher pills (the active one is the card's target).
    // An installed source gets a small dot so you can see which one you're running.
    const pills = group.sources.map((s, i) => {
        const t = normalizeType(s.type);
        const cls = `source-pill src-${t}${i === activeIdx ? ' active' : ''}${s.installed ? ' installed' : ''}`;
        const title = `${sourcePillLabel(s)}${s.installed ? ' • installed' : ''}`;
        return `<button class="${escapeHtml(cls)}" data-srcidx="${i}" title="${escapeHtml(title)}">${sourcePillHTML(s)}</button>`;
    }).join('');
    // When the selected source is AUR, surface its votes (and out-of-date) inline. The build kind
    // is already shown by the active pill's chip, so we don't repeat the "binary/source" word.
    let extra = '';
    if (normalizeType(pkg.type) === 'aur') {
        if (typeof pkg.votes === 'number') {
            extra += `<span class="tag aur-detail" title="AUR votes">▲${pkg.votes}</span>`;
        }
        if (pkg.out_of_date) extra += `<span class="tag ood" title="Flagged out-of-date on the AUR">out of date</span>`;
    }
    return `<div class="source-pills">${pills}</div>${extra}`;
}

// One-line characterisation of a source, for the detail-page comparison panel. For AUR the note is
// build-variant aware (the "guideline" a user wants when choosing between -bin / -git / source).
function sourceCompareNote(type, name) {
    switch (normalizeType(type)) {
        case 'aur': {
            const v = aurVariant(name);
            if (v.kind === 'binary') return 'Community-maintained · prebuilt binary (no compiling)';
            if (v.kind === 'vcs') return `Community-maintained · builds latest ${v.label.toUpperCase()} (may be unstable)`;
            if (v.kind === 'debug') return 'Community-maintained · debug build';
            return 'Community-maintained · builds from source';
        }
        case 'flatpak': return 'Sandboxed · cross-distro';
        case 'arch':
        case 'arch_repo': return 'Official Arch repository';
        case 'appimage': return 'Portable single file';
        case 'snap': return 'Sandboxed · Canonical store';
        default: return '';
    }
}

// Pure builder: when an app is offered by more than one source, a compact "pick where to install
// from" table on the detail page. Built from the in-memory group (version/size/installed) — no
// extra backend calls. Each non-installed source gets an Install button that routes through the
// normal install path (and its full transaction preview). Returns '' for single-source apps.
// Node-VM contract-tested.
function buildSourceCompareHTML(group) {
    const sources = (group && group.sources) || [];
    if (sources.length < 2) return '';
    const rows = sources.map(s => {
        const t = normalizeType(s.type);
        const ver = s.version ? `v${escapeHtml(s.version)}` : '-';
        const size = s.size ? formatBytes(s.size) : (s.download_size ? formatBytes(s.download_size) : '-');
        const note = sourceCompareNote(s.type, s.name);
        const action = s.installed
            ? `<span class="srccmp-installed">✓ Installed</span>`
            : `<button class="btn btn-primary srccmp-install" data-id="${escapeHtml(s.id)}">Install</button>`;
        return `<div class="srccmp-row src-${escapeHtml(t)}${s.installed ? ' is-installed' : ''}">
            <div class="srccmp-src"><span class="source-pill src-${escapeHtml(t)}">${sourcePillHTML(s)}</span></div>
            <div class="srccmp-ver">${ver}</div>
            <div class="srccmp-size">${size}</div>
            <div class="srccmp-note">${escapeHtml(note)}</div>
            <div class="srccmp-action">${action}</div>
        </div>`;
    }).join('');
    // When ≥2 of the options are AUR build variants, spell out what -bin / -git / source mean.
    const aurVariantCount = sources.filter(s => normalizeType(s.type) === 'aur').length;
    const guideline = aurVariantCount >= 2
        ? `<p class="srccmp-guideline"><strong>AUR builds:</strong> <code>-bin</code> installs a prebuilt binary (fast, no compiling - trust the packager); <code>-git</code> builds the latest commit (newest, can be unstable); the plain name builds the released source.</p>`
        : '';
    return `<div class="srccmp">
        <div class="srccmp-head">Available from ${sources.length} sources</div>
        <div class="srccmp-table">${rows}</div>
        <p class="srccmp-hint">Each source is packaged independently - pick where to install from.</p>
        ${guideline}
    </div>`;
}

// Pure: the single-source "why this source?" trust hint for the detail page — the honest one-liner
// an Arch user wants before installing. Keyed off the source type + (for Flatpak) verified/license,
// which the caller refines once Flathub metadata arrives. Returns {text, level}; '' text → hide.
// Node-VM contract-tested.
function whySourceHint(type, opts = {}) {
    const t = normalizeType(type);
    if (t === 'arch' || t === 'arch_repo') {
        return { text: 'From the official Arch repositories - built and signed by Arch maintainers.', level: 'safe' };
    }
    if (t === 'aur') {
        return { text: 'From the AUR - community-submitted and not vetted by Arch. Atlas scans the PKGBUILD before building; review it.', level: 'warn' };
    }
    if (t === 'flatpak') {
        const lic = opts.free_license === true ? ' Open-source license.'
                  : opts.free_license === false ? ' Proprietary license.' : '';
        if (opts.verified === true) return { text: 'Verified on Flathub - published by the app’s own developer.' + lic, level: 'safe' };
        if (opts.verified === false) return { text: 'Community-packaged on Flathub - not verified as published by the app’s developer.' + lic, level: 'info' };
        return { text: 'Distributed via Flathub - sandboxed and cross-distro.' + lic, level: 'info' };
    }
    if (t === 'appimage') return { text: 'A self-contained AppImage - portable but not sandboxed; trust the source.', level: 'info' };
    if (t === 'snap') return { text: 'From the Snap Store (Canonical) - sandboxed.', level: 'info' };
    return { text: '', level: 'info' };
}

function renderWhySource(pkg, opts) {
    const el = document.getElementById('detail-why-source');
    if (!el) return;
    const hint = whySourceHint(pkg.type, opts || {});
    if (!hint.text) { el.classList.add('hidden'); el.innerHTML = ''; return; }
    const icon = hint.level === 'safe' ? '🛡️' : hint.level === 'warn' ? '⚠️' : 'ℹ️';
    el.className = `why-source why-source-${hint.level}`;
    // AUR packages should almost always be read before building — surface the PKGBUILD right here,
    // where the banner already says "review it", rather than burying it on a back tab.
    const isAur = normalizeType(pkg.type) === 'aur';
    const action = isAur ? `<button type="button" class="btn btn-secondary btn-sm why-source-action" id="why-review-pkgbuild">📄 Review PKGBUILD →</button>` : '';
    el.innerHTML = `<span class="why-source-icon">${icon}</span><span class="why-source-text">${escapeHtml(hint.text)}</span>${action}`;
    if (isAur) {
        const btn = document.getElementById('why-review-pkgbuild');
        if (btn) btn.onclick = () => openPkgbuildViewer(pkg);
    }
}

// Pure: a list of expandable dependency nodes (the drill-down tree). Each node carries its name in a
// `data-dep` attr; its child container is filled lazily on first expand by the consumer. Node-VM
// contract-tested. A version constraint (e.g. "glibc>=2.38") is split so we resolve the bare name.
function buildDepNodesHTML(names) {
    names = names || [];
    return names.map(n => {
        const bare = String(n).split(/[<>=:]/)[0];
        return `<details class="dep-node" data-dep="${escapeHtml(bare)}">` +
            `<summary class="dep-node-label">${escapeHtml(n)}</summary>` +
            `<div class="dep-node-children"></div></details>`;
    }).join('');
}

// Pure: the detail-page Dependencies section — Requires / Optional / Build / Provides / Conflicts /
// Replaces / Required by, each an expandable group. Requires + Build are drill-down trees (nodes);
// the rest are flat chip lists. Built from get_dependency_summary; '' when there's nothing to show
// (and no note). Node-VM contract-tested.
function buildDependencySummaryHTML(data) {
    data = data || {};
    const direct = data.direct || [];
    const optional = data.optional || [];
    const requiredBy = data.required_by || [];
    const build = [...(data.makedepends || []), ...(data.checkdepends || [])];
    const provides = data.provides || [];
    const conflicts = data.conflicts || [];
    const replaces = data.replaces || [];
    const anyGroup = direct.length || optional.length || requiredBy.length || build.length ||
        provides.length || conflicts.length || replaces.length;
    if (!anyGroup && !data.note && !data.install_reason) return '';

    // "Why is this installed?" — install reason + orphan status (installed packages only).
    let reasonHTML = '';
    if (data.install_reason === 'explicit') {
        reasonHTML = `<p class="dep-reason dep-reason-explicit">✓ You installed this explicitly.</p>`;
    } else if (data.install_reason === 'dependency') {
        if (data.orphan) {
            reasonHTML = `<p class="dep-reason dep-reason-orphan">⚠ Installed as a dependency, but nothing requires it now — an orphan you can likely remove.</p>`;
        } else {
            // Name who pulled it in: the explicit package(s) that hard-require it, else (a demoted
            // non-orphan) the installed package(s) it's an optional dependency of; else stay generic.
            const nameList = (names) => {
                const shown = names.slice(0, 4).map(r => `<strong>${escapeHtml(r)}</strong>`).join(', ');
                return shown + (names.length > 4 ? ` +${names.length - 4} more` : '');
            };
            const roots = data.installed_because || [];
            const optFor = data.optional_for || [];
            if (roots.length) {
                reasonHTML = `<p class="dep-reason">Installed as a dependency of ${nameList(roots)}.</p>`;
            } else if (optFor.length) {
                reasonHTML = `<p class="dep-reason">Installed as a dependency; now only an optional dependency of ${nameList(optFor)}.</p>`;
            } else {
                reasonHTML = `<p class="dep-reason">Installed as a dependency of other packages.</p>`;
            }
        }
    }

    const chip = s => `<span class="dep-chip">${escapeHtml(s)}</span>`;
    const optChip = o => `<span class="dep-chip" title="${escapeHtml(o.detail || '')}">${escapeHtml(o.name)}</span>`;
    const block = (label, count, bodyHTML, bodyClass = 'dep-chips') => count === 0 ? '' :
        `<details class="dep-group"><summary><span class="dep-count">${count}</span> ${escapeHtml(label)}</summary>` +
        `<div class="${bodyClass}">${bodyHTML}</div></details>`;

    const groups = [
        block('Requires', direct.length, buildDepNodesHTML(direct), 'dep-tree'),
        block('Optional', optional.length, optional.map(optChip).join('')),
        block('Build', build.length, buildDepNodesHTML(build), 'dep-tree'),
        block('Provides', provides.length, provides.map(chip).join('')),
        block('Conflicts', conflicts.length, conflicts.map(chip).join('')),
        block('Replaces', replaces.length, replaces.map(chip).join('')),
        block('Required by', requiredBy.length, requiredBy.map(chip).join('')),
    ].join('');
    const note = data.note ? `<p class="dep-note">${escapeHtml(data.note)}</p>` : '';
    return reasonHTML + groups + note;
}

// Pure: compact per-package Atlas activity for the detail modal. This complements the version
// history table and links to the full Activity page for filtering/export/pacman-log disclosure.
function buildPackageActivityHTML(entries) {
    entries = entries || [];
    if (!entries.length) return '';
    const rows = entries.slice(0, 5).map(e => {
        const ok = e.success ? 'success' : 'error';
        const when = e.timestamp ? new Date(e.timestamp).toLocaleString() : '';
        const err = !e.success && e.error ? `<span class="detail-activity-error"> — ${escapeHtml(cleanActivityError(e.error))}</span>` : '';
        return `<div class="detail-activity-row ${ok}">` +
            `<span class="detail-activity-status">${e.success ? '✓' : '✗'}</span>` +
            `<span class="activity-action ${escapeHtml(e.action || '')}">${escapeHtml(String(e.action || '').replace(/_/g, ' ').toUpperCase())}</span>` +
            `<span class="detail-activity-type">${escapeHtml(e.pkg_type || '')}</span>` +
            `<span class="detail-activity-time">${escapeHtml(when)}</span>${err}</div>`;
    }).join('');
    return rows + `<button class="btn btn-outline btn-sm detail-activity-open">Open full Activity history</button>`;
}

async function renderPackageActivity(pkg, stillCurrent = () => true) {
    const section = document.getElementById('detail-activity-section');
    const body = document.getElementById('detail-activity');
    if (!section || !body) return;
    section.classList.add('hidden');
    body.innerHTML = '';
    if (!pkg || !pkg.installed) return;
    const entries = await pyApiCall('get_package_activity', pkg.id);
    if (!stillCurrent()) return;
    const html = buildPackageActivityHTML(entries);
    if (!html) return;
    body.innerHTML = html;
    const open = body.querySelector('.detail-activity-open');
    if (open) open.addEventListener('click', () => {
        detailModal.classList.add('hidden');
        activityFilter = { action: 'all', type: 'all', query: pkg.name || '' };
        activateView('activity');
    });
    section.classList.remove('hidden');
}

// Escape body text and turn bare http(s) URLs into safe links. The text is fully escaped first
// (XSS-safe), then escaped URL substrings are wrapped — AUR comments are untrusted user content.
function linkifyComment(text) {
    const escaped = escapeHtml(String(text == null ? '' : text));
    return escaped.replace(/https?:\/\/[^\s<]+/g, (m) => {
        // strip trailing sentence punctuation that isn't part of the URL
        const trail = m.match(/(&#039;|&quot;|[.,;:!?)\]]+)$/);
        const suffix = trail ? trail[0] : '';
        const url = suffix ? m.slice(0, m.length - suffix.length) : m;
        const safe = safeExternalUrl(url.replace(/&amp;/g, '&'));
        if (!safe) return m;
        return `<a href="#" data-url="${escapeHtml(safe)}">${escapeHtml(url)}</a>${suffix}`;
    });
}

// Pure: format a scraped comment body into HTML. Runs of shell-prompt lines (starting with `$ ` or
// `# `, including backslash line-continuations) become a monospace code block; everything else is
// linkified prose. AUR comments routinely paste build/version commands, which otherwise read as an
// undifferentiated wall of text. Node-VM contract-tested.
function formatCommentBodyHTML(text) {
    const lines = String(text == null ? '' : text).split('\n');
    const isPrompt = (l) => /^\s*[$#]\s/.test(l);
    const parts = [];
    let prose = [];
    const flushProse = () => {
        while (prose.length && prose[0].trim() === '') prose.shift();
        while (prose.length && prose[prose.length - 1].trim() === '') prose.pop();
        if (prose.length) parts.push(`<p class="aur-comment-text">${prose.map(linkifyComment).join('<br>')}</p>`);
        prose = [];
    };
    for (let i = 0; i < lines.length; i++) {
        if (isPrompt(lines[i])) {
            flushProse();
            const block = [lines[i]];
            // keep pulling continuation lines while the last one ends with a backslash
            while (/\\\s*$/.test(block[block.length - 1]) && i + 1 < lines.length) {
                i++; block.push(lines[i]);
            }
            parts.push(`<pre class="aur-comment-code">${escapeHtml(block.join('\n'))}</pre>`);
        } else {
            prose.push(lines[i]);
        }
    }
    flushProse();
    return parts.join('');
}

// AUR detail comments (Theme 2). Pure: renders scraped plain-text comments (author/date/body).
// Returns '' for no comments so the section stays hidden. URLs in bodies are linkified safely.
function buildAurCommentsHTML(comments) {
    comments = comments || [];
    if (!comments.length) return '';
    const rows = comments.map(c => {
        const author = c.author || 'anonymous';
        const when = c.date ? (new Date(c.date).toString() !== 'Invalid Date'
            ? new Date(c.date).toLocaleString() : c.date) : '';
        const initial = escapeHtml(author.trim().charAt(0).toUpperCase() || '?');
        return `<div class="aur-comment">
            <div class="aur-comment-head">
                <span class="aur-comment-avatar" aria-hidden="true">${initial}</span>
                <span class="aur-comment-author">${escapeHtml(author)}</span>
                ${when ? `<span class="aur-comment-date">${escapeHtml(when)}</span>` : ''}
            </div>
            <div class="aur-comment-body">${formatCommentBodyHTML(c.body || '')}</div>
        </div>`;
    }).join('');
    return rows;
}

async function renderAurComments(pkg, stillCurrent = () => true) {
    const section = document.getElementById('detail-comments-section');
    const body = document.getElementById('detail-comments');
    if (!section || !body) return;
    section.classList.add('hidden');
    body.innerHTML = '';
    if (!pkg || normalizeType(pkg.type) !== 'aur') return;
    const res = await pyApiCall('get_aur_comments', pkg.id);
    if (!stillCurrent()) return;
    const comments = (res && res.comments) || [];
    const html = buildAurCommentsHTML(comments);
    if (!html) return;  // no comments → keep the section hidden
    body.innerHTML = html;
    // Links inside comment bodies open externally through the vetted broker.
    body.querySelectorAll('a[data-url]').forEach(a =>
        a.addEventListener('click', (e) => { e.preventDefault(); openExternalUrl(a.getAttribute('data-url')); }));
    section.classList.remove('hidden');
}

// ---- Detail modal tabs ----------------------------------------------------------------------
// The detail modal groups its sections into tabs (Overview / Details / Dependencies / History /
// Build & Trust). Panels keep their existing section IDs so every async render still works by id.

const MAX_FILE_ROWS = 2000;  // cap rendered file rows so a 10k-file package can't freeze the DOM

function activateDetailTab(name) {
    document.querySelectorAll('#detail-tabs .detail-tab').forEach(b =>
        b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.modal-body .detail-panel').forEach(p =>
        p.classList.toggle('active', p.dataset.panel === name));
}

// Pure: decide which tabs are visible and which should be active. Overview/Details always show;
// deps/history show when their panel has content. If the current active tab ends up hidden, fall
// back to the first visible tab. (DOM-free → unit-tested.)
const DETAIL_TAB_ORDER = ['overview', 'details', 'deps', 'history'];
function computeDetailTabs(content, activeTab) {
    content = content || {};
    const visible = DETAIL_TAB_ORDER.filter(name => {
        if (name === 'overview' || name === 'details') return true;
        return !!content[name];
    });
    const active = visible.includes(activeTab) ? activeTab : (visible[0] || 'overview');
    return { visible, active };
}

// Apply the tab decision to the DOM: read each panel's content state, then show/hide tabs + activate.
function updateDetailTabs() {
    const panelHas = (name) =>
        hasVisibleContent(document.querySelector(`.modal-body .detail-panel[data-panel="${name}"]`));
    const content = { deps: panelHas('deps'), history: panelHas('history') };
    const activeBtn = document.querySelector('#detail-tabs .detail-tab.active');
    const activeName = activeBtn && activeBtn.dataset ? activeBtn.dataset.tab : 'overview';
    const { visible, active } = computeDetailTabs(content, activeName);
    document.querySelectorAll('#detail-tabs .detail-tab').forEach(tab =>
        tab.classList.toggle('hidden', !visible.includes(tab.dataset.tab)));
    activateDetailTab(active);
}

function hasVisibleContent(panel) {
    if (!panel) return false;
    return Array.from(panel.children).some(el =>
        !el.classList.contains('hidden') && (el.children.length > 0 || el.textContent.trim() !== ''));
}

// Pure: the collapsible Installed-files block (header count + filter + scroll list). '' when empty.
function buildInstalledFilesHTML(files) {
    files = (files || []).filter(f => typeof f === 'string' && f.trim() !== '');
    if (!files.length) return '';
    const shown = files.slice(0, MAX_FILE_ROWS);
    const rows = shown.map(f => `<div class="if-row">${escapeHtml(f)}</div>`).join('');
    const capped = files.length > MAX_FILE_ROWS
        ? `<div class="if-note">Showing the first ${MAX_FILE_ROWS.toLocaleString()} of ${files.length.toLocaleString()} files — use the filter to narrow down.</div>`
        : '';
    return `
        <div class="installed-files" data-count="${files.length}">
            <div class="if-head">
                <span class="if-count">${files.length.toLocaleString()} file${files.length === 1 ? '' : 's'}</span>
                <input type="text" class="if-filter" placeholder="🔍 Filter files…" aria-label="Filter installed files">
            </div>
            ${capped}
            <div class="if-list">${rows}</div>
            <div class="if-empty hidden">No files match the filter.</div>
        </div>`;
}

// Render the installed-files block into the Details panel and wire its filter. `files` is the raw
// list from get_info; we render here (not as a table row) to contain the wall of text.
function renderInstalledFiles(files) {
    const section = document.getElementById('detail-files-section');
    const body = document.getElementById('detail-files');
    if (!section || !body) return;
    const html = buildInstalledFilesHTML(files);
    if (!html) { section.classList.add('hidden'); body.innerHTML = ''; return; }
    body.innerHTML = html;
    section.classList.remove('hidden');
    const filter = body.querySelector('.if-filter');
    const rows = Array.from(body.querySelectorAll('.if-row'));
    const empty = body.querySelector('.if-empty');
    if (filter) filter.addEventListener('input', () => {
        const q = filter.value.trim().toLowerCase();
        let any = false;
        rows.forEach(r => {
            const match = !q || r.textContent.toLowerCase().includes(q);
            r.classList.toggle('hidden', !match);
            if (match) any = true;
        });
        if (empty) empty.classList.toggle('hidden', any);
    });
}

// ---- PKGBUILD viewer (first-class AUR build-recipe reader) ----------------------------------
// All builders below are pure (escape their own input) and Node-VM contract-tested.

// Lightweight, regex-based bash highlighter for one PKGBUILD line. Returns HTML (input escaped).
// Deliberately simple — WebKitGTK, offline, no external lib. Order matters: comments & strings win.
const PKGB_KEYWORDS = new Set(['if','then','else','elif','fi','for','while','do','done','case','esac',
    'in','function','return','local','export','cd','echo','exit','break','continue','set','unset']);

function highlightBashLine(line) {
    line = String(line == null ? '' : line);
    // Full-line comment.
    const lead = line.match(/^(\s*)#/);
    if (lead) return `<span class="tok-comment">${escapeHtml(line)}</span>`;

    let out = '';
    let i = 0;
    const n = line.length;
    const flush = (s) => {
        // Highlight bare words (keywords) + $variables inside a plain run.
        return escapeHtml(s)
            .replace(/\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/g, m => `<span class="tok-var">${m}</span>`)
            .replace(/\b([a-z_]+)\b/g, (m, w) => PKGB_KEYWORDS.has(w) ? `<span class="tok-kw">${m}</span>` : m);
    };
    while (i < n) {
        const ch = line[i];
        if (ch === '#' && (i === 0 || /\s/.test(line[i - 1]))) {  // trailing comment
            out += `<span class="tok-comment">${escapeHtml(line.slice(i))}</span>`;
            i = n;
            break;
        }
        if (ch === '"' || ch === "'") {
            // consume the run before the quote
            let j = i + 1;
            while (j < n && line[j] !== ch) j++;
            const str = line.slice(i, Math.min(j + 1, n));
            // variables inside double-quoted strings still read as vars
            const inner = ch === '"'
                ? escapeHtml(str).replace(/\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/g, m => `<span class="tok-var">${m}</span>`)
                : escapeHtml(str);
            out += `<span class="tok-str">${inner}</span>`;
            i = j + 1;
            continue;
        }
        // plain run until next quote or a comment '#' (one preceded by whitespace/start)
        let j = i;
        while (j < n) {
            const c = line[j];
            if (c === '"' || c === "'") break;
            if (c === '#' && (j === 0 || /\s/.test(line[j - 1]))) break;
            j++;
        }
        if (j === i) j++;  // guarantee progress
        out += flush(line.slice(i, j));
        i = j;
    }
    return out;
}

// Sticky risk banner from the scan summary.
function buildPkgbuildRiskHTML(summary, disclaimer) {
    const s = summary || {};
    const warn = s.warn || 0, info = s.info || 0;
    const level = warn ? 'warn' : (info ? 'info' : 'safe');
    // Name each severity so the count is unambiguous (the banner sits above a list of all findings).
    const headline = (warn || info)
        ? [warn ? `${warn} warning${warn === 1 ? '' : 's'}` : null,
           info ? `${info} note${info === 1 ? '' : 's'}` : null].filter(Boolean).join(' · ')
        : 'Nothing flagged by the heuristic scan';
    const icon = warn ? '⚠️' : (info ? 'ℹ️' : '✓');
    const note = escapeHtml(disclaimer || 'Heuristic hints only — NOT a safety check. Read the PKGBUILD.');
    return `<div class="pkgbuild-risk-banner risk-${level}">` +
        `<span class="pkgbuild-risk-icon">${icon}</span>` +
        `<div><div class="pkgbuild-risk-headline">${escapeHtml(headline)}</div>` +
        `<div class="pkgbuild-risk-note">${note}</div></div></div>`;
}

// Maintainer / upstream / sources / checksums summary.
function buildPkgbuildMetaHTML(meta) {
    meta = meta || {};
    const rows = [];
    const row = (label, value) => rows.push(
        `<div class="pkgb-meta-row"><span class="pkgb-meta-label">${escapeHtml(label)}</span>` +
        `<span class="pkgb-meta-value">${value}</span></div>`);

    if (meta.maintainer) row('Maintainer', escapeHtml(meta.maintainer));
    if ((meta.contributors || []).length)
        row('Contributors', escapeHtml(meta.contributors.join(', ')));
    if (meta.pkgver) row('pkgver', escapeHtml(meta.pkgver));
    if (meta.url) {
        row('Upstream', externalLinkHTML(meta.url, meta.url, 'pkgb-link'));
    }
    const sources = meta.sources || [];
    if (sources.length) {
        const items = sources.map(s => externalLinkHTML(s, s, 'pkgb-link')).join('<br>');
        row(`Sources (${sources.length})`, items);
    }
    const sums = meta.checksums || [];
    if (sums.length) {
        const skipped = sums.filter(c => c.skip).length;
        const algos = Array.from(new Set(sums.map(c => c.algo))).join(', ');
        const txt = skipped
            ? `${sums.length} (${algos}) — ⚠ ${skipped} marked SKIP (not verified)`
            : `${sums.length} present (${algos})`;
        row('Checksums', escapeHtml(txt));
    }
    if (!rows.length) return '';
    return `<div class="pkgb-meta-grid">${rows.join('')}</div>`;
}

// Per-finding provenance: the stable rule id (so the heuristic is identifiable) + a "campaign" pill
// for incident-specific rules, with the full kind/added/source in a tooltip. '' when no provenance
// (findings predating the metadata, or fixtures without it). Keeps the advisory framing transparent.
function findingProvenanceHTML(f) {
    const meta = (f && f.meta) || {};
    const rule = f && f.rule;
    if (!rule && !meta.kind) return '';
    const kind = meta.kind || '';
    const tipParts = [];
    if (kind) tipParts.push(kind.charAt(0).toUpperCase() + kind.slice(1) + ' rule');
    if (meta.added) tipParts.push('added ' + meta.added);
    if (meta.source) tipParts.push('source: ' + meta.source);
    const tip = tipParts.join(' · ');
    const ruleChip = rule ? `<span class="pkgb-prov-rule">${escapeHtml(rule)}</span>` : '';
    const campaignPill = kind === 'campaign'
        ? `<span class="pkgb-prov-kind kind-campaign" title="This rule targets a specific known incident">campaign</span>`
        : '';
    return `<div class="pkgb-finding-prov"${tip ? ` title="${escapeHtml(tip)}"` : ''}>${ruleChip}${campaignPill}</div>`;
}

// Clickable findings list — each links to its line in the code panel.
function buildPkgbuildFindingsHTML(findings) {
    findings = findings || [];
    if (!findings.length) return '';
    const items = findings.map(f => `
        <li class="pkgb-finding sev-${escapeHtml(f.severity || 'info')}">
            <a href="#" class="pkgb-finding-link" data-line="${f.line_no}">
                <span class="pkgb-finding-loc">L${f.line_no}</span>
                <span class="pkgb-finding-why">${escapeHtml(f.why || '')}</span>
            </a>
            ${findingProvenanceHTML(f)}
        </li>`).join('');
    return `<h4 class="pkgb-findings-h">Lines worth a look</h4><ul class="pkgb-findings-list">${items}</ul>`;
}

// Line-numbered, syntax-highlighted code. Flagged lines get a severity class + an id to scroll to.
// idPrefix keeps line-anchor ids unique when the same renderer appears in two modals.
function buildPkgbuildCodeHTML(text, findings, idPrefix) {
    idPrefix = idPrefix || 'pkgb-line-';
    const lines = String(text == null ? '' : text).split('\n');
    // Worst severity per line number (warn beats info).
    const sev = {};
    (findings || []).forEach(f => {
        const cur = sev[f.line_no];
        if (!cur || (cur === 'info' && f.severity === 'warn')) sev[f.line_no] = f.severity;
    });
    const rows = lines.map((ln, idx) => {
        const no = idx + 1;
        const cls = sev[no] ? ` flagged sev-${escapeHtml(sev[no])}` : '';
        return `<div class="pkgb-line${cls}" id="${idPrefix}${no}">` +
            `<span class="pkgb-ln">${no}</span>` +
            `<span class="pkgb-code">${highlightBashLine(ln)}</span></div>`;
    }).join('');
    return rows;
}

// Inner HTML of a card for the given active source — re-rendered on source switch.
function cardInnerHTML(group, activeIdx) {
    const pkg = group.sources[activeIdx];
    const actionButton = pkg.installed ?
        (pkg.update_available ?
            `<button class="btn btn-primary action-btn" data-action="update" data-id="${escapeHtml(pkg.id)}">Update</button>` :
            `<button class="btn btn-danger action-btn" data-action="uninstall" data-id="${escapeHtml(pkg.id)}">Uninstall</button>`) :
        `<button class="btn btn-primary action-btn" data-action="install" data-id="${escapeHtml(pkg.id)}">Install</button>`;

    // Add-to-queue toggle — only for not-installed packages (the queue is an install basket).
    const queued = !pkg.installed && queueHas(pkg.id);
    const queueButton = !pkg.installed ?
        `<button class="btn btn-outline action-btn queue-toggle${queued ? ' queued' : ''}" data-action="queue" data-id="${escapeHtml(pkg.id)}" title="${queued ? 'Remove from install queue' : 'Add to install queue'}">${queued ? '✓ Queued' : '＋ Queue'}</button>` : '';

    const pinButton = (pkg.installed && pkg.supports_pinning) ?
        `<button class="btn btn-pin ${pkg.update_ignored ? 'pinned' : ''} action-btn"
            data-action="${pkg.update_ignored ? 'unpin' : 'pin'}"
            data-id="${escapeHtml(pkg.id)}"
            title="${pkg.update_ignored ? 'Click to allow updates' : 'Click to hold (pin) this version'}">
            ${pkg.update_ignored ? '📌 Pinned' : '📌 Pin'}
         </button>` : '';

    const isChecked = selectedPackages.has(pkg.id) ? 'checked' : '';
    const iconUrl = bestIconUrl(group);
    // Installed apps with no icon URL: ask the backend to resolve one from the system (.desktop /
    // icon theme), lazily, via data-pkgicon (handled in deferredIconLoad).
    const installedNoIcon = group.sources.some(s => s.installed) && !iconUrl;
    const pkgIconAttr = installedNoIcon ? ` data-pkgicon="${escapeHtml(pkg.id)}"` : '';

    return `
            <div class="package-header">
                <input type="checkbox" class="pkg-checkbox" ${isChecked}>
                <img src="${(iconUrl && iconUrl.startsWith('data:')) ? iconUrl : letterAvatar(pkg)}" data-src="${escapeHtml(getIconDataSrc(iconUrl))}"${pkgIconAttr} class="package-icon" alt="${escapeHtml(pkg.name)} icon" loading="lazy" decoding="async">
                <div class="package-info">
                    <h3 class="package-title" title="${escapeHtml(pkg.name)}">${escapeHtml(pkg.name)}</h3>
                    <div class="package-publisher" data-meta-id="${escapeHtml(pkg.id)}" data-meta-type="${escapeHtml(normalizeType(pkg.type))}" data-meta-version="${escapeHtml(pkg.version || 'Unknown')}" data-meta-publisher="${escapeHtml(pkg.publisher || 'Unknown Publisher')}">
                        ${escapeHtml(pkg.publisher || 'Unknown Publisher')} • v${escapeHtml(pkg.version || 'Unknown')}
                    </div>
                </div>
            </div>
            <div class="package-description">
                ${escapeHtml(pkg.description || 'No description available for this package.')}
            </div>
            <div class="package-footer">
                <div class="package-tags">${sourceBadges(group, activeIdx)}</div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    ${pinButton}
                    ${queueButton}
                    ${actionButton}
                </div>
            </div>
        `;
}

function getSkeletonGridHTML() {
    let html = '';
    for (let i = 0; i < 6; i++) {
        html += `
        <div class="skeleton-card">
            <div class="skeleton-header">
                <div class="skeleton-icon skeleton-shimmer"></div>
                <div class="skeleton-info">
                    <div class="skeleton-line title skeleton-shimmer"></div>
                    <div class="skeleton-line subtitle skeleton-shimmer"></div>
                </div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
                <div class="skeleton-line description skeleton-shimmer"></div>
                <div class="skeleton-line description-short skeleton-shimmer"></div>
            </div>
            <div class="skeleton-footer">
                <div class="skeleton-tag skeleton-shimmer"></div>
                <div class="skeleton-btn skeleton-shimmer"></div>
            </div>
        </div>`;
    }
    return html;
}

// Render Package Cards (one per app group)
function renderPackages(packages) {
    packagesGrid.innerHTML = '';
    currentGroups = collapseByName(packages);

    if (currentGroups.length === 0) {
        // Context-aware empty state so "no results" is unmistakable (and distinct from loading,
        // which shows skeleton cards). Uses textContent, so the query needs no escaping.
        const q = (searchInput.value || '').trim();
        const h2 = emptyState.querySelector('h2');
        const p = emptyState.querySelector('p');
        if (q) {
            h2.textContent = `No results for “${q}”`;
            p.textContent = 'Nothing matched your search. Check the spelling, try a different term, or widen the type filter.';
        } else if (currentView === 'updates') {
            h2.textContent = 'Everything is up to date';
            p.textContent = 'No updates are available right now.';
        } else if (currentView === 'installed') {
            h2.textContent = 'No installed packages match';
            p.textContent = 'Try clearing the type filter.';
        } else {
            h2.textContent = 'No applications found';
            p.textContent = 'Try adjusting your search or filters.';
        }
        emptyState.classList.remove('hidden');
        packagesGrid.style.display = 'none';
        return;
    }

    emptyState.classList.add('hidden');
    packagesGrid.style.display = 'grid';
    applyViewMode();  // keep the grid/list class in sync on every (re)render

    appendPackageCards(packagesGrid, currentGroups);
    deferredIconLoad();
    deferredMetaLoad();
}

// Build package-card elements for `groups` into `container`. The card's data-gi indexes into
// the module-level currentGroups (the click delegation on #packages-grid resolves it), so the
// caller must have set currentGroups = these groups. Reused by renderPackages and the Browse
// landing's "Suggested" row.
function appendPackageCards(container, groups) {
    const fragment = document.createDocumentFragment();
    groups.forEach((group, gi) => {
        const pkg = group.sources[0];
        const card = document.createElement('div');
        card.className = `package-card ${selectMode ? 'select-mode' : ''} ${selectedPackages.has(pkg.id) ? 'selected' : ''}`;
        card.dataset.id = pkg.id;
        card.dataset.gi = gi;
        card.innerHTML = cardInnerHTML(group, 0);
        fragment.appendChild(card);  // clicks handled by event delegation on #packages-grid
    });
    container.appendChild(fragment);
}

// Silently probe remote icon URLs and upgrade from placeholder on success.
// Uses JS Image() objects which do NOT log 404 errors to console on failure.
// Create the shared lazy-icon IntersectionObserver if it doesn't exist yet, and return it. Lives on
// `window` so every lazy-icon consumer (the package grid *and* the Permissions list) shares one — and
// so a consumer that renders before any grid (e.g. navigating straight to Permissions from the
// dashboard, which has no grid) still gets a working observer instead of silently skipping.
function ensureIconObserver() {
    if (!window.iconObserver) {
        window.iconObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    const remoteSrc = img.getAttribute('data-src');
                    if (remoteSrc) {
                        const probe = new Image();
                        probe.onload = () => { img.src = remoteSrc; };
                        probe.src = remoteSrc;
                    }
                    // Installed app with no icon URL: ask the backend to resolve one from the system.
                    const pkgIconId = img.getAttribute('data-pkgicon');
                    if (pkgIconId) {
                        pyApiCall('get_pkg_icon', pkgIconId).then(uri => {
                            if (!uri) return;
                            const probe = new Image();  // only swap if it actually decodes (keep the avatar otherwise)
                            probe.onload = () => { img.src = uri; };
                            probe.src = uri;
                        });
                    }
                    // Stop observing once handled, regardless of success
                    img.removeAttribute('data-src');
                    img.removeAttribute('data-pkgicon');
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: '200px' }); // probe slightly before scrolling into view
    }
    return window.iconObserver;
}

function deferredIconLoad() {
    const observer = ensureIconObserver();
    const imgs = packagesGrid.querySelectorAll('img.package-icon[data-src], img.package-icon[data-pkgicon]');
    imgs.forEach(img => {
        observer.observe(img);
    });
}

// Silently fetch developer and verification metadata for visible cards.
function deferredMetaLoad() {
    if (!window.metaObserver) {
        window.metaObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                const el = entry.target;
                if (entry.isIntersecting) {
                    // Debounce fetch so fast scrolling doesn't spam the Python backend / Flathub API
                    el._metaTimeout = setTimeout(() => {
                        const id = el.getAttribute('data-meta-id');
                        const type = el.getAttribute('data-meta-type');
                        const version = el.getAttribute('data-meta-version');
                        const basePublisher = el.getAttribute('data-meta-publisher');
                        
                        if (type === 'flatpak') {
                            pyApiCall('get_flatpak_card_meta', id).then(meta => {
                                if (!meta) return;
                                const devName = escapeHtml(meta.developer_name || basePublisher || 'Unknown Developer');
                                const verifiedHtml = meta.verified 
                                    ? `<span class="material-symbols-outlined verified-icon" style="font-size: 14px; margin-left: 2px;" title="Verified by Flathub">verified</span>` 
                                    : `<span class="material-symbols-outlined unverified-icon" style="font-size: 14px; margin-left: 2px;" title="Community maintained (Not verified)">info</span>`;
                                el.innerHTML = `<span style="display:inline-flex;align-items:center;">${devName}${verifiedHtml}</span> <span style="opacity: 0.5;">•</span> v${version}`;
                            });
                        } else if (type === 'aur') {
                            pyApiCall('get_aur_meta', id).then(info => {
                                if (!info) return;
                                let devName = escapeHtml(info.maintainer || basePublisher || 'Unknown');
                                let warnHtml = '';
                                if (!info.maintainer && 'maintainer' in info) {
                                    devName = '<span class="text-danger">Orphaned</span>';
                                    warnHtml = `<span class="material-symbols-outlined text-danger" style="font-size: 14px; margin-left: 2px;" title="No maintainer">error</span>`;
                                } else {
                                    warnHtml = `<span class="material-symbols-outlined unverified-icon" style="font-size: 14px; margin-left: 2px;" title="AUR community package">info</span>`;
                                }
                                el.innerHTML = `<span style="display:inline-flex;align-items:center;">${devName}${warnHtml}</span> <span style="opacity: 0.5;">•</span> v${version}`;
                            });
                        }
                        
                        // Stop observing once handled
                        el.removeAttribute('data-meta-id');
                        observer.unobserve(el);
                    }, 300);
                } else {
                    if (el._metaTimeout) {
                        clearTimeout(el._metaTimeout);
                        el._metaTimeout = null;
                    }
                }
            });
        }, { rootMargin: '50px' });
    }

    const metas = packagesGrid.querySelectorAll('.package-publisher[data-meta-id]');
    metas.forEach(el => {
        window.metaObserver.observe(el);
    });
}

// get_info keys carry Qt-era numeric ordering prefixes (e.g. "03_version",
// "08_first_submitted"); strip the prefix and turn underscores into spaces for display.
function prettifyInfoKey(key) {
    return String(key).replace(/^\d+_/, '').replace(/_/g, ' ').trim();
}

// Screenshot strip in the detail modal (Flatpak/AppImage carry screenshots; Arch doesn't).
async function renderDetailScreenshots(pkg, stillCurrent = () => true) {
    const el = document.getElementById('detail-screenshots');
    if (!el) return;
    el.innerHTML = '';
    el.classList.add('hidden');
    if (!pkg.has_screenshots) return;

    const urls = await pyApiCall('get_screenshots', pkg.id);  // unwrapped list, or null
    if (!stillCurrent()) return;
    if (!urls || urls.length === 0) return;

    el.innerHTML = urls.map((u, i) =>
        `<a class="screenshot-thumb" href="#" data-idx="${i}" title="Click to enlarge">
            <img loading="lazy" src="${escapeHtml(u)}" alt="screenshot">
         </a>`).join('');
    el.classList.remove('hidden');
    el.querySelectorAll('a[data-idx]').forEach(a => {
        a.addEventListener('click', (e) => { e.preventDefault(); openLightbox(urls, Number(a.dataset.idx)); });
    });
    // Drop any thumbnail whose image fails to load.
    el.querySelectorAll('img').forEach(img => {
        img.onerror = () => { img.parentElement.style.display = 'none'; };
    });
}

// Full-size screenshot viewer (lightbox) with prev/next + keyboard nav.
let lightboxUrls = [];
let lightboxIdx = 0;

function openLightbox(urls, idx) {
    lightboxUrls = urls || [];
    if (lightboxUrls.length === 0) return;
    showLightboxImage(idx);
    const box = document.getElementById('screenshot-lightbox');
    box.classList.remove('hidden');
    const multi = lightboxUrls.length > 1;
    document.getElementById('lightbox-prev').style.display = multi ? '' : 'none';
    document.getElementById('lightbox-next').style.display = multi ? '' : 'none';
}

function showLightboxImage(idx) {
    lightboxIdx = (idx + lightboxUrls.length) % lightboxUrls.length;  // wrap around
    document.getElementById('lightbox-img').src = lightboxUrls[lightboxIdx];
}

function closeLightbox() {
    document.getElementById('screenshot-lightbox').classList.add('hidden');
}

function lightboxStep(delta) {
    if (lightboxUrls.length > 1) showLightboxImage(lightboxIdx + delta);
}

(function wireLightbox() {
    const box = document.getElementById('screenshot-lightbox');
    if (!box) return;
    document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
    document.getElementById('lightbox-prev').addEventListener('click', () => lightboxStep(-1));
    document.getElementById('lightbox-next').addEventListener('click', () => lightboxStep(1));
    // Click the backdrop (not the image/buttons) to dismiss.
    box.addEventListener('click', (e) => { if (e.target === box) closeLightbox(); });
    document.addEventListener('keydown', (e) => {
        if (box.classList.contains('hidden')) return;
        if (e.key === 'Escape') closeLightbox();
        else if (e.key === 'ArrowLeft') lightboxStep(-1);
        else if (e.key === 'ArrowRight') lightboxStep(1);
    });
})();

// Dependency summary in the detail modal (lazy). Section stays hidden until the cheap backend probe
// returns something to show; stale-guarded so a slow response can't fill a since-closed/changed modal.
async function renderDependencySummary(pkg, stillCurrent = () => true) {
    const section = document.getElementById('detail-deps-section');
    const body = document.getElementById('detail-deps');
    if (!section || !body) return;
    section.classList.add('hidden');
    body.innerHTML = '';
    const data = await pyApiCall('get_dependency_summary', pkg.id);
    if (!stillCurrent()) return;
    const html = buildDependencySummaryHTML(data);
    if (!html) return;  // nothing to show (e.g. a Flatpak with no note)
    body.innerHTML = html;
    section.classList.remove('hidden');
    wireDependencyTree(body);
}

// Lazy drill-down: when a dependency node is first expanded, fetch its direct requires and render
// them as the same expandable nodes (one cheap level per click; recursion bounded by the user).
function wireDependencyTree(body) {
    if (!body || body._depTreeWired) return;
    body._depTreeWired = true;
    body.addEventListener('click', (e) => {
        const summary = e.target.closest('summary.dep-node-label');
        if (!summary) return;
        const node = summary.parentElement;
        const children = node.querySelector('.dep-node-children');
        if (!children || children.dataset.loaded) return;   // load once
        children.dataset.loaded = '1';
        const name = node.dataset.dep;
        children.innerHTML = '<span class="dep-node-loading">Loading…</span>';
        pyApiCall('get_subdeps', name).then(res => {
            const deps = (res && res.direct) || [];
            children.innerHTML = deps.length
                ? buildDepNodesHTML(deps)
                : '<span class="dep-node-leaf">No further requirements (or not in the repos).</span>';
        }).catch(() => {
            children.innerHTML = '<span class="dep-node-leaf">Couldn’t load.</span>';
        });
    });
}

// Show/hide the "Build recipe" affordance — AUR only (repo packages are built+signed by Arch;
// Flatpak/AppImage have no PKGBUILD).
const pkgbuildModal = document.getElementById('pkgbuild-modal');
let pkgbuildViews = [];      // [{name, kind:'diff'|'code', ...}] — diff (if any) first, then files
let pkgbuildActiveTab = 0;

function closePkgbuildViewer() {
    if (pkgbuildModal) pkgbuildModal.classList.add('hidden');
}

// Pure: the ordered viewer "views" — an optional "changed since your build" diff first, then the
// PKGBUILD and any .install scriptlets. Each view precomputes its tab badge. Node-VM contract-tested.
function buildPkgbuildViews(data) {
    data = data || {};
    const views = [];
    const diff = data.diff || [];
    if (diff.length) {
        const changes = diff.filter(d => d.kind === 'add' || d.kind === 'del').length;
        views.push({ name: 'Changed since your build', kind: 'diff', diff, badge: changes, badgeKind: 'diff' });
    }
    const files = (Array.isArray(data.files) && data.files.length)
        ? data.files
        : [{ name: 'PKGBUILD', text: data.text, findings: data.findings }];
    files.forEach(f => {
        const warns = (f.findings || []).filter(x => x.severity === 'warn').length;
        views.push({ name: f.name, kind: 'code', text: f.text, findings: f.findings,
                     badge: warns, badgeKind: 'warn' });
    });
    return views;
}

// Tab bar across the views. Pure. '' when there's only one (nothing to tab between).
function buildPkgbuildTabsHTML(views, activeIdx) {
    views = views || [];
    if (views.length < 2) return '';
    return views.map((v, i) => {
        const badge = v.badge
            ? `<span class="pkgb-tab-badge${v.badgeKind === 'diff' ? ' pkgb-tab-badge-diff' : ''}">${v.badge}</span>`
            : '';
        return `<button class="pkgb-tab${i === activeIdx ? ' active' : ''}" data-tab="${i}">` +
            `${escapeHtml(v.name)}${badge}</button>`;
    }).join('');
}

// Pure: a colored unified diff (reuses the build-time review's .diff-line markup). Added lines
// carrying `findings` (from diff_lines(..., annotate=True)) get an inline warning badge so the
// reader's eye stops on the suspicious additions, not just "something changed".
function buildPkgbuildDiffHTML(diff) {
    diff = diff || [];
    if (!diff.length) return '';
    const rows = diff.map(d => {
        const findings = d.findings || [];
        const badges = findings.map(f =>
            `<span class="diff-finding-badge sev-${escapeHtml(f.severity)}" title="${escapeHtml(f.why || '')}">⚠ ${escapeHtml(f.rule)}</span>`
        ).join('');
        return `<div class="diff-line diff-${escapeHtml(d.kind)}"><span class="diff-line-text">${escapeHtml(d.text)}</span>${badges}</div>`;
    }).join('');
    return `<div class="review-diff pkgb-diff">${rows}</div>`;
}

// Render the active view (diff, or findings + code for a file).
function renderPkgbuildTab(idx) {
    const view = pkgbuildViews[idx];
    if (!view) return;
    pkgbuildActiveTab = idx;
    const tabsEl = document.getElementById('pkgbuild-tabs');
    if (tabsEl) tabsEl.querySelectorAll('.pkgb-tab').forEach(t =>
        t.classList.toggle('active', Number(t.dataset.tab) === idx));
    const findingsEl = document.getElementById('pkgbuild-findings');
    const codeEl = document.getElementById('pkgbuild-code');
    if (view.kind === 'diff') {
        findingsEl.innerHTML = '';
        codeEl.innerHTML = buildPkgbuildDiffHTML(view.diff);
    } else {
        findingsEl.innerHTML = buildPkgbuildFindingsHTML(view.findings);
        codeEl.innerHTML = buildPkgbuildCodeHTML(view.text, view.findings);
    }
}

// Open the first-class PKGBUILD viewer for an AUR package (lazy fetch + scan + render).
async function openPkgbuildViewer(pkg) {
    if (!pkgbuildModal) return;
    const viewerPkgId = String(pkg.id || '');
    pkgbuildModal.dataset.pkgId = viewerPkgId;
    const stillCurrent = () => pkgbuildModal.dataset.pkgId === viewerPkgId;
    pkgbuildViews = [];
    pkgbuildActiveTab = 0;

    document.getElementById('pkgbuild-name').textContent = pkg.name || '';
    document.getElementById('pkgbuild-risk').innerHTML = '';
    document.getElementById('pkgbuild-meta').innerHTML = '';
    document.getElementById('pkgbuild-findings').innerHTML = '';
    const tabsEl = document.getElementById('pkgbuild-tabs');
    tabsEl.innerHTML = ''; tabsEl.classList.add('hidden');
    document.getElementById('pkgbuild-code').innerHTML =
        '<div class="pkgbuild-loading">Fetching PKGBUILD…</div>';
    const link = document.getElementById('pkgbuild-link');
    const copyBtn = document.getElementById('pkgbuild-copy-btn');
    link.classList.add('hidden');
    if (copyBtn) copyBtn.classList.add('hidden');
    pkgbuildModal.classList.remove('hidden');
    if (pkgbuildModal.focus) setTimeout(() => pkgbuildModal.focus(), 50);

    const data = await pyApiCall('get_pkgbuild', pkg.id);
    if (!stillCurrent()) return;

    if (!data || !data.text) {
        document.getElementById('pkgbuild-code').innerHTML = emptyStateHTML({
            icon: '📄',
            title: 'Couldn’t load the PKGBUILD',
            hint: 'AUR may be unreachable, or this package has no published PKGBUILD. You can read it on the AUR.',
        });
        if (data && data.url) {
            link.href = '#';
            link.onclick = (e) => { e.preventDefault(); openExternalUrl(data.url); };
            link.classList.remove('hidden');
        }
        return;
    }

    document.getElementById('pkgbuild-risk').innerHTML =
        buildPkgbuildRiskHTML(data.summary, data.disclaimer);
    document.getElementById('pkgbuild-meta').innerHTML = buildPkgbuildMetaHTML(data.metadata);

    // Views: an optional "changed since your build" diff first (draws the eye to changes on an
    // update), then PKGBUILD + .install scriptlet tabs.
    pkgbuildViews = buildPkgbuildViews(data);
    tabsEl.innerHTML = buildPkgbuildTabsHTML(pkgbuildViews, 0);
    tabsEl.classList.toggle('hidden', pkgbuildViews.length < 2);
    renderPkgbuildTab(0);

    if (copyBtn) copyBtn.classList.remove('hidden');
    if (data.url) {
        link.href = '#';
        link.onclick = (e) => { e.preventDefault(); openExternalUrl(data.url); };
        link.classList.remove('hidden');
    }
}

// Version-history table in the detail modal; the installed version's row is highlighted.
async function renderDetailHistory(pkg, stillCurrent = () => true) {
    const section = document.getElementById('detail-history-section');
    const body = document.getElementById('detail-history');
    if (!section || !body) return;
    section.classList.add('hidden');
    body.innerHTML = '';
    if (!pkg.has_history) return;

    const data = await pyApiCall('get_history', pkg.id);  // unwrapped {history, current_index}
    if (!stillCurrent()) return;
    const history = data && data.history;
    if (!history || history.length === 0) return;
    const current = (data && typeof data.current_index === 'number') ? data.current_index : -1;

    // Union of columns across entries (prettified, first-seen order).
    const cols = [];
    const seen = new Set();
    history.forEach(row => Object.keys(row).forEach(k => {
        const label = prettifyInfoKey(k);
        const lk = label.toLowerCase();
        if (!seen.has(lk)) { seen.add(lk); cols.push({ key: k, label }); }
    }));

    const head = `<tr>${cols.map(c => `<th>${escapeHtml(c.label)}</th>`).join('')}</tr>`;
    const rows = history.map((row, i) => {
        const cells = cols.map(c => {
            let v = row[c.key];
            if (v === null || v === undefined) v = '';
            else if (Array.isArray(v)) v = v.join(', ');
            else if (typeof v === 'object') v = JSON.stringify(v);
            return `<td>${escapeHtml(String(v))}</td>`;
        }).join('');
        const attrs = i === current ? ' class="history-current" title="Currently installed"' : '';
        return `<tr${attrs}>${cells}</tr>`;
    }).join('');

    body.innerHTML = `<div class="history-scroll"><table class="detail-table history-table">${head}${rows}</table></div>`;
    section.classList.remove('hidden');
}

// These duplicate what the modal header already shows (title, version, description), so
// don't repeat them in the DETAILS table.
// The Dependencies section now renders Requires/Optional and the orphan/install-reason status, so
// drop the raw get_info rows that duplicate it (makedepends/checkdepends are build-only — kept).
// 'maintainer' is also dropped: for Arch its value is just the source string ('aur' / a repo name),
// not a person — the header already shows the real maintainer/developer + the source badge.
// 'pkg build' is the full raw PKGBUILD text (info['..._pkg_build']) — it's a wall of text and we have
// a dedicated viewer (Review PKGBUILD on Overview), so it never belongs in the key/value table.
const SKIP_DETAIL_KEYS = new Set(['id', 'name', 'version', 'description', 'dependson', 'optdepends', 'orphan', 'maintainer', 'pkg build']);

// Package Detail Modal View
// --- Permissions page (Flatseal-style, master/detail) ----------------------
// A successful permission edit surfaces the exact `flatpak override --user …` command it ran
// (click the toast to copy) — Atlas's "nothing hidden from CLI users" angle.
function permissionUpdatedToast(r) {
    const cmd = r && r.command;
    showToast('Permissions', cmd ? `Updated · ${cmd}` : 'Updated — effective next launch', 'success', cmd || null);
}

let permsPageApps = [];
let permsPageSelected = null;
let permsActiveTab = null;   // which category tab is open in the detail panel (persists across re-renders)

async function renderPermissionsPage() {
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, `<div class="state-container"><div class="spinner"></div><p>Loading installed Flatpaks…</p></div>`);
    const installed = await pyApiCall('get_installed', 'all');
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    permsPageApps = (installed || []).filter(p => normalizeType(p.type) === 'flatpak')
        .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    if (!permsPageApps.length) {
        packagesGrid.innerHTML = emptyStateHTML({
            icon: '🔒', title: 'No installed Flatpaks',
            hint: 'Install a Flatpak app and you can manage its sandbox permissions here.',
            actionLabel: 'Browse apps', actionView: 'browse' });
        return;
    }
    if (!permsPageApps.some(a => a.id === permsPageSelected)) permsPageSelected = permsPageApps[0].id;

    packagesGrid.innerHTML = `
        <div class="perms-page">
            <aside class="perms-applist" id="perms-applist"></aside>
            <section class="perms-detail" id="perms-detail"></section>
        </div>`;
    renderPermsAppList();
    renderPermsDetail(permsPageSelected);
}

function renderPermsAppList() {
    const el = document.getElementById('perms-applist');
    el.innerHTML = permsPageApps.map(a => {
        const hasData = a.icon_url && a.icon_url.startsWith('data:');
        // These are all installed Flatpaks; if there's no embedded/remote icon, let the backend
        // resolve one from the system (.desktop / icon theme) lazily via data-pkgicon.
        const pkgIconAttr = (!hasData && !getIconDataSrc(a.icon_url)) ? ` data-pkgicon="${escapeHtml(a.id)}"` : '';
        return `
        <button class="perms-app ${a.id === permsPageSelected ? 'active' : ''}" data-app-id="${escapeHtml(a.id)}">
            <img class="perms-app-icon" src="${hasData ? a.icon_url : letterAvatar(a)}" data-src="${escapeHtml(getIconDataSrc(a.icon_url))}"${pkgIconAttr} alt="" loading="lazy">
            <span class="perms-app-name">${escapeHtml(a.name)}</span>
        </button>`;
    }).join('');
    el.querySelectorAll('.perms-app').forEach(b => b.addEventListener('click', () => {
        permsPageSelected = b.getAttribute('data-app-id');
        renderPermsAppList();
        renderPermsDetail(permsPageSelected);
    }));
    const observer = ensureIconObserver();
    el.querySelectorAll('img.perms-app-icon[data-src], img.perms-app-icon[data-pkgicon]').forEach(i => observer.observe(i));
}

async function renderPermsDetail(appId) {
    const el = document.getElementById('perms-detail');
    const app = permsPageApps.find(a => a.id === appId);
    el.innerHTML = `<div class="state-container"><div class="spinner"></div></div>`;
    const data = await pyApiCall('get_flatpak_grouped_permissions', appId);
    if (!data || !data.editable) {
        el.innerHTML = `<div class="news-empty">Permissions aren't available for this app.</div>`;
        return;
    }
    // One panel per category + the Filesystem section, behind tabs (the combined list is long).
    const sections = (data.groups || []).map(g => ({
        key: g.title.toLowerCase(),
        label: g.title,
        html: `
            <div class="perms-group">
                <div class="perms-group-head"><p>${escapeHtml(g.subtitle)}</p></div>
                <div class="perms-rows">
                    ${g.items.map(t => `
                        <label class="perms-row" title="${escapeHtml(t.detail || '')}">
                            <span class="perms-row-text">
                                <span class="perms-row-name ${t.risky ? 'risky' : ''}">${escapeHtml(t.label)}</span>
                                <span class="perms-row-flag">${escapeHtml(t.flag)}</span>
                            </span>
                            <span class="switch"><input type="checkbox" data-perm-key="${escapeHtml(t.key)}" ${t.enabled ? 'checked' : ''}><span class="switch-track"></span></span>
                        </label>`).join('')}
                </div>
            </div>`,
    }));
    sections.push({ key: 'filesystem', label: 'Filesystem', html: filesystemSectionHtml(data.filesystem || {}) });
    sections.push({ key: 'bus', label: 'Bus', html: busSectionHtml(data.bus || {}) });
    sections.push({ key: 'environment', label: 'Environment', html: environmentSectionHtml(data.environment || []) });
    if (!sections.some(s => s.key === permsActiveTab)) permsActiveTab = sections[0].key;

    const tabs = sections.map(s =>
        `<button class="perms-tab ${s.key === permsActiveTab ? 'active' : ''}" data-tab="${s.key}">${escapeHtml(s.label)}</button>`).join('');
    const panels = sections.map(s =>
        `<div class="perms-tabpanel ${s.key === permsActiveTab ? 'active' : ''}" data-tabpanel="${s.key}">${s.html}</div>`).join('');
    el.innerHTML = `
        <div class="perms-detail-head">
            <h2>${escapeHtml(app ? app.name : appId)}</h2>
            <button class="btn btn-outline" id="perms-reset-all">Reset to defaults</button>
        </div>
        <p class="popup-note">Changes are saved as per-user overrides (no root needed) and take effect the next time the app starts.</p>
        <div class="perms-tabs">${tabs}</div>
        ${panels}`;

    el.querySelectorAll('.perms-tab').forEach(tab => tab.addEventListener('click', () => {
        permsActiveTab = tab.getAttribute('data-tab');
        el.querySelectorAll('.perms-tab').forEach(x => x.classList.toggle('active', x === tab));
        el.querySelectorAll('.perms-tabpanel').forEach(p =>
            p.classList.toggle('active', p.getAttribute('data-tabpanel') === permsActiveTab));
    }));
    el.querySelectorAll('input[data-perm-key]').forEach(cb => cb.addEventListener('change', async () => {
        const r = await pyApiCall('set_flatpak_override', appId, cb.getAttribute('data-perm-key'), cb.checked);
        if (r && r.status === 'ok') permissionUpdatedToast(r);
        else cb.checked = !cb.checked;
    }));
    wireFilesystemHandlers(el, appId);
    wireBusEnvHandlers(el, appId);
    document.getElementById('perms-reset-all').addEventListener('click', async () => {
        const r = await pyApiCall('reset_flatpak_overrides', appId);
        if (r && r.status === 'ok') { showToast('Permissions', 'Reset to defaults', 'success'); renderPermsDetail(appId); }
    });
}

const FS_MODE_OPTS = [['rw', 'Read/write'], ['ro', 'Read-only'], ['create', 'Create']];
function fsModeSelect(name, mode, disabled) {
    const opts = FS_MODE_OPTS.map(([v, l]) => `<option value="${v}" ${mode === v ? 'selected' : ''}>${l}</option>`).join('');
    return `<select class="fs-mode styled-select" data-fs-mode="${escapeHtml(name)}" ${disabled ? 'disabled' : ''}>${opts}</select>`;
}

function filesystemSectionHtml(fs) {
    const presets = (fs.presets || []).map(p => `
        <div class="perms-row" title="Folders the app can access">
            <span class="perms-row-text">
                <span class="perms-row-name ${p.risky ? 'risky' : ''}">${escapeHtml(p.label)}</span>
                <span class="perms-row-flag">filesystem=${escapeHtml(p.name)}</span>
            </span>
            <span class="perms-fs-controls">
                ${fsModeSelect(p.name, p.mode, !p.enabled)}
                <span class="switch"><input type="checkbox" data-fs-toggle="${escapeHtml(p.name)}" ${p.enabled ? 'checked' : ''}><span class="switch-track"></span></span>
            </span>
        </div>`).join('');
    const custom = (fs.custom || []).map(c => `
        <div class="perms-row">
            <span class="perms-row-text">
                <span class="perms-row-name">${escapeHtml(c.name)}</span>
                <span class="perms-row-flag">custom path</span>
            </span>
            <span class="perms-fs-controls">
                ${fsModeSelect(c.name, c.mode, false)}
                <button class="btn-icon" data-fs-remove="${escapeHtml(c.name)}" title="Remove">✕</button>
            </span>
        </div>`).join('');
    return `
        <div class="perms-group">
            <div class="perms-group-head"><p>Folders and paths the app can access</p></div>
            <div class="perms-rows">${presets}${custom}</div>
            <div class="perms-fs-add">
                <input type="text" id="fs-add-input" class="styled-input" placeholder="A path, e.g. ~/Projects or /mnt/data">
                ${fsModeSelect('', 'rw', false).replace('data-fs-mode=""', 'id="fs-add-mode"')}
                <button class="btn btn-outline" id="fs-add-btn">Add path</button>
            </div>
        </div>`;
}

function wireFilesystemHandlers(el, appId) {
    const apply = async (name, enabled, mode, rerender) => {
        const r = await pyApiCall('set_flatpak_filesystem', appId, name, enabled, mode || 'rw');
        if (r && r.status === 'ok') {
            permissionUpdatedToast(r);
            if (rerender) renderPermsDetail(appId);
            return true;
        }
        return false;
    };
    el.querySelectorAll('input[data-fs-toggle]').forEach(cb => cb.addEventListener('change', async () => {
        const name = cb.getAttribute('data-fs-toggle');
        const sel = el.querySelector(`select[data-fs-mode="${CSS.escape(name)}"]`);
        const ok = await apply(name, cb.checked, sel ? sel.value : 'rw', true);
        if (!ok) cb.checked = !cb.checked;
    }));
    el.querySelectorAll('select[data-fs-mode]').forEach(sel => sel.addEventListener('change', () => {
        const name = sel.getAttribute('data-fs-mode');
        if (name) apply(name, true, sel.value, false);  // only meaningful when the entry is enabled
    }));
    el.querySelectorAll('button[data-fs-remove]').forEach(btn => btn.addEventListener('click', () =>
        apply(btn.getAttribute('data-fs-remove'), false, 'rw', true)));
    const addBtn = el.querySelector('#fs-add-btn');
    if (addBtn) addBtn.addEventListener('click', () => {
        const input = el.querySelector('#fs-add-input');
        const mode = el.querySelector('#fs-add-mode');
        const path = (input.value || '').trim();
        if (path) apply(path, true, mode ? mode.value : 'rw', true);
    });
}

// --- Bus + Environment sections (dynamic add/remove lists) ---------------------------------
function permsEmptyRow(text) {
    return `<div class="perms-row perms-row-empty"><span class="perms-row-name">${escapeHtml(text)}</span></div>`;
}

function busScopeHtml(scope, label, entries) {
    const rows = (entries || []).map(e => `
        <div class="perms-row">
            <span class="perms-row-text">
                <span class="perms-row-name">${escapeHtml(e.name)}</span>
                <span class="perms-row-flag">${escapeHtml(e.policy)}</span>
            </span>
            <button class="btn-icon" data-bus-remove="${scope}|${escapeHtml(e.name)}" title="Remove">✕</button>
        </div>`).join('');
    return `
        <div class="perms-subsection">
            <h4>${escapeHtml(label)}</h4>
            <div class="perms-rows">${rows || permsEmptyRow('No names granted.')}</div>
            <div class="perms-fs-add">
                <input type="text" class="styled-input" data-bus-add-name="${scope}" placeholder="A D-Bus name, e.g. org.freedesktop.Notifications">
                <select class="fs-mode styled-select" data-bus-add-policy="${scope}"><option value="talk">Talk</option><option value="own">Own</option></select>
                <button class="btn btn-outline" data-bus-add-btn="${scope}">Add</button>
            </div>
        </div>`;
}

function busSectionHtml(bus) {
    bus = bus || {};
    return `
        <div class="perms-group">
            <div class="perms-group-head"><p>Services the app may communicate with over D-Bus</p></div>
            ${busScopeHtml('session', 'Session bus', bus.session)}
            ${busScopeHtml('system', 'System bus', bus.system)}
        </div>`;
}

function environmentSectionHtml(env) {
    const rows = (env || []).map(e => `
        <div class="perms-row">
            <span class="perms-row-text">
                <span class="perms-row-name">${escapeHtml(e.var)}</span>
                <span class="perms-row-flag">${escapeHtml(e.value)}</span>
            </span>
            <button class="btn-icon" data-env-remove="${escapeHtml(e.var)}" title="Remove">✕</button>
        </div>`).join('');
    return `
        <div class="perms-group">
            <div class="perms-group-head"><p>Environment variables set for the app</p></div>
            <div class="perms-rows">${rows || permsEmptyRow('No variables set.')}</div>
            <div class="perms-fs-add">
                <input type="text" class="styled-input" id="env-add-var" placeholder="Variable, e.g. GTK_THEME">
                <input type="text" class="styled-input" id="env-add-value" placeholder="Value">
                <button class="btn btn-outline" id="env-add-btn">Add</button>
            </div>
        </div>`;
}

function wireBusEnvHandlers(el, appId) {
    const done = (r) => {
        if (r && r.status === 'ok') { permissionUpdatedToast(r); renderPermsDetail(appId); return true; }
        return false;
    };
    el.querySelectorAll('button[data-bus-remove]').forEach(btn => btn.addEventListener('click', async () => {
        const [scope, name] = btn.getAttribute('data-bus-remove').split('|');
        done(await pyApiCall('set_flatpak_bus', appId, scope, name, 'talk', false));
    }));
    el.querySelectorAll('button[data-bus-add-btn]').forEach(btn => btn.addEventListener('click', async () => {
        const scope = btn.getAttribute('data-bus-add-btn');
        const nameEl = el.querySelector(`input[data-bus-add-name="${scope}"]`);
        const polEl = el.querySelector(`select[data-bus-add-policy="${scope}"]`);
        const name = (nameEl.value || '').trim();
        if (name) done(await pyApiCall('set_flatpak_bus', appId, scope, name, polEl ? polEl.value : 'talk', true));
    }));
    el.querySelectorAll('button[data-env-remove]').forEach(btn => btn.addEventListener('click', async () =>
        done(await pyApiCall('set_flatpak_env', appId, btn.getAttribute('data-env-remove'), '', false))));
    const envBtn = el.querySelector('#env-add-btn');
    if (envBtn) envBtn.addEventListener('click', async () => {
        const v = (el.querySelector('#env-add-var').value || '').trim();
        const val = el.querySelector('#env-add-value').value || '';
        if (v) done(await pyApiCall('set_flatpak_env', appId, v, val, true));
    });
}

// Generic client-side info popup (stacks above the detail modal). Body is trusted HTML built here.
function showInfoPopup(title, bodyHtml) {
    document.getElementById('info-popup-title').textContent = title || '';
    document.getElementById('info-popup-body').innerHTML = bodyHtml || '';
    document.getElementById('info-popup').classList.remove('hidden');
}
function closeInfoPopup() {
    document.getElementById('info-popup').classList.add('hidden');
}
document.getElementById('info-popup-close').addEventListener('click', closeInfoPopup);
document.querySelector('#info-popup .modal-backdrop').addEventListener('click', closeInfoPopup);
document.getElementById('info-popup').addEventListener('keydown', (e) => { if (e.key === 'Escape') closeInfoPopup(); });

// Flatseal-style permission editor (installed Flatpaks). Toggles apply immediately via
// `flatpak override --user` (no root); effective on next launch.
async function openPermissionsEditor(pkg) {
    const data = await pyApiCall('get_flatpak_overrides', pkg.id);
    if (!data || !data.editable || !(data.toggles || []).length) {
        showToast('Permissions', 'Permission editing is only available for installed Flatpaks', 'info');
        return;
    }
    const rows = data.toggles.map(t => `
        <label class="perm-toggle" title="${escapeHtml(t.detail || '')}">
            <span class="perm-toggle-label">
                <span class="perm-toggle-name ${t.risky ? 'risky' : ''}">${escapeHtml(t.label)}</span>
                ${t.detail ? `<span class="perm-toggle-detail">${escapeHtml(t.detail)}</span>` : ''}
            </span>
            <input type="checkbox" data-perm-key="${escapeHtml(t.key)}" ${t.enabled ? 'checked' : ''}>
        </label>`).join('');
    showInfoPopup('Manage permissions', `
        <p class="popup-note">Toggle what <strong>${escapeHtml(pkg.name)}</strong> can access. Changes are saved as per-user overrides (no root needed) and take effect the next time the app starts.</p>
        <div class="perm-toggles">${rows}</div>
        <div class="settings-actions"><button class="btn btn-outline" id="perms-reset-btn">Reset to defaults</button></div>`);

    document.querySelectorAll('#info-popup-body input[data-perm-key]').forEach(cb => {
        cb.addEventListener('change', async () => {
            const r = await pyApiCall('set_flatpak_override', pkg.id, cb.getAttribute('data-perm-key'), cb.checked);
            if (r && r.status === 'ok') {
                permissionUpdatedToast(r);
            } else {
                cb.checked = !cb.checked;  // revert (pyApiCall already surfaced the error)
            }
        });
    });
    const resetBtn = document.getElementById('perms-reset-btn');
    if (resetBtn) resetBtn.addEventListener('click', async () => {
        const r = await pyApiCall('reset_flatpak_overrides', pkg.id);
        if (r && r.status === 'ok') { showToast('Permissions', 'Reset to defaults', 'success'); openPermissionsEditor(pkg); }
    });
}

function getPermissionIcon(title) {
    const t = (title || '').toLowerCase();
    if (t.includes('network')) return 'wifi';
    if (t.includes('windowing') || t.includes('x11') || t.includes('wayland')) return 'desktop_windows';
    if (t.includes('audio') || t.includes('microphone')) return 'mic';
    if (t.includes('folder') || t.includes('filesystem') || t.includes('files')) return 'folder';
    if (t.includes('device') || t.includes('gpu')) return 'memory';
    if (t.includes('bus') || t.includes('portal') || t.includes('agent') || t.includes('ipc')) return 'settings';
    if (t.includes('proprietary')) return 'warning';
    if (t.includes('home')) return 'home';
    return 'security';
}

// Icon for a transaction-preview warning notice (unsafe perms, unverified, maintainer, etc.).
// Falls back to a severity-appropriate glyph when the title doesn't match a known case.
function getWarningIcon(title, level) {
    const t = (title || '').toLowerCase();
    if (t.includes('unverified') || t.includes('not verified')) return 'gpp_maybe';
    if (t.includes('verified')) return 'verified';
    if (t.includes('proprietary') || t.includes('closed')) return 'lock';
    if (t.includes('maintainer') || t.includes('hands')) return 'manage_accounts';
    if (t.includes('orphan')) return 'person_off';
    if (t.includes('out-of-date') || t.includes('out of date') || t.includes('outdated')) return 'update';
    if (t.includes('community') || t.includes('aur')) return 'groups';
    if (t.includes('permission') || t.includes('unsafe') || t.includes('access')) return 'shield';
    if (level === 'danger') return 'gpp_bad';
    if (level === 'warn') return 'warning';
    return 'info';
}

function permissionsPopupHtml(meta) {
    const rows = (meta.permissions || []).map(p => {
        const icon = getPermissionIcon(p.title);
        let colorClass = 'perm-icon-safe';
        if (p.level === 'danger') colorClass = 'perm-icon-danger';
        else if (p.level === 'warn') colorClass = 'perm-icon-warn';
        
        return `
        <li class="perm-item">
            <div class="rich-badge-icon ${colorClass}"><span class="material-symbols-outlined">${icon}</span></div>
            <div class="perm-text-group">
                <span class="perm-title">${escapeHtml(p.title)}</span>
                <span class="perm-detail">${escapeHtml(p.detail)}</span>
            </div>
        </li>`;
    }).join('');
    return `<p class="popup-note">These are the sandbox permissions this app <strong>declares</strong> — what it <em>can</em> access, not what it necessarily does. This is an advisory summary, not a safety guarantee.</p>
            <ul class="perm-list">${rows}</ul>`;
}

function verificationPopupHtml(meta, type) {
    if (type && normalizeType(type) === 'aur') {
        return `<p>This package is sourced from the <strong>Arch User Repository (AUR)</strong>. All AUR packages are community-maintained and are not officially verified by Arch Linux or the original developers.</p>
                <p class="popup-note">Always review the PKGBUILD before installing. You are trusting the package maintainer, not the original vendor.</p>`;
    }
    if (meta.verified) {
        const via = meta.verified_via ? ` (via <code>${escapeHtml(meta.verified_via)}</code>)` : '';
        return `<p>The developer has <strong>verified</strong> ownership of this app on Flathub${via}, so you're getting it from the official source.</p>`;
    }
    return `<p>This app is <strong>not developer-verified</strong> on Flathub. It may be community-maintained or a repackaging rather than published by the original developer — for example, many popular proprietary apps (Spotify, Discord, …) are packaged by volunteers, not the vendor.</p>
            <p class="popup-note">Common and not necessarily unsafe — but you're trusting whoever maintains the package, not the original vendor.</p>`;
}

function licensePopupHtml(meta) {
    const lic = meta.license ? `<p class="popup-note">License: <code>${escapeHtml(meta.license)}</code></p>` : '';
    const body = meta.is_free
        ? `<p>This app uses a <strong>free / open-source license</strong>. Its source code is publicly available, so it can be independently inspected and audited.</p>`
        : `<p>This app uses a <strong>proprietary license</strong>. Its source code is not public, so it cannot be independently audited — you're trusting the developer.</p>`;
    return body + lic;
}

// Pure: explains the composite AUR reputation score — the tier, then each signal's contribution
// (value + points/max), then the disclaimer. So the number isn't an opaque "15 · Risk".
function reputationPopupHtml(risk) {
    risk = risk || {};
    const tierLabel = { trusted: 'Trusted', caution: 'Caution', risk: 'Risk' }[risk.tier] || (risk.tier || 'Unknown');
    const rows = (risk.breakdown || []).map(b => {
        const max = b.max || 0;
        const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((b.points / max) * 100))) : 0;
        return `<div class="rep-row">
            <div class="rep-row-head">
                <span class="rep-row-label">${escapeHtml(b.label || b.key || '')}</span>
                <span class="rep-row-value">${escapeHtml(String(b.value == null ? '' : b.value))}</span>
                <span class="rep-row-points">${b.points}/${b.max}</span>
            </div>
            <div class="rep-bar"><div class="rep-bar-fill" style="width:${pct}%"></div></div>
        </div>`;
    }).join('');
    return `<p>Atlas's <strong>reputation score</strong> combines the AUR signals you'd otherwise weigh by hand `
        + `into one number: <strong>${risk.score == null ? '?' : risk.score}/100 · ${escapeHtml(tierLabel)}</strong>.</p>`
        + `<div class="rep-breakdown">${rows}</div>`
        + `<p class="popup-note">Heuristic only — <strong>not a safety check</strong>. A high score means the package has the reputation signals trusted packages usually have, not that its PKGBUILD is safe. Always review it.</p>`;
}

function maintainerChangePopupHtml(changed) {
    changed = changed || {};
    const oldM = escapeHtml(changed.old || 'unknown');
    const newM = changed.new ? escapeHtml(changed.new) : '<em>orphaned (no current maintainer)</em>';
    return `<p>This AUR package's maintainer has <strong>changed since you installed it</strong>:</p>`
        + `<p class="popup-note"><strong>${oldM} → ${newM}</strong></p>`
        + `<p>A package changing hands is common and usually fine, but it's worth a glance before you update — the new maintainer controls what gets built and run. <strong>Advisory, not a verdict.</strong></p>`;
}

// Find the multi-source group (from the current grid) that contains this package id, so the detail
// page can show the source-comparison panel. Returns null when not part of a known group.
function findGroupForPkgId(id) {
    return (currentGroups || []).find(g => (g.sources || []).some(s => s.id === id)) || null;
}

function openDetailModal(pkg, group) {
    const detailPkgId = String(pkg.id || '');
    detailModal.dataset.pkgId = detailPkgId;
    const stillCurrentDetail = () => detailModal.dataset.pkgId === detailPkgId;

    // Reset tabs for the new package: Overview active, files + comments cleared.
    const refreshTabs = () => { if (stillCurrentDetail()) updateDetailTabs(); };
    activateDetailTab('overview');
    const detailBody = detailModal.querySelector('.modal-body');
    if (detailBody) detailBody.scrollTop = 0;  // start at top; don't inherit the last package's scroll
    const filesSection = document.getElementById('detail-files-section');
    if (filesSection) { filesSection.classList.add('hidden'); document.getElementById('detail-files').innerHTML = ''; }
    const commentsSection = document.getElementById('detail-comments-section');
    if (commentsSection) commentsSection.classList.remove('collapsed');  // start expanded each open
    updateDetailTabs();

    const detailIcon = document.getElementById('detail-icon');
    detailIcon.src = getIconSrc(pkg.icon_url);
    const remoteUrl = getIconDataSrc(pkg.icon_url);
    if (remoteUrl) {
        const probe = new Image();
        probe.onload = () => { if (stillCurrentDetail()) detailIcon.src = remoteUrl; };
        probe.src = remoteUrl;
    } else if (pkg.installed && !(pkg.icon_url && pkg.icon_url.startsWith('data:'))) {
        // Installed app with no usable icon: resolve from the system (.desktop / icon theme), the
        // same lazy path the cards use — otherwise the modal shows a blank placeholder.
        pyApiCall('get_pkg_icon', pkg.id).then(uri => {
            if (!stillCurrentDetail()) return;
            if (!uri) return;
            const probe = new Image();
            probe.onload = () => { if (stillCurrentDetail()) detailIcon.src = uri; };
            probe.src = uri;
        });
    }
    document.getElementById('detail-icon').onerror = function() {
        this.onerror = null;
        this.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iIzY0NzQ4YiIgdmlld0JveD0iMCAwIDI0IDI0Ij48cmVjdCB4PSIzIiB5PSIzIiB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHJ4PSIyIiByeT0iMiI+PC9yZWN0Pjwvc3ZnPg==';
    };
    document.getElementById('detail-name').textContent = pkg.name;
    const typeLabel = sourceLabel(pkg.type);
    const typeBadge = document.getElementById('detail-type-badge');
    typeBadge.textContent = typeLabel;
    typeBadge.className = `meta-badge type-${normalizeType(pkg.type)}`;
    document.getElementById('detail-meta').innerHTML = `<span>v${escapeHtml(pkg.version || 'Unknown')}</span>`;
    document.getElementById('detail-description').textContent = pkg.description || 'No description available for this package.';

    // "Why this source?" trust hint — base from type now; refined for Flatpak when metadata arrives.
    renderWhySource(pkg);

    // Source-comparison panel (only when this app is offered by more than one source).
    const compareEl = document.getElementById('detail-source-compare');
    if (compareEl) compareEl.innerHTML = buildSourceCompareHTML(group || findGroupForPkgId(pkg.id));

    // Dependency summary (lazy, stale-guarded). Section stays hidden until there's something to show.
    Promise.resolve(renderDependencySummary(pkg, stillCurrentDetail)).finally(refreshTabs);

    // Link to the package's web page (AUR / official Arch). Routed through open_url so it
    // opens in the system browser rather than navigating the app window.
    const linkEl = document.getElementById('detail-link');
    const pageUrl = packagePageUrl(pkg);
    if (pageUrl) {
        const lt = normalizeType(pkg.type);
        linkEl.textContent = lt === 'aur' ? 'View on AUR ↗'
            : lt === 'flatpak' ? 'View on Flathub ↗'
            : 'View package page ↗';
        linkEl.onclick = (e) => { e.preventDefault(); openExternalUrl(pageUrl); };
        linkEl.classList.remove('hidden');
    } else {
        linkEl.classList.add('hidden');
        linkEl.onclick = null;
    }

    const table = document.getElementById('detail-table');
    table.innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-secondary);">Loading extended properties...</td></tr>`;

    detailModal.classList.remove('hidden');

    // Rich details grid (Sizes + Flathub/AUR metadata)
    const badgesEl = document.getElementById('rich-badges-grid');
    badgesEl.innerHTML = '';
    
    // Add Size Badges Synchronously
    let baseParts = [];
    if (pkg.size) {
        baseParts.push(`<div class="rich-badge-tile no-icon">
            <span class="rich-badge-icon"></span>
            <span class="rich-badge-value">${formatBytes(pkg.size)}</span>
            <span class="rich-badge-title">Installed Size</span>
        </div>`);
    }
    if (pkg.download_size) {
        baseParts.push(`<div class="rich-badge-tile no-icon">
            <span class="rich-badge-icon"></span>
            <span class="rich-badge-value">${formatBytes(pkg.download_size)}</span>
            <span class="rich-badge-title">Download</span>
        </div>`);
    }
    badgesEl.innerHTML = baseParts.join('');

    if (normalizeType(pkg.type) === 'flatpak') {
        pyApiCall('get_flatpak_meta', pkg.id).then(meta => {
            if (!stillCurrentDetail()) return;
            if (!meta || !Object.keys(meta).length) return;
            // Refine the "why this source?" hint now that we know verified/license.
            renderWhySource(pkg, { verified: meta.verified, free_license: meta.is_free });
            const parts = [];
            const hasPerms = (meta.permissions || []).length > 0;
            if (meta.safety && meta.safety.level) {
                let iconsHtml = '';
                if (hasPerms) {
                    const topPerms = meta.permissions.slice(0, 3);
                    iconsHtml = topPerms.map(p => {
                        let i = getPermissionIcon(p.title);
                        let colorClass = 'perm-icon-safe';
                        if (p.level === 'danger') colorClass = 'perm-icon-danger';
                        else if (p.level === 'warn') colorClass = 'perm-icon-warn';
                        
                        return `<div class="rich-badge-icon ${colorClass}"><span class="material-symbols-outlined">${i}</span></div>`;
                    }).join('');
                    
                    iconsHtml = `<div class="rich-badge-icon-container">${iconsHtml}</div>`;
                } else {
                    let icon = 'security';
                    if (meta.safety.level === 'safe') icon = 'verified_user';
                    else if (meta.safety.level === 'probably-safe') icon = 'gpp_maybe';
                    else icon = 'gpp_bad';
                    iconsHtml = `<div class="rich-badge-icon-container"><div class="rich-badge-icon"><span class="material-symbols-outlined">${icon}</span></div></div>`;
                }

                parts.push(`<div class="rich-badge-tile safety-${escapeHtml(meta.safety.level)}${hasPerms ? ' clickable' : ''}" data-popup="safety" title="${hasPerms ? 'Click for the permission details' : ''}">
                    ${iconsHtml}
                    <span class="rich-badge-value">${escapeHtml(meta.safety.label || 'Unknown')}</span>
                    <span class="rich-badge-title">Safety${hasPerms ? ' ⓘ' : ''}</span>
                </div>`);
            }
            if (typeof meta.is_free === 'boolean') {
                parts.push(`<div class="rich-badge-tile license-${meta.is_free ? 'foss' : 'proprietary'} clickable" data-popup="license" title="Click for license details">
                    <div class="rich-badge-icon-container"><div class="rich-badge-icon"><span class="material-symbols-outlined">${meta.is_free ? 'code' : 'lock'}</span></div></div>
                    <span class="rich-badge-value">${meta.is_free ? 'Open Source' : 'Proprietary'}</span>
                    <span class="rich-badge-title">License ⓘ</span>
                </div>`);
            }
            
            // Build the developer + verified UI in the header
            const devName = escapeHtml(meta.developer_name || pkg.developer || 'Unknown Developer');
            const verifiedHtml = meta.verified 
                ? `<span class="material-symbols-outlined verified-icon" data-popup="verified" title="Verified by Flathub">verified</span>` 
                : `<span class="material-symbols-outlined unverified-icon" data-popup="verified" title="Unverified community package">info</span>`;
            
            document.getElementById('detail-meta').innerHTML = `
                <span class="developer-name">${devName}</span>
                ${verifiedHtml}
                <span class="meta-separator">•</span>
                <span>v${escapeHtml(pkg.version || 'Unknown')}</span>
            `;
            if (meta.content_rating) {
                parts.push(`<div class="rich-badge-tile no-icon">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">${escapeHtml(meta.content_rating)}</span>
                    <span class="rich-badge-title">Age Rating</span>
                </div>`);
            }
            if (meta.desktop_only) {
                parts.push(`<div class="rich-badge-tile no-icon">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">Desktop</span>
                    <span class="rich-badge-title">Form Factor</span>
                </div>`);
            }
            if (typeof meta.installs_last_month === 'number') {
                parts.push(`<div class="rich-badge-tile no-icon" title="Installs in the last month (Flathub)">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">${meta.installs_last_month.toLocaleString()}</span>
                    <span class="rich-badge-title">Downloads/Month</span>
                </div>`);
            }
            badgesEl.insertAdjacentHTML('beforeend', parts.join(''));

            const safetyBadge = badgesEl.querySelector('[data-popup="safety"]');
            if (safetyBadge && hasPerms) {
                safetyBadge.addEventListener('click', () => showInfoPopup(meta.safety.label || 'Permissions', permissionsPopupHtml(meta)));
            }
            const licenseBadge = badgesEl.querySelector('[data-popup="license"]');
            if (licenseBadge) {
                licenseBadge.addEventListener('click', () => showInfoPopup(meta.is_free ? 'Open source' : 'Proprietary', licensePopupHtml(meta)));
            }
            const inlineVerifiedIcon = document.getElementById('detail-meta').querySelector('[data-popup="verified"]');
            if (inlineVerifiedIcon) {
                inlineVerifiedIcon.addEventListener('click', () => showInfoPopup(meta.verified ? 'Verified developer' : 'Unverified', verificationPopupHtml(meta, pkg.type)));
            }
        });
    } else if (normalizeType(pkg.type) === 'aur') {
        pyApiCall('get_aur_meta', pkg.id).then(info => {
            if (!stillCurrentDetail()) return;
            if (!info) return;
            const parts = [];
            if (info.update_available) {
                parts.push(`<div class="rich-badge-tile" title="A newer version is available on the AUR">
                    <div class="rich-badge-icon-container"><div class="rich-badge-icon"><span class="material-symbols-outlined">upgrade</span></div></div>
                    <span class="rich-badge-value">v${escapeHtml(info.latest_version || 'Update')}</span>
                    <span class="rich-badge-title">Update Available</span>
                </div>`);
            }
            
            // Build the developer + verified UI in the header
            const maint = info.maintainer;
            if (maint) {
                document.getElementById('detail-meta').innerHTML = `
                    <span class="developer-name">${escapeHtml(maint)}</span>
                    <span class="material-symbols-outlined unverified-icon" data-popup="verified" title="AUR packages are community-maintained">info</span>
                    <span class="meta-separator">•</span>
                    <span>v${escapeHtml(pkg.version || 'Unknown')}</span>
                `;
            } else if ('maintainer' in info) {
                 document.getElementById('detail-meta').innerHTML = `
                    <span class="developer-name text-danger">Orphaned</span>
                    <span class="material-symbols-outlined unverified-icon text-danger" data-popup="verified" title="No maintainer">error</span>
                    <span class="meta-separator">•</span>
                    <span>v${escapeHtml(pkg.version || 'Unknown')}</span>
                `;
            }
            
            const inlineVerifiedIcon = document.getElementById('detail-meta').querySelector('[data-popup="verified"]');
            if (inlineVerifiedIcon) {
                const aurMeta = { verified: false, verified_via: null };
                inlineVerifiedIcon.addEventListener('click', () => showInfoPopup('AUR Community Package', verificationPopupHtml(aurMeta, pkg.type)));
            }
            if (info.changed) {
                parts.push(`<div class="rich-badge-tile clickable" data-popup="maint" title="Click for details">
                    <div class="rich-badge-icon-container"><div class="rich-badge-icon"><span class="material-symbols-outlined">manage_accounts</span></div></div>
                    <span class="rich-badge-value">Changed</span>
                    <span class="rich-badge-title">Maintainer ⓘ</span>
                </div>`);
            }
            if (info.risk && info.risk.score !== undefined) {
                const tierLabel = { trusted: 'Trusted', caution: 'Caution', risk: 'Risk' }[info.risk.tier] || info.risk.tier;
                parts.push(`<div class="rich-badge-tile clickable risk-${escapeHtml(info.risk.tier)}" data-popup="reputation" title="Click to see how this score is calculated">
                    <div class="rich-badge-icon-container"><div class="rich-badge-icon"><span class="material-symbols-outlined">shield</span></div></div>
                    <span class="rich-badge-value">${info.risk.score} · ${escapeHtml(tierLabel)}</span>
                    <span class="rich-badge-title">Reputation ⓘ</span>
                </div>`);
            }
            // Surface the score's own inputs as badges — fills the grid and shows the trust signals
            // at a glance (votes/popularity), plus the out-of-date flag when set.
            if (typeof info.votes === 'number') {
                parts.push(`<div class="rich-badge-tile no-icon" title="AUR community votes">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">${info.votes.toLocaleString()}</span>
                    <span class="rich-badge-title">Votes</span>
                </div>`);
            }
            if (typeof info.popularity === 'number') {
                parts.push(`<div class="rich-badge-tile no-icon" title="AUR popularity (recent install activity)">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">${info.popularity.toFixed(2)}</span>
                    <span class="rich-badge-title">Popularity</span>
                </div>`);
            }
            if (info.out_of_date) {
                parts.push(`<div class="rich-badge-tile risk-risk" title="The AUR community has flagged this package out of date">
                    <div class="rich-badge-icon-container"><div class="rich-badge-icon"><span class="material-symbols-outlined">schedule</span></div></div>
                    <span class="rich-badge-value">Flagged</span>
                    <span class="rich-badge-title">Out of Date</span>
                </div>`);
            }
            badgesEl.insertAdjacentHTML('beforeend', parts.join(''));
            const mb = badgesEl.querySelector('[data-popup="maint"]');
            if (mb) mb.addEventListener('click', () => showInfoPopup('Maintainer changed', maintainerChangePopupHtml(info.changed)));
            const rb = badgesEl.querySelector('[data-popup="reputation"]');
            if (rb) rb.addEventListener('click', () => showInfoPopup('AUR reputation score', reputationPopupHtml(info.risk)));

            if (info.update_available && pkg.installed && !pkg.update_available) {
                const old = document.getElementById('detail-action-btn');
                if (old) {
                    const upd = document.createElement('button');
                    upd.className = 'btn btn-primary';
                    upd.id = 'detail-action-btn';
                    upd.textContent = 'Update';
                    upd.onclick = () => { detailModal.classList.add('hidden'); updateApp(pkg.id); };
                    old.replaceWith(upd);
                }
            }
        });
    }

    // Manage-permissions entry point (installed Flatpaks only; uses flatpak info/override, so it
    // works even for apps not on Flathub — independent of the badges above).
    const permActionEl = document.getElementById('detail-perms-action');
    permActionEl.innerHTML = '';
    if (normalizeType(pkg.type) === 'flatpak' && pkg.installed) {
        permActionEl.innerHTML = `<button class="btn btn-outline" id="manage-perms-btn">⚙ Manage permissions</button>`;
        document.getElementById('manage-perms-btn').addEventListener('click', () => openPermissionsEditor(pkg));
    }

    // Rich detail extras (read-only): screenshots for Flatpak/AppImage and version history.
    // Re-evaluate which tabs to show once a section's content (or lack of it) settles.
    Promise.resolve(renderDetailScreenshots(pkg, stillCurrentDetail)).finally(refreshTabs);
    Promise.resolve(renderDetailHistory(pkg, stillCurrentDetail)).finally(refreshTabs);
    Promise.resolve(renderPackageActivity(pkg, stillCurrentDetail)).finally(refreshTabs);
    Promise.resolve(renderAurComments(pkg, stillCurrentDetail)).finally(refreshTabs);

    // Fetch key-value info from python
    pyApiCall('get_info', pkg.id).then(info => {
        if (!stillCurrentDetail()) return;
        table.innerHTML = '';
        if (info && Object.keys(info).length > 0) {
            
            // If download or installed sizes are returned from the deeper info check and we didn't have them
            if (!pkg.size && info.installed) {
                badgesEl.insertAdjacentHTML('afterbegin', `<div class="rich-badge-tile no-icon">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">${escapeHtml(info.installed)}</span>
                    <span class="rich-badge-title">Installed Size</span>
                </div>`);
            }
            if (!pkg.download_size && info.download) {
                badgesEl.insertAdjacentHTML('afterbegin', `<div class="rich-badge-tile no-icon">
                    <span class="rich-badge-icon"></span>
                    <span class="rich-badge-value">${escapeHtml(info.download)}</span>
                    <span class="rich-badge-title">Download Size</span>
                </div>`);
            }

            const seenLabels = new Set();
            Object.entries(info).forEach(([key, val]) => {
                // Skip empty, null, undefined, or 'None' values to keep the table clean
                if (val === null || val === undefined || val === '' || val === 'None' || val === 'none' || val === 'null') {
                    return;
                }
                if (Array.isArray(val) && val.length === 0) {
                    return;
                }

                const label = prettifyInfoKey(key);
                const labelKey = label.toLowerCase();
                // The installed-files list (pacman -Qlq) can be thousands of entries — render it as a
                // dedicated filterable/scrollable block instead of a giant table cell.
                if (labelKey === 'installed files' && Array.isArray(val)) {
                    renderInstalledFiles(val);
                    refreshTabs();
                    return;
                }
                // Drop rows that just repeat the header (name / version / description),
                // and collapse duplicate labels (e.g. AUR's 00_url + 10_url) to the first.
                if (SKIP_DETAIL_KEYS.has(labelKey) || seenLabels.has(labelKey)) {
                    return;
                }
                seenLabels.add(labelKey);

                const tr = document.createElement('tr');
                const tdKey = document.createElement('td');
                tdKey.textContent = label;
                const tdVal = document.createElement('td');
                
                if (Array.isArray(val)) {
                    // Format arrays nicely as a comma-separated list
                    tdVal.textContent = val.join(', ');
                } else if (typeof val === 'object') {
                    tdVal.textContent = JSON.stringify(val);
                } else {
                    tdVal.textContent = String(val);
                }
                
                tr.appendChild(tdKey);
                tr.appendChild(tdVal);
                table.appendChild(tr);
            });
        } else {
            table.innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-secondary);">No additional properties available.</td></tr>`;
        }
    });

    // Action button in footer
    const footer = document.getElementById('modal-footer');
    footer.innerHTML = '';
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn btn-outline';
    closeBtn.textContent = 'Close';
    closeBtn.onclick = () => detailModal.classList.add('hidden');
    
    let actionBtn = null;
    if (pkg.installed) {
        if (pkg.update_available) {
            actionBtn = document.createElement('button');
            actionBtn.className = 'btn btn-primary';
            actionBtn.id = 'detail-action-btn';
            actionBtn.textContent = 'Update';
            actionBtn.onclick = () => {
                detailModal.classList.add('hidden');
                updateApp(pkg.id);
            };
        } else {
            actionBtn = document.createElement('button');
            actionBtn.className = 'btn btn-danger';
            actionBtn.id = 'detail-action-btn';
            actionBtn.textContent = 'Uninstall';
            actionBtn.onclick = () => {
                detailModal.classList.add('hidden');
                uninstallApp(pkg.id);
            };
        }
    } else {
        actionBtn = document.createElement('button');
        actionBtn.className = 'btn btn-primary';
        actionBtn.id = 'detail-action-btn';
        actionBtn.textContent = 'Install';
        actionBtn.onclick = () => {
            detailModal.classList.add('hidden');
            installApp(pkg.id);
        };
    }
    
    // "Copy command" — the equivalent terminal command for the primary action (left-aligned, so it
    // reads as a utility, not a commit button). Sources with a clean one-liner only.
    const cmdType = normalizeType(pkg.type);
    if (['arch_repo', 'arch', 'aur', 'flatpak'].includes(cmdType)) {
        const cmdAction = !pkg.installed ? 'install' : (pkg.update_available ? 'update' : 'uninstall');
        const copyCmdBtn = document.createElement('button');
        copyCmdBtn.className = 'btn btn-outline';
        copyCmdBtn.style.marginRight = 'auto';   // push the rest (Close / action) to the right
        copyCmdBtn.textContent = '⧉ Copy command';
        copyCmdBtn.title = 'Copy the equivalent terminal command';
        copyCmdBtn.onclick = () => copyEquivalentCommand(pkg.id, cmdAction, copyCmdBtn);
        footer.appendChild(copyCmdBtn);
    }

    footer.appendChild(closeBtn);

    // Roll back to a previous version (gem decides the target / may prompt).
    if (pkg.installed && pkg.can_be_downgraded) {
        const downgradeBtn = document.createElement('button');
        downgradeBtn.className = 'btn btn-outline';
        downgradeBtn.textContent = 'Downgrade';
        downgradeBtn.title = 'Roll back to a previous version';
        downgradeBtn.onclick = () => {
            detailModal.classList.add('hidden');
            downgradeApp(pkg.id);
        };
        footer.appendChild(downgradeBtn);
    }

    // Add-to-queue toggle (not-installed only) — collect for a batch install without leaving the page.
    if (!pkg.installed) {
        const qBtn = document.createElement('button');
        const setQLabel = () => {
            const q = queueHas(pkg.id);
            qBtn.className = `btn btn-outline${q ? ' queued' : ''}`;
            qBtn.textContent = q ? '✓ Queued' : '＋ Queue';
            qBtn.title = q ? 'Remove from install queue' : 'Add to install queue';
        };
        setQLabel();
        qBtn.onclick = () => {
            if (queueHas(pkg.id)) queueRemove(pkg.id); else queueAdd(pkg);
            setQLabel();
        };
        footer.appendChild(qBtn);
    }

    if (actionBtn) {
        footer.appendChild(actionBtn);
    }
}

modalClose.addEventListener('click', () => detailModal.classList.add('hidden'));
modalBackdrop.addEventListener('click', () => detailModal.classList.add('hidden'));

// PKGBUILD viewer interactions: close, backdrop, escape, finding→line scroll, in-text links.
if (pkgbuildModal) {
    document.getElementById('pkgbuild-close').addEventListener('click', closePkgbuildViewer);
    const pkgbBackdrop = pkgbuildModal.querySelector('.modal-backdrop');
    if (pkgbBackdrop) pkgbBackdrop.addEventListener('click', closePkgbuildViewer);
    pkgbuildModal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closePkgbuildViewer();
    });
    // Click a flagged finding → scroll its line into view and flash it.
    document.getElementById('pkgbuild-findings').addEventListener('click', (e) => {
        const a = e.target.closest('.pkgb-finding-link');
        if (!a) return;
        e.preventDefault();
        const line = document.getElementById(`pkgb-line-${a.dataset.line}`);
        if (line) {
            line.scrollIntoView({ behavior: 'smooth', block: 'center' });
            line.classList.add('pkgb-line-flash');
            setTimeout(() => line.classList.remove('pkgb-line-flash'), 1200);
        }
    });
    // Row hover highlight driven from JS, not CSS :hover — WebKitGTK can fail to clear :hover on
    // fast pointer movement, leaving a trail of stuck-highlighted lines. We keep exactly one lit.
    const pkgbCode = document.getElementById('pkgbuild-code');
    if (pkgbCode) {
        let hoveredLine = null;
        const clearPkgbHover = () => {
            if (hoveredLine) { hoveredLine.classList.remove('pkgb-hover'); hoveredLine = null; }
        };
        pkgbCode.addEventListener('mouseover', (e) => {
            const line = e.target.closest('.pkgb-line');
            if (line === hoveredLine) return;
            clearPkgbHover();
            if (line && pkgbCode.contains(line)) { line.classList.add('pkgb-hover'); hoveredLine = line; }
        });
        pkgbCode.addEventListener('mouseleave', clearPkgbHover);
    }
    // Open upstream/source URLs in the system browser.
    pkgbuildModal.addEventListener('click', (e) => {
        const a = e.target.closest('.pkgb-link');
        if (!a) return;
        e.preventDefault();
        if (a.dataset.url) openExternalUrl(a.dataset.url);
    });
    // Switch tabs (PKGBUILD ↔ .install scriptlets).
    document.getElementById('pkgbuild-tabs').addEventListener('click', (e) => {
        const tab = e.target.closest('.pkgb-tab');
        if (tab) renderPkgbuildTab(Number(tab.dataset.tab));
    });
    // Copy the active file's raw text.
    const pkgbCopyBtn = document.getElementById('pkgbuild-copy-btn');
    if (pkgbCopyBtn) pkgbCopyBtn.addEventListener('click', () => {
        const view = pkgbuildViews[pkgbuildActiveTab];
        if (!view) return;
        const text = view.kind === 'diff'
            ? (view.diff || []).map(d => d.text).join('\n')
            : view.text;
        if (!text) return;
        const done = () => {
            const orig = pkgbCopyBtn.textContent;
            pkgbCopyBtn.textContent = '✓ Copied';
            setTimeout(() => { pkgbCopyBtn.textContent = orig; }, 1500);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done).catch(() => {});
        }
    });
}

// Multi-Select and Batch Panel
selectModeBtn.addEventListener('click', () => {
    toggleSelectMode(!selectMode);
});

function toggleSelectMode(active) {
    selectMode = active;
    selectedPackages.clear();
    updateBatchBar();
    
    if (selectMode) {
        selectModeBtn.textContent = 'Exit Select';
        selectModeBtn.classList.add('btn-primary');
        document.querySelectorAll('.package-card').forEach(card => {
            card.classList.add('select-mode');
        });
    } else {
        selectModeBtn.textContent = 'Select';
        selectModeBtn.classList.remove('btn-primary');
        document.querySelectorAll('.package-card').forEach(card => {
            card.classList.remove('select-mode', 'selected');
            const chk = card.querySelector('.pkg-checkbox');
            if (chk) chk.checked = false;
        });
    }
}

function updateBatchBar() {
    if (selectMode && selectedPackages.size > 0) {
        let installedCount = 0;
        let uninstalledCount = 0;
        selectedPackages.forEach(id => {
            const pkg = currentPackages.find(p => p.id === id);
            if (pkg) {
                if (pkg.installed) {
                    installedCount++;
                } else {
                    uninstalledCount++;
                }
            }
        });

        batchCount.textContent = `${selectedPackages.size} selected`;

        if (installedCount > 0) {
            batchUninstallBtn.classList.remove('hidden');
            batchUninstallBtn.textContent = `Uninstall Selected (${installedCount})`;
        } else {
            batchUninstallBtn.classList.add('hidden');
        }

        if (uninstalledCount > 0) {
            batchInstallBtn.classList.remove('hidden');
            batchInstallBtn.textContent = `Install Selected (${uninstalledCount})`;
        } else {
            batchInstallBtn.classList.add('hidden');
        }

        batchBar.classList.remove('hidden');
    } else {
        batchBar.classList.add('hidden');
    }
}

batchInstallBtn.addEventListener('click', async () => {
    if (selectedPackages.size === 0) return;
    const ids = Array.from(selectedPackages);
    const toInstall = ids.filter(id => {
        const pkg = currentPackages.find(p => p.id === id);
        return pkg && !pkg.installed;
    });
    if (toInstall.length === 0) return;
    toggleSelectMode(false);
    showToast('Batch Installing', `Installing ${toInstall.length} package(s)...`, 'info');
    
    const result = await pyApiCall('batch_install', toInstall);
    if (result && result.success) {
        packageCache = {}; // Invalidate cache on batch operation completion
        showToast('Success', 'Selected packages installed', 'success');
    } else {
        showToast('Error', result ? result.error : 'Batch operation failed', 'error');
    }
});

batchUninstallBtn.addEventListener('click', async () => {
    if (selectedPackages.size === 0) return;
    const ids = Array.from(selectedPackages);
    const toUninstall = ids.filter(id => {
        const pkg = currentPackages.find(p => p.id === id);
        return pkg && pkg.installed;
    });
    if (toUninstall.length === 0) return;
    toggleSelectMode(false);
    showToast('Batch Uninstalling', `Uninstalling ${toUninstall.length} package(s)...`, 'info');
    
    const result = await pyApiCall('batch_uninstall', toUninstall);
    if (result && result.success) {
        packageCache = {}; // Invalidate cache on batch operation completion
        showToast('Success', 'Selected packages uninstalled', 'success');
    } else {
        showToast('Error', result ? result.error : 'Batch operation failed', 'error');
    }
});

batchCancelBtn.addEventListener('click', () => {
    toggleSelectMode(false);
});

// ---- Install-queue wiring (Theme 5) ----
loadQueue();
updateQueueBadge();
const queueBtn = document.getElementById('queue-btn');
if (queueBtn) queueBtn.addEventListener('click', openQueueModal);
const queueModal = document.getElementById('queue-modal');
if (queueModal) {
    queueModal.addEventListener('click', (e) => {
        if (e.target.closest('[data-queue-close]')) { queueModal.classList.add('hidden'); return; }
        const remove = e.target.closest('[data-queue-remove]');
        if (remove) {
            queueRemove(remove.getAttribute('data-queue-remove'));
            // Re-render the list; reflect the removal on any visible card toggle for this package too.
            openQueueModal();
            document.querySelectorAll(`.queue-toggle[data-id="${CSS.escape(remove.getAttribute('data-queue-remove'))}"]`)
                .forEach(b => { b.classList.remove('queued'); b.textContent = '＋ Queue'; b.title = 'Add to install queue'; });
        }
    });
}
const queueClearBtn = document.getElementById('queue-clear-btn');
if (queueClearBtn) queueClearBtn.addEventListener('click', () => {
    queueClear();
    openQueueModal();
    document.querySelectorAll('.queue-toggle.queued').forEach(b => {
        b.classList.remove('queued'); b.textContent = '＋ Queue'; b.title = 'Add to install queue';
    });
});
const queueInstallAllBtn = document.getElementById('queue-install-all-btn');
if (queueInstallAllBtn) queueInstallAllBtn.addEventListener('click', installQueuedPackages);

updateAllBtn.addEventListener('click', async () => {
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }

    // Cheap pre-flight signals (news since last sync + pending .pacnew + one batched AUR
    // reputation-tier call). Fail-open — a null result just means that signal is omitted; the
    // upgrade is never blocked by a check failing.
    const updates = (currentPackages || []).filter(p => p && p.update_available);
    // The pre-flight (news + .pacnew + AUR risk scoring) can take a beat on a large update
    // set, so give immediate feedback rather than a dead button.
    showToast('Preparing update', `Checking ${updates.length} package${updates.length === 1 ? '' : 's'}…`, 'info');
    const news = await pyApiCall('check_upgrade_news');
    const pacnew = await pyApiCall('get_pacnew_files');
    const riskTiers = await pyApiCall('get_update_risk_tiers', updates.map(p => p.id));
    const prefs = await pyApiCall('get_update_all_prefs');  // remembered source skip list

    // Aggregate preview: how many packages, the source split, total download size, and the above
    // signals — built from the already-loaded updates list (no extra read_installed).
    const previewData = buildUpdateAllPreviewData(updates, {
        news_count: news ? news.new_count : 0,
        pacnew_count: pacnew ? pacnew.count : 0,
        tiers: riskTiers,
        excluded: (prefs && prefs.exclude) || [],
    });
    const proceed = await openTransactionPreview(previewData);
    if (!proceed) { showToast('Upgrade cancelled', 'Nothing was changed', 'info'); return; }

    // Read the source selection from the (still-rendered) chooser: any unticked source is skipped.
    const excludeSources = [...document.querySelectorAll('#tx-preview-body input[data-source]')]
        .filter(t => !t.checked).map(t => t.dataset.source);

    // Arch news gate: after the aggregate, show the actual articles (clickable) so the user can read
    // any manual-intervention notice before `-Syu`.
    if (news && news.new_count > 0) {
        const ok = await showNewsGate(news.news);
        if (!ok) {
            showToast('Upgrade cancelled', 'Review the Arch news, then run Update All again', 'info');
            return;
        }
    }

    showToast('Updating All', 'Starting system packages upgrade...', 'info');
    const result = await pyApiCall('update_all', excludeSources);
    if (result && result.success) {
        showToast('Success', 'System upgrade finished', 'success');
    } else {
        showToast('Error', result ? result.error : 'Bulk upgrade failed', 'error');
    }
    refreshUpdatesBadge();  // count should drop to ~0 after a full upgrade
});

async function checkOrphans() {
    // Cheap count only (pacman -Qtdq). The full list is fetched on click, so the badge
    // shows instantly and reliably without a slow read_installed.
    const res = await pyApiCall('get_orphan_count');
    const count = (res && typeof res.count === 'number') ? res.count : 0;
    if (count > 0) {
        cleanupOrphansBtn.classList.remove('hidden');
        cleanupOrphansBtn.innerHTML = `
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6l-1 14H6L5 6"></path>
                <path d="M10 11v6M14 11v6"></path>
            </svg>
            Cleanup ${escapeHtml(count)} Orphan${count > 1 ? 's' : ''}
        `;
    } else {
        cleanupOrphansBtn.classList.add('hidden');
    }
}

// Shared orphan-cleanup flow used by both the topbar button and the Disk-view
// maintenance panel. Returns true if packages were actually removed.
async function runOrphanCleanup() {
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return false; }

    // Fetch the real orphan list on demand (the badge only knows the count).
    const orphans = await pyApiCall('get_orphans');
    if (!orphans || orphans.length === 0) {
        showToast('Nothing to clean', 'There are no orphan packages to remove', 'info');
        cleanupOrphansBtn.classList.add('hidden');
        return false;
    }

    // Show the orphans as a checklist (all ticked) so the user can keep any they still
    // want. Reuses the confirm-modal's MultipleSelectComponent rendering.
    const components = [{
        kind: 'multiselect',
        label: '',
        options: orphans.map((p, i) => ({ oi: i, label: p.name, tooltip: null,
                                          selected: true, readOnly: false, icon: null })),
    }];
    const res = await pyApiCall('prompt_confirmation',
        'Remove orphan packages?',
        'These were installed as dependencies and are no longer required. Uncheck any you want to keep:',
        'Remove selected', 'Cancel', true, components);

    if (!(res && res[0])) return false;  // cancelled
    const selectedIdx = (res[1] && res[1][0]) || [];   // selected option indices of component 0
    const ids = selectedIdx.map(i => orphans[i] && orphans[i].id).filter(Boolean);
    if (ids.length === 0) {
        showToast('Nothing selected', 'No packages were selected to remove', 'info');
        return false;
    }

    showToast('Orphan Cleanup', "Removing " + ids.length + " package(s)...", 'info');
    const result = await pyApiCall('batch_uninstall', ids);
    if (result && result.success) {
        packageCache = {}; // Invalidate cache on orphan cleanup
        showToast('Success', 'Selected packages removed', 'success');
        checkOrphans();
        return true;
    }
    showToast('Error', result ? result.error : 'Orphan cleanup failed', 'error');
    return false;
}

cleanupOrphansBtn.addEventListener('click', async () => {
    if (await runOrphanCleanup()) refreshCurrentView();
});

function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 B';
    const k = 1000;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'kB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

async function renderDiskView() {
    packagesGrid.style.display = 'grid';
    emptyState.classList.add('hidden');
    loadingState.classList.add('hidden');
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, getSkeletonGridHTML());

    const data = await pyApiCall('get_disk_usage');
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    loadingState.classList.add('hidden');

    if (!data) {
        packagesGrid.style.display = 'block';
        packagesGrid.innerHTML = '<div style="padding: 32px; color: var(--text-secondary); text-align: center;">Error loading disk usage data.</div>';
        return;
    }

    const { packages, by_type } = data;
    diskPackages = packages || []; // Store globally for event delegation click listener

    if (diskPackages.length === 0) {
        packagesGrid.style.display = 'block';
        packagesGrid.innerHTML = '<div style="padding: 32px; color: var(--text-secondary); text-align: center;">No packages found with disk usage information.</div>';
        return;
    }

    packagesGrid.style.display = 'block';
    
    // Calculate total bytes
    const totalBytes = by_type.reduce((acc, curr) => acc + curr.total_bytes, 0);
    const totalHuman = formatBytes(totalBytes);

    let html = `
        <div class="disk-view-container">
            <div id="maintenance-panel"></div>
            <div class="disk-summary-card">
                <div class="disk-summary-title">Total Managed Disk Usage</div>
                <div class="disk-summary-value">${escapeHtml(totalHuman)}</div>
                
                <div class="disk-chart-container">
                    <div class="disk-bar-track">
    `;

    const typeColors = {
        'flatpak': '#38bdf8',
        'snap': '#f43f5e',
        'appimage': '#a855f7',
        'aur': '#f59e0b',
        'web': '#10b981',
        'unknown': '#64748b'
    };

    const getColorForType = (type) => {
        const t = type.toLowerCase();
        return typeColors[t] || '#6366f1';
    };

    // Render bar segments
    by_type.forEach(item => {
        const percentage = totalBytes > 0 ? ((item.total_bytes / totalBytes) * 100).toFixed(1) : 0;
        if (percentage > 0) {
            const color = getColorForType(item.type);
            html += `<div class="disk-bar-fill" style="width: ${percentage}%; background-color: ${color};" title="${escapeHtml(item.type)}: ${escapeHtml(item.total_human)} (${percentage}%)"></div>`;
        }
    });

    html += `
                    </div>
                </div>
                
                <div class="disk-legend">
    `;

    by_type.forEach(item => {
        const percentage = totalBytes > 0 ? ((item.total_bytes / totalBytes) * 100).toFixed(1) : 0;
        const color = getColorForType(item.type);
        html += `
            <div class="legend-item">
                <span class="legend-dot" style="background-color: ${color};"></span>
                <span class="legend-label">${escapeHtml(item.type)}</span>
                <span class="legend-value">${escapeHtml(item.total_human)} (${percentage}%)</span>
            </div>
        `;
    });

    html += `
                </div>
            </div>
            
            <div class="disk-packages-section">
                <div class="disk-section-title">Package Breakdown</div>
                <div class="disk-packages-list">
    `;

    diskPackages.forEach(pkg => {
        const color = getColorForType(pkg.type);
        html += `
            <div class="disk-package-row" data-id="${escapeHtml(pkg.id)}">
                <div class="disk-package-left">
                    <span class="disk-package-name" title="${escapeHtml(pkg.name)}">${escapeHtml(pkg.name)}</span>
                    <span class="disk-package-tag" style="background-color: ${color}20; color: ${color}; border: 1px solid ${color}40;">${escapeHtml(pkg.type)}</span>
                </div>
                <div class="disk-package-right">
                    <span class="disk-package-size">${escapeHtml(pkg.size_human)}</span>
                </div>
            </div>
        `;
    });

    html += `
                </div>
            </div>
        </div>
    `;

    packagesGrid.innerHTML = html;
    renderMaintenancePanel();
}

// "Reclaim space" maintenance panel at the top of the Disk view. Surfaces the three big
// Arch space-wasters (orphans / pacman cache / unused Flatpak runtimes) with a size or
// count estimate and an action button. Backed by the cheap, read-only get_cleanup_summary.
async function renderMaintenancePanel() {
    const panel = document.getElementById('maintenance-panel');
    if (!panel) return;

    const data = await pyApiCall('get_cleanup_summary');  // unwrapped {orphans, pacman_cache, flatpak}
    if (!data) { panel.innerHTML = ''; return; }

    const rows = [];

    const orphanCount = (data.orphans && data.orphans.count) || 0;
    if (orphanCount > 0) {
        rows.push(maintenanceRow('orphans', 'Orphan packages',
            `${orphanCount} package${orphanCount > 1 ? 's' : ''} installed as dependencies, no longer required`,
            'Review & remove'));
    }

    const cache = data.pacman_cache || {};
    if (cache.available) {
        rows.push(maintenanceRow('cache', 'Package cache',
            `${cache.total_human} cached · clear tarballs for packages no longer installed`,
            'Clean cache'));
    }

    if (data.flatpak && data.flatpak.available) {
        rows.push(maintenanceRow('flatpak', 'Unused Flatpak runtimes',
            'Remove runtimes and extensions that no installed app uses', 'Remove unused'));
    }

    if (rows.length === 0) {
        panel.innerHTML = `<div class="maintenance-card maintenance-empty">✓ Nothing to clean up — your system is tidy.</div>`;
        return;
    }

    panel.innerHTML = `
        <div class="maintenance-card">
            <div class="maintenance-title">Reclaim space</div>
            <div class="maintenance-rows">${rows.join('')}</div>
        </div>`;

    panel.querySelectorAll('button[data-action]').forEach(btn => {
        btn.addEventListener('click', () => handleMaintenanceAction(btn.dataset.action));
    });
}

function maintenanceRow(action, title, desc, btnLabel, disabled = false) {
    return `
        <div class="maintenance-row">
            <div class="maintenance-row-info">
                <span class="maintenance-row-title">${escapeHtml(title)}</span>
                <span class="maintenance-row-desc">${escapeHtml(desc)}</span>
            </div>
            <button class="btn btn-secondary" data-action="${escapeHtml(action)}" ${disabled ? 'disabled' : ''}>${escapeHtml(btnLabel)}</button>
        </div>`;
}

async function handleMaintenanceAction(action, refresh) {
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }

    if (action === 'orphans') {
        const removed = await runOrphanCleanup();
        // Refresh the caller's view; default (Disk) keeps its lighter panel-only path when nothing changed.
        if (refresh) refresh();
        else if (removed) renderDiskView(); else renderMaintenancePanel();
        return;
    }

    if (action === 'cache') {
        const ok = await pyApiCall('prompt_confirmation',
            'Clean package cache?',
            'Remove cached package files for software that is no longer installed? Cache for installed packages is kept, so you can still downgrade.',
            'Clean', 'Cancel');
        if (!(ok && ok[0])) return;
        showToast('Cleaning cache', 'Removing old cached packages…', 'info');
        const result = await pyApiCall('clean_pacman_cache');  // null on error (already toasted)
        if (result && result.status === 'ok') {
            showToast('Cache cleaned', `Freed ${result.freed_human || '0 B'} from the package cache`, 'success');
            (refresh || renderDiskView)();
        }
        return;
    }

    if (action === 'flatpak') {
        const ok = await pyApiCall('prompt_confirmation',
            'Remove unused Flatpak runtimes?',
            'Remove Flatpak runtimes and extensions that no installed app uses?',
            'Remove', 'Cancel');
        if (!(ok && ok[0])) return;
        showToast('Flatpak cleanup', 'Removing unused runtimes…', 'info');
        const result = await pyApiCall('clean_flatpak_unused');
        if (result && result.status === 'ok') {
            showToast('Done', 'Unused Flatpak runtimes removed', 'success');
            (refresh || renderDiskView)();
        }
        return;
    }
}

// ===================== System Health (the "Arch cockpit") =====================
// Pure mapping of the get_system_health payload → ordered cards. Status/tone logic lives here so
// it's unit-tested in the Node VM harness. See docs/plans/2026-06-04-system-health.md.

// Audit rule-health card — fetched separately from the main health payload (the rescan is
// potentially long-running). Renders after the standard checks.
function buildAuditHealthCard(ar) {
    if (!ar) {
        return '<div class="health-card tone-info"><div class="health-head"><span class="health-icon">🔬</span><span class="health-title">PKGBUILD Audit Rules</span><span class="health-status">Not run</span></div><div class="health-detail">Sample live AUR packages to surface noisy rules (firing too often) and stale rules (never firing).</div><button class="health-action" data-health-action="audit-rescan">Run sample scan</button></div>';
    }
    if (ar.error) {
        return '<div class="health-card tone-info"><div class="health-head"><span class="health-icon">🔬</span><span class="health-title">PKGBUILD Audit Rules</span><span class="health-status">Error</span></div><div class="health-detail">' + escapeHtml(ar.error) + '</div><button class="health-action" data-health-action="audit-rescan">Retry scan</button></div>';
    }
    const r = ar.report;
    if (!r || !r.total) {
        return '<div class="health-card tone-info"><div class="health-head"><span class="health-icon">🔬</span><span class="health-title">PKGBUILD Audit Rules</span><span class="health-status">No data</span></div><div class="health-detail">The last scan did not return results. The AUR may be unreachable.</div><button class="health-action" data-health-action="audit-rescan">Retry scan</button></div>';
    }
    const fpCount = (r.fp_drift || []).length;
    const nfCount = (r.never_fired || []).length;
    const total = r.total;
    let tone = 'ok', status = 'Healthy';
    if (fpCount > 5) { tone = 'warn'; status = fpCount + ' noisy'; }
    if (nfCount > 15) { tone = 'warn'; status = nfCount + ' silent'; }
    if (fpCount > 10 || nfCount > 25) { tone = 'danger'; status = 'Review'; }
    const detail = total + ' PKGBUILDs scanned · ' + r.rules.length + ' rules active · ' + fpCount + ' noisy (>50% fire), ' + nfCount + ' never fired.';
    const more = fpCount ? 'Noisy rules: ' + r.fp_drift.map(function(x) { return x.rule + ' (' + Math.round(x.pct*100) + '%)'; }).join(', ') : '';
    var html = '<div class="health-card tone-' + tone + '"><div class="health-head"><span class="health-icon">🔬</span><span class="health-title">PKGBUILD Audit Rules</span><span class="health-status">' + escapeHtml(status) + '</span></div><div class="health-detail">' + escapeHtml(detail) + '</div>';
    if (more) html += '<details class="health-more"><summary>Noisy rules</summary><div class="health-more-body">' + escapeHtml(more) + '</div></details>';
    html += '<button class="health-action" data-health-action="audit-rescan">Rescan</button></div>';
    return html;
}

function systemHealthChecks(data) {
    const d = data || {};
    const checks = [];

    const ageH = d.db_sync ? d.db_sync.age_hours : null;
    if (ageH == null) {
        checks.push({ id: 'db', icon: '🔄', title: 'Database sync', tone: 'info',
            detail: 'Couldn’t determine when the package databases were last synced.',
            actionLabel: 'Open Updates', actionId: 'updates' });
    } else {
        const tone = ageH > 168 ? 'danger' : (ageH > 24 ? 'warn' : 'ok');
        checks.push({ id: 'db', icon: '🔄', title: 'Database sync', tone,
            detail: `Package databases last synced ${attnAge(ageH)} ago. Update from the Updates page (a full upgrade — never a bare sync).`,
            actionLabel: 'Open Updates', actionId: 'updates' });
    }

    const tool = d.mirrors ? d.mirrors.tool : null;
    checks.push(tool
        ? { id: 'mirrors', icon: '📡', title: 'Mirror list', tone: 'ok',
            detail: `Can be refreshed with ${tool} to use the fastest mirrors.`,
            actionLabel: 'Regenerate', actionId: 'mirrors' }
        : { id: 'mirrors', icon: '📡', title: 'Mirror list', tone: 'info',
            detail: 'Install reflector to regenerate the mirror list from Atlas.' });

    const locked = d.lock ? d.lock.locked : null;
    checks.push(locked
        ? { id: 'lock', icon: '🔒', title: 'Pacman lock', tone: 'danger',
            detail: 'A database lock (/var/lib/pacman/db.lck) is present — a package operation may be running, or a previous one was interrupted.',
            actionLabel: 'Remove stale lock', actionId: 'remove-lock',
            more: 'Atlas refuses to remove it while a pacman process is actually running, so this is safe when nothing is in progress.' }
        : { id: 'lock', icon: '🔒', title: 'Pacman lock', tone: 'ok',
            detail: 'No stale database lock.' });

    // Keyring freshness — a stale archlinux-keyring is the classic cause of PGP signature errors.
    const kd = d.keyring ? d.keyring.age_days : null;
    if (kd != null) {
        const stale = kd > 90;
        checks.push({ id: 'keyring', icon: '🔑', title: 'Keyring freshness', tone: stale ? 'warn' : 'ok',
            detail: stale
                ? `archlinux-keyring was last updated ${Math.round(kd)} days ago. A stale keyring causes “invalid or corrupted package (PGP signature)” errors — refresh it before a big upgrade.`
                : `archlinux-keyring updated ${Math.round(kd)} days ago.`,
            more: 'Refresh with: sudo pacman -Sy archlinux-keyring && sudo pacman-key --populate archlinux' });
    }

    // AUR index age — only shown when an index exists (AUR users); drives dependency resolution.
    const ai = d.aur_index ? d.aur_index.age_days : null;
    if (ai != null) {
        const old = ai > 14;
        checks.push({ id: 'aur-index', icon: '📇', title: 'AUR index', tone: old ? 'info' : 'ok',
            detail: old
                ? `The AUR package index is ${Math.round(ai)} days old. Refresh it so dependency resolution sees recently-added packages.`
                : `AUR package index refreshed ${Math.round(ai)} days ago.`,
            actionLabel: 'Refresh index', actionId: 'aur-index',
            more: 'Atlas downloads aur.archlinux.org/packages.gz and caches the package names locally.' });
    }

    const pn = d.pacnew ? d.pacnew.count : null;
    if (pn == null) checks.push({ id: 'pacnew', icon: '📝', title: 'Config files (.pacnew)', tone: 'info',
        detail: 'Couldn’t check for .pacnew/.pacsave files.' });
    else if (pn > 0) checks.push({ id: 'pacnew', icon: '📝', title: 'Config files (.pacnew)', tone: 'warn',
        detail: `${pn} config file${pn === 1 ? '' : 's'} left by updates need review and merging.`,
        actionLabel: 'Review files', actionId: 'pacnew-center' });
    else checks.push({ id: 'pacnew', icon: '📝', title: 'Config files (.pacnew)', tone: 'ok',
        detail: 'No .pacnew/.pacsave files to review.' });

    const orph = d.orphans ? d.orphans.count : null;
    if (orph == null) checks.push({ id: 'orphans', icon: '🧩', title: 'Orphan packages', tone: 'info',
        detail: 'Couldn’t determine orphan packages.' });
    else if (orph > 0) checks.push({ id: 'orphans', icon: '🧩', title: 'Orphan packages', tone: 'warn',
        detail: `${orph} package${orph === 1 ? '' : 's'} installed as dependencies but no longer required by anything.`,
        actionLabel: 'Review & remove', actionId: 'orphans' });
    else checks.push({ id: 'orphans', icon: '🧩', title: 'Orphan packages', tone: 'ok',
        detail: 'No orphan packages.' });

    const cache = d.cache ? d.cache.human : null;
    checks.push(cache
        ? { id: 'cache', icon: '💾', title: 'Package cache', tone: 'info',
            detail: `${cache} in the pacman cache. Cleaning keeps the cache for installed packages, so downgrades still work.`,
            actionLabel: 'Clean cache', actionId: 'cache' }
        : { id: 'cache', icon: '💾', title: 'Package cache', tone: 'info',
            detail: 'Package cache size is unavailable.' });

    if (d.flatpak && d.flatpak.unused_available) checks.push({ id: 'flatpak', icon: '📦',
        title: 'Flatpak runtimes', tone: 'info',
        detail: 'Remove Flatpak runtimes and extensions that no installed app uses.',
        actionLabel: 'Remove unused', actionId: 'flatpak' });

    const cr = d.chroot || {};
    if (!cr.available) checks.push({ id: 'chroot', icon: '🔧', title: 'AUR clean-chroot builds', tone: 'info',
        detail: 'Install devtools to build AUR packages in an isolated clean chroot.',
        actionLabel: 'Settings', actionId: 'settings' });
    else checks.push({ id: 'chroot', icon: '🔧', title: 'AUR clean-chroot builds', tone: cr.enabled ? 'ok' : 'info',
        detail: cr.enabled ? 'AUR packages build in an isolated clean chroot.'
                           : 'Available but off — enable it in Settings for safer AUR builds.',
        actionLabel: 'Settings', actionId: 'settings' });

    return checks;
}

function healthStatusLabel(tone) {
    return tone === 'ok' ? 'OK' : tone === 'warn' ? 'Attention'
        : tone === 'danger' ? 'Action needed' : 'Info';
}

function runHealthAction(actionId, btn) {
    switch (actionId) {
        case 'updates': activateView('updates'); break;
        case 'settings': activateView('settings'); break;
        case 'mirrors': regenerateMirrors(btn); break;
        case 'pacdiff': pyApiCall('launch_pacdiff'); break;
        case 'pacnew-center': openPacnewCenter(); break;
        case 'cache':
        case 'flatpak':
        case 'orphans': handleMaintenanceAction(actionId, renderSystemHealth); break;
        case 'remove-lock': removePacmanLock(btn); break;
        case 'aur-index': refreshAurIndex(btn); break;
        case 'audit-rescan': startAuditRescan(btn); break;
    }
}

// Remove a stale pacman db lock (backend refuses while pacman is actually running).
async function removePacmanLock(btn) {
    if (btn) btn.classList.add('loading');
    const r = await pyApiCall('remove_pacman_lock');  // null on error (toast already shown)
    if (btn) btn.classList.remove('loading');
    if (!r || r.status === 'cancelled') return;
    showToast('Pacman lock', r.removed ? 'Removed the stale lock' : 'No lock to remove', 'success');
    renderSystemHealth();
}

// Re-download the AUR package-name index (can take a few seconds).
async function refreshAurIndex(btn) {
    if (btn) btn.classList.add('loading');
    showToast('AUR index', 'Refreshing the AUR package index…', 'info');
    const r = await pyApiCall('refresh_aur_index');  // null on error (toast already shown)
    if (btn) btn.classList.remove('loading');
    if (!r) return;
    showToast('AUR index', 'AUR package index refreshed', 'success');
    renderSystemHealth();
}

async function startAuditRescan(btn) {
    if (btn) btn.classList.add('loading');
    showToast('Audit rules', 'Sampling live AUR PKGBUILDs — this can take a moment…', 'info');
    const r = await pyApiCall('start_audit_rescan', 80);  // null on error (toasted)
    if (btn) btn.classList.remove('loading');
    if (!r) return;
    // If we got a cached result back immediately, show it. Otherwise, poll once after a short delay.
    if (r.note) showToast('Audit rules', r.note, 'info');
    if (r.data) {
        renderSystemHealth();
    } else {
        // Scan just started — refresh after a few seconds to pick up results.
        setTimeout(() => { if (currentView === 'health') renderSystemHealth(); }, 4000);
    }
}

async function renderSystemHealth() {
    packagesGrid.style.display = 'block';
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, `<div class="state-container"><div class="spinner"></div><p>Checking system health…</p></div>`);
    const data = await pyApiCall('get_system_health');  // unwrapped data, or null on error
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    if (!data) {
        packagesGrid.innerHTML = emptyStateHTML({ icon: '📡', title: 'Couldn’t check system health',
            hint: 'Something went wrong gathering the checks. Try again.' });
        return;
    }
    const cards = systemHealthChecks(data).map(c => `
        <div class="health-card tone-${c.tone}">
            <div class="health-head">
                <span class="health-icon">${c.icon}</span>
                <span class="health-title">${escapeHtml(c.title)}</span>
                <span class="health-status">${escapeHtml(healthStatusLabel(c.tone))}</span>
            </div>
            <div class="health-detail">${escapeHtml(c.detail)}</div>
            ${c.more ? `<details class="health-more"><summary>Details</summary><div class="health-more-body">${escapeHtml(c.more)}</div></details>` : ''}
            ${c.actionLabel && c.actionId
                ? `<button class="health-action" data-health-action="${escapeHtml(c.actionId)}">${escapeHtml(c.actionLabel)}</button>`
                : ''}
        </div>`).join('');
    // Fetch the audit rule-health rescan result separately (it may still be running).
    let auditCard = '';
    try {
        const ar = await pyApiCall('get_audit_rescan_result');
        auditCard = buildAuditHealthCard(ar);
    } catch (e) { /* omit on error */ }
    packagesGrid.innerHTML = `<div class="health-page"><div class="browse-header">System health</div><div class="health-grid">${cards}${auditCard}</div></div>`;
    packagesGrid.querySelectorAll('.health-action').forEach(btn => {
        btn.addEventListener('click', () => runHealthAction(btn.dataset.healthAction, btn));
    });
}

// ===================== .pacnew center =====================
// Reachable from System Health + the Updates notice (no permanent nav item — usually empty).
// Risk classification is pure (unit-tested).
function pacnewRisk(path) {
    const base = (path || '').replace(/\.pac(new|save)$/, '');
    const name = base.split('/').pop();
    // info, not danger: the risky action (Apply) doesn't exist for mirrorlist — every action
    // left on its row is safe, so there's nothing for the styling to warn about.
    if (name === 'mirrorlist') return { level: 'info', label: 'Safe to discard',
        note: 'This .pacnew is the stock mirror list with every server commented out. Discard it, or get fresh servers from Mirror settings first.' };
    const critical = new Set(['pacman.conf', 'sudoers', 'fstab', 'crypttab', 'mkinitcpio.conf',
        'passwd', 'shadow', 'group', 'gshadow', 'hosts', 'resolv.conf', 'locale.gen', 'nsswitch.conf']);
    if (critical.has(name) || base.includes('/sudoers.d/')) return { level: 'warn',
        label: 'Review carefully', note: 'System-critical config — read the diff before merging.' };
    return { level: 'info', label: 'Review', note: 'Review and merge when convenient.' };
}

function fallbackCopy(text) {
    try {
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        showToast(ok ? 'Copied' : 'Copy this', text, ok ? 'success' : 'info');
    } catch (e) { showToast('Copy this', text, 'info'); }
}
function copyText(text) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => showToast('Copied', text, 'success'),
                                                     () => fallbackCopy(text));
            return;
        }
    } catch (e) { /* fall through */ }
    fallbackCopy(text);
}

async function openPacnewCenter() {
    currentView = 'pacnew';
    navEpoch++;
    resetContentScroll();  // see activateView: avoid a stranded scroll blanking a short view
    navItems.forEach(n => n.classList.remove('active'));  // not a nav item
    searchInput.value = '';
    applyTopbarContext();
    const ac = document.getElementById('attention-center'); if (ac) ac.innerHTML = '';
    const notice = document.getElementById('updates-notice'); if (notice) notice.innerHTML = '';
    emptyState.classList.add('hidden');
    loadingState.classList.add('hidden');
    await renderPacnewCenter();
}

async function renderPacnewCenter() {
    packagesGrid.style.display = 'block';
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, `<div class="state-container"><div class="spinner"></div><p>Finding config files…</p></div>`);
    const res = await pyApiCall('get_pacnew_files');  // {files, count} or null
    clearTimeout(spin);
    if (epoch !== navEpoch) return;
    const files = (res && res.files) || [];
    const back = `<button class="browse-back" id="pacnew-back" type="button">← Back</button>`;

    if (files.length === 0) {
        packagesGrid.innerHTML = `<div class="pacnew-page"><div class="browse-subheader">${back}<span class="browse-cat-title">Config files</span></div>`
            + emptyStateHTML({ icon: '📝', title: 'No .pacnew/.pacsave files',
                hint: 'Nothing to review. These appear after an update ships a new version of a config you’ve edited.' })
            + `</div>`;
        document.getElementById('pacnew-back').addEventListener('click', () => activateView('health'));
        return;
    }

    const rows = files.map((f) => {
        const r = pacnewRisk(f);
        // mirrorlist gets a link to Settings → Mirrors instead of Apply — its .pacnew is the stock
        // all-commented list, so applying it wipes your servers (backend blocks apply_pacnew too).
        // Deliberately navigation, not an inline regen button: regeneration lives only in Settings
        // (plan 2026-07-16-mirrorlist-regeneration-safety — reflector/rate-mirrors write upstream
        // Arch mirrors, a footgun on derivatives like CachyOS).
        const isMirrorlist = f.replace(/\.pac(new|save)$/, '').split('/').pop() === 'mirrorlist';
        const applyBtn = isMirrorlist
            ? `<button class="btn btn-outline btn-small pacnew-mirror-settings-btn">Open Mirror settings</button>`
            : `<button class="btn btn-outline btn-small pacnew-apply-btn" data-path="${escapeHtml(f)}">Apply (overwrite)</button>`;
        return `<div class="pacnew-item tone-${r.level}">
            <div class="pacnew-row">
                <code class="pacnew-path">${escapeHtml(f)}</code>
                <span class="pacnew-risk">${escapeHtml(r.label)}</span>
            </div>
            <div class="pacnew-note">${escapeHtml(r.note)}</div>
            <div class="pacnew-actions">
                <button class="btn btn-outline btn-small pacnew-diff-btn" data-path="${escapeHtml(f)}">Show diff</button>
                ${applyBtn}
                <button class="btn btn-outline btn-small pacnew-discard-btn" data-path="${escapeHtml(f)}">Discard .pacnew</button>
                <button class="btn btn-outline btn-small pacnew-copy-btn" data-path="${escapeHtml(f)}">Copy path</button>
            </div>
            <pre class="pacnew-diff hidden" data-diff-for="${escapeHtml(f)}"></pre>
        </div>`;
    }).join('');

    packagesGrid.innerHTML = `<div class="pacnew-page">
        <div class="browse-subheader">${back}<span class="browse-cat-title">Config files (.pacnew)</span></div>
        <p class="settings-help">Review the diff, then <strong>Discard</strong> to keep your config or <strong>Apply</strong> to take the new default. For a line-by-line merge, open <code>pacdiff</code> in a terminal. Atlas never auto-merges.</p>
        <div class="pacnew-global">
            <button class="btn btn-outline" id="pacnew-pacdiff">Open pacdiff in a terminal</button>
        </div>
        <div class="pacnew-list">${rows}</div>
    </div>`;

    document.getElementById('pacnew-back').addEventListener('click', () => activateView('health'));
    const pd = document.getElementById('pacnew-pacdiff');
    if (pd) pd.addEventListener('click', async () => {
        const r = await pyApiCall('launch_pacdiff');
        if (r) showToast('pacdiff', 'Opened pacdiff in a terminal — merge the files there', 'info');
    });
    packagesGrid.querySelectorAll('.pacnew-mirror-settings-btn').forEach(b => b.addEventListener('click', () => activateView('settings')));
    packagesGrid.querySelectorAll('.pacnew-copy-btn').forEach(b => b.addEventListener('click', () => copyText(b.dataset.path)));
    packagesGrid.querySelectorAll('.pacnew-diff-btn').forEach(b => b.addEventListener('click', () => togglePacnewDiff(b)));
    packagesGrid.querySelectorAll('.pacnew-discard-btn').forEach(b => b.addEventListener('click', () => resolvePacnew(b.dataset.path, 'discard')));
    packagesGrid.querySelectorAll('.pacnew-apply-btn').forEach(b => b.addEventListener('click', () => resolvePacnew(b.dataset.path, 'apply')));
}

// Per-file resolution from the .pacnew center: 'discard' (rm the .pacnew, keep your config) or
// 'apply' (overwrite your config with the new default). Both confirm, then run as root and
// refresh via `onDone`. mirrorlist has no Apply button (backend blocks it too).
async function resolvePacnew(path, mode, onDone = renderPacnewCenter) {
    const critical = pacnewRisk(path).level !== 'info';
    const isApply = mode === 'apply';
    const title = isApply ? 'Apply this .pacnew?' : 'Discard this .pacnew?';
    let message = isApply
        ? `Overwrite ${path.replace(/\.pac(new|save)$/, '')} with the new default and delete the .pacnew? Any changes you made to this file will be lost.`
        : `Delete ${path} and keep your current config unchanged?`;
    if (isApply && critical) message += ' This is a system-critical file — review the diff first if you’re unsure.';
    const ok = await pyApiCall('prompt_confirmation', title, message, isApply ? 'Apply' : 'Discard', 'Cancel');
    if (!(ok && ok[0])) return;
    const res = await pyApiCall(isApply ? 'apply_pacnew' : 'discard_pacnew', path);  // null on error (toasted)
    if (res && res.status === 'cancelled') return;
    if (res && res.status === 'ok') {
        showToast('Config files', isApply ? 'Applied the .pacnew and removed it' : 'Discarded the .pacnew', 'success');
        onDone();
    }
}

async function togglePacnewDiff(btn) {
    const path = btn.dataset.path;
    const pre = packagesGrid.querySelector(`.pacnew-diff[data-diff-for="${CSS.escape(path)}"]`);
    if (!pre) return;
    if (!pre.classList.contains('hidden')) { pre.classList.add('hidden'); btn.textContent = 'Show diff'; return; }
    pre.textContent = 'Loading diff…';
    pre.classList.remove('hidden');
    btn.textContent = 'Hide diff';
    const res = await pyApiCall('get_pacnew_diff', path);
    if (!res) { pre.textContent = 'Could not read the diff.'; return; }
    if (!res.readable) { pre.textContent = 'This file needs root to read — use “Open pacdiff” to review it.'; return; }
    if (!res.diff) { pre.textContent = 'No differences — the .pacnew matches your current file (safe to remove).'; return; }
    pre.textContent = res.diff + (res.truncated ? '\n… (diff truncated)' : '');
}

// Render Chronological Activity Log
// --- History / rollback center (Activity page) -------------------------------------------------
// Pure helpers (Node-VM-tested); DOM wiring below. See plan 2026-06-05-history-rollback-center.md.

// Filter entries by action, source type, and a package-name query. Composes; case-insensitive.
function filterActivity(entries, filter = {}) {
    const action = filter.action || 'all';
    const type = (filter.type || 'all').toLowerCase();
    const query = (filter.query || '').trim().toLowerCase();
    return (entries || []).filter(e => {
        if (action !== 'all' && e.action !== action) return false;
        if (type !== 'all' && (e.pkg_type || '').toLowerCase() !== type) return false;
        if (query && !(e.pkg_name || '').toLowerCase().includes(query)) return false;
        return true;
    });
}

// Bucket entries (already newest-first) into Today / Yesterday / Earlier this week / Older.
function groupActivityByDate(entries, now = new Date()) {
    const startOfDay = new Date(now); startOfDay.setHours(0, 0, 0, 0);
    const today = startOfDay.getTime();
    const dayMs = 86400000;
    const buckets = [
        { key: 'today', label: 'Today', items: [] },
        { key: 'yesterday', label: 'Yesterday', items: [] },
        { key: 'week', label: 'Earlier this week', items: [] },
        { key: 'older', label: 'Older', items: [] },
    ];
    const at = k => buckets.find(b => b.key === k).items;
    (entries || []).forEach(e => {
        const t = new Date(e.timestamp).getTime();
        if (isNaN(t)) at('older').push(e);
        else if (t >= today) at('today').push(e);
        else if (t >= today - dayMs) at('yesterday').push(e);
        else if (t >= today - 6 * dayMs) at('week').push(e);
        else at('older').push(e);
    });
    return buckets.filter(b => b.items.length > 0);
}

// Which rollback affordances an entry offers. Only successful entries get them; they route through
// the normal preview/terminal flow (which re-resolves the package), so they're entry points, not
// guarantees. Downgrade is an Arch/AUR/Flatpak concept; reinstall applies to a prior uninstall.
function activityEntryActions(entry) {
    if (!entry || !entry.success) return [];
    const type = (entry.pkg_type || '').toLowerCase();
    const id = `${entry.pkg_type}:${entry.pkg_name}`;
    const supportsDowngrade = type === 'arch_repo' || type === 'arch' || type === 'aur' || type === 'flatpak';
    if (entry.action === 'uninstall') return [{ label: 'Reinstall', handler: 'installApp', id }];
    if (['install', 'update', 'downgrade'].includes(entry.action) && supportsDowngrade) {
        return [{ label: 'Downgrade', handler: 'downgradeApp', id }];
    }
    return [];
}

// Distinct actions present in the log, for the action filter chips (always leads with All).
function activityActionsPresent(entries) {
    const order = ['install', 'update', 'update_all', 'uninstall', 'downgrade'];
    const present = new Set((entries || []).map(e => e.action));
    return ['all', ...order.filter(a => present.has(a)), ...[...present].filter(a => !order.includes(a)).sort()];
}

// Distinct source types present, for the type filter.
function activityTypesPresent(entries) {
    const present = [...new Set((entries || []).map(e => (e.pkg_type || '').trim()).filter(Boolean))].sort();
    return ['all', ...present];
}

async function renderActivityFeed() {
    packagesGrid.style.display = 'block'; // activity items stack vertically
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, '<div class="state-container"><div class="spinner"></div></div>');
    activityEntries = await pyApiCall('get_activity') || [];
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    if (activityEntries.length === 0) {
        packagesGrid.innerHTML = emptyStateHTML({
            icon: '🕘', title: 'No activity yet',
            hint: 'Installs, updates, and removals you make in Atlas will show up here.' });
        return;
    }
    renderActivityView();
}

// Re-render the Activity page from the cached entries + active filter (no refetch). Called by
// renderActivityFeed after fetch and by the filter controls.
function renderActivityView() {
    const ACTION_LABELS = { all: 'All', install: 'Installs', update: 'Updates', update_all: 'Update All', uninstall: 'Removals', downgrade: 'Downgrades' };
    const filtered = filterActivity(activityEntries, activityFilter);
    const groups = groupActivityByDate(filtered);

    const container = document.createElement('div');
    container.className = 'activity-page';

    // --- Filter bar: action chips + type select + name search ---
    const bar = document.createElement('div');
    bar.className = 'activity-filters';
    const actionChips = activityActionsPresent(activityEntries).map(a => {
        const active = activityFilter.action === a ? ' active' : '';
        return `<button class="activity-chip${active}" data-action="${escapeHtml(a)}">${escapeHtml(ACTION_LABELS[a] || a)}</button>`;
    }).join('');
    const typeOpts = activityTypesPresent(activityEntries).map(t =>
        `<option value="${escapeHtml(t)}"${activityFilter.type === t ? ' selected' : ''}>${t === 'all' ? 'All sources' : escapeHtml(t)}</option>`).join('');
    bar.innerHTML = `
        <div class="activity-chips">${actionChips}</div>
        <div class="activity-filter-right">
            <select class="activity-type-select" aria-label="Filter by source">${typeOpts}</select>
            <input class="activity-search" type="search" placeholder="Filter by name…" value="${escapeHtml(activityFilter.query)}" aria-label="Filter activity by package name">
            <button class="btn btn-outline btn-sm activity-export-btn" title="Export the activity log to a JSON file">Export</button>
            <button class="btn btn-outline btn-sm activity-clear-btn" title="Clear the activity log">Clear</button>
        </div>`;
    container.appendChild(bar);

    // --- Grouped feed (or an empty state when filters exclude everything) ---
    if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.innerHTML = emptyStateHTML({ icon: '🔍', title: 'No matching activity', hint: 'Try a different filter or clear the search.' });
        container.appendChild(empty);
    } else {
        groups.forEach(group => {
            const section = document.createElement('div');
            section.className = 'activity-group';
            section.innerHTML = `<h3 class="activity-group-title">${escapeHtml(group.label)}</h3>`;
            const feed = document.createElement('div');
            feed.className = 'activity-feed';
            group.items.forEach(act => feed.appendChild(buildActivityItem(act)));
            section.appendChild(feed);
            container.appendChild(section);
        });
    }

    packagesGrid.innerHTML = '';
    packagesGrid.appendChild(container);

    // --- Wire the filter controls (re-render from cache, no refetch) ---
    bar.querySelectorAll('.activity-chip').forEach(chip => chip.addEventListener('click', () => {
        activityFilter.action = chip.dataset.action;
        renderActivityView();
    }));
    bar.querySelector('.activity-type-select').addEventListener('change', e => {
        activityFilter.type = e.target.value;
        renderActivityView();
    });
    const search = bar.querySelector('.activity-search');
    search.addEventListener('input', e => {
        activityFilter.query = e.target.value;
        renderActivityView();
        // restore focus + caret after the re-render replaces the input
        const s = packagesGrid.querySelector('.activity-search');
        if (s) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    });

    // Export: write the log to ~/atlas-activity.json and tell the user where it landed.
    bar.querySelector('.activity-export-btn').addEventListener('click', async () => {
        const r = await pyApiCall('export_activity');
        if (r && r.path) showToast('Activity exported', `${r.count} entries → ${r.path}`, 'success');
    });

    // Clear: destructive, so confirm inline (one re-click within 3s) rather than fire immediately.
    const clearBtn = bar.querySelector('.activity-clear-btn');
    clearBtn.addEventListener('click', async () => {
        if (clearBtn.dataset.armed !== '1') {
            clearBtn.dataset.armed = '1';
            clearBtn.textContent = 'Click to confirm';
            clearBtn.classList.add('btn-danger');
            setTimeout(() => {
                if (clearBtn.isConnected) { clearBtn.dataset.armed = ''; clearBtn.textContent = 'Clear'; clearBtn.classList.remove('btn-danger'); }
            }, 3000);
            return;
        }
        const r = await pyApiCall('clear_activity');
        if (r && r.status === 'ok') {
            activityEntries = [];
            activityFilter = { action: 'all', type: 'all', query: '' };
            showToast('Activity cleared', 'The activity log is now empty.', 'success');
            renderActivityFeed();
        }
    });
}

// Turn a stored error into a concise human line. pywebview bubbles a JS exception as a stringified
// object (e.g. "{'name': 'ReferenceError', 'message': "…", 'stack': …}"); pull out just the message
// and drop the stack/line noise. Falls back to the raw string (truncated) when it's not that shape.
function cleanActivityError(error) {
    if (!error) return '';
    const s = String(error);
    const m = s.match(/['"]message['"]\s*:\s*(['"])([\s\S]*?)\1/);
    let msg = (m ? m[2] : s).trim();
    if (msg.length > 200) msg = msg.slice(0, 199) + '…';
    return msg;
}

// Arch/AUR entries can show the matching pacman.log lines (those are the only ones pacman records).
function activityHasPacmanLog(entry) {
    const type = (entry && entry.pkg_type || '').toLowerCase();
    return type === 'arch_repo' || type === 'arch' || type === 'aur';
}

function buildActivityItem(act) {
    const entry = document.createElement('div');
    entry.className = 'activity-entry';

    const item = document.createElement('div');
    item.className = 'activity-item';
    const isSuccess = act.success;
    const timeStr = new Date(act.timestamp).toLocaleString();
    const actions = activityEntryActions(act);
    const actionsHTML = actions.map(a =>
        `<button class="btn btn-outline btn-sm activity-rollback" data-handler="${escapeHtml(a.handler)}" data-id="${escapeHtml(a.id)}">${escapeHtml(a.label)}</button>`).join('');
    const logToggleHTML = activityHasPacmanLog(act)
        ? `<button class="btn btn-outline btn-sm activity-log-toggle" aria-expanded="false">pacman log</button>` : '';

    item.innerHTML = `
        <div class="activity-icon ${isSuccess ? 'success' : 'error'}">${isSuccess ? '✓' : '✗'}</div>
        <div class="activity-body">
            <span class="activity-action ${escapeHtml(act.action)}">${escapeHtml(act.action.replace(/_/g, ' ').toUpperCase())}</span>
            <span class="activity-pkg activity-pkg-link" title="Search for this package">${escapeHtml(act.pkg_name)}</span>
            <span style="color: var(--text-secondary);">(${escapeHtml(act.pkg_type)})</span>
            ${!isSuccess && act.error ? `<span class="activity-error" title="${escapeHtml(cleanActivityError(act.error))}">— ${escapeHtml(cleanActivityError(act.error))}</span>` : ''}
        </div>
        <div class="activity-actions">${actionsHTML}${logToggleHTML}</div>
        <div class="activity-time">${escapeHtml(timeStr)}</div>
    `;
    entry.appendChild(item);

    // Clicking the package name searches for it (the "view" path — the live card shows accurate state).
    item.querySelector('.activity-pkg-link').addEventListener('click', () => {
        searchInput.value = act.pkg_name;
        activateView('installed');
        fetchPackages();
    });
    // Rollback affordances route through the existing handlers (preview → root → terminal).
    item.querySelectorAll('.activity-rollback').forEach(btn => btn.addEventListener('click', () => {
        const fn = window[btn.dataset.handler];
        if (typeof fn === 'function') fn(btn.dataset.id);
    }));

    // Lazy pacman.log disclosure: fetch the matching lines on first expand, then just toggle.
    const logToggle = item.querySelector('.activity-log-toggle');
    if (logToggle) {
        const panel = document.createElement('div');
        panel.className = 'activity-log hidden';
        entry.appendChild(panel);
        let loaded = false;
        logToggle.addEventListener('click', async () => {
            const open = panel.classList.toggle('hidden') === false;
            logToggle.setAttribute('aria-expanded', String(open));
            if (open && !loaded) {
                loaded = true;
                panel.innerHTML = '<div class="activity-log-line muted">Loading pacman log…</div>';
                const lines = await pyApiCall('get_pacman_log', act.pkg_name) || [];
                panel.innerHTML = lines.length
                    ? lines.map(renderPacmanLogLine).join('')
                    : '<div class="activity-log-line muted">No matching pacman.log entries.</div>';
            }
        });
    }
    return entry;
}

// One pacman.log row: an action chip + version (raw token, e.g. "1.0-1" or "1.0-1 -> 1.1-1") + time.
function renderPacmanLogLine(line) {
    return `<div class="activity-log-line">` +
        `<span class="activity-action ${escapeHtml(line.action)}">${escapeHtml(line.action.toUpperCase())}</span>` +
        `<span class="activity-log-ver">${escapeHtml(line.version)}</span>` +
        `<span class="activity-log-ts">${escapeHtml(line.timestamp)}</span></div>`;
}

// Data Fetching
async function fetchPackages() {
    const fetchEpoch = nextPackageFetchEpoch();
    const fetchView = currentView;
    packagesGrid.style.display = 'grid';
    packagesGrid.innerHTML = getSkeletonGridHTML();
    emptyState.classList.add('hidden');
    loadingState.classList.add('hidden');
    updateAllBtn.classList.add('hidden'); // hidden by default
    cleanupOrphansBtn.classList.add('hidden'); // hidden by default
    checkOrphans(); // cheap count; shows the cleanup button on any view when orphans exist

    // If batch mode was active, cancel it before view changes or search queries
    if (selectMode) {
        toggleSelectMode(false);
    }

    const query = searchInput.value.trim();
    applyTopbarContext();  // show/hide package-list controls for the current context

    // The dashboard is the "Attention Center" only — no package/suggestions grid (app discovery
    // lives in Browse + Installed). With no active search we render the cards and stop; a search
    // from the dashboard falls through to the normal results grid below.
    const attnHost = document.getElementById('attention-center');
    if (currentView === 'dashboard' && !query) {
        if (attnHost) renderAttentionCenter();  // fire-and-forget; fills its cards asynchronously
        packagesGrid.style.display = 'none';
        packagesGrid.innerHTML = '';
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        currentPackages = [];
        currentGroups = [];
        return;
    }
    if (attnHost) {
        attentionEpoch++;  // leaving the dashboard cards → invalidate any in-flight render
        attnHost.innerHTML = '';
    }

    if (currentView === 'browse' && !query) {
        if (activeBrowseCategory) {
            await renderCategoryPackages(activeBrowseCategory.key, activeBrowseCategory.label);
        } else {
            await renderBrowse();
        }
        return;
    }
    if (currentView === 'browse' && query) {
        activeBrowseCategory = null;
    }

    // The Updates view shows a notice when pacman left .pacnew/.pacsave files to review.
    if (currentView === 'updates') renderUpdatesNotice();

    // Fetch the full (all-types) set; the type filter is applied client-side at render so
    // switching it is instant and doesn't refetch. Cache key is therefore type-independent.
    const cacheKey = getCacheKey(currentView, 'all', query);
    if (currentView !== 'activity' && currentView !== 'disk' && packageCache[cacheKey] !== undefined) {
        currentPackages = packageCache[cacheKey];
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        if (currentView === 'updates') {
            if (currentPackages.length > 0) {
                updateAllBtn.classList.remove('hidden');
            }
            if (!query) {
                document.getElementById('updates-badge').textContent = currentPackages.length;
            }
        }
        renderFiltered();
        return;
    }

    let results = [];
    if (query && PACKAGE_LIST_VIEWS.has(currentView)) {
        // Searching a finite local view filters that view's own list (with a fuzzy fallback), not a
        // global cross-source search — searching Installed should find your installed apps.
        const fullList = await localListFor(currentView);
        if (!isCurrentPackageFetch(fetchEpoch, fetchView)) return;
        results = filterLocalPackages(fullList, query);
    } else if (query) {
        results = await pyApiCall('search', query, 'all');
        // Surface the closest name match first (the backend also matches description/keywords).
        results = rerankByFuzzy(results, query);
    } else {
        if (currentView === 'installed') {
            results = await pyApiCall('get_installed', 'all');
        } else if (currentView === 'updates') {
            results = await getUpdatesCached();
        } else if (currentView === 'activity') {
            loadingState.classList.add('hidden');
            renderActivityFeed();
            return;
        } else if (currentView === 'disk') {
            renderDiskView();
            return;
        } else {
            results = await pyApiCall('get_suggestions', 'all');
        }
    }

    if (!isCurrentPackageFetch(fetchEpoch, fetchView)) return;

    if (currentView === 'updates' && results && results.length > 0) {
        updateAllBtn.classList.remove('hidden');
    }

    if (currentView !== 'activity' && currentView !== 'disk') {
        writeToCache(cacheKey, results || []);
    }

    loadingState.classList.add('hidden');
    currentPackages = results || [];
    renderFiltered();

    // Update Badge if viewing updates
    if (currentView === 'updates' && !query) {
        setUpdatesBadge(currentPackages.length);
    }
}

// Sidebar "Updates" badge. Shown proactively (startup, after updates, and pushed by the tray
// poller) so the count is visible without opening the Updates page. Hidden when there are none.
function setUpdatesBadge(count) {
    const el = document.getElementById('updates-badge');
    if (!el) return;
    const n = Math.max(0, Number(count) || 0);
    el.textContent = String(n);
    el.style.display = n > 0 ? '' : 'none';
}
window.setUpdatesBadge = setUpdatesBadge;  // the tray (Python) calls this to keep the badge live

async function refreshUpdatesBadge() {
    try {
        const results = await getUpdatesCached();
        setUpdatesBadge((results || []).length);
    } catch (e) {
        // non-fatal: the badge just won't refresh this time
    }
}

// Arch Linux News page (read-only feed from archlinux.org).
async function renderNews() {
    packagesGrid.style.display = 'block';
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, `<div class="state-container"><div class="spinner"></div><p>Loading Arch news…</p></div>`);

    const data = await pyApiCall('get_arch_news');  // unwrapped list, or null on error
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    if (!data) {
        packagesGrid.innerHTML = emptyStateHTML({
            icon: '📡', title: 'Couldn’t load Arch news',
            hint: 'The archlinux.org feed couldn’t be reached. Check your connection and try again.' });
        return;
    }
    if (data.length === 0) {
        packagesGrid.innerHTML = emptyStateHTML({ icon: '📰', title: 'No recent Arch news' });
        return;
    }

    const items = data.map(n => `
        <article class="news-card">
            <div class="news-card-head">
                <h3 class="news-title">${escapeHtml(n.title)}</h3>
                ${n.date ? `<span class="news-date">${escapeHtml(n.date)}</span>` : ''}
            </div>
            ${n.summary ? `<p class="news-summary">${escapeHtml(n.summary)}</p>` : ''}
            ${safeExternalUrl(n.url) ? `<a class="news-link" href="#" data-news-url="${escapeHtml(safeExternalUrl(n.url))}">Read on archlinux.org ↗</a>` : ''}
        </article>`).join('');

    packagesGrid.innerHTML = `<div class="news-list"><div class="news-header">Arch Linux News</div>${items}</div>`;
    packagesGrid.querySelectorAll('a[data-news-url]').forEach(a => {
        a.addEventListener('click', (e) => { e.preventDefault(); openExternalUrl(a.dataset.newsUrl); });
    });
}

// Browse-by-category: a store-like discovery view. Top level shows category cards; clicking
// one lists that category's repo packages (reusing the normal package grid).
// Pure: a richer Browse category card — icon + label + short description (no count; the repo-only
// count understates a bucket that also lists Flathub apps). Node-VM contract-tested.
function buildCategoryCardHTML(c) {
    c = c || {};
    const desc = c.description
        ? `<span class="browse-chip-desc">${escapeHtml(c.description)}</span>` : '';
    return `<button class="browse-chip browse-chip-rich" data-cat-key="${escapeHtml(c.key)}" data-cat-label="${escapeHtml(c.label)}">
        <span class="browse-chip-icon">${escapeHtml(c.icon || '📦')}</span>
        <span class="browse-chip-text">
            <span class="browse-chip-label">${escapeHtml(c.label)}</span>
            ${desc}
        </span>
    </button>`;
}

// Pure: the "jump back to your last category" resume chip on the Browse landing. '' when there's no
// stored category. Node-VM contract-tested.
function buildResumeBrowseHTML(last) {
    if (!last || !last.key || !last.label) return '';
    return `<div class="browse-resume"><button class="browse-resume-btn" type="button">↩ Resume <strong>${escapeHtml(last.label)}</strong></button></div>`;
}

// Persist the last-opened category so the landing can offer a resume chip (a convenience, not
// auto-navigation). Stored as {key, label, api}. Best-effort — localStorage may be unavailable.
function setLastBrowseCategory(cat) {
    try { localStorage.setItem('atlas_last_browse_cat', JSON.stringify(cat)); } catch (e) { /* ignore */ }
}
function getLastBrowseCategory() {
    try { return JSON.parse(localStorage.getItem('atlas_last_browse_cat') || 'null'); } catch (e) { return null; }
}

async function renderBrowse() {
    activeBrowseCategory = null;
    resetContentScroll();  // category list → landing can also strand the scroll (see activateView)
    applyTopbarContext();  // landing = category grid → hide package-list controls
    currentPackages = [];
    currentGroups = [];
    packagesGrid.style.display = 'block';
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, `<div class="state-container"><div class="spinner"></div><p>Loading categories…</p></div>`);

    // Fetch categories + the curated suggestions together (suggestions used to live on the
    // dashboard; they now seed Browse). Suggestions are best-effort — Browse still works without.
    const [data, suggestions, aurBuckets] = await Promise.all([
        pyApiCall('get_categories'),       // unwrapped list, or null on error
        pyApiCall('get_suggestions', 'all'),
        pyApiCall('get_aur_discovery'),    // unwrapped list, or null/[]
    ]);
    clearTimeout(spin);
    if (epoch !== navEpoch || activeBrowseCategory) return;  // navigated away / opened a category
    if (!data) {
        packagesGrid.innerHTML = emptyStateHTML({
            icon: '📡', title: 'Couldn’t load categories',
            hint: 'Category data is fetched from atlas-files — check your connection and try again.' });
        return;
    }
    if (data.length === 0) {
        packagesGrid.innerHTML = emptyStateHTML({ icon: '🗂️', title: 'No category data available yet' });
        return;
    }

    // No count on category chips: the count is repo-only (categories.txt), but an opened category
    // also lists Flathub apps, so the number would understate what you actually see. (Counting
    // Flatpak per bucket would mean a network call per category on every Browse open.) The AUR
    // buckets below keep their count — those are exactly the curated top-N we show.
    const cards = data.map(buildCategoryCardHTML).join('');

    // "Jump back to your last category" — a convenience at the top of the landing (not auto-nav).
    const lastCat = getLastBrowseCategory();
    const resumeSection = buildResumeBrowseHTML(lastCat);

    const hasSuggestions = Array.isArray(suggestions) && suggestions.length > 0;
    const suggestedSection = hasSuggestions
        ? `<div class="browse-header browse-header-spaced">Suggested for you</div><div class="browse-suggested" id="browse-suggested"></div>`
        : '';

    // AUR discovery buckets (community-maintained — compact chips, distinct from the big category
    // tiles and left-packed so a short list of buckets doesn't leave a half-empty grid row).
    const hasAur = Array.isArray(aurBuckets) && aurBuckets.length > 0;
    const aurCards = hasAur ? aurBuckets.map(b => `
        <button class="browse-chip browse-chip-rich browse-chip-aur" data-aur-key="${escapeHtml(b.key)}" data-aur-label="${escapeHtml(b.label)}">
            <span class="browse-chip-icon">${escapeHtml(b.icon || '📦')}</span>
            <span class="browse-chip-text">
                <span class="browse-chip-label">${escapeHtml(b.label)}</span>
                <span class="browse-chip-count">${escapeHtml(b.count)} package${b.count === 1 ? '' : 's'}</span>
            </span>
        </button>`).join('') : '';
    const aurSection = hasAur
        ? `<div class="browse-header browse-header-spaced">Discover on the AUR <span class="browse-header-note browse-header-note-aur">community-maintained</span></div><div class="browse-chip-row browse-chip-grid">${aurCards}</div>`
        : '';

    // Resume chip (if any), then categories (the primary purpose of Browse), then AUR discovery,
    // then the suggested row.
    packagesGrid.innerHTML =
        `<div class="browse-view">` +
        `${resumeSection}` +
        `<div class="browse-header">Browse by category <span class="browse-header-note">official repos & Flatpak</span></div><div class="browse-chip-row browse-chip-grid">${cards}</div>` +
        `${aurSection}${suggestedSection}</div>`;

    // Render the suggestions as real package cards (install/detail/source-switch all work via the
    // existing #packages-grid delegation, which resolves data-gi against currentGroups).
    if (hasSuggestions) {
        currentPackages = suggestions;
        currentGroups = collapseByName(suggestions);
        const host = packagesGrid.querySelector('#browse-suggested');
        if (host) {
            appendPackageCards(host, currentGroups);
            deferredIconLoad();
            deferredMetaLoad();
        }
    }

    packagesGrid.querySelectorAll('.browse-chip[data-cat-key]').forEach(btn => {
        btn.addEventListener('click', () => renderCategoryPackages(btn.dataset.catKey, btn.dataset.catLabel));
    });
    packagesGrid.querySelectorAll('.browse-chip[data-aur-key]').forEach(btn => {
        btn.addEventListener('click', () => renderCategoryPackages(btn.dataset.aurKey, btn.dataset.aurLabel,
                                                                   { api: 'get_aur_bucket_packages' }));
    });
    const resumeBtn = packagesGrid.querySelector('.browse-resume-btn');
    if (resumeBtn && lastCat) resumeBtn.addEventListener('click', () =>
        renderCategoryPackages(lastCat.key, lastCat.label,
                               lastCat.api ? { api: lastCat.api } : undefined));
}

function browseCategoryHeader(category) {
    const header = document.createElement('div');
    header.className = 'browse-subheader';
    // Breadcrumb: Browse / <Category> — the "Browse" crumb returns to the landing.
    header.innerHTML = `<nav class="browse-breadcrumb" aria-label="Breadcrumb">` +
        `<button class="breadcrumb-crumb" type="button">Browse</button>` +
        `<span class="breadcrumb-sep">/</span>` +
        `<span class="breadcrumb-current">${escapeHtml(category.label)}</span></nav>`;
    header.querySelector('.breadcrumb-crumb').addEventListener('click', renderBrowse);
    return header;
}

async function renderCategoryPackages(key, label, opts) {
    const api = (opts && opts.api) || 'get_category_packages';
    activeBrowseCategory = { key, label };
    resetContentScroll();  // landing → category (or category → category) shouldn't inherit scroll
    setLastBrowseCategory({ key, label, api });  // remember for the landing's resume chip
    applyTopbarContext();  // open category = package list → show the controls
    packagesGrid.style.display = 'block';
    // Breadcrumb + skeleton grid while loading (not a bare spinner).
    packagesGrid.innerHTML = '';
    packagesGrid.appendChild(browseCategoryHeader({ key, label }));
    const skel = document.createElement('div');
    skel.className = 'packages-grid';
    skel.innerHTML = getSkeletonGridHTML();
    packagesGrid.appendChild(skel);

    const data = await pyApiCall(api, key);  // unwrapped list, or null on error
    if (!activeBrowseCategory || activeBrowseCategory.key !== key) return;
    const header = browseCategoryHeader(activeBrowseCategory);
    currentPackages = data || [];

    if (!data || data.length === 0) {
        currentGroups = [];
        packagesGrid.style.display = 'block';
        packagesGrid.innerHTML = '';
        packagesGrid.appendChild(header);
        const empty = document.createElement('div');
        empty.innerHTML = data
            ? emptyStateHTML({ icon: '🗂️', title: 'Nothing in this category',
                               hint: 'No packages here for the current type filter — try “All Types”.' })
            : emptyStateHTML({ icon: '📡', title: 'Couldn’t load this category',
                               hint: 'Check your connection and try again.' });
        packagesGrid.appendChild(empty);
    } else {
        renderFiltered();  // sets packagesGrid to the grid/list layout + cards, preserving the header
    }
}

// Reflector regen controls (Settings → Mirrors). Pure: renders country/sort/protocol pickers from
// the mirror-status payload. Returns '' for rate-mirrors / no tool (no reflector options to offer).
function buildMirrorOptionsHTML(mirror) {
    if (!mirror || !mirror.options) return '';
    const o = mirror.options;
    const countryOpts = ['<option value="">Auto (all countries)</option>']
        .concat((mirror.countries || []).map(c =>
            `<option value="${escapeHtml(c.code)}"${c.code === o.country ? ' selected' : ''}>${escapeHtml(c.name)}</option>`))
        .join('');
    const sortOpts = (mirror.sorts || []).map(s =>
        `<option value="${escapeHtml(s)}"${s === o.sort ? ' selected' : ''}>${escapeHtml(s)}</option>`).join('');
    const protoBoxes = (mirror.protocols || []).map(p =>
        `<label class="mirror-proto"><input type="checkbox" data-mirror-proto="${escapeHtml(p)}"${(o.protocols || []).includes(p) ? ' checked' : ''}> ${escapeHtml(p)}</label>`).join('');
    return `
        <div class="mirror-options">
            <label class="mirror-opt">Country
                <select id="mirror-country" class="styled-select">${countryOpts}</select>
            </label>
            <label class="mirror-opt">Sort by
                <select id="mirror-sort" class="styled-select">${sortOpts}</select>
            </label>
            <div class="mirror-opt">Protocols
                <div class="mirror-protos">${protoBoxes}</div>
            </div>
        </div>`;
}

// Gather the current reflector option selection from the rendered controls.
function readMirrorOptionsFromDOM() {
    const countryEl = document.getElementById('mirror-country');
    const sortEl = document.getElementById('mirror-sort');
    const protocols = Array.from(document.querySelectorAll('[data-mirror-proto]'))
        .filter(el => el.checked).map(el => el.getAttribute('data-mirror-proto'));
    return {
        country: countryEl ? countryEl.value : '',
        sort: sortEl ? sortEl.value : 'rate',
        protocols,
        latest: 20,
    };
}

function getSavedMirrorOptions() {
    try { return JSON.parse(localStorage.getItem('atlas_mirror_opts')) || null; }
    catch (e) { return null; }
}
function setSavedMirrorOptions(opts) {
    try { localStorage.setItem('atlas_mirror_opts', JSON.stringify(opts)); } catch (e) { /* ignore */ }
}

// Regenerate /etc/pacman.d/mirrorlist (reflector/rate-mirrors via the root broker). Only called
// from intentional contexts (System Health, Settings → Mirrors). Always confirms before running
// — the preview command is shown and the user is told a backup will be saved. After success,
// caller should re-render to pick up the new backup status.
async function regenerateMirrors(btnEl, options) {
    // Show the exact command that will run before asking for confirmation.
    const prev = await pyApiCall('preview_mirror_command', options);
    const cmdPreview = (prev && prev.command) ? `\n\nCommand: ${prev.command}` : '';
    const msg = `This will overwrite /etc/pacman.d/mirrorlist with freshly-ranked mirrors. A backup will be saved at /etc/pacman.d/mirrorlist.atlas.bak in case you need to restore.${cmdPreview}`;
    const ok = await pyApiCall('prompt_confirmation', 'Regenerate mirror list?', msg, 'Regenerate', 'Cancel');
    if (!(ok && ok[0])) {
        showToast('Mirrors', 'Mirror regeneration cancelled', 'info');
        return;
    }
    if (btnEl) btnEl.classList.add('loading');
    showToast('Mirrors', 'Regenerating the mirror list — this can take up to a minute…', 'info');
    const r = await pyApiCall('regenerate_mirrorlist', options);  // null on error (toast already shown)
    if (btnEl) btnEl.classList.remove('loading');
    if (r && r.status === 'ok') {
        showToast('Mirrors', `Mirror list regenerated via ${r.tool || 'reflector'} — a backup was saved.`, 'success');
    } else if (r && r.status === 'cancelled') {
        showToast('Mirrors', 'Mirror regeneration cancelled', 'info');
    }
}

// Notice on the Updates view: .pacnew/.pacsave config files pacman left for manual review.
// Deliberately compact — one sentence, one button. All detail, warnings, and per-file actions
// live in the .pacnew center; a banner with no destructive buttons can't lead anyone into
// overwriting their mirrorlist.
async function renderUpdatesNotice() {
    const el = document.getElementById('updates-notice');
    if (!el) return;
    const res = await pyApiCall('get_pacnew_files');  // unwrapped {files, count} or null
    if (!res || !res.count) { el.innerHTML = ''; return; }
    el.innerHTML = `
        <div class="config-notice">
            <span class="config-notice-text">📝 ${res.count} config file${res.count > 1 ? 's are' : ' is'} waiting for review. Updates left new default configs next to yours.</span>
            <button class="btn btn-outline btn-small" id="pacnew-review-btn">Review</button>
        </div>`;
    const reviewBtn = document.getElementById('pacnew-review-btn');
    if (reviewBtn) reviewBtn.addEventListener('click', () => openPacnewCenter());
}

// Action Handlers
window.installApp = async (id, btn = null) => {
    // Pre-flight transaction preview — show what will change and confirm before anything
    // privileged runs. Cancel here aborts cleanly with nothing started.
    const proceed = await showInstallPreview(id);
    if (!proceed) {
        if (btn) btn.classList.remove('loading');
        return;
    }
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Installing', 'Installation started in background', 'info');
    try {
        const result = await pyApiCall('install', id);
        if (result && result.status === 'cancelled') {
            operationInProgress = false;
            showToast('Cancelled', 'Authentication cancelled', 'info');
            if (btn) btn.classList.remove('loading');
        } else if (result && result.success) {
            showToast('Success', 'Application installed successfully', 'success');
            packageCache = {}; // Wipe cache
        } else {
            operationInProgress = false; // Release lock on immediate failure
            showToast('Error', result ? result.error : 'Installation failed', 'error');
            if (btn) btn.classList.remove('loading');
        }
    } catch (err) {
        operationInProgress = false;
        if (btn) btn.classList.remove('loading');
    }
};

window.uninstallApp = async (id, btn = null) => {
    // Pre-flight preview — what depends on this + space freed — before anything privileged runs.
    const ok = await showTransactionPreview(id, 'uninstall');
    if (!ok) { if (btn) btn.classList.remove('loading'); return; }
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Uninstalling', 'Uninstallation started', 'info');
    try {
        const result = await pyApiCall('uninstall', id);
        if (result && result.status === 'cancelled') {
            operationInProgress = false;
            showToast('Cancelled', 'Authentication cancelled', 'info');
            if (btn) btn.classList.remove('loading');
        } else if (result && result.success) {
            showToast('Success', 'Application uninstalled', 'success');
            packageCache = {}; // Wipe cache
        } else {
            operationInProgress = false; // Release lock on immediate failure
            showToast('Error', result ? result.error : 'Uninstallation failed', 'error');
            if (btn) btn.classList.remove('loading');
        }
    } catch (err) {
        operationInProgress = false;
        if (btn) btn.classList.remove('loading');
    }
};

window.updateApp = async (id, btn = null) => {
    // Pre-flight preview — current → new version, size, advisories — before anything privileged runs.
    const ok = await showTransactionPreview(id, 'update');
    if (!ok) { if (btn) btn.classList.remove('loading'); return; }
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Updating', 'Update started', 'info');
    try {
        const result = await pyApiCall('update', id);
        if (result && result.status === 'cancelled') {
            operationInProgress = false;
            showToast('Cancelled', 'Authentication cancelled', 'info');
            if (btn) btn.classList.remove('loading');
        } else if (result && result.success) {
            showToast('Success', 'Application updated', 'success');
            packageCache = {}; // Wipe cache
            refreshUpdatesBadge();  // one fewer pending update
        } else {
            operationInProgress = false; // Release lock on immediate failure
            showToast('Error', result ? result.error : 'Update failed', 'error');
            if (btn) btn.classList.remove('loading');
        }
    } catch (err) {
        operationInProgress = false;
        if (btn) btn.classList.remove('loading');
    }
};

window.downgradeApp = async (id, btn = null) => {
    // Pre-flight preview — advisory rollback warnings — before anything privileged runs.
    const ok = await showTransactionPreview(id, 'downgrade');
    if (!ok) { if (btn) btn.classList.remove('loading'); return; }
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Downgrading', 'Downgrade started', 'info');
    try {
        const result = await pyApiCall('downgrade', id);
        if (result && result.status === 'cancelled') {
            operationInProgress = false;
            showToast('Cancelled', 'Authentication cancelled', 'info');
            if (btn) btn.classList.remove('loading');
        } else if (result && result.success) {
            showToast('Success', 'Application downgraded', 'success');
            packageCache = {}; // Wipe cache
        } else {
            operationInProgress = false; // Release lock on immediate failure
            showToast('Error', (result && result.error) || 'Downgrade failed', 'error');
            if (btn) btn.classList.remove('loading');
        }
    } catch (err) {
        operationInProgress = false;
        if (btn) btn.classList.remove('loading');
    }
};

// Event Listeners
let searchTimeout;
searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        fetchPackages();
    }, 400); // debounce
});

typeFilter.addEventListener('change', () => {
    if (currentView === 'browse' && activeBrowseCategory) {
        renderFiltered();
    } else {
        fetchPackages();
    }
});

// Sort dropdown. Sorting is client-side, so just re-render the current package list (no
// refetch). Live re-sort covers dashboard/installed/updates/search and an open Browse
// category; the top-level Browse category grid is not a package list and is left alone.
const SORTABLE_VIEWS = new Set(['dashboard', 'installed', 'updates']);
if (sortFilter) {
    sortFilter.value = sortMode;  // reflect the persisted choice
    sortFilter.addEventListener('change', () => {
        sortMode = SORT_MODES.includes(sortFilter.value) ? sortFilter.value : 'relevance';
        localStorage.setItem('atlas_sort_mode', sortMode);
        if (SORTABLE_VIEWS.has(currentView) || (currentView === 'browse' && activeBrowseCategory)) {
            renderFiltered();
        }
    });
}

// Grid/list layout toggle. Layout is pure CSS, so just flip the mode + class (no refetch).
document.querySelectorAll('.view-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => setViewMode(btn.dataset.viewMode));
});
applyViewMode();  // reflect the persisted choice on first paint
applyDensity();   // reflect the persisted display density on first paint

// Export / Import Manifest listeners
// Backup: export installed apps to a manifest / reinstall from one. Lives in Settings now
// (and Ctrl+E). Defined as functions so they work whether or not the Settings page is open.
async function exportPackages() {
    showToast('Exporting', 'Writing manifest...', 'info');
    const result = await pyApiCall('export_packages');
    if (result) {
        showToast('Exported', `${result.count} packages saved to ${result.path}`, 'success');
    }
}

async function importPackages() {
    showToast('Importing', 'Reading ~/atlas-manifest.json and installing missing packages...', 'info');
    const result = await pyApiCall('import_packages');
    if (result) {
        packageCache = {}; // Invalidate cache on manifest import
        const installed = result.installed || 0;
        const skipped = result.skipped || 0;
        const failed = result.failed || [];
        showToast('Import Complete', "Installed: " + installed + " | Skipped (already present): " + skipped + " | Failed: " + failed.length, failed.length > 0 ? 'error' : 'success');
        refreshCurrentView();
    }
}

const refreshBtn = document.getElementById('refresh-btn');
if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
        if (operationInProgress) {
            showToast('Busy', 'Another operation is already running', 'warning');
            return;
        }
        packageCache = {}; // Wipe cache completely for a hard reload
        searchInput.value = ''; // Reset query
        refreshCurrentView();  // refresh the active view (utility pages included), not just lists
    });
}

// --- Settings page ---------------------------------------------------------
const GENERAL_TOGGLES = [
    ['suggestions_enabled', 'Show app suggestions', 'Display recommended apps on the dashboard'],
    ['system_notifications', 'System notifications', 'Notify when long operations finish'],
    ['ask_for_reboot', 'Ask to reboot after updates', 'Prompt for a reboot when an update needs one'],
    ['download_icons', 'Download app icons', 'Fetch package icons (uses the network)'],
    ['store_root_password', 'Remember root password for the session', 'Avoid re-entering it for every privileged action'],
];

async function renderSettings() {
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, '<div class="settings-loading">Loading settings…</div>');
    const data = await pyApiCall('get_app_settings');
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    if (!data) {
        packagesGrid.innerHTML = '<div class="settings-loading">Could not load settings.</div>';
        return;
    }

    const typeRows = (data.types || []).map(t => `
        <label class="settings-row ${t.can_work ? '' : 'disabled'}">
            <input type="checkbox" data-type-id="${escapeHtml(t.id)}" ${t.enabled ? 'checked' : ''} ${t.can_work ? '' : 'disabled'}>
            <span class="settings-row-label">${escapeHtml(t.label)}</span>
            ${t.can_work ? '' : '<span class="settings-note">not available on this system</span>'}
        </label>`).join('');

    const level = data.flatpak_installation_level || '';
    const flatpakSection = data.flatpak_available ? `
        <section class="settings-section">
            <h3>Flatpak</h3>
            <label class="settings-row">
                <span class="settings-row-label">Install level</span>
                <select id="settings-flatpak-level" class="styled-select">
                    <option value="" ${level === '' ? 'selected' : ''}>Ask each time</option>
                    <option value="system" ${level === 'system' ? 'selected' : ''}>System</option>
                    <option value="user" ${level === 'user' ? 'selected' : ''}>User</option>
                </select>
            </label>
        </section>` : '';

    const g = data.general || {};
    const generalToggleRows = GENERAL_TOGGLES.map(([key, label, tip]) => `
        <label class="settings-row" title="${escapeHtml(tip)}">
            <input type="checkbox" data-gen-key="${escapeHtml(key)}" ${g[key] ? 'checked' : ''}>
            <span class="settings-row-label">${escapeHtml(label)}</span>
        </label>`).join('');
    const greetingRow = `
        <label class="settings-row" title="Name shown in the dashboard greeting (leave blank to use your system name)">
            <span class="settings-row-label">Display name</span>
            <input type="text" id="settings-greeting-name" class="styled-input" maxlength="40"
                   placeholder="Your system name" value="${escapeHtml(g.greeting_name || '')}">
        </label>`;
    const density = localStorage.getItem('atlas_density') || 'comfortable';
    const densityRow = `
        <label class="settings-row" title="How compact cards and lists are — applies immediately">
            <span class="settings-row-label">Display density</span>
            <select id="settings-density" class="styled-select">
                <option value="comfortable" ${density === 'comfortable' ? 'selected' : ''}>Comfortable</option>
                <option value="compact" ${density === 'compact' ? 'selected' : ''}>Compact</option>
                <option value="dense" ${density === 'dense' ? 'selected' : ''}>Dense</option>
            </select>
        </label>`;
    const generalRows = greetingRow + densityRow + generalToggleRows;

    const appearanceSection = `
        <section class="settings-section">
            <h3>Appearance</h3>
            ${buildThemeRow()}
            ${buildAccentRow()}
        </section>`;

    const tray = data.tray || {};
    const trayDisabledAttr = tray.available ? '' : 'disabled';
    const traySection = `
        <section class="settings-section">
            <h3>System tray</h3>
            ${tray.available ? ''
                : '<p class="settings-help">Not available on this system. Install the <code>libayatana-appindicator</code> package to enable the tray.</p>'}
            <label class="settings-row ${tray.available ? '' : 'disabled'}" title="Show an Atlas icon in the system tray">
                <input type="checkbox" data-tray-key="enabled" ${tray.enabled ? 'checked' : ''} ${trayDisabledAttr}>
                <span class="settings-row-label">Show tray icon</span>
            </label>
            <label class="settings-row ${tray.available ? '' : 'disabled'}" title="Closing the window hides Atlas to the tray instead of quitting">
                <input type="checkbox" data-tray-key="minimize_to_tray" ${tray.minimize_to_tray ? 'checked' : ''} ${trayDisabledAttr}>
                <span class="settings-row-label">Close to tray (keep running in background)</span>
            </label>
            <label class="settings-row ${tray.available ? '' : 'disabled'}" title="How often the tray checks for updates (0 = never)">
                <span class="settings-row-label">Check for updates every (minutes, 0 = off)</span>
                <input type="number" id="settings-tray-interval" class="styled-input" min="0" step="5"
                       value="${Number.isFinite(tray.update_check_interval) ? tray.update_check_interval : 60}" ${trayDisabledAttr}>
            </label>
            <p class="settings-help">Tray changes take effect the next time Atlas starts.</p>
        </section>`;

    const arch = data.arch || {};
    const archSection = arch.available ? `
        <section class="settings-section">
            <h3>AUR safety</h3>
            <label class="settings-row" title="Heuristically scan a PKGBUILD before building and flag suspicious lines">
                <input type="checkbox" data-arch-key="check_pkgbuild" ${arch.check_pkgbuild ? 'checked' : ''}>
                <span class="settings-row-label">Scan PKGBUILDs before building (AUR)</span>
            </label>
            <p class="settings-help">A heuristic helper that flags risky-looking lines (pipe-to-shell, base64, writes to <code>~/.ssh</code>, …) for a second look before an AUR build. <strong>Not a safety check</strong> — a clean result doesn't mean a package is safe.</p>
            <label class="settings-row ${arch.chroot_available ? '' : 'disabled'}" title="Build AUR packages in a clean systemd-nspawn chroot (like paru/aurutils) instead of against your live system">
                <input type="checkbox" data-arch-key="build_chroot" ${arch.build_chroot ? 'checked' : ''} ${arch.chroot_available ? '' : 'disabled'}>
                <span class="settings-row-label">Build AUR packages in a clean chroot</span>
            </label>
            <p class="settings-help">${arch.chroot_available
                ? 'Isolates the <em>build</em> so a build script can\'t touch your <code>$HOME</code>/system, and enforces clean dependencies. The first build downloads a ~1&nbsp;GB base chroot (reused afterward). <strong>It does not make a malicious package safe</strong> — the result is still installed with pacman. Falls back to the normal build if the chroot fails.'
                : 'Install the <code>devtools</code> package to enable this (provides <code>makechrootpkg</code>).'}</p>
        </section>` : '';

    const savedMirrorOpts = getSavedMirrorOptions();
    const mirror = arch.available ? (await pyApiCall('get_mirror_status', savedMirrorOpts) || {}) : {};
    if (epoch !== navEpoch) return;  // user navigated away during the mirror fetch
    const mirrorBackup = arch.available ? (await pyApiCall('get_mirrorlist_backup_status') || {}) : {};
    const mirrorWhen = mirror.last_modified_iso ? new Date(mirror.last_modified_iso).toLocaleString() : null;
    const mirrorSummary = (mirror.count)
        ? `<div class="mirror-summary">
               <div class="mirror-stat"><strong>${escapeHtml(mirror.count)}</strong> active mirror${mirror.count === 1 ? '' : 's'}${mirrorWhen ? ` · updated ${escapeHtml(mirrorWhen)}` : ''}</div>
               ${(mirror.servers && mirror.servers.length) ? `<div class="mirror-hosts">${mirror.servers.map(h => `<span class="attn-chip">${escapeHtml(h)}</span>`).join('')}</div>` : ''}
           </div>`
        : '';
    const mirrorCmd = mirror.command
        ? `<p class="settings-help">Runs: <code id="mirror-cmd-preview">${escapeHtml(mirror.command)}</code></p>` : '';
    const backupLine = (mirrorBackup && mirrorBackup.exists)
        ? `<div class="mirror-backup"><p class="settings-help">📦 A pre-regeneration backup is available (taken ${escapeHtml(mirrorBackup.age_minutes)} min ago). <button class="btn btn-outline btn-small" id="settings-restore-mirrors-btn">Restore backup</button></p></div>`
        : '';
    const mirrorsSection = arch.available ? `
        <section class="settings-section">
            <h3>Mirrors</h3>
            ${mirrorSummary}
            ${backupLine}
            <p class="settings-help">Rebuild <code>/etc/pacman.d/mirrorlist</code> with the fastest mirrors${arch.mirror_tool ? ` (via <code>${escapeHtml(arch.mirror_tool)}</code>)` : ''}. Takes up to a minute. ${arch.mirror_tool ? '' : '<strong>Install <code>reflector</code> to enable this.</strong>'}</p>
            ${buildMirrorOptionsHTML(mirror)}
            ${mirrorCmd}
            <div class="settings-actions">
                <button id="settings-regen-mirrors-btn" class="btn btn-outline" ${arch.mirror_tool ? '' : 'disabled'}>Regenerate mirror list</button>
                ${mirror.command ? '<button id="settings-copy-mirror-cmd-btn" class="btn btn-outline">⧉ Copy command</button>' : ''}
            </div>
        </section>` : '';

    packagesGrid.innerHTML = `
        <div class="settings-page">
            <section class="settings-section">
                <h3>Package types</h3>
                <p class="settings-help">Enable the sources Atlas manages. Greyed-out types aren't available on this system.</p>
                ${typeRows}
            </section>
            ${flatpakSection}
            <section class="settings-section">
                <h3>General</h3>
                ${generalRows}
            </section>
            ${appearanceSection}
            ${traySection}
            ${archSection}
            ${mirrorsSection}
            <section class="settings-section">
                <h3>Backup</h3>
                <p class="settings-help">Save the list of installed apps to <code>~/atlas-manifest.json</code>, or reinstall everything from it (handy for migrating or after a reinstall).</p>
                <div class="settings-actions">
                    <button id="settings-export-btn" class="btn btn-outline">⬆ Export installed apps</button>
                    <button id="settings-import-btn" class="btn btn-outline">⬇ Import from manifest</button>
                </div>
            </section>
            <div class="settings-actions">
                <button id="settings-save-btn" class="btn btn-primary">Save changes</button>
            </div>
        </div>`;

    document.getElementById('settings-save-btn').addEventListener('click', saveSettings);
    document.getElementById('settings-export-btn').addEventListener('click', exportPackages);
    document.getElementById('settings-import-btn').addEventListener('click', importPackages);
    // Track the live command (changes as the user edits the reflector options) for the copy button.
    let currentMirrorCommand = mirror.command || null;
    const mirrorCmdPreviewEl = document.getElementById('mirror-cmd-preview');
    // When a reflector option changes: persist the selection, recompute the previewed command.
    const onMirrorOptionChange = async () => {
        const opts = readMirrorOptionsFromDOM();
        setSavedMirrorOptions(opts);
        const r = await pyApiCall('preview_mirror_command', opts);
        if (r && r.command) {
            currentMirrorCommand = r.command;
            if (mirrorCmdPreviewEl) mirrorCmdPreviewEl.textContent = r.command;
        }
    };
    if (mirror.options) {
        ['mirror-country', 'mirror-sort'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', onMirrorOptionChange);
        });
        document.querySelectorAll('[data-mirror-proto]').forEach(el =>
            el.addEventListener('change', onMirrorOptionChange));
    }
    const regenMirrorsBtn = document.getElementById('settings-regen-mirrors-btn');
    if (regenMirrorsBtn) regenMirrorsBtn.addEventListener('click', async () => {
        await regenerateMirrors(regenMirrorsBtn, mirror.options ? readMirrorOptionsFromDOM() : undefined);
        if (currentView === 'settings') renderSettings();  // refresh the mirror summary
    });
    const restoreMirrorsBtn = document.getElementById('settings-restore-mirrors-btn');
    if (restoreMirrorsBtn) restoreMirrorsBtn.addEventListener('click', async () => {
        restoreMirrorsBtn.classList.add('loading');
        const r = await pyApiCall('restore_mirrorlist_backup');
        restoreMirrorsBtn.classList.remove('loading');
        if (r && r.status === 'ok') {
            showToast('Mirrors', 'Mirror list restored from backup', 'success');
            if (currentView === 'settings') renderSettings();
        } else if (r && r.status === 'cancelled') {
            showToast('Mirrors', 'Restore cancelled', 'info');
        }
    });
    const copyMirrorCmdBtn = document.getElementById('settings-copy-mirror-cmd-btn');
    if (copyMirrorCmdBtn) copyMirrorCmdBtn.addEventListener('click', () => {
        const cmd = currentMirrorCommand;
        if (!cmd) return;
        const done = () => {
            copyMirrorCmdBtn.textContent = '✓ Copied';
            setTimeout(() => { copyMirrorCmdBtn.textContent = '⧉ Copy command'; }, 1500);
            showToast('Copied command', cmd, 'success');
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(cmd).then(done).catch(() => {});
        } else { done(); }
    });
    // Density is a localStorage display pref — apply it instantly (no Save needed).
    const densitySel = document.getElementById('settings-density');
    if (densitySel) densitySel.addEventListener('change', () => setDensity(densitySel.value));

    const themeSel = document.getElementById('settings-theme');
    if (themeSel) themeSel.addEventListener('change', () => setTheme(themeSel.value));

    const accentHost = document.getElementById('settings-accent');
    if (accentHost) accentHost.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-accent-pick]');
        if (!btn) return;
        setAccent(btn.dataset.accentPick);
        accentHost.querySelectorAll('.accent-swatch').forEach(s => s.classList.remove('selected'));
        btn.classList.add('selected');
    });
}

async function saveSettings() {
    const btn = document.getElementById('settings-save-btn');
    btn.classList.add('loading');

    const types = {};
    packagesGrid.querySelectorAll('input[data-type-id]').forEach(el => {
        types[el.getAttribute('data-type-id')] = el.checked;
    });
    const general = {};
    packagesGrid.querySelectorAll('input[data-gen-key]').forEach(el => {
        general[el.getAttribute('data-gen-key')] = el.checked;
    });
    const greetingEl = document.getElementById('settings-greeting-name');
    if (greetingEl) general.greeting_name = greetingEl.value.trim();
    const payload = { types, general };
    const levelEl = document.getElementById('settings-flatpak-level');
    if (levelEl) payload.flatpak_installation_level = levelEl.value;

    const tray = {};
    packagesGrid.querySelectorAll('input[data-tray-key]').forEach(el => {
        tray[el.getAttribute('data-tray-key')] = el.checked;
    });
    const intervalEl = document.getElementById('settings-tray-interval');
    if (intervalEl) {
        const mins = parseInt(intervalEl.value, 10);
        if (Number.isFinite(mins)) tray.update_check_interval = Math.max(0, mins);
    }
    payload.tray = tray;

    const arch = {};
    packagesGrid.querySelectorAll('input[data-arch-key]').forEach(el => {
        arch[el.getAttribute('data-arch-key')] = el.checked;
    });
    if (Object.keys(arch).length) payload.arch = arch;

    const res = await pyApiCall('save_app_settings', payload);
    btn.classList.remove('loading');
    if (res && res.status === 'ok') {
        packageCache = {};  // package-type changes alter what searches/installed return
        showToast('Saved', 'Settings updated', 'success');
    } else if (res) {
        // res === null means pyApiCall already surfaced the backend error toast
        showToast('Error', res.message || 'Could not save settings', 'error');
    }
}

function activateView(viewName) {
    navItems.forEach(n => n.classList.remove('active'));
    const btn = document.querySelector(`.nav-item[data-view="${viewName}"]`);
    if (btn) {
        btn.classList.add('active');
    }
    
    currentView = viewName;
    navEpoch++;  // supersede any in-flight view render so it can't paint over us
    resetContentScroll();  // don't inherit the previous view's scroll (strands a short view → blank)
    searchInput.value = ''; // clear search on view change

    const notice = document.getElementById('updates-notice');
    if (notice) notice.innerHTML = '';  // only the Updates view shows the .pacnew notice

    // The Attention Center belongs to the dashboard; clear it for non-package views (the
    // dashboard repopulates it via fetchPackages). Invalidate any in-flight render first.
    if (viewName !== 'dashboard') {
        attentionEpoch++;
        const ac = document.getElementById('attention-center');
        if (ac) ac.innerHTML = '';
    }

    if (viewName === 'settings') {
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        renderSettings();
    } else if (viewName === 'news') {
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        renderNews();
    } else if (viewName === 'browse') {
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        renderBrowse();
    } else if (viewName === 'permissions') {
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        renderPermissionsPage();
    } else if (viewName === 'health') {
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        renderSystemHealth();
    } else {
        fetchPackages();  // calls applyTopbarContext() itself
        return;
    }
    applyTopbarContext();  // utility/landing views: hide the package-list controls
}

// Re-render the active view after an operation finishes (e.g. the terminal panel closes), without
// clearing the search box. Utility views (health/news/permissions/settings/browse) need their own
// renderer — falling back to fetchPackages() on them would wrongly show app suggestions.
function refreshCurrentView() {
    switch (currentView) {
        case 'settings': renderSettings(); break;
        case 'news': renderNews(); break;
        case 'permissions': renderPermissionsPage(); break;
        case 'health': renderSystemHealth(); break;
        case 'pacnew': renderPacnewCenter(); break;
        case 'browse':
            if (activeBrowseCategory) renderCategoryPackages(activeBrowseCategory.key, activeBrowseCategory.label);
            else renderBrowse();
            break;
        default: fetchPackages();
    }
}

navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const viewName = btn.getAttribute('data-view');
        activateView(viewName);
    });
});

// Attention Center cards click through to the page that acts on them.
const attentionHost = document.getElementById('attention-center');
if (attentionHost) {
    attentionHost.addEventListener('click', (e) => {
        const card = e.target.closest('.attention-card');
        if (card && card.dataset.view) activateView(card.dataset.view);
    });
}

const shortcutsHelpBtn = document.getElementById('shortcuts-help-btn');
if (shortcutsHelpBtn) {
    shortcutsHelpBtn.addEventListener('click', () => {
        showToast(
            'Keyboard Shortcuts',
            'Ctrl+K Command palette  •  / Search  •  Esc Clear/Close  •  Ctrl+H Home  •  Ctrl+I Installed  •  Ctrl+U Updates  •  Ctrl+A Activity  •  Ctrl+D Disk  •  Ctrl+Shift+U Update All  •  Ctrl+E Export',
            'info'
        );
    });
}

// Event delegation for packagesGrid (disk rows, package cards, and action buttons)
packagesGrid.addEventListener('click', async (e) => {
    // 0. Empty-state action button → navigate to the suggested view
    const emptyAction = e.target.closest('.empty-state-action');
    if (emptyAction && emptyAction.dataset.emptyView) {
        activateView(emptyAction.dataset.emptyView);
        return;
    }

    // 1. Check disk package row click
    const row = e.target.closest('.disk-package-row');
    if (row) {
        const pkgId = row.dataset.id;
        const pkg = diskPackages.find(p => p.id === pkgId);
        if (pkg) {
            openDetailModal({
                id: pkg.id,
                name: pkg.name,
                type: pkg.type,
                icon_url: '',
                description: '',
                installed: true,
                update_available: false
            });
        }
        return;
    }

    // 1b. Source-switcher pill: re-target the card to the chosen source.
    const pill = e.target.closest('.source-pill');
    if (pill) {
        e.stopPropagation();
        const pcard = pill.closest('.package-card');
        const group = pcard && currentGroups[parseInt(pcard.dataset.gi, 10)];
        const idx = parseInt(pill.dataset.srcidx, 10);
        if (group && group.sources[idx]) {
            pcard.innerHTML = cardInnerHTML(group, idx);
            pcard.dataset.id = group.sources[idx].id;
            pcard.classList.toggle('selected', selectedPackages.has(group.sources[idx].id));
            deferredIconLoad();
        }
        return;
    }

    // 2. Check package action button click
    const actionBtn = e.target.closest('.action-btn');
    if (actionBtn) {
        e.stopPropagation();
        const action = actionBtn.dataset.action;
        const pid = actionBtn.dataset.id;

        // Queue toggle is a cheap local op — allowed even while an install/update is running.
        if (action === 'queue') {
            toggleQueueFor(pid, actionBtn);
            return;
        }

        if (operationInProgress) {
            showToast('Busy', 'Another operation is already running', 'warning');
            return;
        }
        
        if (action === 'pin') {
            operationInProgress = true;
            actionBtn.classList.add('loading');
            const res = await pyApiCall('pin_update', pid);
            operationInProgress = false; // Reset lock
            if (res && res.success) {
                packageCache = {};
                showToast('Pinned', 'Package pinned successfully', 'success');
                fetchPackages();
            } else {
                actionBtn.classList.remove('loading');
            }
        } else if (action === 'unpin') {
            operationInProgress = true;
            actionBtn.classList.add('loading');
            const res = await pyApiCall('unpin_update', pid);
            operationInProgress = false; // Reset lock
            if (res && res.success) {
                packageCache = {};
                showToast('Unpinned', 'Package unpinned successfully', 'success');
                fetchPackages();
            } else {
                actionBtn.classList.remove('loading');
            }
        } else if (action === 'install') {
            installApp(pid, actionBtn);
        } else if (action === 'uninstall') {
            uninstallApp(pid, actionBtn);
        } else if (action === 'update') {
            updateApp(pid, actionBtn);
        }
        return;
    }

    // 3. Check package card click (only if not clicking on action-btn)
    const card = e.target.closest('.package-card');
    if (card && !e.target.closest('.action-btn')) {
        const pkgId = card.dataset.id;
        const pkg = currentPackages.find(p => p.id === pkgId);
        if (!pkg) return;
        const cardGroup = card.dataset.gi != null ? currentGroups[parseInt(card.dataset.gi, 10)] : null;

        if (selectMode) {
            const chk = card.querySelector('.pkg-checkbox');
            const isSel = selectedPackages.has(pkg.id);
            if (isSel) {
                selectedPackages.delete(pkg.id);
                card.classList.remove('selected');
                if (chk) chk.checked = false;
            } else {
                selectedPackages.add(pkg.id);
                card.classList.add('selected');
                if (chk) chk.checked = true;
            }
            updateBatchBar();
        } else {
            openDetailModal(pkg, cardGroup);
        }
    }
});

// Detail-modal tab bar: switch panels on click (ignores hidden tabs).
document.getElementById('detail-tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.detail-tab');
    if (!tab || tab.classList.contains('hidden')) return;
    activateDetailTab(tab.dataset.tab);
    // Reset the body scroll on switch: panels differ in height, so a tab switched from a long,
    // scrolled panel (e.g. collapsed AUR comments) would otherwise leave the new (shorter) panel
    // scrolled past its content — a blank body with the sticky tab bar scrolled out of view.
    const body = detailModal.querySelector('.modal-body');
    if (body) body.scrollTop = 0;
});

// AUR comments (Overview tab) collapse/expand toggle.
const commentsToggle = document.getElementById('detail-comments-toggle');
if (commentsToggle) {
    const toggleComments = () => {
        const section = document.getElementById('detail-comments-section');
        if (section) section.classList.toggle('collapsed');
    };
    commentsToggle.addEventListener('click', toggleComments);
    commentsToggle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleComments(); }
    });
}

// Source-comparison panel: install from the chosen source (routes through the full preview).
document.getElementById('detail-source-compare').addEventListener('click', (e) => {
    const btn = e.target.closest('.srccmp-install');
    if (!btn) return;
    e.stopPropagation();
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }
    installApp(btn.dataset.id, btn);
});

// Initialization hook when pywebview is ready
// Boot splash control. Window-first startup (see docs/plans/2026-06-20-launch-optimization.md)
// shows the window before the backend manager is built, so we keep the splash up until the backend
// reports ready, then reveal the app. Falls through after a safety timeout so a stuck readiness
// check can never trap the user behind the splash (API calls block server-side regardless).
function hideBootSplash() {
    const splash = document.getElementById('boot-splash');
    if (!splash || splash.classList.contains('hidden')) return;
    splash.classList.add('hidden');
    setTimeout(() => { if (splash.parentNode) splash.remove(); }, 300);  // after the fade
}

async function waitForBackendReady(maxMs = 30000) {
    const start = Date.now();
    while (Date.now() - start < maxMs) {
        try {
            const api = window.pywebview && window.pywebview.api;
            if (api && api.is_backend_ready) {
                if (await api.is_backend_ready()) return true;
            } else {
                return true;  // legacy build with no readiness probe: don't block
            }
        } catch (e) { /* transient bridge hiccup — keep polling */ }
        await new Promise(r => setTimeout(r, 100));
    }
    return false;  // timed out; proceed anyway
}

window.addEventListener('pywebviewready', async function() {
    console.log("pywebview is ready!");
    await waitForBackendReady();
    hideBootSplash();
    syncWindowBg();  // persist the current theme's base bg for next launch's native window color
    fetchPackages();
    refreshUpdatesBadge();  // populate the sidebar Updates count without opening that page
});

// Mock API for development outside of pywebview
const mockApi = {
    search: async (query, type) => [
        { id: '1', name: `Mock Result for ${query}`, publisher: 'Mock Dev', version: '1.0', type: 'Flatpak', description: 'This is a mock search result.', installed: false }
    ],
    get_suggestions: async () => [
        { id: 'app1', name: 'Firefox', publisher: 'Mozilla', version: '115.0', type: 'Flatpak', description: 'A fast, private browser.', installed: false },
        { id: 'app2', name: 'Spotify', publisher: 'Spotify', version: '1.2.0', type: 'Snap', description: 'Music streaming service.', installed: true, update_available: false },
        { id: 'app3', name: 'Discord', publisher: 'Discord', version: '0.0.28', type: 'AUR', description: 'Chat for Gamers.', installed: true, update_available: true }
    ],
    get_installed: async () => [
        { id: 'app2', name: 'Spotify', publisher: 'Spotify', version: '1.2.0', type: 'Snap', description: 'Music streaming service.', installed: true },
        { id: 'app3', name: 'Discord', publisher: 'Discord', version: '0.0.28', type: 'AUR', description: 'Chat for Gamers.', installed: true, update_available: true }
    ],
    get_orphans: async () => [
        { id: 'orphan1', name: 'Mock Orphan Package', publisher: 'Mock Dev', version: '1.0', type: 'Flatpak', description: 'An unused orphaned package.', installed: true, orphan: true }
    ],
    get_updates: async () => [
        { id: 'app3', name: 'Discord', publisher: 'Discord', version: '0.0.28', type: 'AUR', description: 'Chat for Gamers.', installed: true, update_available: true }
    ],
    get_activity: async () => [
        { timestamp: new Date().toISOString(), action: 'install', pkg_name: 'Firefox', pkg_type: 'Flatpak', success: true }
    ],
    get_package_activity: async () => [],
    get_info: async (id) => {
        return {
            'Package ID': id,
            'License': 'MPL-2.0',
            'Size': '125 MB',
            'Source': 'flathub.org',
            'Install Date': new Date().toLocaleDateString()
        };
    },
    install: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 1000)); },
    uninstall: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 1000)); },
    update: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 1000)); },
    batch_uninstall: async (ids) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 1500)); },
    update_all: async () => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 2000)); },
    pin_update: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 500)); },
    unpin_update: async (id) => { return new Promise(resolve => setTimeout(() => resolve({success: true}), 500)); },
    get_disk_usage: async () => {
        return {
            packages: [
                { id: 'app1', name: 'Firefox', type: 'Flatpak', size_bytes: 350000000, size_human: '350.00 MB' },
                { id: 'app2', name: 'Spotify', type: 'Snap', size_bytes: 180000000, size_human: '180.00 MB' },
                { id: 'app3', name: 'Discord', type: 'AUR', size_bytes: 120000000, size_human: '120.00 MB' },
                { id: 'app4', name: 'Steam', type: 'Flatpak', size_bytes: 850000000, size_human: '850.00 MB' }
            ],
            by_type: [
                { type: 'Flatpak', total_bytes: 1200000000, total_human: '1.20 GB' },
                { type: 'Snap', total_bytes: 180000000, total_human: '180.00 MB' },
                { type: 'AUR', total_bytes: 120000000, total_human: '120.00 MB' }
            ]
        };
    },
    export_packages: async () => {
        return {
            path: '~/atlas-manifest.json',
            count: 3
        };
    },
    import_packages: async () => {
        return {
            installed: 1,
            skipped: 2,
            failed: []
        };
    }
};

// Fallback initialization if pywebview event doesn't fire within 1s
setTimeout(() => {
    if (!window.pywebview) {
        fetchPackages();
    }
}, 1000);

// Global Keyboard Shortcuts
document.addEventListener('keydown', (e) => {
    const activeEl = document.activeElement;
    const isInput = activeEl && (
        activeEl.tagName === 'INPUT' ||
        activeEl.tagName === 'TEXTAREA' ||
        activeEl.tagName === 'SELECT' ||
        activeEl.isContentEditable
    );

    const key = e.key;
    const ctrlKey = e.ctrlKey || e.metaKey; // Treat CMD key on macOS like Ctrl
    const shiftKey = e.shiftKey;

    // Ctrl+K / Ctrl+P: toggle the command palette (works even while focused in an input).
    if (ctrlKey && !shiftKey && (key.toLowerCase() === 'k' || key.toLowerCase() === 'p')) {
        e.preventDefault();
        if (commandPaletteOpen()) closeCommandPalette(); else openCommandPalette();
        return;
    }
    // Esc closes the palette first (its input has its own Enter/arrow handling).
    if (key === 'Escape' && commandPaletteOpen()) {
        closeCommandPalette();
        return;
    }

    // / pressed and not in input: focus search
    if (key === '/' && !isInput) {
        e.preventDefault();
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
        return;
    }

    // Escape pressed: context-aware close / clear
    if (key === 'Escape') {
        // 1. Close detail modal if open
        if (detailModal && !detailModal.classList.contains('hidden')) {
            detailModal.classList.add('hidden');
            return;
        }

        // 2. Close terminal panel if open and not busy
        const terminalPanel = document.getElementById('terminal-panel');
        const terminalOverlay = document.getElementById('terminal-overlay');
        if (terminalPanel && !terminalPanel.classList.contains('hidden') && !operationInProgress) {
            terminalPanel.classList.add('hidden');
            if (terminalOverlay) {
                terminalOverlay.classList.add('hidden');
            }
            refreshCurrentView();
            return;
        }

        // 3. Deactivate select mode if active
        if (selectMode) {
            toggleSelectMode(false);
            return;
        }

        // 4. Clear search input if not empty
        if (searchInput && searchInput.value) {
            searchInput.value = '';
            fetchPackages();
            return;
        }
    }

    // Ctrl+H: Home/Dashboard
    if (ctrlKey && !shiftKey && key.toLowerCase() === 'h' && !isInput) {
        e.preventDefault();
        activateView('dashboard');
        return;
    }

    // Ctrl+I: Installed
    if (ctrlKey && !shiftKey && key.toLowerCase() === 'i' && !isInput) {
        e.preventDefault();
        activateView('installed');
        return;
    }

    // Ctrl+U: Updates
    if (ctrlKey && !shiftKey && key.toLowerCase() === 'u' && !isInput) {
        e.preventDefault();
        activateView('updates');
        return;
    }

    // Ctrl+A: Activity (only when not typing in an input)
    if (ctrlKey && !shiftKey && key.toLowerCase() === 'a' && !isInput) {
        e.preventDefault();
        activateView('activity');
        return;
    }

    // Ctrl+D: Disk Usage
    if (ctrlKey && !shiftKey && key.toLowerCase() === 'd' && !isInput) {
        e.preventDefault();
        activateView('disk');
        return;
    }

    // Ctrl+Shift+U: Update All
    if (ctrlKey && shiftKey && key.toLowerCase() === 'u' && !isInput) {
        e.preventDefault();
        const updateAllBtn = document.getElementById('update-all-btn');
        if (updateAllBtn && !updateAllBtn.classList.contains('hidden')) {
            updateAllBtn.click();
        }
        return;
    }

    // Ctrl+E: Export
    if (ctrlKey && !shiftKey && key.toLowerCase() === 'e' && !isInput) {
        e.preventDefault();
        exportPackages();
        return;
    }
});

// ===================== Dashboard "Attention Center" =====================
// A row of lazy, best-effort cards above the suggestions grid answering "what needs my
// attention today?". The HTML builders below are pure (data → markup, no DOM) so they're
// unit-tested in the Node VM contract harness. See
// docs/plans/2026-06-04-dashboard-attention-center.md.

let attentionEpoch = 0;  // stale-render guard: a later render invalidates an in-flight one

function attnLine(html, cls) {
    return `<div class="attention-line${cls ? ' ' + cls : ''}">${html}</div>`;
}
function attnUnknown() {
    return attnLine('Couldn’t check', 'muted');
}
function attnAge(hours) {
    if (hours == null) return '';
    if (hours < 1) return '<1h';
    if (hours < 48) return `${Math.round(hours)}h`;
    return `${Math.round(hours / 24)}d`;
}
// Richer card: a big hero metric + subtitle + detail lines + a footer action. All fields
// optional. `hero` is rendered verbatim (callers pass safe glyphs/numbers); text fields are escaped.
function attentionCard({ view, icon, title, tone, hero, subtitle, linesHTML, actionText }) {
    const t = tone ? ` tone-${tone}` : '';
    const heroHTML = (hero !== undefined && hero !== null && hero !== '')
        ? `<div class="attention-hero">${hero}</div>` : '';
    const subHTML = subtitle ? `<div class="attention-subtitle">${escapeHtml(subtitle)}</div>` : '';
    return `<button class="attention-card${t}" data-view="${escapeHtml(view || '')}">
        <div class="attention-head"><span class="attention-icon">${icon || ''}</span>
            <span class="attention-title">${escapeHtml(title || '')}</span></div>
        ${heroHTML}${subHTML}
        <div class="attention-lines">${linesHTML || ''}</div>
        ${actionText ? `<div class="attention-action">${escapeHtml(actionText)} →</div>` : ''}
    </button>`;
}
function attnChip(text) { return `<span class="attn-chip">${escapeHtml(text)}</span>`; }

// `updates`: undefined = still loading, null/'error' = couldn't check, [] = up to date, [...] = list
function buildUpdatesCardHTML(updates) {
    if (updates === undefined) {
        return attentionCard({ view: 'updates', icon: '⟳', title: 'Updates', subtitle: 'Checking…' });
    }
    if (updates === null || updates === 'error') {
        return attentionCard({ view: 'updates', icon: '⟳', title: 'Updates', tone: 'warn',
            hero: '—', subtitle: 'Couldn’t check', actionText: 'Open Updates' });
    }
    const n = updates.length;
    if (n === 0) {
        return attentionCard({ view: 'updates', icon: '✓', title: 'Updates', tone: 'ok',
            hero: '✓', subtitle: 'Everything is up to date' });
    }
    const counts = {};
    updates.forEach(p => { const k = sourceLabel(p.type); counts[k] = (counts[k] || 0) + 1; });
    const chips = Object.entries(counts).map(([k, v]) => attnChip(`${v} ${k}`)).join('');
    return attentionCard({ view: 'updates', icon: '⬆', title: 'Updates', tone: 'warn',
        hero: n, subtitle: `update${n === 1 ? '' : 's'} available`,
        linesHTML: `<div class="attn-chips">${chips}</div>`, actionText: 'Open Updates' });
}

function buildSafetyCardHTML(safety) {
    if (!safety) return attentionCard({ view: 'updates', icon: '🛡', title: 'System safety',
        tone: 'warn', hero: '—', subtitle: 'Couldn’t check' });
    const lines = [];
    let issues = 0;
    if (safety.pacman_locked) { lines.push(attnLine('pacman database is locked', 'danger')); issues++; }
    if (typeof safety.news_count === 'number' && safety.news_count > 0) {
        lines.push(attnLine(`${safety.news_count} unread news since last sync`)); issues++;
    }
    if (typeof safety.pacnew_count === 'number' && safety.pacnew_count > 0) {
        lines.push(attnLine(`${safety.pacnew_count} .pacnew file${safety.pacnew_count === 1 ? '' : 's'} to review`)); issues++;
    }
    if (safety.db_sync_age_hours != null) lines.push(attnLine(`Databases synced ${attnAge(safety.db_sync_age_hours)} ago`, 'muted'));
    const tone = issues > 0 ? 'warn' : 'ok';
    const view = (typeof safety.news_count === 'number' && safety.news_count > 0) ? 'news' : 'updates';
    return attentionCard({ view, icon: '🛡', title: 'System safety', tone,
        hero: issues > 0 ? issues : '✓',
        subtitle: issues > 0 ? `item${issues === 1 ? '' : 's'} to review` : 'All clear',
        linesHTML: lines.join(''), actionText: 'Review' });
}

function buildReclaimCardHTML(reclaim) {
    if (!reclaim) return attentionCard({ view: 'disk', icon: '🧹', title: 'Reclaim space',
        tone: 'info', hero: '—', subtitle: 'Couldn’t check' });
    const lines = [];
    let tone = 'info';
    if (typeof reclaim.orphans === 'number') {
        if (reclaim.orphans > 0) { lines.push(attnLine(`${reclaim.orphans} orphan package${reclaim.orphans === 1 ? '' : 's'}`)); tone = 'warn'; }
        else lines.push(attnLine('No orphan packages', 'muted'));
    }
    if (reclaim.flatpak_available) lines.push(attnLine('Unused Flatpak runtimes can be cleaned', 'muted'));
    if (lines.length === 0) lines.push(attnUnknown());
    // Hero = pacman cache size (the headline reclaimable figure) when known.
    const hero = reclaim.cache_human ? escapeHtml(reclaim.cache_human) : null;
    return attentionCard({ view: 'disk', icon: '🧹', title: 'Reclaim space', tone,
        hero, subtitle: hero ? 'in pacman cache' : null,
        linesHTML: lines.join(''), actionText: 'Open Disk' });
}

function buildActivityCardHTML(activity) {
    const list = Array.isArray(activity) ? activity : [];
    if (list.length === 0) return attentionCard({ view: 'activity', icon: '🕘', title: 'Recent activity',
        tone: 'info', subtitle: 'No recent activity yet' });
    const ACTION = { install: 'Installed', update: 'Updated', uninstall: 'Removed', downgrade: 'Downgraded' };
    const lines = list.slice(0, 3).map(e => {
        const verb = ACTION[e.action] || e.action || '';
        const mark = e.success === false ? ' <span class="attn-fail">failed</span>' : '';
        return attnLine(`${escapeHtml(verb)} <strong>${escapeHtml(e.pkg_name || '')}</strong>${mark}`);
    });
    return attentionCard({ view: 'activity', icon: '🕘', title: 'Recent activity', tone: 'info',
        linesHTML: lines.join(''), actionText: 'Open Activity' });
}

function buildAurCardHTML(aur) {
    if (!aur) return attentionCard({ view: 'settings', icon: '📦', title: 'AUR safety',
        tone: 'info', hero: '—', subtitle: 'Couldn’t check' });
    const enabled = !!aur.chroot_enabled;
    const lines = [];
    if (!aur.chroot_available) lines.push(attnLine('Install devtools to enable', 'muted'));
    else lines.push(attnLine(enabled ? 'Builds run in an isolated chroot' : 'Builds run on the host', 'muted'));
    return attentionCard({ view: 'settings', icon: '📦', title: 'AUR safety', tone: enabled ? 'ok' : 'info',
        hero: enabled ? 'On' : 'Off', subtitle: 'clean-chroot builds',
        linesHTML: lines.join(''), actionText: 'Settings' });
}

function buildAttentionCenterHTML(summary, updates) {
    const s = summary || {};
    const cards = [
        buildUpdatesCardHTML(updates),
        buildSafetyCardHTML(s.safety || null),
        buildReclaimCardHTML(s.reclaim || null),
        buildActivityCardHTML(s.activity || []),
        buildAurCardHTML(s.aur || null),
    ];
    return `<div class="attention-grid">${cards.join('')}</div>`;
}

// --- Dashboard header: a time-of-day greeting + a status line summarizing actionable items ---
function dashboardGreeting(hour) {
    if (hour >= 5 && hour < 12) return 'Good morning';
    if (hour >= 12 && hour < 18) return 'Good afternoon';
    return 'Good evening';
}

// Count the "areas" that need action — mirrors the warn-tone cards (Updates / System safety /
// Reclaim orphans), so the header number matches what's highlighted below.
function countActionable(summary, updates) {
    let n = 0;
    if (Array.isArray(updates) && updates.length > 0) n += 1;
    const s = (summary && summary.safety) || null;
    if (s) {
        const issues = (s.pacman_locked ? 1 : 0)
            + ((typeof s.news_count === 'number' && s.news_count > 0) ? 1 : 0)
            + ((typeof s.pacnew_count === 'number' && s.pacnew_count > 0) ? 1 : 0);
        if (issues > 0) n += 1;
    }
    const r = (summary && summary.reclaim) || null;
    if (r && typeof r.orphans === 'number' && r.orphans > 0) n += 1;
    return n;
}

function dashboardMessage(count) {
    if (count <= 0) return 'You’re all caught up — nothing needs your attention.';
    if (count === 1) return '1 thing needs your attention.';
    return `${count} things need your attention.`;
}

// tone: 'ok' (all caught up → green ✓), 'warn' (items pending → amber), or null (loading → muted)
function buildDashboardHeaderHTML(greeting, name, message, tone) {
    const who = name ? `${escapeHtml(greeting)}, ${escapeHtml(name)}` : escapeHtml(greeting);
    const t = tone ? ` tone-${tone}` : '';
    const check = tone === 'ok' ? '<span class="dash-check">✓</span> ' : '';
    return `<div class="dashboard-header">
        <h1 class="dash-greeting">${who}</h1>
        <p class="dash-subtitle${t}">${check}${escapeHtml(message)}</p>
    </div>`;
}

async function renderAttentionCenter() {
    const host = document.getElementById('attention-center');
    if (!host) return;
    const token = ++attentionEpoch;
    const greeting = dashboardGreeting(new Date().getHours());
    const paint = (summary, updates, message, tone) => {
        const name = (summary && summary.user) || '';
        host.innerHTML = buildDashboardHeaderHTML(greeting, name, message, tone)
            + buildAttentionCenterHTML(summary, updates);
    };
    paint(null, undefined, 'Checking your system…', null);  // skeleton/loading

    const summaryP = pyApiCall('get_dashboard_summary');
    // Updates is the one expensive signal (read_installed). Reuse the Updates view's warm cache
    // when present, and warm it here otherwise, so the dashboard and Updates view share one fetch.
    const updatesP = getUpdatesCached();

    const summary = await summaryP;
    if (token !== attentionEpoch || currentView !== 'dashboard') return;  // user moved on
    paint(summary, undefined, 'Checking your system…', null);  // cheap cards in, updates loading

    const updates = await updatesP;
    if (token !== attentionEpoch || currentView !== 'dashboard') return;
    const u = updates === null ? 'error' : updates;
    const count = countActionable(summary, u);
    paint(summary, u, dashboardMessage(count), count > 0 ? 'warn' : 'ok');
}

// ===================== Command palette (Ctrl+K / Ctrl+P) =====================
// A keyboard-first launcher. The registry + filtering are pure (unit-tested in the Node VM
// harness); open/close/render/keyboard-nav are DOM-bound. See
// docs/plans/2026-06-04-command-palette.md.

let cmdSelected = 0;       // index into the currently-filtered list
let cmdFiltered = [];      // the filtered commands currently shown

function commandRegistry() {
    const nav = (label, view, keywords, shortcut) => ({
        id: 'nav:' + view, label, keywords, shortcut,
        run: () => activateView(view),
    });
    return [
        nav('Dashboard', 'dashboard', 'home overview attention', ['Ctrl', 'H']),
        nav('Browse', 'browse', 'categories discover store suggested'),
        nav('Installed', 'installed', 'apps packages', ['Ctrl', 'I']),
        nav('Updates', 'updates', 'upgrade outdated', ['Ctrl', 'U']),
        nav('News', 'news', 'arch announcements'),
        nav('Disk', 'disk', 'space usage reclaim', ['Ctrl', 'D']),
        nav('System health', 'health', 'cockpit maintenance status checks pacman'),
        nav('Activity', 'activity', 'history log', ['Ctrl', 'A']),
        nav('Permissions', 'permissions', 'flatpak flatseal sandbox'),
        nav('Settings', 'settings', 'preferences config options'),
        { id: 'act:search', label: 'Search packages…', keywords: 'find', shortcut: ['/'],
          run: () => { if (searchInput) { searchInput.focus(); searchInput.select(); } } },
        { id: 'act:update-all', label: 'Update all', keywords: 'upgrade', shortcut: ['Ctrl', 'Shift', 'U'],
          available: () => updateAllBtn && !updateAllBtn.classList.contains('hidden'),
          run: () => updateAllBtn.click() },
        { id: 'act:cleanup-orphans', label: 'Clean up orphan packages', keywords: 'remove unused reclaim',
          available: () => cleanupOrphansBtn && !cleanupOrphansBtn.classList.contains('hidden'),
          run: () => cleanupOrphansBtn.click() },
        { id: 'act:refresh', label: 'Refresh', keywords: 'reload',
          run: () => { const b = document.getElementById('refresh-btn'); if (b) b.click(); else fetchPackages(); } },
        { id: 'act:view-grid', label: 'Grid view', keywords: 'layout cards',
          run: () => setViewMode('grid') },
        { id: 'act:view-list', label: 'List view', keywords: 'layout rows',
          run: () => setViewMode('list') },
        { id: 'act:select', label: 'Select multiple packages', keywords: 'batch checkbox multi',
          run: () => toggleSelectMode(true) },
        { id: 'act:mirrors', label: 'Regenerate mirror list', keywords: 'reflector pacman speed',
          run: () => regenerateMirrors() },
        { id: 'act:pacdiff', label: 'Open pacdiff', keywords: 'pacnew pacsave config merge',
          run: () => pyApiCall('launch_pacdiff') },
        { id: 'act:export', label: 'Export package manifest', keywords: 'backup save list',
          shortcut: ['Ctrl', 'E'], run: () => exportPackages() },
    ];
}

// Commands available right now (drops e.g. Update-all when there's nothing to update).
function buildCommandList() {
    return commandRegistry().filter(c => !c.available || c.available());
}

// Fuzzy subsequence score: >=0 if every char of `query` appears in order in `text`, else -1.
// Rewards consecutive matches and matches at word starts so the best target floats to the top.
function fuzzyScore(query, text) {
    const q = (query || '').toLowerCase();
    const t = (text || '').toLowerCase();
    if (!q) return 0;
    if (!t) return -1;
    let ti = 0, score = 0, streak = 0;
    for (let qi = 0; qi < q.length; qi++) {
        let found = -1;
        for (let i = ti; i < t.length; i++) { if (t[i] === q[qi]) { found = i; break; } }
        if (found === -1) return -1;
        if (found === ti && qi > 0) { streak += 1; score += 4 + streak; }  // contiguous run
        else { streak = 0; score += 1; }
        if (found === 0 || t[found - 1] === ' ' || t[found - 1] === '-') score += 6;  // word start
        ti = found + 1;
    }
    return score;
}

// Fuzzy filter over label + keywords, best matches first. Empty query → all (registry order).
function filterCommands(commands, query) {
    const q = (query || '').trim();
    if (!q) return commands.slice();
    const scored = [];
    commands.forEach((c, idx) => {
        const ls = fuzzyScore(q, c.label);
        const ks = c.keywords ? fuzzyScore(q, c.keywords) : -1;
        let best = ls;
        if (ks >= 0) best = Math.max(best, ks - 3);  // keyword hits rank just below label hits
        if (best >= 0) scored.push({ c, score: best, idx });
    });
    scored.sort((a, b) => (b.score - a.score) || (a.idx - b.idx));  // stable on ties
    return scored.map(s => s.c);
}

// Pure: stable re-rank of backend search results so the best *name* match floats to the top
// (the backend matches on name/description/keywords, but the user's query is almost always a name).
// Reuses fuzzyScore. **Never drops** a result — items whose name fuzzyScore can't match keep their
// original backend order, below the matches. Empty query / <2 results → returned unchanged.
function rerankByFuzzy(results, query) {
    const list = Array.isArray(results) ? results : [];
    const q = (query || '').trim();
    if (!q || list.length < 2) return list;
    return list
        .map((pkg, idx) => ({ pkg, idx, score: fuzzyScore(q, (pkg && (pkg.name || pkg.display_name)) || '') }))
        .sort((a, b) => (b.score - a.score) || (a.idx - b.idx))  // best name match first; stable on ties
        .map(s => s.pkg);
}

// Theme 6 part 2: search *within* a finite local view (Installed / Updates) by filtering that view's
// own list, rather than a global cross-source search. Exact substring matches (name or description)
// win and are relevance-ordered; when there are none and the query is long enough, fall back to
// thresholded fuzzy *name* matches so a partial/subsequence query still finds the package (e.g.
// "frfx" → firefox). Returns [] for no match, the full list for an empty query. Reuses fuzzyScore.
const LOCAL_FUZZY_MIN_SCORE = 8;
const LOCAL_FUZZY_MIN_QUERY_LEN = 3;
function filterLocalPackages(list, query) {
    const items = Array.isArray(list) ? list : [];
    const raw = (query || '').trim();
    if (!raw) return items;
    const q = raw.toLowerCase();
    const nameOf = (p) => (p && (p.name || p.display_name)) || '';
    const exact = items.filter(p =>
        nameOf(p).toLowerCase().includes(q) || ((p && p.description) || '').toLowerCase().includes(q));
    if (exact.length) return rerankByFuzzy(exact, raw);              // exact hits, best name match first
    if (raw.length < LOCAL_FUZZY_MIN_QUERY_LEN) return [];           // too short to fuzzy without noise
    return items
        .map((p, idx) => ({ p, idx, score: fuzzyScore(raw, nameOf(p)) }))
        .filter(s => s.score >= LOCAL_FUZZY_MIN_SCORE)
        .sort((a, b) => (b.score - a.score) || (a.idx - b.idx))
        .map(s => s.p);
}

// ---- Install queue (Theme 5) ----------------------------------------------------------------
// A persistent, cross-view basket of packages to install together. Items are minimal snapshots so
// they survive view changes (no dependence on the current view's `currentPackages`).

// Pure: the minimal fields we keep for a queued package.
function pkgSnapshot(pkg) {
    return {
        id: pkg.id,
        name: pkg.name || pkg.id,
        type: normalizeType(pkg.type),
        icon_url: pkg.icon_url || '',
        version: pkg.version || '',
    };
}

// Pure: add a snapshot to a queue array, de-duped by id (returns a new array). Ignores bad input.
function queueUpsert(list, pkg) {
    const arr = Array.isArray(list) ? list.slice() : [];
    if (!pkg || !pkg.id || arr.some(q => q.id === pkg.id)) return arr;
    arr.push(pkgSnapshot(pkg));
    return arr;
}

function loadQueue() {
    try {
        const raw = JSON.parse(localStorage.getItem(QUEUE_STORAGE_KEY));
        installQueue = Array.isArray(raw) ? raw.filter(q => q && q.id) : [];
    } catch (e) { installQueue = []; }
}
function persistQueue() {
    try { localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(installQueue)); } catch (e) { /* ignore */ }
}

function queueHas(id) { return installQueue.some(q => q.id === id); }
function queueAdd(pkg) {
    const before = installQueue.length;
    installQueue = queueUpsert(installQueue, pkg);
    if (installQueue.length !== before) { persistQueue(); updateQueueBadge(); }
}
function queueRemove(id) {
    const before = installQueue.length;
    installQueue = installQueue.filter(q => q.id !== id);
    if (installQueue.length !== before) { persistQueue(); updateQueueBadge(); }
}
function queueClear() { installQueue = []; persistQueue(); updateQueueBadge(); }

// Reflect the queue count on the topbar "Queue (N)" button (hidden when empty).
function updateQueueBadge() {
    const btn = document.getElementById('queue-btn');
    if (!btn) return;
    const n = installQueue.length;
    btn.textContent = `Queue (${n})`;
    btn.classList.toggle('hidden', n === 0);
}

// Toggle a package's queue membership from a card/detail button, updating the button in place.
function toggleQueueFor(pid, btn) {
    if (queueHas(pid)) {
        queueRemove(pid);
    } else {
        const pkg = currentPackages.find(p => p.id === pid);
        if (!pkg) { showToast('Queue', 'Could not queue this package.', 'warning'); return; }
        queueAdd(pkg);
    }
    if (btn) {
        const q = queueHas(pid);
        btn.classList.toggle('queued', q);
        btn.textContent = q ? '✓ Queued' : '＋ Queue';
        btn.title = q ? 'Remove from install queue' : 'Add to install queue';
    }
}

// Open the queue review modal, (re)rendering the current list + wiring per-row Remove.
function openQueueModal() {
    const modal = document.getElementById('queue-modal');
    const body = document.getElementById('queue-modal-body');
    if (!modal || !body) return;
    body.innerHTML = buildQueueReviewHTML(installQueue);
    const installAll = document.getElementById('queue-install-all-btn');
    if (installAll) installAll.disabled = installQueue.length === 0;
    const clearBtn = document.getElementById('queue-clear-btn');
    if (clearBtn) clearBtn.disabled = installQueue.length === 0;
    modal.classList.remove('hidden');
}

async function installQueuedPackages() {
    const ids = installQueue.map(q => q.id);
    if (!ids.length) return;
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }
    document.getElementById('queue-modal').classList.add('hidden');
    showToast('Installing queue', `Installing ${ids.length} package(s)…`, 'info');
    operationInProgress = true;
    const result = await pyApiCall('batch_install', ids);
    operationInProgress = false;
    if (result && result.success) {
        packageCache = {};                 // installs changed state — drop cached lists
        queueClear();
        showToast('Queue installed', 'All queued packages were installed.', 'success');
        fetchPackages();
    } else {
        showToast('Error', result ? result.error : 'Queue install failed', 'error');
    }
}

// Pure: the review-modal list of queued items (icon + name + source chip + Remove). '' when empty.
function buildQueueReviewHTML(items) {
    items = items || [];
    if (!items.length) return '<p class="queue-empty">Your install queue is empty. Add packages with “＋ Queue” while you browse.</p>';
    return items.map(it => `
        <div class="queue-row" data-id="${escapeHtml(it.id)}">
            <img class="queue-row-icon" src="${(it.icon_url && it.icon_url.startsWith('data:')) ? it.icon_url : letterAvatar(it)}" alt="" loading="lazy">
            <div class="queue-row-info">
                <span class="queue-row-name">${escapeHtml(it.name || it.id)}</span>
                <span class="queue-row-meta">${escapeHtml(sourceLabel(it.type))}${it.version ? ' • v' + escapeHtml(it.version) : ''}</span>
            </div>
            <button type="button" class="btn btn-outline btn-sm queue-row-remove" data-queue-remove="${escapeHtml(it.id)}">Remove</button>
        </div>`).join('');
}

function renderCommandResults(query) {
    const list = document.getElementById('command-results');
    if (!list) return;
    cmdFiltered = filterCommands(buildCommandList(), query);
    if (cmdSelected >= cmdFiltered.length) cmdSelected = Math.max(0, cmdFiltered.length - 1);
    if (cmdFiltered.length === 0) {
        list.innerHTML = '<div class="command-empty">No matching commands</div>';
        return;
    }
    list.innerHTML = cmdFiltered.map((c, i) => {
        const keys = (c.shortcut || []).map(k => `<kbd>${escapeHtml(k)}</kbd>`).join('');
        return `
        <div class="command-item ${i === cmdSelected ? 'cmd-selected' : ''}" data-cmd-index="${i}">
            <span class="command-label">${escapeHtml(c.label)}</span>
            ${keys ? `<span class="command-keys">${keys}</span>` : ''}
        </div>`;
    }).join('');
}

function runCommandAt(index) {
    const cmd = cmdFiltered[index];
    closeCommandPalette();
    if (cmd && typeof cmd.run === 'function') {
        try { cmd.run(); } catch (e) { console.error('command failed:', cmd.id, e); }
    }
}

function openCommandPalette() {
    const palette = document.getElementById('command-palette');
    const input = document.getElementById('command-palette-input');
    if (!palette || !input) return;
    cmdSelected = 0;
    input.value = '';
    renderCommandResults('');
    palette.classList.remove('hidden');
    input.focus();
}

function closeCommandPalette() {
    const palette = document.getElementById('command-palette');
    if (palette) palette.classList.add('hidden');
}

function commandPaletteOpen() {
    const palette = document.getElementById('command-palette');
    return palette && !palette.classList.contains('hidden');
}

(function wireCommandPalette() {
    const palette = document.getElementById('command-palette');
    const input = document.getElementById('command-palette-input');
    if (!palette || !input) return;

    input.addEventListener('input', () => { cmdSelected = 0; renderCommandResults(input.value); });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            cmdSelected = Math.min(cmdSelected + 1, cmdFiltered.length - 1);
            renderCommandResults(input.value);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            cmdSelected = Math.max(cmdSelected - 1, 0);
            renderCommandResults(input.value);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (cmdFiltered.length) runCommandAt(cmdSelected);
        }
    });
    const results = document.getElementById('command-results');
    if (results) {
        results.addEventListener('click', (e) => {
            const item = e.target.closest('.command-item');
            if (item) runCommandAt(parseInt(item.dataset.cmdIndex, 10));
        });
    }
    palette.querySelector('.command-palette-backdrop').addEventListener('click', closeCommandPalette);
})();

if (typeof window !== 'undefined' && window.__ATLAS_TEST__) {
    window.__atlasTestHooks = {
        setTheme,
        setAccent,
        buildThemeRow,
        buildAccentRow,
        buildAttentionCenterHTML,
        buildUpdatesCardHTML,
        buildDashboardHeaderHTML,
        dashboardGreeting,
        countActionable,
        dashboardMessage,
        renderAttentionCenter,
        buildCommandList,
        filterCommands,
        densityClass,
        shouldShowPackageControls,
        emptyStateHTML,
        systemHealthChecks,
        pacnewRisk,
        buildTransactionPreviewHTML,
        renderDepTree,
        buildUpdateAllPreviewData,
        buildSourceCompareHTML,
        groupKey,
        stripBuildSuffix,
        collapseByName,
        sourcePillLabel,
        sourcePillHTML,
        sourceCompareNote,
        whySourceHint,
        buildCategoryCardHTML,
        buildResumeBrowseHTML,
        buildMirrorOptionsHTML,
        buildDependencySummaryHTML,
        buildDepNodesHTML,
        buildPackageActivityHTML,
        buildAurCommentsHTML,
        formatCommentBodyHTML,
        linkifyComment,
        buildInstalledFilesHTML,
        computeDetailTabs,
        reputationPopupHtml,
        rerankByFuzzy,
        filterLocalPackages,
        pkgSnapshot,
        queueUpsert,
        buildQueueReviewHTML,
        highlightBashLine,
        buildPkgbuildRiskHTML,
        buildPkgbuildMetaHTML,
        buildPkgbuildFindingsHTML,
        findingProvenanceHTML,
        buildPkgbuildCodeHTML,
        renderPkgbuildReview,
        buildPkgbuildTabsHTML,
        buildPkgbuildViews,
        buildPkgbuildDiffHTML,
        safeExternalUrl,
        summarizeFailure,
        highlightLogLine,
        pickActivityText,
        stripProgressBar,
        extractPercent,
        filterActivity,
        groupActivityByDate,
        activityEntryActions,
        activityActionsPresent,
        activityTypesPresent,
        activityHasPacmanLog,
        renderPacmanLogLine,
        cleanActivityError,
        permissionUpdatedToast,
        ensureIconObserver,
        renderPermsAppList,
        setPermsPageApps: (apps) => { permsPageApps = apps; },
        showInstallPreview,
        showTransactionPreview,
        resolveTxPreview,
        refreshCurrentView,
        activateView,
        fetchPackages,
        openDetailModal,
        renderBrowse,
        renderCategoryPackages,
        renderFiltered,
        renderPackages,
        getState: () => ({
            activeBrowseCategory,
            currentPackages: currentPackages.slice(),
            currentView,
            packageFetchEpoch,
            sortMode,
        }),
        setCurrentView: (viewName) => { currentView = viewName; },
        setSearchQuery: (query) => { searchInput.value = query; },
    };
}
