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
const navItems = document.querySelectorAll('.nav-item');

const selectModeBtn = document.getElementById('select-mode-btn');
const batchBar = document.getElementById('batch-bar');
const batchCount = document.getElementById('batch-count');
const batchUninstallBtn = document.getElementById('batch-uninstall-btn');
const batchCancelBtn = document.getElementById('batch-cancel-btn');
const updateAllBtn = document.getElementById('update-all-btn');
const cleanupOrphansBtn = document.getElementById('cleanup-orphans-btn');

const detailModal = document.getElementById('detail-modal');
const modalClose = document.getElementById('modal-close');
const modalBackdrop = detailModal.querySelector('.modal-backdrop');

let currentPackages = [];
let diskPackages = [];
let currentView = 'dashboard'; // 'dashboard', 'installed', 'updates', 'activity'

let selectMode = false;
let selectedPackages = new Set();
let operationInProgress = false;

let packageCache = {};

function getCacheKey(view, type, query) {
    return `${view}\0${type}\0${query}`;
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

// Terminal Watcher Controls called from WebviewWatcher
window.terminalOpen = (title) => {
    const panel = document.getElementById('terminal-panel');
    const overlay = document.getElementById('terminal-overlay');
    const output = document.getElementById('terminal-output');
    const titleEl = document.getElementById('terminal-title');
    const statusEl = document.getElementById('terminal-status');
    const substatusEl = document.getElementById('terminal-substatus');
    const progressFill = document.getElementById('terminal-progress-fill');
    const doneMsg = document.getElementById('terminal-done-msg');

    operationInProgress = true;
    titleEl.textContent = title;
    statusEl.textContent = 'Initializing...';
    substatusEl.textContent = '';
    progressFill.style.width = '0%';
    output.innerHTML = '';
    doneMsg.className = 'hidden';
    doneMsg.textContent = '';

    panel.classList.remove('hidden');
    overlay.classList.remove('hidden');
    
    // Hide close button during run
    document.getElementById('terminal-close').style.display = 'none';
};

window.terminalAppend = (line) => {
    const output = document.getElementById('terminal-output');
    const lineEl = document.createElement('span');
    lineEl.className = 'line';
    lineEl.textContent = line;
    output.appendChild(lineEl);
    output.scrollTop = output.scrollHeight;
};

window.terminalSetStatus = (status) => {
    document.getElementById('terminal-status').textContent = status;
};

window.terminalSetSubstatus = (substatus) => {
    document.getElementById('terminal-substatus').textContent = substatus;
};

window.terminalSetProgress = (val) => {
    document.getElementById('terminal-progress-fill').style.width = `${val}%`;
};

window.terminalSetDone = (success) => {
    operationInProgress = false;
    packageCache = {}; // Invalidate cache on terminal operation completion
    const doneMsg = document.getElementById('terminal-done-msg');
    doneMsg.className = success ? 'terminal-done-success' : 'terminal-done-error';
    doneMsg.textContent = success ? '✓ Operation completed successfully.' : '✗ Operation failed.';
    
    document.getElementById('terminal-status').textContent = success ? 'Success' : 'Failed';
    
    // Show close button
    document.getElementById('terminal-close').style.display = 'block';
    
    // Reset any buttons loading spinner
    document.querySelectorAll('.btn.loading').forEach(b => b.classList.remove('loading'));
};

document.getElementById('terminal-close').addEventListener('click', () => {
    document.getElementById('terminal-panel').classList.add('hidden');
    document.getElementById('terminal-overlay').classList.add('hidden');
    fetchPackages(); // refresh packages list
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

// Render Package Cards
function renderPackages(packages) {
    packagesGrid.innerHTML = '';
    
    if (packages.length === 0) {
        emptyState.classList.remove('hidden');
        packagesGrid.style.display = 'none';
        return;
    }

    emptyState.classList.add('hidden');
    packagesGrid.style.display = 'grid';

    // Optimize: Use DocumentFragment to batch DOM insertions in a single reflow pass
    const fragment = document.createDocumentFragment();

    packages.forEach(pkg => {
        const card = document.createElement('div');
        card.className = `package-card ${selectMode ? 'select-mode' : ''} ${selectedPackages.has(pkg.id) ? 'selected' : ''}`;
        card.dataset.id = pkg.id;
        
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
        
        card.innerHTML = `
            <div class="package-header">
                <input type="checkbox" class="pkg-checkbox" ${isChecked} onclick="event.stopPropagation();">
                <img src="${getIconSrc(pkg.icon_url)}" data-src="${escapeHtml(getIconDataSrc(pkg.icon_url))}" class="package-icon" alt="${escapeHtml(pkg.name)} icon" loading="lazy" decoding="async">
                <div class="package-info">
                    <h3 class="package-title" title="${escapeHtml(pkg.name)}">${escapeHtml(pkg.name)}</h3>
                    <div class="package-publisher">
                        ${escapeHtml(pkg.publisher || 'Unknown Publisher')} • v${escapeHtml(pkg.version || 'Unknown')}
                    </div>
                </div>
            </div>
            <div class="package-description">
                ${escapeHtml(pkg.description || 'No description available for this package.')}
            </div>
            <div class="package-footer">
                <div class="package-tags">
                    <span class="tag ${escapeHtml(pkg.type.toLowerCase())}">${escapeHtml(pkg.type)}</span>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    ${pinButton}
                    ${actionButton}
                </div>
            </div>
        `;
        
        // Optimize: Clicks are now handled by single event delegation on packagesGrid
        fragment.appendChild(card);
    });

    packagesGrid.appendChild(fragment);
    deferredIconLoad();
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
                    // Stop observing once probed, regardless of success
                    img.removeAttribute('data-src');
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: '200px' }); // probe slightly before scrolling into view
    }

    const imgs = packagesGrid.querySelectorAll('img.package-icon[data-src]');
    imgs.forEach(img => {
        window.iconObserver.observe(img);
    });
}

