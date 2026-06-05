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

// Theme Management
const themeToggleBtn = document.getElementById('theme-toggle');
const rootElement = document.documentElement;

// Initialize theme from localStorage or default to dark
const savedTheme = localStorage.getItem('atlas-theme') || 'dark';
rootElement.setAttribute('data-theme', savedTheme);

themeToggleBtn.addEventListener('click', () => {
    const currentTheme = rootElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    rootElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('atlas-theme', newTheme);
});

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

// Toast Notifications
const toastContainer = document.getElementById('toast-container');

function showToast(title, message, type = 'info') {
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

    toast.innerHTML = `
        ${iconSvg}
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
    `;

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

let packageCache = {};

function getCacheKey(view, type, query) {
    return `${view}\0${type}\0${query}`;
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
        return { title: 'Download failed', hint: 'A file couldn’t be fetched — a mirror may be down or you’re offline. Refresh mirrors / check your connection and retry.' };
    if (has('conflicting files', 'exists in filesystem'))
        return { title: 'File conflict', hint: 'A package would overwrite files owned by another. The log lists the files — resolve the conflict before retrying.' };
    if (has('conflicting packages', 'are in conflict'))
        return { title: 'Package conflict', hint: 'Two packages conflict and can’t be installed together (see the log).' };
    if (has('unable to satisfy dependency', 'could not find all required packages', 'target not found', 'breaks dependency', 'cannot resolve'))
        return { title: 'Dependency problem', hint: 'A required dependency couldn’t be found or satisfied (see the log).' };
    if (has('==> error', 'build failed', 'a failure occurred in build', 'error: makepkg'))
        return { title: 'Build failed', hint: 'The AUR package failed to build — see the log for the makepkg/compiler error.' };
    return { title: 'The operation failed', hint: 'See the raw log below for details.' };
}

// Pure: pick the line to show as the "current activity" from the latest signals. Prefer the gem's
// substatus, then its high-level status, then the last raw-log line (some gems — e.g. Flatpak —
// blank the substatus and only print), then a generic fallback. Never returns an empty string.
function pickActivityText({ substatus, status, lastLine } = {}) {
    return (substatus && substatus.trim()) || (status && status.trim())
        || (lastLine && lastLine.trim()) || 'Working…';
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

window.terminalAppend = (line) => {
    terminalLogBuffer += (line == null ? '' : line) + '\n';
    if (line && line.trim()) { terminalActivity.lastLine = line; renderTerminalActivity(); }
    const output = document.getElementById('terminal-output');
    const lineEl = document.createElement('span');
    lineEl.className = 'line';
    lineEl.textContent = line;
    output.appendChild(lineEl);
    output.scrollTop = output.scrollHeight;
};

window.terminalSetStatus = (status) => {
    terminalActivity.status = status || '';
    renderTerminalActivity();
};

window.terminalSetSubstatus = (substatus) => {
    terminalActivity.substatus = substatus || '';
    renderTerminalActivity();
};

window.terminalSetProgress = (val) => {
    document.getElementById('terminal-progress-fill').style.width = `${val}%`;
};

window.terminalSetDone = (success) => {
    operationInProgress = false;
    packageCache = {}; // Invalidate cache on terminal operation completion

    // Stop the activity spinner and settle the line on a final message.
    const spinner = document.getElementById('terminal-activity-spinner');
    if (spinner) spinner.classList.add('done');
    terminalActivity.status = success ? 'Done' : 'Failed';
    terminalActivity.substatus = ''; terminalActivity.lastLine = '';
    renderTerminalActivity();

    const doneMsg = document.getElementById('terminal-done-msg');
    doneMsg.className = success ? 'terminal-done-success' : 'terminal-done-error';
    doneMsg.textContent = success ? '✓ Operation completed successfully.' : '✗ Operation failed.';

    const statusEl = document.getElementById('terminal-status');
    statusEl.textContent = success ? 'Success' : 'Failed';
    statusEl.className = 'terminal-status ' + (success ? 'ok' : 'failed');

    // On failure, surface a friendly summary of the likely cause above the raw log.
    const failureEl = document.getElementById('terminal-failure');
    if (failureEl) {
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
        ? `<div class="review-banner ${s.warn ? 'warn' : 'info'}">⚠ ${s.warn || 0} line${s.warn === 1 ? '' : 's'} worth a look${s.info ? ` · ${s.info} minor` : ''} — a hint, not a safety check</div>`
        : '';

    let maintHtml = '';
    const mc = review.maintainer_change;
    if (mc) {
        const oldM = escapeHtml(mc.old || 'unknown');
        const newM = mc.new ? escapeHtml(mc.new) : '<em>orphaned (no maintainer)</em>';
        maintHtml = `<div class="review-banner warn">⚠ Maintainer changed since you installed: <strong>${oldM} → ${newM}</strong>. The package changed hands — worth a look before updating.</div>`;
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

    host.innerHTML = maintHtml + banner + diffHtml + findHtml;
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
            ${n.url ? `<a class="news-link" href="#" data-news-url="${escapeHtml(n.url)}">Read on archlinux.org ↗</a>` : ''}
        </article>`).join('');
    list.querySelectorAll('a[data-news-url]').forEach(a => {
        a.addEventListener('click', (e) => { e.preventDefault(); pyApiCall('open_url', a.dataset.newsUrl); });
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
    if (direct.length || optional.length) {
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

function openTransactionPreview(data) {
    const copy = TX_PREVIEW_COPY[(data && data.action) || 'install'] || TX_PREVIEW_COPY.install;
    const name = (data && data.name) || 'package';
    document.getElementById('tx-preview-body').innerHTML = buildTransactionPreviewHTML(data);
    const title = document.getElementById('tx-preview-title');
    if (title) title.textContent = copy.title(name);
    const desc = document.getElementById('tx-preview-desc');
    if (desc) desc.textContent = copy.desc;
    const proceed = document.getElementById('tx-preview-proceed-btn');
    if (proceed) {
        proceed.textContent = copy.btn;
        proceed.classList.toggle('btn-danger', !!copy.danger);
        proceed.classList.toggle('btn-primary', !copy.danger);
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
    return openTransactionPreview(data);
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
    const data = {
        action: 'update-all',
        name: `${n} package${n === 1 ? '' : 's'}`,
        source_label: '', version: '',
        sizes: sizedCount > 0 ? { download: totalDownload, installed: null } : null,
        deps: { direct: [], optional: [] }, permissions: null, warnings: [], notes: [],
    };
    const parts = [];
    if (counts.arch) parts.push(`Arch: ${counts.arch}`);
    if (counts.aur) parts.push(`AUR: ${counts.aur}`);
    if (counts.flatpak) parts.push(`Flatpak: ${counts.flatpak}`);
    if (counts.other) parts.push(`Other: ${counts.other}`);
    if (parts.length) data.notes.push(parts.join(' · '));
    if (counts.aur) data.notes.push('AUR packages are rebuilt from source — their download size and build time are not included above.');
    if (sizedCount > 0 && sizedCount < n) data.notes.push('Download size shown covers only the packages that report one.');

    const newsCount = extras.news_count || 0;
    if (newsCount > 0) {
        data.warnings.push({ level: 'warn', title: `${newsCount} unread Arch news item${newsCount === 1 ? '' : 's'}`,
            detail: "Published since your last sync — review before upgrading (shown next)." });
    }
    const pacnewCount = extras.pacnew_count || 0;
    if (pacnewCount > 0) {
        data.warnings.push({ level: 'info', title: `${pacnewCount} config file${pacnewCount === 1 ? '' : 's'} to review`,
            detail: '.pacnew/.pacsave files from a previous upgrade are still pending in the Updates view.' });
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
function compareSourcePreference(a, b) {
    if (!!a.installed !== !!b.installed) return a.installed ? -1 : 1;  // installed source wins
    const pa = SOURCE_PREF[normalizeType(a.type)] ?? 9;
    const pb = SOURCE_PREF[normalizeType(b.type)] ?? 9;
    return pa - pb;
}
function collapseByName(packages) {
    const order = [], map = new Map();
    (packages || []).forEach(p => {
        const key = (p.name || '').trim().toLowerCase();
        if (!map.has(key)) { map.set(key, []); order.push(key); }
        map.get(key).push(p);
    });
    const groups = [];
    order.forEach(key => {
        const items = map.get(key);
        const types = items.map(p => normalizeType(p.type));
        // The switcher is for ONE app available from DIFFERENT sources. Same name + same
        // source = genuinely different packages (e.g. several Flatpaks that share a display
        // name like "Adwaita theme") — don't fake a multi-source switcher; keep them apart.
        if (new Set(types).size !== types.length) {
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
        const v = aurVariant(pkg.name);
        const votesStr = (typeof pkg.votes === 'number') ? ` · ▲${pkg.votes}` : '';
        let out = `<span class="tag aur" title="AUR — community-maintained, less vetted than the official repo. Build: ${escapeHtml(v.label)}">AUR · ${escapeHtml(v.label)}${escapeHtml(votesStr)}</span>`;
        if (pkg.out_of_date) out += `<span class="tag ood" title="Flagged out-of-date on the AUR">out of date</span>`;
        return out;
    }
    // Multiple sources: clickable switcher pills (the active one is the card's target).
    // An installed source gets a small dot so you can see which one you're running.
    const pills = group.sources.map((s, i) => {
        const t = normalizeType(s.type);
        const cls = `source-pill src-${t}${i === activeIdx ? ' active' : ''}${s.installed ? ' installed' : ''}`;
        const title = `${sourceLabel(s.type)}${s.installed ? ' • installed' : ''}`;
        return `<button class="${escapeHtml(cls)}" data-srcidx="${i}" title="${escapeHtml(title)}">${escapeHtml(sourceLabel(s.type))}</button>`;
    }).join('');
    // When the selected source is AUR, surface its build kind + votes (and out-of-date)
    // inline — the same detail single-source AUR cards show, minus the redundant "AUR".
    let extra = '';
    if (normalizeType(pkg.type) === 'aur') {
        const v = aurVariant(pkg.name);
        const votesStr = (typeof pkg.votes === 'number') ? ` · ▲${pkg.votes}` : '';
        extra += `<span class="tag aur-detail" title="AUR build: ${escapeHtml(v.label)}">${escapeHtml(v.label)}${escapeHtml(votesStr)}</span>`;
        if (pkg.out_of_date) extra += `<span class="tag ood" title="Flagged out-of-date on the AUR">out of date</span>`;
    }
    return `<div class="source-pills">${pills}</div>${extra}`;
}

// One-line characterisation of a source, for the detail-page comparison panel.
function sourceCompareNote(type) {
    switch (normalizeType(type)) {
        case 'aur': return 'Community-maintained · built from source';
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
        const ver = s.version ? `v${escapeHtml(s.version)}` : '—';
        const size = s.size ? formatBytes(s.size) : (s.download_size ? formatBytes(s.download_size) : '—');
        const note = sourceCompareNote(s.type);
        const action = s.installed
            ? `<span class="srccmp-installed">✓ Installed</span>`
            : `<button class="btn btn-primary srccmp-install" data-id="${escapeHtml(s.id)}">Install</button>`;
        return `<div class="srccmp-row src-${escapeHtml(t)}${s.installed ? ' is-installed' : ''}">
            <div class="srccmp-src"><span class="source-pill src-${escapeHtml(t)}">${escapeHtml(sourceLabel(s.type))}</span></div>
            <div class="srccmp-ver">${ver}</div>
            <div class="srccmp-size">${size}</div>
            <div class="srccmp-note">${escapeHtml(note)}</div>
            <div class="srccmp-action">${action}</div>
        </div>`;
    }).join('');
    return `<div class="srccmp">
        <div class="srccmp-head">Available from ${sources.length} sources</div>
        <div class="srccmp-table">${rows}</div>
        <p class="srccmp-hint">Each source is packaged independently — pick where to install from.</p>
    </div>`;
}

// Inner HTML of a card for the given active source — re-rendered on source switch.
function cardInnerHTML(group, activeIdx) {
    const pkg = group.sources[activeIdx];
    const actionButton = pkg.installed ?
        (pkg.update_available ?
            `<button class="btn btn-primary action-btn" data-action="update" data-id="${escapeHtml(pkg.id)}">Update</button>` :
            `<button class="btn btn-danger action-btn" data-action="uninstall" data-id="${escapeHtml(pkg.id)}">Uninstall</button>`) :
        `<button class="btn btn-primary action-btn" data-action="install" data-id="${escapeHtml(pkg.id)}">Install</button>`;

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
function deferredIconLoad() {
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

    const imgs = packagesGrid.querySelectorAll('img.package-icon[data-src], img.package-icon[data-pkgicon]');
    imgs.forEach(img => {
        window.iconObserver.observe(img);
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
const SKIP_DETAIL_KEYS = new Set(['id', 'name', 'version', 'description']);

// Package Detail Modal View
// --- Permissions page (Flatseal-style, master/detail) ----------------------
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
    el.innerHTML = permsPageApps.map(a => `
        <button class="perms-app ${a.id === permsPageSelected ? 'active' : ''}" data-app-id="${escapeHtml(a.id)}">
            <img class="perms-app-icon" src="${(a.icon_url && a.icon_url.startsWith('data:')) ? a.icon_url : letterAvatar(a)}" data-src="${escapeHtml(getIconDataSrc(a.icon_url))}" alt="" loading="lazy">
            <span class="perms-app-name">${escapeHtml(a.name)}</span>
        </button>`).join('');
    el.querySelectorAll('.perms-app').forEach(b => b.addEventListener('click', () => {
        permsPageSelected = b.getAttribute('data-app-id');
        renderPermsAppList();
        renderPermsDetail(permsPageSelected);
    }));
    if (window.iconObserver) el.querySelectorAll('img.perms-app-icon[data-src]').forEach(i => window.iconObserver.observe(i));
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
        if (r && r.status === 'ok') showToast('Permissions', 'Updated — effective next launch', 'success');
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
            showToast('Permissions', 'Updated — effective next launch', 'success');
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
        if (r && r.status === 'ok') { showToast('Permissions', 'Updated — effective next launch', 'success'); renderPermsDetail(appId); return true; }
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
                showToast('Permissions', 'Updated — effective next launch', 'success');
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

    // Source-comparison panel (only when this app is offered by more than one source).
    const compareEl = document.getElementById('detail-source-compare');
    if (compareEl) compareEl.innerHTML = buildSourceCompareHTML(group || findGroupForPkgId(pkg.id));

    // Link to the package's web page (AUR / official Arch). Routed through open_url so it
    // opens in the system browser rather than navigating the app window.
    const linkEl = document.getElementById('detail-link');
    const pageUrl = packagePageUrl(pkg);
    if (pageUrl) {
        const lt = normalizeType(pkg.type);
        linkEl.textContent = lt === 'aur' ? 'View on AUR ↗'
            : lt === 'flatpak' ? 'View on Flathub ↗'
            : 'View package page ↗';
        linkEl.onclick = (e) => { e.preventDefault(); pyApiCall('open_url', pageUrl); };
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
            badgesEl.insertAdjacentHTML('beforeend', parts.join(''));
            const mb = badgesEl.querySelector('[data-popup="maint"]');
            if (mb) mb.addEventListener('click', () => showInfoPopup('Maintainer changed', maintainerChangePopupHtml(info.changed)));

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
    renderDetailScreenshots(pkg, stillCurrentDetail);
    renderDetailHistory(pkg, stillCurrentDetail);

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

    if (actionBtn) {
        footer.appendChild(actionBtn);
    }
}

modalClose.addEventListener('click', () => detailModal.classList.add('hidden'));
modalBackdrop.addEventListener('click', () => detailModal.classList.add('hidden'));

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

updateAllBtn.addEventListener('click', async () => {
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }

    // Cheap pre-flight signals (news since last sync + pending .pacnew). Fail-open — a null result
    // just means that signal is omitted; the upgrade is never blocked by a check failing.
    const news = await pyApiCall('check_upgrade_news');
    const pacnew = await pyApiCall('get_pacnew_files');

    // Aggregate preview: how many packages, the source split, total download size, and the above
    // signals — built from the already-loaded updates list (no extra read_installed).
    const updates = (currentPackages || []).filter(p => p && p.update_available);
    const previewData = buildUpdateAllPreviewData(updates, {
        news_count: news ? news.new_count : 0,
        pacnew_count: pacnew ? pacnew.count : 0,
    });
    const proceed = await openTransactionPreview(previewData);
    if (!proceed) { showToast('Upgrade cancelled', 'Nothing was changed', 'info'); return; }

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
    const result = await pyApiCall('update_all');
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
            detail: 'A database lock (/var/lib/pacman/db.lck) is present — a package operation may be running, or a previous one was interrupted. If nothing is running, remove the lock file manually.' }
        : { id: 'lock', icon: '🔒', title: 'Pacman lock', tone: 'ok',
            detail: 'No stale database lock.' });

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
            ${c.actionLabel && c.actionId
                ? `<button class="health-action" data-health-action="${escapeHtml(c.actionId)}">${escapeHtml(c.actionLabel)}</button>`
                : ''}
        </div>`).join('');
    packagesGrid.innerHTML = `<div class="health-page"><div class="browse-header">System health</div><div class="health-grid">${cards}</div></div>`;
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
    if (name === 'mirrorlist') return { level: 'danger', label: 'Do not overwrite',
        note: 'Overwriting this with the .pacnew wipes your mirror servers — regenerate it instead.' };
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

    const hasMirrorlist = files.some(f => f.replace(/\.pac(new|save)$/, '').split('/').pop() === 'mirrorlist');
    const rows = files.map((f) => {
        const r = pacnewRisk(f);
        return `<div class="pacnew-item tone-${r.level}">
            <div class="pacnew-row">
                <code class="pacnew-path">${escapeHtml(f)}</code>
                <span class="pacnew-risk">${escapeHtml(r.label)}</span>
            </div>
            <div class="pacnew-note">${escapeHtml(r.note)}</div>
            <div class="pacnew-actions">
                <button class="btn btn-outline btn-small pacnew-diff-btn" data-path="${escapeHtml(f)}">Show diff</button>
                <button class="btn btn-outline btn-small pacnew-copy-btn" data-path="${escapeHtml(f)}">Copy path</button>
            </div>
            <pre class="pacnew-diff hidden" data-diff-for="${escapeHtml(f)}"></pre>
        </div>`;
    }).join('');

    packagesGrid.innerHTML = `<div class="pacnew-page">
        <div class="browse-subheader">${back}<span class="browse-cat-title">Config files (.pacnew)</span></div>
        <p class="settings-help">Review each file and merge with <code>pacdiff</code>, then remove the <code>.pacnew</code>. Atlas never auto-merges.</p>
        <div class="pacnew-global">
            <button class="btn btn-outline" id="pacnew-pacdiff">Open pacdiff in a terminal</button>
            ${hasMirrorlist ? '<button class="btn btn-outline" id="pacnew-regen">Regenerate mirror list</button>' : ''}
        </div>
        <div class="pacnew-list">${rows}</div>
    </div>`;

    document.getElementById('pacnew-back').addEventListener('click', () => activateView('health'));
    const pd = document.getElementById('pacnew-pacdiff');
    if (pd) pd.addEventListener('click', async () => {
        const r = await pyApiCall('launch_pacdiff');
        if (r) showToast('pacdiff', 'Opened pacdiff in a terminal — merge the files there', 'info');
    });
    const rg = document.getElementById('pacnew-regen');
    if (rg) rg.addEventListener('click', () => regenerateMirrors(rg));
    packagesGrid.querySelectorAll('.pacnew-copy-btn').forEach(b => b.addEventListener('click', () => copyText(b.dataset.path)));
    packagesGrid.querySelectorAll('.pacnew-diff-btn').forEach(b => b.addEventListener('click', () => togglePacnewDiff(b)));
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
async function renderActivityFeed() {
    packagesGrid.style.display = 'block'; // activity items stack vertically
    const epoch = navEpoch;
    const spin = pendingSpinner(epoch, '<div class="state-container"><div class="spinner"></div></div>');
    const activities = await pyApiCall('get_activity') || [];
    clearTimeout(spin);
    if (epoch !== navEpoch) return;  // a newer navigation superseded this render
    if (activities.length === 0) {
        packagesGrid.innerHTML = emptyStateHTML({
            icon: '🕘', title: 'No activity yet',
            hint: 'Installs, updates, and removals you make in Atlas will show up here.' });
        return;
    }
    
    const feed = document.createElement('div');
    feed.className = 'activity-feed';
    
    activities.forEach(act => {
        const item = document.createElement('div');
        item.className = 'activity-item';
        
        const isSuccess = act.success;
        const iconClass = isSuccess ? 'success' : 'error';
        const iconChar = isSuccess ? '✓' : '✗';
        
        const date = new Date(act.timestamp);
        const timeStr = date.toLocaleString();
        
        const actionLabel = act.action.toUpperCase();
        
        item.innerHTML = `
            <div class="activity-icon ${escapeHtml(iconClass)}">${escapeHtml(iconChar)}</div>
            <div class="activity-body">
                <span class="activity-action ${escapeHtml(act.action)}">${escapeHtml(actionLabel)}</span>
                <span class="activity-pkg">${escapeHtml(act.pkg_name)}</span>
                <span style="color: var(--text-secondary);">(${escapeHtml(act.pkg_type)})</span>
                ${!isSuccess && act.error ? `<span style="color: var(--status-danger); margin-left: 8px;">— ${escapeHtml(act.error)}</span>` : ''}
            </div>
            <div class="activity-time">${escapeHtml(timeStr)}</div>
        `;
        feed.appendChild(item);
    });

    packagesGrid.innerHTML = '';  // replace any prior view / spinner before showing the feed
    packagesGrid.appendChild(feed);
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
    if (query) {
        results = await pyApiCall('search', query, 'all');
    } else {
        if (currentView === 'installed') {
            results = await pyApiCall('get_installed', 'all');
        } else if (currentView === 'updates') {
            results = await pyApiCall('get_updates', 'all');
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
    el.textContent = n;
    el.style.display = n > 0 ? '' : 'none';
}
window.setUpdatesBadge = setUpdatesBadge;  // the tray (Python) calls this to keep the badge live

async function refreshUpdatesBadge() {
    try {
        const results = await pyApiCall('get_updates', 'all');
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
            ${n.url ? `<a class="news-link" href="#" data-news-url="${escapeHtml(n.url)}">Read on archlinux.org ↗</a>` : ''}
        </article>`).join('');

    packagesGrid.innerHTML = `<div class="news-list"><div class="news-header">Arch Linux News</div>${items}</div>`;
    packagesGrid.querySelectorAll('a[data-news-url]').forEach(a => {
        a.addEventListener('click', (e) => { e.preventDefault(); pyApiCall('open_url', a.dataset.newsUrl); });
    });
}

// Browse-by-category: a store-like discovery view. Top level shows category cards; clicking
// one lists that category's repo packages (reusing the normal package grid).
async function renderBrowse() {
    activeBrowseCategory = null;
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
    const cards = data.map(c => `
        <button class="browse-chip" data-cat-key="${escapeHtml(c.key)}" data-cat-label="${escapeHtml(c.label)}">
            <span class="browse-chip-icon">${escapeHtml(c.icon || '📦')}</span>
            <span class="browse-chip-text">
                <span class="browse-chip-label">${escapeHtml(c.label)}</span>
            </span>
        </button>`).join('');

    const hasSuggestions = Array.isArray(suggestions) && suggestions.length > 0;
    const suggestedSection = hasSuggestions
        ? `<div class="browse-header browse-header-spaced">Suggested for you</div><div class="browse-suggested" id="browse-suggested"></div>`
        : '';

    // AUR discovery buckets (community-maintained — compact chips, distinct from the big category
    // tiles and left-packed so a short list of buckets doesn't leave a half-empty grid row).
    const hasAur = Array.isArray(aurBuckets) && aurBuckets.length > 0;
    const aurCards = hasAur ? aurBuckets.map(b => `
        <button class="browse-chip browse-chip-aur" data-aur-key="${escapeHtml(b.key)}" data-aur-label="${escapeHtml(b.label)}">
            <span class="browse-chip-icon">${escapeHtml(b.icon || '📦')}</span>
            <span class="browse-chip-text">
                <span class="browse-chip-label">${escapeHtml(b.label)}</span>
                <span class="browse-chip-count">${escapeHtml(b.count)} package${b.count === 1 ? '' : 's'}</span>
            </span>
        </button>`).join('') : '';
    const aurSection = hasAur
        ? `<div class="browse-header browse-header-spaced">Discover on the AUR <span class="browse-header-note browse-header-note-aur">community-maintained</span></div><div class="browse-chip-row">${aurCards}</div>`
        : '';

    // Categories first (the primary purpose of Browse), then AUR discovery, then the suggested row.
    packagesGrid.innerHTML =
        `<div class="browse-view">` +
        `<div class="browse-header">Browse by category <span class="browse-header-note">official repos & Flatpak</span></div><div class="browse-chip-row">${cards}</div>` +
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
}

function browseCategoryHeader(category) {
    const header = document.createElement('div');
    header.className = 'browse-subheader';
    header.innerHTML = `<button class="browse-back" type="button">← Categories</button><span class="browse-cat-title">${escapeHtml(category.label)}</span>`;
    header.querySelector('.browse-back').addEventListener('click', renderBrowse);
    return header;
}

async function renderCategoryPackages(key, label, opts) {
    const api = (opts && opts.api) || 'get_category_packages';
    activeBrowseCategory = { key, label };
    applyTopbarContext();  // open category = package list → show the controls
    packagesGrid.style.display = 'block';
    packagesGrid.innerHTML = `<div class="state-container"><div class="spinner"></div><p>Loading ${escapeHtml(label)}…</p></div>`;

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

// Regenerate /etc/pacman.d/mirrorlist (reflector/rate-mirrors via the root broker). Shared by the
// .pacnew mirrorlist caution and the Settings → Mirrors button.
async function regenerateMirrors(btnEl) {
    if (btnEl) btnEl.classList.add('loading');
    showToast('Mirrors', 'Regenerating the mirror list — this can take up to a minute…', 'info');
    const r = await pyApiCall('regenerate_mirrorlist');  // null on error (toast already shown)
    if (btnEl) btnEl.classList.remove('loading');
    if (r && r.status === 'ok') {
        showToast('Mirrors', `Mirror list regenerated via ${r.tool || 'reflector'} — run a sync to refresh`, 'success');
    } else if (r && r.status === 'cancelled') {
        showToast('Mirrors', 'Mirror regeneration cancelled', 'info');
    }
}

// Notice on the Updates view: .pacnew/.pacsave config files pacman left for manual review.
async function renderUpdatesNotice() {
    const el = document.getElementById('updates-notice');
    if (!el) return;
    const res = await pyApiCall('get_pacnew_files');  // unwrapped {files, count} or null
    if (!res || !res.count) { el.innerHTML = ''; return; }
    const list = res.files.map(f => `<li><code>${escapeHtml(f)}</code></li>`).join('');
    // mirrorlist is the classic pacdiff footgun: overwriting it with the stock .pacnew wipes your
    // mirror servers. Call it out specifically so people don't blindly merge it.
    const hasMirrorlist = (res.files || []).some(f => f === '/etc/pacman.d/mirrorlist' || f.endsWith('/mirrorlist.pacnew'));
    const mirrorlistCaution = hasMirrorlist ? `
            <p class="config-notice-warn">⚠ <code>/etc/pacman.d/mirrorlist</code> is listed — <strong>do not overwrite it with pacdiff</strong>. The <code>.pacnew</code> is the stock all-commented list; merging it wipes your mirror servers. Instead, regenerate it (<code>reflector</code> / <code>rate-mirrors</code>) or just discard the <code>.pacnew</code>.</p>` : '';
    el.innerHTML = `
        <div class="config-notice">
            <div class="config-notice-title">⚠ ${escapeHtml(res.count)} configuration file${res.count > 1 ? 's' : ''} need review</div>
            <p class="config-notice-body">These <code>.pacnew</code>/<code>.pacsave</code> files were installed alongside updates and may need merging with your current config. Review them with <code>pacdiff</code> (from <code>pacman-contrib</code>), then remove the <code>.pacnew</code> file.</p>
            ${mirrorlistCaution}
            <ul class="config-notice-list">${list}</ul>
            <div class="config-notice-actions">
                <button class="btn btn-outline" id="pacnew-review-btn">Review config files</button>
                <button class="btn btn-outline" id="pacdiff-btn">Open pacdiff in a terminal</button>
                ${hasMirrorlist ? '<button class="btn btn-outline" id="regen-mirrors-btn">Regenerate mirror list</button>' : ''}
            </div>
        </div>`;
    const reviewBtn = document.getElementById('pacnew-review-btn');
    if (reviewBtn) reviewBtn.addEventListener('click', () => openPacnewCenter());
    const pacdiffBtn = document.getElementById('pacdiff-btn');
    if (pacdiffBtn) pacdiffBtn.addEventListener('click', async () => {
        const r = await pyApiCall('launch_pacdiff');  // null on error (toast already shown)
        if (r) showToast('pacdiff', 'Opened pacdiff in a terminal — merge the files there', 'info');
    });
    const regenBtn = document.getElementById('regen-mirrors-btn');
    if (regenBtn) regenBtn.addEventListener('click', () => regenerateMirrors(regenBtn));
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

    const mirror = arch.available ? (await pyApiCall('get_mirror_status') || {}) : {};
    if (epoch !== navEpoch) return;  // user navigated away during the mirror fetch
    const mirrorWhen = mirror.last_modified_iso ? new Date(mirror.last_modified_iso).toLocaleString() : null;
    const mirrorSummary = (mirror.count)
        ? `<div class="mirror-summary">
               <div class="mirror-stat"><strong>${escapeHtml(mirror.count)}</strong> active mirror${mirror.count === 1 ? '' : 's'}${mirrorWhen ? ` · updated ${escapeHtml(mirrorWhen)}` : ''}</div>
               ${(mirror.servers && mirror.servers.length) ? `<div class="mirror-hosts">${mirror.servers.map(h => `<span class="attn-chip">${escapeHtml(h)}</span>`).join('')}</div>` : ''}
           </div>`
        : '';
    const mirrorCmd = mirror.command ? `<p class="settings-help">Runs: <code>${escapeHtml(mirror.command)}</code></p>` : '';
    const mirrorsSection = arch.available ? `
        <section class="settings-section">
            <h3>Mirrors</h3>
            ${mirrorSummary}
            <p class="settings-help">Rebuild <code>/etc/pacman.d/mirrorlist</code> with the fastest mirrors${arch.mirror_tool ? ` (via <code>${escapeHtml(arch.mirror_tool)}</code>)` : ''}. Takes up to a minute. ${arch.mirror_tool ? '' : '<strong>Install <code>reflector</code> to enable this.</strong>'}</p>
            ${mirrorCmd}
            <div class="settings-actions">
                <button id="settings-regen-mirrors-btn" class="btn btn-outline" ${arch.mirror_tool ? '' : 'disabled'}>Regenerate mirror list</button>
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
    const regenMirrorsBtn = document.getElementById('settings-regen-mirrors-btn');
    if (regenMirrorsBtn) regenMirrorsBtn.addEventListener('click', async () => {
        await regenerateMirrors(regenMirrorsBtn);
        if (currentView === 'settings') renderSettings();  // refresh the mirror summary
    });
    // Density is a localStorage display pref — apply it instantly (no Save needed).
    const densitySel = document.getElementById('settings-density');
    if (densitySel) densitySel.addEventListener('change', () => setDensity(densitySel.value));
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

// Source-comparison panel: install from the chosen source (routes through the full preview).
document.getElementById('detail-source-compare').addEventListener('click', (e) => {
    const btn = e.target.closest('.srccmp-install');
    if (!btn) return;
    e.stopPropagation();
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }
    installApp(btn.dataset.id, btn);
});

// Initialization hook when pywebview is ready
window.addEventListener('pywebviewready', function() {
    console.log("pywebview is ready!");
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
    const updatesKey = getCacheKey('updates', 'all', '');
    const updatesP = (packageCache[updatesKey] !== undefined)
        ? Promise.resolve(packageCache[updatesKey])
        : pyApiCall('get_updates', 'all').then(u => { if (Array.isArray(u)) writeToCache(updatesKey, u); return u; });

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
        buildUpdateAllPreviewData,
        buildSourceCompareHTML,
        summarizeFailure,
        pickActivityText,
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