// Package Detail Modal View
function openDetailModal(pkg) {
    const detailIcon = document.getElementById('detail-icon');
    detailIcon.src = getIconSrc(pkg.icon_url);
    const remoteUrl = getIconDataSrc(pkg.icon_url);
    if (remoteUrl) {
        const probe = new Image();
        probe.onload = () => { detailIcon.src = remoteUrl; };
        probe.src = remoteUrl;
    }
    document.getElementById('detail-icon').onerror = function() {
        this.onerror = null;
        this.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iIzY0NzQ4YiIgdmlld0JveD0iMCAwIDI0IDI0Ij48cmVjdCB4PSIzIiB5PSIzIiB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHJ4PSIyIiByeT0iMiI+PC9yZWN0Pjwvc3ZnPg==';
    };
    document.getElementById('detail-name').textContent = pkg.name;
    document.getElementById('detail-meta').textContent = `${pkg.type} • v${pkg.version || 'Unknown'}`;
    document.getElementById('detail-description').textContent = pkg.description || 'No description available for this package.';
    
    const table = document.getElementById('detail-table');
    table.innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-secondary);">Loading extended properties...</td></tr>`;
    
    detailModal.classList.remove('hidden');
    
    // Fetch key-value info from python
    pyApiCall('get_info', pkg.id).then(info => {
        table.innerHTML = '';
        if (info && Object.keys(info).length > 0) {
            Object.entries(info).forEach(([key, val]) => {
                const tr = document.createElement('tr');
                const tdKey = document.createElement('td');
                tdKey.textContent = key;
                const tdVal = document.createElement('td');
                if (typeof val === 'object' && val !== null) {
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
            actionBtn.textContent = 'Update';
            actionBtn.onclick = () => {
                detailModal.classList.add('hidden');
                updateApp(pkg.id);
            };
        } else {
            actionBtn = document.createElement('button');
            actionBtn.className = 'btn btn-danger';
            actionBtn.textContent = 'Uninstall';
            actionBtn.onclick = () => {
                detailModal.classList.add('hidden');
                uninstallApp(pkg.id);
            };
        }
    } else {
        actionBtn = document.createElement('button');
        actionBtn.className = 'btn btn-primary';
        actionBtn.textContent = 'Install';
        actionBtn.onclick = () => {
            detailModal.classList.add('hidden');
            installApp(pkg.id);
        };
    }
    
    footer.appendChild(closeBtn);
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
        batchCount.textContent = `${selectedPackages.size} selected`;
        batchBar.classList.remove('hidden');
    } else {
        batchBar.classList.add('hidden');
    }
}

batchUninstallBtn.addEventListener('click', async () => {
    if (selectedPackages.size === 0) return;
    const ids = Array.from(selectedPackages);
    toggleSelectMode(false);
    showToast('Batch Uninstalling', `Uninstalling ${ids.length} packages in batch...`, 'info');
    
    const result = await pyApiCall('batch_uninstall', ids);
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
    showToast('Updating All', 'Starting system packages upgrade...', 'info');
    const result = await pyApiCall('update_all');
    if (result && result.success) {
        showToast('Success', 'System upgrade finished', 'success');
    } else {
        showToast('Error', result ? result.error : 'Bulk upgrade failed', 'error');
    }
});

async function checkOrphans() {
    const orphans = await pyApiCall('get_orphans');
    if (orphans && orphans.length > 0) {
        cleanupOrphansBtn.classList.remove('hidden');
        cleanupOrphansBtn.innerHTML = `
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6l-1 14H6L5 6"></path>
                <path d="M10 11v6M14 11v6"></path>
            </svg>
            Cleanup ${escapeHtml(orphans.length)} Orphan${orphans.length > 1 ? 's' : ''}
        `;
        cleanupOrphansBtn.dataset.orphanIds = JSON.stringify(orphans.map(pkg => pkg.id));
    } else {
        cleanupOrphansBtn.classList.add('hidden');
    }
}

cleanupOrphansBtn.addEventListener('click', async () => {
    if (operationInProgress) { showToast('Busy', 'Another operation is already running', 'warning'); return; }
    const rawIds = cleanupOrphansBtn.dataset.orphanIds;
    if (!rawIds) return;
    const ids = JSON.parse(rawIds);
    if (!ids || ids.length === 0) return;
    
    showToast('Orphan Cleanup', "Removing " + ids.length + " orphaned package(s)...", 'info');
    
    const result = await pyApiCall('batch_uninstall', ids);
    if (result && result.success) {
        packageCache = {}; // Invalidate cache on orphan cleanup
        showToast('Success', 'Orphaned packages removed successfully', 'success');
        cleanupOrphansBtn.classList.add('hidden');
        fetchPackages();
    } else {
        showToast('Error', result ? result.error : 'Orphan cleanup failed', 'error');
    }
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
    packagesGrid.style.display = 'none';
    loadingState.classList.remove('hidden');
    emptyState.classList.add('hidden');

    const data = await pyApiCall('get_disk_usage');
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
}

// Render Chronological Activity Log
async function renderActivityFeed() {
    packagesGrid.innerHTML = '';
    packagesGrid.style.display = 'block'; // activity items stack vertically
    
    const activities = await pyApiCall('get_activity') || [];
    if (activities.length === 0) {
        packagesGrid.innerHTML = '<div style="padding: 32px; color: var(--text-secondary); text-align: center;">No activity recorded yet.</div>';
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
    
    packagesGrid.appendChild(feed);
}

// Data Fetching
async function fetchPackages() {
    packagesGrid.style.display = 'none';
    emptyState.classList.add('hidden');
    loadingState.classList.remove('hidden');
    updateAllBtn.classList.add('hidden'); // hidden by default
    cleanupOrphansBtn.classList.add('hidden'); // hidden by default

    // If batch mode was active, cancel it before view changes or search queries
    if (selectMode) {
        toggleSelectMode(false);
    }

    const query = searchInput.value.trim();
    const type = typeFilter.value;

    const cacheKey = getCacheKey(currentView, type, query);
    if (currentView !== 'activity' && currentView !== 'disk' && packageCache[cacheKey] !== undefined) {
        currentPackages = packageCache[cacheKey];
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        if (currentView === 'installed') {
            checkOrphans();
        }
        if (currentView === 'updates') {
            if (currentPackages.length > 0) {
                updateAllBtn.classList.remove('hidden');
            }
            if (!query) {
                document.getElementById('updates-badge').textContent = currentPackages.length;
            }
        }
        renderPackages(currentPackages);
        return;
    }

    let results = [];
    if (query) {
        results = await pyApiCall('search', query, type);
    } else {
        if (currentView === 'installed') {
            results = await pyApiCall('get_installed', type);
            checkOrphans();
        } else if (currentView === 'updates') {
            results = await pyApiCall('get_updates', type);
            if (results && results.length > 0) {
                updateAllBtn.classList.remove('hidden');
            }
        } else if (currentView === 'activity') {
            loadingState.classList.add('hidden');
            renderActivityFeed();
            return;
        } else if (currentView === 'disk') {
            renderDiskView();
            return;
        } else {
            results = await pyApiCall('get_suggestions', type);
        }
    }

    if (currentView !== 'activity' && currentView !== 'disk') {
        writeToCache(cacheKey, results || []);
    }

    loadingState.classList.add('hidden');
    currentPackages = results || [];
    renderPackages(currentPackages);
    
    // Update Badge if viewing updates
    if (currentView === 'updates' && !query) {
        document.getElementById('updates-badge').textContent = currentPackages.length;
    }
}

// Action Handlers
window.installApp = async (id, btn = null) => {
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Installing', 'Installation started in background', 'info');
    try {
        const result = await pyApiCall('install', id);
        if (result && result.success) {
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
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Uninstalling', 'Uninstallation started', 'info');
    try {
        const result = await pyApiCall('uninstall', id);
        if (result && result.success) {
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
    if (btn) btn.classList.add('loading');
    operationInProgress = true; // Synch lock
    showToast('Updating', 'Update started', 'info');
    try {
        const result = await pyApiCall('update', id);
        if (result && result.success) {
            showToast('Success', 'Application updated', 'success');
            packageCache = {}; // Wipe cache
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

// Event Listeners
let searchTimeout;
searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        fetchPackages();
    }, 400); // debounce
});

typeFilter.addEventListener('change', () => {
    fetchPackages();
});

// Export / Import Manifest listeners
document.getElementById('export-btn').addEventListener('click', async () => {
    showToast('Exporting', 'Writing manifest...', 'info');
    const result = await pyApiCall('export_packages');
    if (result) {
        showToast('Exported', `${result.count} packages saved to ${result.path}`, 'success');
    }
});

document.getElementById('import-btn').addEventListener('click', async () => {
    showToast('Importing', 'Reading ~/atlas-manifest.json and installing missing packages...', 'info');
    const result = await pyApiCall('import_packages');
    if (result) {
        packageCache = {}; // Invalidate cache on manifest import
        const installed = result.installed || 0;
        const skipped = result.skipped || 0;
        const failed = result.failed || [];
        showToast('Import Complete', "Installed: " + installed + " | Skipped (already present): " + skipped + " | Failed: " + failed.length, failed.length > 0 ? 'error' : 'success');
        fetchPackages();
    }
});

const refreshBtn = document.getElementById('refresh-btn');
if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
        if (operationInProgress) {
            showToast('Busy', 'Another operation is already running', 'warning');
            return;
        }
        packageCache = {}; // Wipe cache completely for a hard reload
        searchInput.value = ''; // Reset query
        fetchPackages();
    });
}

function activateView(viewName) {
    navItems.forEach(n => n.classList.remove('active'));
    const btn = document.querySelector(`.nav-item[data-view="${viewName}"]`);
    if (btn) {
        btn.classList.add('active');
    }
    
    currentView = viewName;
    searchInput.value = ''; // clear search on view change
    
    if (viewName === 'settings') {
        packagesGrid.innerHTML = '';
        emptyState.classList.add('hidden');
        loadingState.classList.add('hidden');
        packagesGrid.style.display = 'block';
        packagesGrid.innerHTML = '<div style="padding: 32px; color: var(--text-secondary);">Settings module not yet implemented in Web UI.</div>';
    } else {
        fetchPackages();
    }
}

navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const viewName = btn.getAttribute('data-view');
        activateView(viewName);
    });
});

const shortcutsHelpBtn = document.getElementById('shortcuts-help-btn');
if (shortcutsHelpBtn) {
    shortcutsHelpBtn.addEventListener('click', () => {
        showToast(
            'Keyboard Shortcuts',
            '/ Search  •  Esc Clear/Close  •  Ctrl+H Home  •  Ctrl+I Installed  •  Ctrl+U Updates  •  Ctrl+A Activity  •  Ctrl+D Disk  •  Ctrl+Shift+U Update All  •  Ctrl+E Export',
            'info'
        );
    });
}

// Event delegation for packagesGrid (disk rows, package cards, and action buttons)
packagesGrid.addEventListener('click', async (e) => {
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
            openDetailModal(pkg);
        }
    }
});

// Initialization hook when pywebview is ready
window.addEventListener('pywebviewready', function() {
    console.log("pywebview is ready!");
    fetchPackages();
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
            fetchPackages();
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
        const exportBtn = document.getElementById('export-btn');
        if (exportBtn) {
            exportBtn.click();
        }
        return;
    }
});
