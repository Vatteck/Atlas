const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

class ClassList {
  constructor(owner) {
    this.owner = owner;
    this.classes = new Set();
  }
  _sync() {
    this.owner.className = Array.from(this.classes).join(' ');
  }
  add(...names) {
    names.filter(Boolean).forEach(name => this.classes.add(name));
    this._sync();
  }
  remove(...names) {
    names.filter(Boolean).forEach(name => this.classes.delete(name));
    this._sync();
  }
  contains(name) {
    return this.classes.has(name);
  }
  toggle(name, force) {
    const shouldAdd = force === undefined ? !this.classes.has(name) : !!force;
    if (shouldAdd) this.classes.add(name);
    else this.classes.delete(name);
    this._sync();
    return shouldAdd;
  }
}

class FakeElement {
  constructor(tagName = 'div', id = '') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.parentElement = null;
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.eventListeners = {};
    this._selectorCache = new Map();
    this.className = '';
    this.classList = new ClassList(this);
    this._innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.checked = false;
    this.src = '';
    this.href = '';
    this.onerror = null;
    this.onclick = null;
    this.isContentEditable = false;
  }

  set innerHTML(value) {
    this._innerHTML = String(value || '');
    this.children = [];
    this._selectorCache.clear();
  }
  get innerHTML() {
    return this._innerHTML;
  }

  appendChild(child) {
    if (!child) return child;
    if (child.isFragment) {
      const fragmentChildren = child.children.slice();
      fragmentChildren.forEach(grandchild => this.appendChild(grandchild));
      child.children = [];
      return child;
    }
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  insertBefore(child, before) {
    if (!child) return child;
    if (child.isFragment) {
      child.children.slice().forEach(grandchild => this.insertBefore(grandchild, before));
      child.children = [];
      return child;
    }
    child.parentElement = this;
    const idx = this.children.indexOf(before);
    if (idx === -1) this.children.unshift(child);
    else this.children.splice(idx, 0, child);
    return child;
  }

  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    this.parentElement = null;
  }

  addEventListener(type, cb) {
    if (!this.eventListeners[type]) this.eventListeners[type] = [];
    this.eventListeners[type].push(cb);
  }

  dispatchEvent(event) {
    event = event || {};
    event.target = event.target || this;
    event.currentTarget = this;
    if (!event.preventDefault) event.preventDefault = () => {};
    if (!event.stopPropagation) event.stopPropagation = () => {};
    for (const cb of this.eventListeners[event.type] || []) cb(event);
    const handler = this[`on${event.type}`];
    if (typeof handler === 'function') handler(event);
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name.startsWith('data-')) {
      this.dataset[dataAttrToProp(name.slice(5))] = String(value);
    }
  }
  getAttribute(name) {
    if (name.startsWith('data-')) {
      const value = this.dataset[dataAttrToProp(name.slice(5))];
      return value === undefined ? null : value;
    }
    return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
    if (name.startsWith('data-')) delete this.dataset[dataAttrToProp(name.slice(5))];
  }

  focus() {}
  select() {}

  closest(selector) {
    if (matchesSelector(this, selector)) return this;
    return this.parentElement ? this.parentElement.closest(selector) : null;
  }

  querySelector(selector) {
    const found = findFirst(this.children, selector);
    if (found) return found;
    if (!this._selectorCache.has(selector)) {
      const el = new FakeElement(selector.startsWith('button') || selector.includes('button') ? 'button' : 'div');
      if (selector.startsWith('#')) el.id = selector.slice(1);
      if (selector.startsWith('.')) el.classList.add(selector.slice(1));
      this._selectorCache.set(selector, el);
    }
    return this._selectorCache.get(selector);
  }

  querySelectorAll(selector) {
    const results = [];
    collectMatches(this.children, selector, results);
    return results;
  }
}

function dataAttrToProp(attr) {
  return attr.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
}

function matchesSelector(el, selector) {
  if (!el || !selector) return false;
  if (selector.startsWith('#')) return el.id === selector.slice(1);
  if (selector.startsWith('.')) return (el.className || '').split(/\s+/).includes(selector.slice(1));
  const classMatch = selector.match(/^\.([\w-]+)/);
  if (classMatch) return (el.className || '').split(/\s+/).includes(classMatch[1]);
  const tagClass = selector.match(/^([a-zA-Z0-9-]+)\.([\w-]+)/);
  if (tagClass) {
    return el.tagName.toLowerCase() === tagClass[1].toLowerCase()
      && (el.className || '').split(/\s+/).includes(tagClass[2]);
  }
  return el.tagName.toLowerCase() === selector.toLowerCase();
}

function findFirst(children, selector) {
  for (const child of children) {
    if (matchesSelector(child, selector)) return child;
    const nested = findFirst(child.children || [], selector);
    if (nested) return nested;
  }
  return null;
}

function collectMatches(children, selector, results) {
  for (const child of children) {
    if (matchesSelector(child, selector)) results.push(child);
    collectMatches(child.children || [], selector, results);
  }
}

class FakeDocument {
  constructor() {
    this.elements = new Map();
    this.eventListeners = {};
    this.documentElement = this.getElementById('documentElement');
    this.activeElement = null;
    this.navItems = ['dashboard', 'browse', 'installed', 'updates', 'news', 'disk', 'activity', 'permissions', 'settings']
      .map(view => {
        const btn = new FakeElement('button');
        btn.classList.add('nav-item');
        btn.dataset.view = view;
        btn.setAttribute('data-view', view);
        return btn;
      });
    this.viewToggleButtons = ['grid', 'list'].map(mode => {
      const btn = new FakeElement('button');
      btn.classList.add('view-toggle-btn');
      btn.dataset.viewMode = mode;
      btn.setAttribute('data-view-mode', mode);
      return btn;
    });
  }

  getElementById(id) {
    if (!this.elements.has(id)) this.elements.set(id, new FakeElement('div', id));
    return this.elements.get(id);
  }

  createElement(tag) {
    return new FakeElement(tag);
  }

  createDocumentFragment() {
    const frag = new FakeElement('fragment');
    frag.isFragment = true;
    return frag;
  }

  querySelector(selector) {
    if (selector.startsWith('.nav-item')) {
      const viewMatch = selector.match(/data-view="([^"]+)"/);
      if (viewMatch) return this.navItems.find(btn => btn.dataset.view === viewMatch[1]) || null;
      return this.navItems[0] || null;
    }
    if (selector === '#info-popup .modal-backdrop') return this.getElementById('info-popup-backdrop');
    if (selector.startsWith('#')) return this.getElementById(selector.slice(1));
    return new FakeElement('div');
  }

  querySelectorAll(selector) {
    if (selector === '.nav-item') return this.navItems;
    if (selector === '.view-toggle-btn') return this.viewToggleButtons;
    if (selector === '.package-card') return this.getElementById('packages-grid').children.filter(el => (el.className || '').includes('package-card'));
    return [];
  }

  addEventListener(type, cb) {
    if (!this.eventListeners[type]) this.eventListeners[type] = [];
    this.eventListeners[type].push(cb);
  }
}

function controlledPromise() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function flushPromises() {
  return new Promise(resolve => setImmediate(resolve));
}

function makePkg(id, name, type = 'arch_repo', overrides = {}) {
  return Object.assign({
    id,
    name,
    type,
    publisher: 'Publisher',
    version: '1.0',
    description: `${name} description`,
    installed: false,
    update_available: false,
    icon_url: '',
    has_screenshots: false,
    has_history: false,
  }, overrides);
}

function loadMainJs(apiOverrides = {}) {
  const document = new FakeDocument();
  const packagesGrid = document.getElementById('packages-grid');
  packagesGrid.classList.add('packages-grid');
  document.getElementById('empty-state').querySelector('h2');
  document.getElementById('empty-state').querySelector('p');
  document.getElementById('detail-modal').querySelector('.modal-backdrop');

  const defaultApi = {
    get_category_packages: async () => [],
    get_categories: async () => [],
    get_orphan_count: async () => ({ count: 0 }),
    get_suggestions: async () => [],
    search: async () => [],
    get_installed: async () => [],
    get_updates: async () => [],
    get_info: async () => ({}),
    get_flatpak_meta: async () => ({}),
    get_aur_meta: async () => ({}),
    get_screenshots: async () => [],
    get_history: async () => ({ history: [] }),
    get_package_activity: async () => [],
    get_dependency_summary: async () => ({}),
    get_pkg_icon: async () => '',
    open_url: async () => ({ status: 'ok' }),
  };
  const api = Object.assign(defaultApi, apiOverrides);

  const window = {
    __ATLAS_TEST__: true,
    pywebview: { api },
    localStorage: {
      _data: {},
      setItem(k, v) { this._data[k] = String(v); },
      getItem(k) { return Object.prototype.hasOwnProperty.call(this._data, k) ? this._data[k] : null; },
      removeItem(k) { delete this._data[k]; },
      clear() { this._data = {}; },
    },
    addEventListener() {},
    console,
  };

  function FakeImage() {
    this.onload = null;
    this.onerror = null;
    this._src = '';
  }
  Object.defineProperty(FakeImage.prototype, 'src', {
    set(value) {
      this._src = value;
      if (typeof this.onload === 'function') this.onload();
    },
    get() { return this._src; },
  });

  class FakeIntersectionObserver {
    constructor() {}
    observe() {}
    unobserve() {}
  }

  const context = {
    window,
    document,
    localStorage: window.localStorage,
    console,
    Image: FakeImage,
    IntersectionObserver: FakeIntersectionObserver,
    CSS: { escape: value => String(value).replace(/"/g, '\\"') },
    setTimeout: () => 0,
    clearTimeout: () => {},
    setImmediate,
    URL,
  };
  context.global = context;
  context.window.window = window;
  context.window.document = document;
  context.window.Image = FakeImage;
  context.window.IntersectionObserver = FakeIntersectionObserver;

  const source = fs.readFileSync(path.join(process.cwd(), 'atlas/view/webview/main.js'), 'utf8');
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'main.js' });
  if (!context.window.__atlasTestHooks) {
    throw new Error('main.js must expose window.__atlasTestHooks when window.__ATLAS_TEST__ is true');
  }
  return { context, window, document, hooks: context.window.__atlasTestHooks };
}

function renderedCardIds(document) {
  return document.getElementById('packages-grid').children
    .filter(el => (el.className || '').includes('package-card'))
    .map(el => el.dataset.id);
}

async function testRenderCategoryPackagesStoresCurrentPackages() {
  const alpha = makePkg('alpha', 'Alpha');
  const zed = makePkg('zed', 'Zed');
  const { document, hooks } = loadMainJs({
    get_category_packages: async () => [zed, alpha],
  });

  await hooks.renderCategoryPackages('utilities', 'Utilities');

  assert.deepStrictEqual(hooks.getState().currentPackages.map(pkg => pkg.id), ['zed', 'alpha']);
  assert.deepStrictEqual(renderedCardIds(document), ['zed', 'alpha']);
}

async function testSortDropdownRerendersOpenBrowseCategory() {
  const alpha = makePkg('alpha', 'Alpha');
  const zed = makePkg('zed', 'Zed');
  const { document, hooks } = loadMainJs({
    get_category_packages: async () => [zed, alpha],
  });

  hooks.setCurrentView('browse');
  await hooks.renderCategoryPackages('utilities', 'Utilities');
  assert.deepStrictEqual(renderedCardIds(document), ['zed', 'alpha']);

  const sortFilter = document.getElementById('sort-filter');
  sortFilter.value = 'name';
  sortFilter.dispatchEvent({ type: 'change' });

  assert.deepStrictEqual(renderedCardIds(document), ['alpha', 'zed']);
}

async function testStaleDetailMetaDoesNotOverwriteNewModal() {
  const staleMeta = controlledPromise();
  const stalePkg = makePkg('flatpak:stale', 'Stale', 'flatpak');
  const freshPkg = makePkg('arch:fresh', 'Fresh', 'arch_repo', { version: '2.0' });
  const { document, hooks } = loadMainJs({
    get_flatpak_meta: () => staleMeta.promise,
    get_info: async () => ({}),
  });

  hooks.openDetailModal(stalePkg);
  hooks.openDetailModal(freshPkg);
  staleMeta.resolve({ developer_name: 'Stale Developer', verified: true, is_free: true, permissions: [] });
  await flushPromises();

  assert.strictEqual(document.getElementById('detail-name').textContent, 'Fresh');
  assert.ok(!document.getElementById('detail-meta').innerHTML.includes('Stale Developer'));
  assert.ok(document.getElementById('detail-meta').innerHTML.includes('2.0'));
}

async function testTopLevelBrowseFetchRendersCategories() {
  // Browse must render the category landing (not fall through to the dashboard). It now also
  // seeds a "Suggested for you" row, so get_suggestions IS expected to be called here.
  let categoryCalls = 0;
  let suggestionCalls = 0;
  const { document, hooks } = loadMainJs({
    get_categories: async () => {
      categoryCalls += 1;
      return [{ key: 'utilities', label: 'Utilities', icon: '🛠️', count: 2 }];
    },
    get_suggestions: async () => {
      suggestionCalls += 1;
      return [makePkg('suggestion', 'Suggestion')];
    },
  });

  hooks.setCurrentView('browse');
  hooks.setSearchQuery('');
  await hooks.fetchPackages();
  await flushPromises();

  assert.strictEqual(categoryCalls, 1);
  assert.strictEqual(suggestionCalls, 1);  // suggestions now seed the Browse landing
  assert.ok(document.getElementById('packages-grid').innerHTML.includes('Browse by category'));
}

async function testStaleFetchDoesNotOverwriteNewerResults() {
  const slowSearch = controlledPromise();
  const installedPkg = makePkg('home', 'Home');
  const stalePkg = makePkg('stale', 'Stale');
  // Tested on the Installed view (the dashboard no longer renders a package grid).
  const { document, hooks } = loadMainJs({
    search: () => slowSearch.promise,
    get_installed: async () => [installedPkg],
  });
  hooks.setCurrentView('installed');

  hooks.setSearchQuery('stale');
  const staleFetch = hooks.fetchPackages();
  hooks.setSearchQuery('');
  await hooks.fetchPackages();
  assert.deepStrictEqual(renderedCardIds(document), ['home']);

  slowSearch.resolve([stalePkg]);
  await staleFetch;
  await flushPromises();

  assert.deepStrictEqual(hooks.getState().currentPackages.map(pkg => pkg.id), ['home']);
  assert.deepStrictEqual(renderedCardIds(document), ['home']);
}

async function testDashboardShowsAttentionCenterNotPackages() {
  const suggestion = makePkg('sugg', 'Suggested');
  const { document, hooks } = loadMainJs({
    get_dashboard_summary: async () => ({}),
    get_updates: async () => [],
    get_suggestions: async () => [suggestion],  // must NOT appear on the dashboard
  });
  hooks.setCurrentView('dashboard');
  hooks.setSearchQuery('');
  await hooks.fetchPackages();
  await flushPromises();

  // no package cards on the dashboard; the attention center is populated instead
  assert.deepStrictEqual(renderedCardIds(document), []);
  assert.ok(document.getElementById('attention-center').innerHTML.includes('attention-grid'));
}

async function testBrowseRendersSuggestedRowAboveCategories() {
  const suggestion = makePkg('sugg', 'Suggested');
  const { document, hooks } = loadMainJs({
    get_categories: async () => [{ key: 'games', label: 'Games', icon: '🎮', count: 3 }],
    get_suggestions: async () => [suggestion],
  });

  hooks.setCurrentView('browse');  // renderBrowse now guards on the active view
  await hooks.renderBrowse();
  await flushPromises();

  const grid = document.getElementById('packages-grid');
  assert.ok(grid.innerHTML.includes('Suggested for you'), 'suggested header present');
  assert.ok(grid.innerHTML.includes('browse-suggested'), 'suggested row present');
  assert.ok(grid.innerHTML.includes('data-cat-key'), 'categories still present');
  // the suggestion is rendered as a real package card backed by currentGroups
  assert.strictEqual(hooks.getState().currentPackages.map(p => p.id).join(','), 'sugg');
}

async function testAttentionCenterBuildsCardsAndTones() {
  const { hooks } = loadMainJs({});
  const summary = {
    safety: { pacnew_count: 2, db_sync_age_hours: 5, pacman_locked: false, news_count: 1 },
    reclaim: { orphans: 3, cache_human: '1.2 GB', flatpak_available: true },
    aur: { chroot_enabled: true, chroot_available: true },
    activity: [{ action: 'install', pkg_name: 'gimp', success: true }],
  };
  const updates = [{ type: 'arch_repo' }, { type: 'aur' }, { type: 'arch_repo' }];
  const html = hooks.buildAttentionCenterHTML(summary, updates);

  // five cards, updates first, with the right hero/chips/lines and tones
  assert.ok(html.includes('attention-grid'));
  assert.ok(html.includes('attention-hero">3</div>'), 'updates hero count');
  assert.ok(html.includes('updates available'), 'updates subtitle');
  assert.ok(html.includes('2 Arch') && html.includes('1 AUR'), 'type split chips');
  assert.ok(html.includes('2 .pacnew files to review'), 'pacnew line');
  assert.ok(html.includes('1.2 GB'), 'cache size hero');
  assert.ok(html.includes('Installed <strong>gimp</strong>'), 'activity');
  assert.ok(html.includes('tone-warn'), 'a warn-tone card exists');
}

async function testAttentionUpdatesCardStates() {
  const { hooks } = loadMainJs({});
  assert.ok(hooks.buildUpdatesCardHTML(undefined).includes('Checking'), 'loading');
  assert.ok(hooks.buildUpdatesCardHTML('error').includes('Couldn'), 'error → couldn’t check');
  assert.ok(hooks.buildUpdatesCardHTML([]).includes('up to date'), 'empty → up to date');
}

async function testAttentionCenterAndBadgeShareUpdatesFetch() {
  const updates = controlledPromise();
  let updateCalls = 0;
  const { context, document, hooks } = loadMainJs({
    get_dashboard_summary: async () => ({ user: 'Cory' }),
    get_updates: () => {
      updateCalls += 1;
      return updates.promise;
    },
  });

  hooks.setCurrentView('dashboard');
  const renderPromise = hooks.renderAttentionCenter();
  await flushPromises();  // dashboard summary resolved; updates fetch is still in flight
  const badgePromise = context.refreshUpdatesBadge();
  await flushPromises();

  assert.strictEqual(updateCalls, 1, 'dashboard and sidebar badge reuse one in-flight get_updates call');

  updates.resolve([{ type: 'arch_repo' }]);
  await renderPromise;
  await badgePromise;

  assert.strictEqual(document.getElementById('updates-badge').textContent, '1', 'badge updated from shared result');
  const attentionHtml = document.getElementById('attention-center').innerHTML;
  assert.ok(attentionHtml.includes('attention-hero">1</div>'), 'dashboard updated from shared result');
}

async function testUpdatesViewSharesInFlightBadgeFetch() {
  const updates = controlledPromise();
  let updateCalls = 0;
  const pkg = makePkg('arch_repo:vim', 'Vim', 'arch_repo');
  const { context, document, hooks } = loadMainJs({
    get_updates: () => {
      updateCalls += 1;
      return updates.promise;
    },
  });

  const badgePromise = context.refreshUpdatesBadge();
  await flushPromises();
  hooks.setCurrentView('updates');
  const fetchPromise = hooks.fetchPackages();
  await flushPromises();

  assert.strictEqual(updateCalls, 1, 'Updates view reuses the in-flight badge get_updates call');

  updates.resolve([pkg]);
  await badgePromise;
  await fetchPromise;

  assert.strictEqual(document.getElementById('updates-badge').textContent, '1', 'badge updated from shared fetch');
  assert.deepStrictEqual(hooks.getState().currentPackages.map(p => p.id), ['arch_repo:vim'], 'Updates view consumed shared result');
}

async function testExternalUrlHelpersRejectUnsafeValues() {
  const opened = [];
  const { context, hooks } = loadMainJs({
    open_url: async url => { opened.push(url); return { status: 'ok' }; },
  });

  assert.strictEqual(hooks.safeExternalUrl('https://example.invalid/path?q=1'), 'https://example.invalid/path?q=1', 'valid https allowed');
  assert.strictEqual(hooks.safeExternalUrl('HTTP://example.invalid/path'), 'HTTP://example.invalid/path', 'valid http is scheme-case tolerant');
  for (const bad of [
    'javascript:alert(1)',
    'file:///etc/passwd',
    'ftp://example.invalid/file.tar.gz',
    'git+https://example.invalid/repo.git',
    'https://',
    'https://example.invalid/\nfile:///etc/passwd',
    'https://exa mple.invalid/path',
    '',
    null,
  ]) {
    assert.strictEqual(hooks.safeExternalUrl(bad), '', `${bad} rejected`);
  }

  await context.openExternalUrl('javascript:alert(1)');
  assert.deepStrictEqual(opened, [], 'unsafe URL never reaches backend bridge');
  await context.openExternalUrl('https://example.invalid/ok');
  assert.deepStrictEqual(opened, ['https://example.invalid/ok'], 'safe URL reaches backend bridge');
}

async function testDashboardHeaderGreetingAndMessage() {
  const { hooks } = loadMainJs({});
  // greeting tracks the hour
  assert.strictEqual(hooks.dashboardGreeting(8), 'Good morning');
  assert.strictEqual(hooks.dashboardGreeting(14), 'Good afternoon');
  assert.strictEqual(hooks.dashboardGreeting(22), 'Good evening');
  assert.strictEqual(hooks.dashboardGreeting(3), 'Good evening');

  // actionable count mirrors the warn cards (updates / safety issues / orphans)
  const summary = {
    safety: { pacnew_count: 1, news_count: 2, pacman_locked: false },  // 1 area
    reclaim: { orphans: 3 },                                            // 1 area
  };
  assert.strictEqual(hooks.countActionable(summary, [{ type: 'arch_repo' }]), 3);  // + updates
  assert.strictEqual(hooks.countActionable({ safety: {}, reclaim: { orphans: 0 } }, []), 0);

  assert.ok(hooks.dashboardMessage(0).includes('caught up'));
  assert.strictEqual(hooks.dashboardMessage(1), '1 thing needs your attention.');
  assert.strictEqual(hooks.dashboardMessage(3), '3 things need your attention.');

  // header: personal greeting + tone-colored status line
  const warnHtml = hooks.buildDashboardHeaderHTML('Good evening', 'Vatteck', '3 things need your attention.', 'warn');
  assert.ok(warnHtml.includes('Good evening, Vatteck'), 'personal greeting');
  assert.ok(warnHtml.includes('3 things need your attention.'));
  assert.ok(warnHtml.includes('tone-warn'), 'warn tone');

  const okHtml = hooks.buildDashboardHeaderHTML('Good morning', '', 'All caught up.', 'ok');
  assert.ok(okHtml.includes('tone-ok') && okHtml.includes('dash-check'), 'ok tone + check');
  assert.ok(!okHtml.includes(', '), 'no trailing comma when name is empty');
}

async function testCommandPaletteFilterAndAvailability() {
  const { document, hooks } = loadMainJs({});
  const all = hooks.buildCommandList();
  assert.ok(all.length >= 9, 'has navigation + actions');

  // filter by label
  assert.ok(hooks.filterCommands(all, 'settings').some(c => c.id === 'nav:settings'));
  // filter by keyword (the mirrors command carries the "reflector" keyword)
  assert.ok(hooks.filterCommands(all, 'reflector').some(c => c.id === 'act:mirrors'));
  // fuzzy (non-contiguous subsequence): "instl" → Installed
  assert.ok(hooks.filterCommands(all, 'instl').some(c => c.id === 'nav:installed'));
  // best match ranks first: "dash" should put Dashboard at the top
  assert.strictEqual(hooks.filterCommands(all, 'dash')[0].id, 'nav:dashboard');
  // empty query returns all (registry order); no match returns none
  assert.strictEqual(hooks.filterCommands(all, '').length, all.length);
  assert.strictEqual(hooks.filterCommands(all, 'zzznomatch').length, 0);

  // availability gating: hide the Update-all button → the command drops out
  assert.ok(all.some(c => c.id === 'act:update-all'), 'present when button visible');
  document.getElementById('update-all-btn').classList.add('hidden');
  assert.ok(!hooks.buildCommandList().some(c => c.id === 'act:update-all'), 'dropped when button hidden');
}

async function testDensityClass() {
  const { hooks } = loadMainJs({});
  assert.strictEqual(hooks.densityClass('compact'), 'density-compact');
  assert.strictEqual(hooks.densityClass('dense'), 'density-dense');
  assert.strictEqual(hooks.densityClass('comfortable'), 'density-comfortable');
  assert.strictEqual(hooks.densityClass('bogus'), 'density-comfortable');  // junk → default
  assert.strictEqual(hooks.densityClass(null), 'density-comfortable');
}

async function testTopbarContextDecision() {
  const { hooks } = loadMainJs({});
  const f = hooks.shouldShowPackageControls;
  // package-list views → show
  assert.ok(f('installed', false, false));
  assert.ok(f('updates', false, false));
  // any view with an active search → show
  assert.ok(f('dashboard', true, false));
  assert.ok(f('news', true, false));
  // browse: landing → hide, open category → show
  assert.ok(!f('browse', false, false));
  assert.ok(f('browse', false, true));
  // utility / dashboard with no search → hide
  assert.ok(!f('dashboard', false, false));
  assert.ok(!f('settings', false, false));
  assert.ok(!f('disk', false, false));
}

async function testEmptyStateHTML() {
  const { hooks } = loadMainJs({});
  const withAction = hooks.emptyStateHTML({
    icon: '🔒', title: 'No installed Flatpaks', hint: 'Install one first.',
    actionLabel: 'Browse apps', actionView: 'browse' });
  assert.ok(withAction.includes('No installed Flatpaks') && withAction.includes('Install one first.'));
  assert.ok(withAction.includes('data-empty-view="browse"') && withAction.includes('Browse apps'));
  // no action button unless both label + view are given
  const noAction = hooks.emptyStateHTML({ title: 'No recent Arch news' });
  assert.ok(!noAction.includes('empty-state-action'));
}

async function testSystemHealthChecks() {
  const { hooks } = loadMainJs({});
  const byId = (checks) => Object.fromEntries(checks.map(c => [c.id, c]));

  // healthy-ish system
  let c = byId(hooks.systemHealthChecks({
    db_sync: { age_hours: 3 }, mirrors: { tool: 'reflector' }, lock: { locked: false },
    pacnew: { count: 0 }, orphans: { count: 0 }, cache: { human: '1 GB' },
    flatpak: { unused_available: false }, chroot: { available: true, enabled: true },
  }));
  assert.strictEqual(c.db.tone, 'ok');                 // <24h
  assert.strictEqual(c.mirrors.actionId, 'mirrors');
  assert.strictEqual(c.lock.tone, 'ok');
  assert.strictEqual(c.orphans.tone, 'ok');
  assert.ok(!c.flatpak, 'no flatpak card when nothing unused');

  // problems present
  c = byId(hooks.systemHealthChecks({
    db_sync: { age_hours: 200 }, mirrors: { tool: null }, lock: { locked: true },
    pacnew: { count: 3 }, orphans: { count: 5 }, cache: { human: '9 GB' },
    flatpak: { unused_available: true }, chroot: { available: false },
  }));
  assert.strictEqual(c.db.tone, 'danger');             // >7d
  assert.strictEqual(c.lock.tone, 'danger');
  assert.strictEqual(c.lock.actionId, 'remove-lock', 'locked → gated remove action');
  assert.ok(c.lock.more, 'lock card has a details disclosure');
  assert.strictEqual(c.pacnew.tone, 'warn');
  assert.strictEqual(c.pacnew.actionId, 'pacnew-center');
  assert.strictEqual(c.orphans.tone, 'warn');
  assert.strictEqual(c.orphans.actionId, 'orphans');
  assert.strictEqual(c.flatpak.actionId, 'flatpak');

  // keyring freshness: stale (>90d) warns, fresh is ok; both carry the refresh command in `more`
  let k = byId(hooks.systemHealthChecks({ keyring: { age_days: 120 } }));
  assert.strictEqual(k.keyring.tone, 'warn');
  assert.ok(/pacman-key/.test(k.keyring.more), 'keyring details show the refresh command');
  k = byId(hooks.systemHealthChecks({ keyring: { age_days: 5 } }));
  assert.strictEqual(k.keyring.tone, 'ok');
  // no keyring signal → no card
  assert.ok(!byId(hooks.systemHealthChecks({ keyring: { age_days: null } })).keyring, 'no keyring card without data');

  // AUR index: old (>14d) → info + refresh action; absent → no card
  let a = byId(hooks.systemHealthChecks({ aur_index: { age_days: 30 } }));
  assert.strictEqual(a['aur-index'].actionId, 'aur-index');
  assert.strictEqual(a['aur-index'].tone, 'info');
  assert.ok(!byId(hooks.systemHealthChecks({ aur_index: { age_days: null } }))['aur-index'], 'no aur-index card without data');

  // fail-open: null fields → info "couldn't check", page still has cards
  c = byId(hooks.systemHealthChecks({ db_sync: { age_hours: null }, pacnew: { count: null },
                                      orphans: { count: null } }));
  assert.strictEqual(c.db.tone, 'info');
  assert.strictEqual(c.pacnew.tone, 'info');
  assert.strictEqual(c.orphans.tone, 'info');
}

async function testPacnewRisk() {
  const { hooks } = loadMainJs({});
  assert.strictEqual(hooks.pacnewRisk('/etc/pacman.d/mirrorlist.pacnew').level, 'danger');
  assert.strictEqual(hooks.pacnewRisk('/etc/pacman.conf.pacnew').level, 'warn');
  assert.strictEqual(hooks.pacnewRisk('/etc/sudoers.d/wheel.pacnew').level, 'warn');
  assert.strictEqual(hooks.pacnewRisk('/etc/foobar.conf.pacnew').level, 'info');
  assert.strictEqual(hooks.pacnewRisk('/etc/default/grub.pacsave').level, 'info');
  // mirrorlist note steers away from overwriting
  assert.ok(/regenerate/i.test(hooks.pacnewRisk('/etc/pacman.d/mirrorlist.pacnew').note));
}

async function testStaleUtilityRenderDoesNotClobber() {
  // Regression: open Permissions (slow load), switch to Settings before it resolves — the late
  // Permissions result must not overwrite the Settings page.
  const slowInstalled = controlledPromise();
  const { document, hooks } = loadMainJs({
    get_installed: () => slowInstalled.promise,
    get_app_settings: async () => ({ types: [], flatpak_available: false, general: {},
                                     tray: {}, arch: { available: false } }),
  });

  hooks.activateView('permissions');   // starts awaiting get_installed
  hooks.activateView('settings');      // switch before it resolves
  await flushPromises();
  slowInstalled.resolve([]);           // Permissions load finishes late
  await flushPromises();

  const html = document.getElementById('packages-grid').innerHTML;
  assert.ok(html.includes('settings-page'), 'Settings stays rendered');
  assert.ok(!html.includes('No installed Flatpaks'), 'stale Permissions render did not clobber');
}

async function testRefreshCurrentViewRespectsUtilityViews() {
  // Regression: after an operation on a utility view (e.g. orphan cleanup on Health), refreshing
  // must re-render that view, not fall through to app suggestions.
  let suggestionsCalled = false, healthCalled = false;
  const { hooks } = loadMainJs({
    get_system_health: async () => { healthCalled = true; return {}; },
    get_suggestions: async () => { suggestionsCalled = true; return []; },
  });
  hooks.setCurrentView('health');
  hooks.refreshCurrentView();
  await flushPromises();
  assert.ok(healthCalled, 'refresh re-renders System Health');
  assert.ok(!suggestionsCalled, 'refresh does not show suggestions on the Health view');
}

async function testAttentionCenterFailsOpenOnNullSummary() {
  const { hooks } = loadMainJs({});
  const html = hooks.buildAttentionCenterHTML(null, 'error');
  // null summary still renders all five cards, degraded to "couldn’t check"
  const cardCount = (html.match(/attention-card/g) || []).length;
  assert.strictEqual(cardCount, 5);
  assert.ok(html.includes('Couldn'), 'degrades to couldn’t check');
}

async function testTransactionPreviewRendersAllSections() {
  const { hooks } = loadMainJs({});
  const html = hooks.buildTransactionPreviewHTML({
    name: 'gimp', source: 'flatpak', source_label: 'Flatpak', version: '2.10.36',
    sizes: { download: 1000000, installed: 5000000 },
    deps: { direct: ['glib2', 'gtk3'], optional: [{ name: 'python', detail: 'scripting' }] },
    permissions: [{ title: 'Home folder', detail: 'read/write', level: 'danger' }],
    warnings: [
      { level: 'info', title: 'Proprietary', detail: 'non-free license' },
      { level: 'danger', title: 'Potentially unsafe permissions', detail: 'broad access' },
    ],
    notes: ['Permissions can be adjusted later.'],
  });
  assert.ok(html.includes('txp-title">gimp<'), 'name');
  assert.ok(html.includes('Flatpak') && html.includes('v2.10.36'), 'source + version');
  assert.ok(html.includes('1 MB') && html.includes('5 MB'), 'human sizes');
  assert.ok(html.includes('glib2') && html.includes('gtk3'), 'direct deps');
  assert.ok(html.includes('python') && html.includes('scripting'), 'optional dep + detail');
  assert.ok(html.includes('Dependencies (2 required, 1 optional)'), 'dep accordion summary');
  assert.ok(html.includes('Permissions (1)'), 'perms accordion');
  assert.ok(html.includes('txp-perm-danger'), 'perm level class');
  assert.ok(html.includes('Permissions can be adjusted later.'), 'note');
  // danger warning sorts above info
  assert.ok(html.indexOf('Potentially unsafe') < html.indexOf('Proprietary'), 'danger sorts first');
}

async function testTransactionPreviewHandlesMissingFields() {
  const { hooks } = loadMainJs({});
  // AUR-style payload: no sizes, no perms, no optional deps
  const html = hooks.buildTransactionPreviewHTML({
    name: 'yay', source_label: 'AUR', version: '12.0',
    sizes: null, deps: { direct: ['go'], optional: [] }, permissions: null,
    warnings: [], notes: ['Built from source.'],
  });
  assert.ok(html.includes('yay'), 'name');
  assert.ok(!html.includes('txp-sizes'), 'no size row when sizes null');
  assert.ok(!html.includes('Permissions ('), 'no perms accordion');
  assert.ok(html.includes('Dependencies (1 required)'), 'no optional count when empty');
  // empty object must not throw
  assert.doesNotThrow(() => hooks.buildTransactionPreviewHTML({}));
  assert.doesNotThrow(() => hooks.buildTransactionPreviewHTML(null));
}

async function testTransactionPreviewEscapesNames() {
  const { hooks } = loadMainJs({});
  const html = hooks.buildTransactionPreviewHTML({ name: '<img src=x>', deps: { direct: [], optional: [] } });
  assert.ok(!html.includes('<img src=x>'), 'name is escaped');
  assert.ok(html.includes('&lt;img'), 'escaped form present');
}

async function testShowInstallPreviewOpensModalThroughEnvelope() {
  // Regression: pyApiCall unwraps {status,data}, so showInstallPreview must treat the result as the
  // payload itself (not check .status) — otherwise the gate silently skips. (Bug found in GUI test.)
  const { document, hooks } = loadMainJs({
    get_install_preview: async () => ({ status: 'ok', data: { name: 'vim', source_label: 'Arch', deps: { direct: [], optional: [] } } }),
  });
  const pending = hooks.showInstallPreview('arch_repo:vim');
  await flushPromises();
  const modal = document.getElementById('tx-preview-modal');
  assert.ok(!modal.classList.contains('hidden'), 'preview modal is shown');
  assert.ok(document.getElementById('tx-preview-body').innerHTML.includes('vim'), 'payload rendered');
  hooks.resolveTxPreview(false);
  assert.strictEqual(await pending, false, 'cancel resolves false');
  assert.ok(modal.classList.contains('hidden'), 'modal hidden after resolve');
}

async function testShowInstallPreviewProceedsWhenBridgeReturnsNothing() {
  // Bridge error / not-injected → pyApiCall returns null → never block the user (proceed).
  const { hooks } = loadMainJs({ get_install_preview: async () => ({ status: 'error', message: 'x' }) });
  assert.strictEqual(await hooks.showInstallPreview('x:y'), true, 'proceeds on backend error');
}

async function testTransactionPreviewActionLabelsSizeRow() {
  const { hooks } = loadMainJs({});
  const install = hooks.buildTransactionPreviewHTML({ action: 'install', name: 'vim', sizes: { download: null, installed: 5000000 }, deps: { direct: [], optional: [] } });
  assert.ok(install.includes('Installed'), 'install shows Installed size');
  const uninstall = hooks.buildTransactionPreviewHTML({ action: 'uninstall', name: 'vim', sizes: { download: null, installed: 5000000 }, deps: { direct: [], optional: [] } });
  assert.ok(uninstall.includes('Frees'), 'uninstall shows Frees size');
  assert.ok(!uninstall.includes('>Installed<'), 'uninstall does not label it Installed');
}

async function testTransactionPreviewUpdateShowsVersionDelta() {
  const { hooks } = loadMainJs({});
  const html = hooks.buildTransactionPreviewHTML({ action: 'update', name: 'vim', from_version: '9.0', version: '9.1', deps: { direct: [], optional: [] } });
  assert.ok(html.includes('v9.0 → v9.1'), 'update shows from → to version');
  // install with no from_version is unchanged (single version)
  const inst = hooks.buildTransactionPreviewHTML({ action: 'install', name: 'vim', version: '9.1', deps: { direct: [], optional: [] } });
  assert.ok(inst.includes('v9.1') && !inst.includes('→'), 'install shows single version');
}

async function testBuildUpdateAllPreviewData() {
  const { hooks } = loadMainJs({});
  const updates = [
    { type: 'arch_repo', download_size: 1000 },
    { type: 'flatpak', download_size: 2000 },
    { type: 'aur' },  // no download size (built from source)
  ];
  const data = hooks.buildUpdateAllPreviewData(updates, { news_count: 2, pacnew_count: 1 });
  assert.strictEqual(data.action, 'update-all');
  assert.strictEqual(data.name, '3 packages');
  assert.strictEqual(data.sizes.download, 3000);
  assert.strictEqual(data.sizes.installed, null);
  assert.ok(data.notes.some(n => n.includes('Arch: 1') && n.includes('AUR: 1') && n.includes('Flatpak: 1')), 'source split note');
  const titles = data.warnings.map(w => w.title);
  assert.ok(titles.some(t => t.includes('2 unread Arch news')), 'news warning');
  assert.ok(titles.some(t => t.includes('1 config file')), 'pacnew warning');
  // no sizes at all → sizes null; empty list → "0 packages"
  const empty = hooks.buildUpdateAllPreviewData([], {});
  assert.strictEqual(empty.sizes, null);
  assert.strictEqual(empty.name, '0 packages');

  // AUR reputation tiers (single batched call): breakdown note always shown when tiers present,
  // a named warning only when at least one package is 'risk' tier.
  const aurUpdates = [
    { id: 'aur:safe-pkg', type: 'aur', name: 'safe-pkg' },
    { id: 'aur:risky-pkg', type: 'aur', name: 'risky-pkg' },
  ];
  const tiered = hooks.buildUpdateAllPreviewData(aurUpdates, {
    tiers: { tiers: { 'aur:safe-pkg': { tier: 'safe', score: 90 }, 'aur:risky-pkg': { tier: 'risk', score: 10 } },
             counts: { safe: 1, caution: 0, risk: 1 } },
  });
  assert.ok(tiered.notes.some(n => n.includes('1 safe to update') && n.includes('1 high risk')), 'tier breakdown note');
  assert.ok(tiered.warnings.some(w => w.title.includes('1 package') && w.detail.includes('risky-pkg')), 'risky package named in warnings');

  // no risk-tier packages → breakdown note shown, no extra warning
  const allSafe = hooks.buildUpdateAllPreviewData(aurUpdates, {
    tiers: { tiers: { 'aur:safe-pkg': { tier: 'safe', score: 90 }, 'aur:risky-pkg': { tier: 'safe', score: 80 } },
             counts: { safe: 2, caution: 0, risk: 0 } },
  });
  assert.ok(allSafe.notes.some(n => n.includes('2 safe to update')), 'all-safe breakdown note');
  assert.ok(!allSafe.warnings.some(w => w.title.includes('low reputation')), 'no risk warning when nothing is risky');
}

async function testBuildSourceCompareHTML() {
  const { hooks } = loadMainJs({});
  // single source → no panel
  assert.strictEqual(hooks.buildSourceCompareHTML({ sources: [{ id: 'a', type: 'arch_repo', version: '1.0' }] }), '');
  assert.strictEqual(hooks.buildSourceCompareHTML(null), '');
  // multi-source → a row per source, install button only for non-installed
  const group = { name: 'steam', sources: [
    { id: 'arch_repo:steam', type: 'arch_repo', version: '1.0', size: 1000, installed: true },
    { id: 'flatpak:com.valvesoftware.Steam', type: 'flatpak', version: '1.1', download_size: 2000, installed: false },
  ]};
  const html = hooks.buildSourceCompareHTML(group);
  assert.ok(html.includes('Available from 2 sources'), 'header');
  assert.ok(html.includes('✓ Installed'), 'installed source marked');
  assert.ok(html.includes('class="btn btn-primary srccmp-install" data-id="flatpak:com.valvesoftware.Steam"'), 'install button targets the non-installed source');
  assert.ok(!html.includes('data-id="arch_repo:steam"'), 'no install button for the installed source');
  assert.ok(html.includes('Official Arch repository') && html.includes('Sandboxed'), 'per-source notes');
}

async function testSummarizeFailureCategories() {
  const { hooks } = loadMainJs({});
  const cases = [
    ['sudo: incorrect password attempt', 'Authentication failed'],
    ['error: key "ABC" could not be looked up remotely', 'PGP signature / keyring problem'],
    ['error: failed retrieving file \'core.db\' from mirror : The requested URL returned error: 404', 'Download failed'],
    ['error: could not resolve host: mirror.example.org', 'Download failed'],
    ['error: failed to commit transaction (conflicting files)\nfoo: /usr/bin/x exists in filesystem', 'File conflict'],
    ['error: unable to satisfy dependency \'libfoo\' required by bar', 'Dependency problem'],
    ['==> ERROR: A failure occurred in build().', 'Build failed'],
    ['some unrecognized output that still failed', 'The operation failed'],
  ];
  for (const [log, title] of cases) {
    const r = hooks.summarizeFailure(log);
    assert.ok(r && r.title === title, `"${log.slice(0, 30)}…" → ${title}, got ${r && r.title}`);
    assert.ok(r.hint && r.hint.length, 'has a hint');
  }
  assert.strictEqual(hooks.summarizeFailure(''), null, 'empty log → null');
  assert.strictEqual(hooks.summarizeFailure('   '), null, 'whitespace log → null');
}

async function testPickActivityText() {
  const { hooks } = loadMainJs({});
  // substatus wins when present
  assert.strictEqual(hooks.pickActivityText({ substatus: 'Installing pulseaudio', status: 'Upgrading', lastLine: 'foo' }), 'Installing pulseaudio');
  // falls back to status when substatus is blank (gems sometimes clear substatus)
  assert.strictEqual(hooks.pickActivityText({ substatus: '   ', status: 'Upgrading', lastLine: 'foo' }), 'Upgrading');
  // falls back to the last log line when both are blank (e.g. Flatpak: blank substatus, print only)
  assert.strictEqual(hooks.pickActivityText({ substatus: '', status: '', lastLine: 'Uninstall complete.' }), 'Uninstall complete.');
  // never empty
  assert.strictEqual(hooks.pickActivityText({}), 'Working…');
  assert.strictEqual(hooks.pickActivityText(), 'Working…');
}

async function testWhySourceHint() {
  const { hooks } = loadMainJs({});
  const { whySourceHint } = hooks;
  assert.strictEqual(whySourceHint('arch_repo').level, 'safe', 'repo is safe-toned');
  assert.ok(whySourceHint('arch_repo').text.includes('official Arch'), 'repo text');
  assert.strictEqual(whySourceHint('aur').level, 'warn', 'AUR is warn-toned');
  assert.ok(whySourceHint('aur').text.includes('PKGBUILD'), 'AUR mentions PKGBUILD review');
  // flatpak refines with verified/license
  assert.strictEqual(whySourceHint('flatpak', { verified: true }).level, 'safe', 'verified flatpak safe');
  assert.ok(whySourceHint('flatpak', { verified: true }).text.includes('Verified'), 'verified text');
  assert.ok(whySourceHint('flatpak', { verified: false }).text.includes('Community-packaged'), 'unverified text');
  assert.ok(whySourceHint('flatpak', { free_license: false }).text.includes('Proprietary'), 'proprietary appended');
  assert.strictEqual(whySourceHint('mystery').text, '', 'unknown type → no hint');
}

async function testBuildDependencySummaryHTML() {
  const { hooks } = loadMainJs({});
  const { buildDependencySummaryHTML, buildDepNodesHTML } = hooks;
  // empty + no note → nothing
  assert.strictEqual(buildDependencySummaryHTML({ direct: [], optional: [], required_by: [], note: '' }), '', 'empty → no HTML');
  // a flatpak-style note alone still renders
  assert.ok(buildDependencySummaryHTML({ note: 'bundled in a runtime' }).includes('bundled in a runtime'), 'note-only renders');
  const html = buildDependencySummaryHTML({
    direct: ['glibc', 'gpm'],
    optional: [{ name: 'python', detail: 'scripting' }],
    required_by: ['neovim'],
    note: 'Direct requirements.',
  });
  assert.ok(html.includes('>2<') && html.includes('Requires'), 'requires count + label');
  assert.ok(html.includes('Optional') && html.includes('python'), 'optional chip');
  assert.ok(html.includes('Required by') && html.includes('neovim'), 'required-by chip');
  assert.ok(html.includes('title="scripting"'), 'optdep detail in title');
  // requires renders as drill-down tree nodes (not flat chips)
  assert.ok(html.includes('class="dep-node" data-dep="glibc"'), 'requires are tree nodes');
  // missing groups are omitted (no "Required by" when empty)
  const partial = buildDependencySummaryHTML({ direct: ['glibc'], optional: [], required_by: [] });
  assert.ok(partial.includes('Requires') && !partial.includes('Required by'), 'empty groups omitted');

  // new relationship groups: build / provides / conflicts / replaces
  const rich = buildDependencySummaryHTML({
    direct: [], makedepends: ['gcc'], checkdepends: ['perl'],
    provides: ['aur-helper'], conflicts: ['paru'], replaces: ['yay-git'],
  });
  assert.ok(rich.includes('Build') && rich.includes('gcc') && rich.includes('perl'), 'build group (make+check)');
  assert.ok(rich.includes('Provides') && rich.includes('aur-helper'), 'provides group');
  assert.ok(rich.includes('Conflicts') && rich.includes('paru'), 'conflicts group');
  assert.ok(rich.includes('Replaces') && rich.includes('yay-git'), 'replaces group');

  // dep nodes: data-dep strips version constraints to the bare name
  const nodes = buildDepNodesHTML(['glibc>=2.38', 'gpm']);
  assert.ok(nodes.includes('data-dep="glibc"'), 'version constraint stripped for resolution');
  assert.ok(nodes.includes('glibc&gt;=2.38'), 'full constraint shown as label (escaped)');
  assert.strictEqual(buildDepNodesHTML([]), '', 'no names → empty');

  // "why is this installed?" reason line
  assert.ok(buildDependencySummaryHTML({ install_reason: 'explicit' }).includes('installed this explicitly'), 'explicit reason');
  const orphan = buildDependencySummaryHTML({ install_reason: 'dependency', orphan: true });
  assert.ok(orphan.includes('orphan'), 'orphan reason');
  assert.ok(buildDependencySummaryHTML({ install_reason: 'dependency', orphan: false }).includes('dependency of other packages'), 'plain dependency reason (no roots)');
  // dependency attributed to the explicit package(s) that pulled it in
  const attributed = buildDependencySummaryHTML({ install_reason: 'dependency', orphan: false, installed_because: ['gimp'] });
  assert.ok(attributed.includes('dependency of') && attributed.includes('gimp') && !attributed.includes('other packages'), 'names the explicit root');
  const manyRoots = buildDependencySummaryHTML({ install_reason: 'dependency', orphan: false, installed_because: ['a', 'b', 'c', 'd', 'e'] });
  assert.ok(manyRoots.includes('+1 more'), 'caps the root list with +N more');
  // demoted-from-orphan: names what it's an optional dependency of
  const optFor = buildDependencySummaryHTML({ install_reason: 'dependency', orphan: false, optional_for: ['ark', 'yazi'] });
  assert.ok(optFor.includes('optional dependency of') && optFor.includes('ark') && optFor.includes('yazi'), 'names optional-for packages');
  // hard-dep roots take precedence over optional_for
  const both = buildDependencySummaryHTML({ install_reason: 'dependency', orphan: false, installed_because: ['app'], optional_for: ['x'] });
  assert.ok(both.includes('dependency of <strong>app') && !both.includes('optional dependency'), 'hard roots win over optional_for');
  // orphan takes precedence over roots; explicit unaffected
  assert.ok(buildDependencySummaryHTML({ install_reason: 'dependency', orphan: true, installed_because: ['x'] }).includes('orphan'), 'orphan wins over roots');
  // reason alone (no deps) still renders
  assert.notStrictEqual(buildDependencySummaryHTML({ install_reason: 'explicit' }), '', 'reason-only renders');
}

async function testPackageActivitySectionClearsForNonInstalledPackages() {
  const { document, hooks } = loadMainJs({
    get_package_activity: async () => ([
      { action: 'install', pkg_type: 'arch_repo', success: true, timestamp: '2026-06-16T00:00:00' },
    ]),
  });
  const section = document.getElementById('detail-activity-section');
  const body = document.getElementById('detail-activity');

  hooks.openDetailModal(makePkg('arch:installed', 'Installed', 'arch_repo', { installed: true }));
  await flushPromises();
  assert.ok(!section.classList.contains('hidden'), 'installed package with activity shows package history');
  assert.ok(body.innerHTML.includes('INSTALL'), 'activity body populated');

  hooks.openDetailModal(makePkg('arch:new', 'New', 'arch_repo', { installed: false }));
  assert.ok(section.classList.contains('hidden'), 'non-installed package clears stale package history');
  assert.strictEqual(body.innerHTML, '', 'non-installed package clears stale package history body');
}

async function testBuildPackageActivityHTML() {
  const { hooks } = loadMainJs({});
  const { buildPackageActivityHTML } = hooks;
  assert.strictEqual(buildPackageActivityHTML([]), '', 'empty package activity hidden');
  const html = buildPackageActivityHTML([
    { action: 'install', pkg_type: 'arch_repo', success: true, timestamp: '2026-06-16T00:00:00' },
    { action: 'update', pkg_type: '<img>', success: false, error: '<boom>', timestamp: '2026-06-16T01:00:00' },
  ]);
  assert.ok(html.includes('INSTALL') && html.includes('UPDATE'), 'renders actions');
  assert.ok(html.includes('Open full Activity history'), 'renders activity jump');
  assert.ok(!html.includes('<img>') && html.includes('&lt;img&gt;'), 'escapes source type');
  assert.ok(html.includes('&lt;boom&gt;'), 'escapes errors');
}

async function testBuildAurCommentsHTML() {
  const { hooks } = loadMainJs({});
  const { buildAurCommentsHTML, linkifyComment, formatCommentBodyHTML } = hooks;

  assert.strictEqual(buildAurCommentsHTML([]), '', 'no comments → empty (section hidden)');
  assert.strictEqual(buildAurCommentsHTML(null), '', 'null → empty');

  const html = buildAurCommentsHTML([
    { author: 'alice', date: '2024-03-01T00:00:00Z', body: 'see https://wiki.archlinux.org/x for help' },
    { author: '<script>', date: '', body: 'line1\nline2 <b>bold</b>' },
  ]);
  assert.ok(html.includes('alice'), 'renders author');
  assert.ok(html.includes('aur-comment-avatar'), 'renders an author avatar');
  assert.ok(html.includes('>A<'), 'avatar shows the author initial');
  assert.ok(html.includes('<a href="#" data-url="https://wiki.archlinux.org/x"'), 'linkifies safe URL');
  // untrusted author/body are escaped, never injected as live HTML
  assert.ok(!html.includes('<script>') && html.includes('&lt;script&gt;'), 'escapes author');
  assert.ok(!html.includes('<b>bold</b>') && html.includes('&lt;b&gt;bold'), 'escapes body HTML');
  assert.ok(html.includes('line1<br>line2'), 'newlines become <br>');

  // linkify refuses non-http(s) schemes
  assert.ok(!linkifyComment('javascript:alert(1)').includes('<a '), 'no link for javascript: scheme');

  // formatCommentBodyHTML: shell-prompt blocks (incl. backslash continuations) become code blocks
  const cmd = formatCommentBodyHTML(
    'To get the version:\n$ curl -sSf https://example.com/x | \\\ngrep Version | \\\nawk \'{print $2}\'\nDone.');
  assert.ok(cmd.includes('<pre class="aur-comment-code">'), 'shell prompt → code block');
  assert.ok(cmd.includes('grep Version') && cmd.includes('awk'), 'continuation lines stay in the block');
  assert.ok(cmd.includes('<p class="aur-comment-text">To get the version:</p>'), 'prose before the block');
  assert.ok(cmd.includes('<p class="aur-comment-text">Done.</p>'), 'prose after the block');
  // code is escaped, not linkified into live HTML
  assert.ok(cmd.includes('https://example.com/x') && !cmd.split('<pre')[1].includes('<a '),
    'URLs inside a code block are not turned into anchors');
  // plain prose stays a single paragraph with <br>
  const plain = formatCommentBodyHTML('one\ntwo');
  assert.ok(plain.includes('<p class="aur-comment-text">one<br>two</p>'), 'plain prose → one paragraph');
  assert.ok(!plain.includes('<pre'), 'no code block for plain prose');
}

async function testBuildInstalledFilesHTML() {
  const { hooks } = loadMainJs({});
  const { buildInstalledFilesHTML } = hooks;

  assert.strictEqual(buildInstalledFilesHTML([]), '', 'no files → empty (section hidden)');
  assert.strictEqual(buildInstalledFilesHTML(null), '', 'null → empty');

  const html = buildInstalledFilesHTML(['/usr/bin/foo', '/usr/share/foo/<x>.png']);
  assert.ok(html.includes('2 files'), 'header shows the count');
  assert.ok(html.includes('if-filter'), 'renders a filter input');
  assert.ok(html.includes('/usr/bin/foo'), 'renders a file row');
  assert.ok(!html.includes('<x>') && html.includes('&lt;x&gt;'), 'escapes file paths');

  assert.ok(buildInstalledFilesHTML(['/only/one']).includes('1 file<'), 'singular "file" for one entry');

  // huge list is capped with a note (DOM-size guard)
  const many = Array.from({ length: 2500 }, (_, i) => `/f/${i}`);
  const big = buildInstalledFilesHTML(many);
  assert.ok(big.includes('2,500 files'), 'count reflects the full list');
  assert.ok(big.includes('Showing the first 2,000'), 'caps rendered rows with a note');
  assert.ok((big.match(/if-row/g) || []).length === 2000, 'renders exactly the cap of rows');
}

function testComputeDetailTabs() {
  const { hooks } = loadMainJs({});
  const { computeDetailTabs } = hooks;

  // overview + details always show; empty deps/history hidden
  // (join to strings — hooks return VM-realm arrays, which deepStrictEqual rejects on prototype)
  let r = computeDetailTabs({}, 'overview');
  assert.strictEqual(r.visible.join(','), 'overview,details', 'only always-on tabs by default');
  assert.strictEqual(r.active, 'overview', 'overview stays active');

  // content present → tabs appear
  r = computeDetailTabs({ deps: true, history: true }, 'overview');
  assert.strictEqual(r.visible.join(','), 'overview,details,deps,history', 'all tabs when content present');

  // active tab that becomes hidden falls back to the first visible tab
  r = computeDetailTabs({ deps: false }, 'deps');
  assert.strictEqual(r.active, 'overview', 'hidden active tab falls back');

  // a still-visible active tab is preserved
  r = computeDetailTabs({ history: true }, 'history');
  assert.strictEqual(r.active, 'history', 'visible active tab preserved');
  assert.ok(!r.visible.includes('deps'), 'deps hidden when it has no content');
}

function testReputationPopupHtml() {
  const { hooks } = loadMainJs({});
  const { reputationPopupHtml } = hooks;

  const html = reputationPopupHtml({
    score: 85, tier: 'trusted',
    breakdown: [
      { key: 'votes', label: 'Community votes', value: '500', points: 30, max: 30 },
      { key: 'age', label: 'Package age', value: '3.0 yr', points: 25, max: 25 },
      { key: 'popularity', label: 'Popularity', value: '<x>', points: 5, max: 10 },
    ],
  });
  assert.ok(html.includes('85/100') && /Trusted/.test(html), 'shows score + tier');
  assert.ok(html.includes('Community votes') && html.includes('500'), 'renders a breakdown row with its value');
  assert.ok(html.includes('30/30') && html.includes('5/10'), 'shows each signal\'s points/max');
  assert.ok(html.includes('width:50%'), 'bar fill reflects points/max ratio');
  assert.ok(html.includes('not a safety check'), 'keeps the disclaimer');
  assert.ok(!html.includes('<x>') && html.includes('&lt;x&gt;'), 'escapes untrusted values');

  // resilient to missing data
  assert.ok(reputationPopupHtml({}).includes('?/100'), 'no score → ?/100, no crash');
  assert.ok(reputationPopupHtml(null).includes('not a safety check'), 'null risk → still renders');
}

function testRerankByFuzzy() {
  const { hooks } = loadMainJs({});
  const { rerankByFuzzy } = hooks;
  // join to a string — hooks return VM-realm arrays, which deepStrictEqual rejects on prototype
  const ids = (list) => list.map(p => p.id).join(',');

  // the closest name match floats to the top, even if the backend returned it last
  const results = [
    { id: 'a', name: 'libwidget-extras' },
    { id: 'b', name: 'something-unrelated' },
    { id: 'c', name: 'widget' },
  ];
  const out = rerankByFuzzy(results, 'widget');
  assert.strictEqual(out[0].id, 'c', 'exact name match ranks first');
  assert.strictEqual(out.length, 3, 'no result dropped');
  assert.strictEqual(ids(out).split(',').sort().join(','), 'a,b,c', 'same ids, just reordered');

  // stable: non-matching items keep their original backend order (below matches)
  const r2 = rerankByFuzzy([
    { id: 'x', name: 'zzz' }, { id: 'y', name: 'yyy' }, { id: 'm', name: 'gimp' },
  ], 'gimp');
  assert.strictEqual(ids(r2), 'm,x,y', 'match first, non-matches keep backend order');

  // empty query / tiny lists / bad input pass through unchanged
  assert.strictEqual(ids(rerankByFuzzy(results, '')), 'a,b,c', 'empty query → unchanged');
  assert.strictEqual(rerankByFuzzy(null, 'x').length, 0, 'null → []');
  assert.strictEqual(ids(rerankByFuzzy([{ id: 'solo', name: 'solo' }], 'x')), 'solo', '<2 → unchanged');
}

function testFilterLocalPackages() {
  const { hooks } = loadMainJs({});
  const { filterLocalPackages } = hooks;
  const ids = (list) => list.map(p => p.id).join(',');

  const list = [
    { id: 'ff', name: 'firefox', description: 'web browser' },
    { id: 'gimp', name: 'gimp', description: 'image editor' },
    { id: 'tb', name: 'thunderbird', description: 'mail client' },
  ];

  // exact substring on name
  assert.strictEqual(ids(filterLocalPackages(list, 'fire')), 'ff', 'name substring matches');
  // exact substring on description (no name hit)
  assert.strictEqual(ids(filterLocalPackages(list, 'mail')), 'tb', 'description substring matches');
  // empty query → full list unchanged
  assert.strictEqual(ids(filterLocalPackages(list, '')), 'ff,gimp,tb', 'empty query → full list');

  // fuzzy fallback only when there is NO exact hit: "frfx" isn't a substring of any, but is a
  // subsequence of firefox → found via fallback
  assert.strictEqual(ids(filterLocalPackages(list, 'frfx')), 'ff', 'fuzzy fallback finds subsequence match');

  // a real exact hit must NOT be replaced by fuzzy noise
  assert.strictEqual(ids(filterLocalPackages(list, 'gimp')), 'gimp', 'exact hit wins, no fuzzy noise');

  // short queries (<3) never trigger fuzzy → no match when not an exact substring
  assert.strictEqual(filterLocalPackages(list, 'zx').length, 0, 'short non-matching query → []');
  // a nonsense long query below threshold → []
  assert.strictEqual(filterLocalPackages(list, 'qqqqq').length, 0, 'no match → []');
  // bad input
  assert.strictEqual(filterLocalPackages(null, 'x').length, 0, 'null list → []');
}

function testInstallQueueHelpers() {
  const { hooks } = loadMainJs({});
  const { pkgSnapshot, queueUpsert, buildQueueReviewHTML } = hooks;

  // snapshot keeps only the minimal fields, normalizes type
  const snap = pkgSnapshot({ id: 'vlc', name: 'VLC', type: 'arch_repo', version: '3.0', extra: 'drop me' });
  assert.strictEqual(snap.id, 'vlc');
  assert.strictEqual(snap.extra, undefined, 'extra fields dropped');
  assert.strictEqual(snap.name, 'VLC');

  // upsert is pure (new array), de-dupes by id, ignores bad input
  let q = queueUpsert([], { id: 'a', name: 'A', type: 'aur' });
  q = queueUpsert(q, { id: 'b', name: 'B', type: 'aur' });
  q = queueUpsert(q, { id: 'a', name: 'A again', type: 'aur' });   // dupe ignored
  assert.strictEqual(q.map(x => x.id).join(','), 'a,b', 'dedupes by id');
  assert.strictEqual(queueUpsert(q, null).length, 2, 'null pkg ignored');
  assert.strictEqual(queueUpsert(q, { name: 'no id' }).length, 2, 'pkg without id ignored');
  const orig = [{ id: 'x', name: 'X', type: 'aur' }];
  queueUpsert(orig, { id: 'y', name: 'Y', type: 'aur' });
  assert.strictEqual(orig.length, 1, 'input array not mutated');

  // review HTML: a row per item, escaped; empty-state message when empty
  assert.ok(buildQueueReviewHTML([]).includes('empty'), 'empty queue → message');
  const html = buildQueueReviewHTML([
    { id: 'a', name: '<b>A</b>', type: 'aur', version: '1.0' },
    { id: 'b', name: 'B', type: 'flatpak', version: '' },
  ]);
  assert.ok(html.includes('data-queue-remove="a"') && html.includes('data-queue-remove="b"'), 'remove buttons per row');
  assert.ok(!html.includes('<b>A</b>') && html.includes('&lt;b&gt;A'), 'escapes names');
  assert.ok(html.includes('v1.0') && !html.includes('v•'), 'shows version, omits when blank');
}

async function testBrowseLandingBuilders() {
  const { hooks } = loadMainJs({});
  const { buildCategoryCardHTML, buildResumeBrowseHTML } = hooks;

  // category card: icon + label + description, escaped, no count
  const card = buildCategoryCardHTML({ key: 'games', label: 'Games', icon: '🎮',
    description: 'Games & <emulators>', count: 99 });
  assert.ok(card.includes('data-cat-key="games"') && card.includes('data-cat-label="Games"'), 'card carries key+label');
  assert.ok(card.includes('🎮') && card.includes('Games'), 'icon + label shown');
  assert.ok(card.includes('Games &amp; &lt;emulators&gt;'), 'description shown + escaped');
  assert.ok(!card.includes('99'), 'no misleading count on category cards');
  // missing icon falls back; no description → no desc span
  const bare = buildCategoryCardHTML({ key: 'x', label: 'X' });
  assert.ok(bare.includes('📦'), 'icon fallback');
  assert.ok(!bare.includes('browse-chip-desc'), 'no desc span when absent');

  // resume chip: present when a last category is stored, '' otherwise
  assert.strictEqual(buildResumeBrowseHTML(null), '', 'no last → no chip');
  assert.strictEqual(buildResumeBrowseHTML({ key: 'x' }), '', 'incomplete last → no chip');
  const resume = buildResumeBrowseHTML({ key: 'games', label: 'Games' });
  assert.ok(resume.includes('browse-resume-btn') && resume.includes('Games'), 'resume chip shows the label');
}

async function testBuildMirrorOptionsHTML() {
  const { hooks } = loadMainJs({});
  const { buildMirrorOptionsHTML } = hooks;

  // reflector payload → country select (Auto + list, current selected), sort select, protocol boxes
  const mirror = {
    options: { country: 'DE', protocols: ['https', 'rsync'], sort: 'age', latest: 20 },
    countries: [{ code: 'US', name: 'United States' }, { code: 'DE', name: 'Germany' }],
    protocols: ['https', 'http', 'rsync'],
    sorts: ['rate', 'age', 'score'],
  };
  const html = buildMirrorOptionsHTML(mirror);
  assert.ok(html.includes('id="mirror-country"'), 'country select rendered');
  assert.ok(html.includes('Auto (all countries)'), 'Auto option present');
  assert.ok(html.includes('value="DE" selected'), 'current country selected');
  assert.ok(html.includes('id="mirror-sort"'), 'sort select rendered');
  assert.ok(html.includes('value="age" selected'), 'current sort selected');
  // protocol checkboxes: current ones checked, others not
  assert.ok(html.includes('data-mirror-proto="https"') && html.includes('data-mirror-proto="rsync"'), 'protocol boxes rendered');
  const httpBox = html.match(/data-mirror-proto="http"[^>]*/)[0];
  assert.ok(!httpBox.includes('checked'), 'unselected protocol not checked');
  const httpsBox = html.match(/data-mirror-proto="https"[^>]*/)[0];
  assert.ok(httpsBox.includes('checked'), 'selected protocol checked');

  // rate-mirrors / no tool: no options → empty string (plain button kept)
  assert.strictEqual(buildMirrorOptionsHTML({ command: 'rate-mirrors ...' }), '', 'no options → empty');
  assert.strictEqual(buildMirrorOptionsHTML(null), '', 'null mirror → empty');
}

async function testPkgbuildViewerBuilders() {
  const { hooks } = loadMainJs({});
  const { highlightBashLine, buildPkgbuildRiskHTML, buildPkgbuildMetaHTML,
          buildPkgbuildFindingsHTML, findingProvenanceHTML, buildPkgbuildCodeHTML,
          buildPkgbuildTabsHTML, buildPkgbuildViews, buildPkgbuildDiffHTML } = hooks;

  // highlightBashLine: escapes HTML, colors comments/strings/keywords/vars, never stalls.
  assert.ok(highlightBashLine('# a comment').includes('tok-comment'), 'full-line comment');
  assert.ok(!highlightBashLine('echo "<script>"').includes('<script>'), 'HTML escaped');
  assert.ok(highlightBashLine('echo "$pkgver"').includes('tok-str'), 'string token');
  assert.ok(highlightBashLine('if true; then').includes('tok-kw'), 'keyword token');
  assert.ok(highlightBashLine('foo=$bar').includes('tok-var'), 'variable token');
  assert.strictEqual(highlightBashLine('${pkgname#x}').replace(/<[^>]+>/g, '').includes('${pkgname#x}'), true, 'param-expansion # not a comment / no stall');

  // risk banner reflects severity
  assert.ok(buildPkgbuildRiskHTML({ warn: 2, info: 1 }, 'D').includes('risk-warn'), 'warn tone');
  assert.ok(buildPkgbuildRiskHTML({ warn: 0, info: 0 }, 'D').includes('risk-safe'), 'safe tone when clean');
  assert.ok(buildPkgbuildRiskHTML({ warn: 0, info: 0 }, 'My disclaimer').includes('My disclaimer'), 'disclaimer shown');
  // headline names each severity unambiguously (counts add up to the findings list)
  assert.ok(buildPkgbuildRiskHTML({ warn: 2, info: 2 }, 'D').includes('2 warnings · 2 notes'), 'warn + info headline');
  assert.ok(buildPkgbuildRiskHTML({ warn: 1, info: 0 }, 'D').includes('1 warning'), 'singular warning, no notes clause');
  assert.ok(buildPkgbuildRiskHTML({ warn: 0, info: 1 }, 'D').includes('1 note'), 'info-only headline');

  // metadata panel
  const meta = buildPkgbuildMetaHTML({ maintainer: 'Jane', pkgver: '1.0', url: 'https://x.example',
    sources: ['https://s.example/a.tar.gz'], checksums: [{ algo: 'sha256', value: 'ab', skip: false }, { algo: 'sha256', value: 'SKIP', skip: true }] });
  assert.ok(meta.includes('Jane') && meta.includes('1.0'), 'maintainer + pkgver');
  assert.ok(meta.includes('data-url="https://x.example"'), 'upstream link');
  assert.ok(/SKIP/.test(meta), 'flags SKIP checksums');
  assert.strictEqual(buildPkgbuildMetaHTML({}), '', 'empty meta → no panel');

  // findings link to their line numbers
  const findings = [{ line_no: 8, severity: 'warn', why: 'pipes to shell' }];
  const fh = buildPkgbuildFindingsHTML(findings);
  assert.ok(fh.includes('data-line="8"') && fh.includes('pipes to shell'), 'finding links to line');
  assert.strictEqual(buildPkgbuildFindingsHTML([]), '', 'no findings → empty');

  // provenance: rule id chip always, campaign pill only for campaign rules, tooltip carries detail
  const prov = findingProvenanceHTML({ rule: 'npm_install_unknown',
    meta: { kind: 'campaign', added: '2026-06', source: 'Atomic Arch' } });
  assert.ok(prov.includes('npm_install_unknown'), 'rule id chip shown');
  assert.ok(prov.includes('kind-campaign') && prov.includes('campaign'), 'campaign pill');
  assert.ok(prov.includes('Atomic Arch') && prov.includes('added 2026-06'), 'tooltip detail');
  const evergreen = findingProvenanceHTML({ rule: 'eval', meta: { kind: 'evergreen' } });
  assert.ok(evergreen.includes('eval') && !evergreen.includes('kind-campaign'), 'evergreen: rule chip, no campaign pill');
  assert.strictEqual(findingProvenanceHTML({ line_no: 1, severity: 'warn' }), '', 'no rule/meta → no provenance block');
  // the findings list embeds provenance when a finding carries it
  const fhMeta = buildPkgbuildFindingsHTML([{ line_no: 3, severity: 'warn', why: 'x', rule: 'sudo', meta: { kind: 'evergreen' } }]);
  assert.ok(fhMeta.includes('pkgb-prov-rule') && fhMeta.includes('sudo'), 'list renders provenance');

  // code: line ids + flagged class on the right line
  const code = buildPkgbuildCodeHTML('a\nb\nc', [{ line_no: 2, severity: 'warn', why: 'x' }]);
  assert.ok(code.includes('id="pkgb-line-1"') && code.includes('id="pkgb-line-3"'), 'every line gets an id');
  assert.ok(code.includes('class="pkgb-line flagged sev-warn" id="pkgb-line-2"'), 'flagged line carries severity class');

  // views: a diff view (when present) leads, then PKGBUILD + .install files; each precomputes a badge
  const noDiffViews = buildPkgbuildViews({
    files: [{ name: 'PKGBUILD', findings: [] }, { name: 'x.install', findings: [{ severity: 'warn' }, { severity: 'info' }] }],
  });
  assert.strictEqual(JSON.stringify(noDiffViews.map(v => v.name)), '["PKGBUILD","x.install"]', 'files in order, no diff');
  assert.strictEqual(noDiffViews[1].badge, 1, 'warn count badge (info excluded)');

  const withDiff = buildPkgbuildViews({
    diff: [{ kind: 'add', text: '+x' }, { kind: 'del', text: '-y' }, { kind: 'ctx', text: ' z' }],
    files: [{ name: 'PKGBUILD', findings: [] }],
  });
  assert.strictEqual(withDiff[0].kind, 'diff', 'diff view leads');
  assert.strictEqual(withDiff[0].badge, 2, 'diff badge counts add/del only');
  assert.strictEqual(withDiff[1].name, 'PKGBUILD', 'file follows diff');

  // single view → no tab bar; >1 → a tab each, active marked, diff badge styled
  assert.strictEqual(buildPkgbuildTabsHTML(buildPkgbuildViews({ files: [{ name: 'PKGBUILD', findings: [] }] }), 0), '', 'single view → no tabs');
  const tabs = buildPkgbuildTabsHTML(withDiff, 0);
  assert.ok(tabs.includes('data-tab="0"') && tabs.includes('data-tab="1"'), 'a tab per view');
  assert.ok(tabs.includes('class="pkgb-tab active" data-tab="0"'), 'active tab marked');
  assert.ok(tabs.includes('pkgb-tab-badge-diff'), 'diff badge uses the diff style');

  // diff renderer: colored unified-diff rows, escaped
  assert.strictEqual(buildPkgbuildDiffHTML([]), '', 'empty diff → nothing');
  const diffHtml = buildPkgbuildDiffHTML([{ kind: 'add', text: '+<x>' }]);
  assert.ok(diffHtml.includes('diff-add') && diffHtml.includes('&lt;x&gt;'), 'diff row colored + escaped');
}

async function testPkgbuildMetaOnlyLinksSafeHttpUrls() {
  const { hooks } = loadMainJs({});
  const html = hooks.buildPkgbuildMetaHTML({
    url: 'javascript:alert(1)',
    sources: [
      'https://safe.example/src.tar.gz',
      'ftp://legacy.example/src.tar.gz',
      'git+https://git.example/repo.git',
      'https://bad.example/\nfile:///tmp/x',
      '<img src=x onerror=alert(1)>',
    ],
  });

  assert.ok(html.includes('data-url="https://safe.example/src.tar.gz"'), 'safe http(s) source is clickable');
  assert.ok(!html.includes('data-url="javascript:'), 'javascript upstream is not clickable');
  assert.ok(!html.includes('data-url="ftp:'), 'ftp source is not clickable');
  assert.ok(!html.includes('data-url="git+https:'), 'git source is not clickable');
  assert.ok(!html.includes('<img src=x'), 'source text remains escaped');
}

async function testStripProgressBarAndPercent() {
  const { hooks } = loadMainJs({});
  // Flatpak-style textual progress bar (block glyphs) is stripped; the meaningful text stays.
  const flatpakLine = 'Installing… ██████ 100% 99.8 MB/s';
  const cleaned = hooks.stripProgressBar(flatpakLine);
  assert.ok(!/[─-◿]/.test(cleaned), 'block glyphs removed');
  assert.ok(cleaned.includes('Installing') && cleaned.includes('100%') && cleaned.includes('99.8 MB/s'), 'text kept');
  // ASCII-style bar too
  assert.ok(!hooks.stripProgressBar('progress [#####=====] 50%').includes('#####'), 'ascii bar removed');
  // pickActivityText applies the strip
  assert.ok(!/[─-◿]/.test(hooks.pickActivityText({ lastLine: flatpakLine })), 'activity line stripped');
  // percent extraction
  assert.strictEqual(hooks.extractPercent('Installing… 33% 82.7 MB/s'), 33);
  assert.strictEqual(hooks.extractPercent('100% done'), 100);
  assert.strictEqual(hooks.extractPercent('no percent here'), null);
  assert.strictEqual(hooks.extractPercent('999%'), null);  // out of range
}

async function testTerminalFlowRunsWithoutError() {
  // Drives the real terminal handlers end-to-end so runtime errors (e.g. an undeclared variable)
  // are caught here, not only in the live app. (Regression: terminalOpen referenced a removed
  // `substatusEl`, which threw a ReferenceError on every install.)
  const { window, document } = loadMainJs({});
  assert.doesNotThrow(() => window.terminalOpen('Installing zoom'), 'terminalOpen');
  assert.doesNotThrow(() => window.terminalSetStatus('Resolving'), 'setStatus');
  assert.doesNotThrow(() => window.terminalSetSubstatus('(50%) [2/3] Installing pulseaudio'), 'setSubstatus');
  assert.doesNotThrow(() => window.terminalSetProgress(50), 'setProgress');
  assert.doesNotThrow(() => window.terminalAppend('some raw output line'), 'append');
  // activity line reflects the substatus (the highest-priority signal)
  assert.strictEqual(document.getElementById('terminal-activity-text').textContent, '(50%) [2/3] Installing pulseaudio');
  // failure path renders the summary card
  assert.doesNotThrow(() => window.terminalAppend('error: failed retrieving file (404)'), 'append err');
  assert.doesNotThrow(() => window.terminalSetDone(false), 'setDone(false)');
  assert.ok(document.getElementById('terminal-failure').innerHTML.includes('Download failed'), 'failure summary shown');
}

async function testTerminalDoneWarnedState() {
  // success + non-fatal warnings (e.g. an optional dependency failed to build) → amber
  // "completed with warnings", not a bare green Success and not a red failure.
  const { window, document } = loadMainJs({});
  window.terminalOpen('Installing visual-studio-code-bin');
  window.terminalSetDone(true, ['vscode was installed, but these optional dependencies could not be built: icu69']);
  assert.strictEqual(document.getElementById('terminal-status').textContent, 'Completed with warnings', 'status pill');
  assert.ok(document.getElementById('terminal-status').className.includes('warned'), 'status warned class');
  assert.strictEqual(document.getElementById('terminal-done-msg').className, 'terminal-done-warning', 'done msg amber');
  const notice = document.getElementById('terminal-failure');
  assert.ok(notice.className.includes('terminal-failure-warn'), 'notice amber-toned');
  assert.ok(notice.innerHTML.includes('icu69'), 'failed optdep named');
  assert.ok(document.getElementById('terminal-progress-fill').style.background.includes('--status-warning'), 'bar amber');

  // plain success (no warnings) stays green, notice hidden
  window.terminalOpen('Installing vim');
  window.terminalSetDone(true);
  assert.strictEqual(document.getElementById('terminal-status').textContent, 'Success', 'plain success pill');
  assert.ok(document.getElementById('terminal-failure').className.includes('hidden'), 'no notice on clean success');
  assert.ok(document.getElementById('terminal-progress-fill').style.background.includes('--status-success'), 'bar green');
}

async function testActivityFilterGroupAndActions() {
  const { hooks } = loadMainJs({});
  const { filterActivity, groupActivityByDate, activityEntryActions, activityActionsPresent, activityTypesPresent } = hooks;

  const now = new Date('2026-06-05T12:00:00');
  const entries = [
    { timestamp: '2026-06-05T09:00:00', action: 'install', pkg_name: 'firefox', pkg_type: 'arch_repo', success: true },
    { timestamp: '2026-06-04T20:00:00', action: 'uninstall', pkg_name: 'vlc', pkg_type: 'flatpak', success: true },
    { timestamp: '2026-06-02T08:00:00', action: 'update', pkg_name: 'yay', pkg_type: 'aur', success: true },
    { timestamp: '2026-05-01T08:00:00', action: 'install', pkg_name: 'gimp', pkg_type: 'flatpak', success: false },
  ];

  // Compare as strings: the helpers build arrays in the VM realm, so deepStrictEqual would trip on
  // the cross-realm Array prototype mismatch even with equal contents.
  const names = arr => arr.map(e => e.pkg_name).join(',');

  // filter: action
  assert.strictEqual(names(filterActivity(entries, { action: 'install' })), 'firefox,gimp', 'action filter');
  // filter: type (case-insensitive)
  assert.strictEqual(names(filterActivity(entries, { type: 'AUR' })), 'yay', 'type filter');
  // filter: query (substring, case-insensitive) — composes with action
  assert.strictEqual(names(filterActivity(entries, { action: 'install', query: 'FIRE' })), 'firefox', 'query+action');
  assert.strictEqual(filterActivity(entries, { query: 'nope' }).length, 0, 'no match');

  // grouping by date
  const groups = groupActivityByDate(entries, now);
  assert.strictEqual(groups.map(g => g.key).join(','), 'today,yesterday,week,older', 'all buckets present, ordered');
  assert.strictEqual(names(groups.find(g => g.key === 'today').items), 'firefox', 'today bucket');
  assert.strictEqual(names(groups.find(g => g.key === 'older').items), 'gimp', 'older bucket');
  // empty buckets are dropped
  assert.strictEqual(groupActivityByDate([entries[0]], now).length, 1, 'only non-empty buckets');
  // invalid timestamp → older, never throws
  assert.doesNotThrow(() => groupActivityByDate([{ timestamp: 'garbage', action: 'install', pkg_name: 'x', pkg_type: 'aur', success: true }], now));

  // per-entry rollback affordances
  assert.strictEqual(JSON.stringify(activityEntryActions(entries[0])), JSON.stringify([{ label: 'Downgrade', handler: 'downgradeApp', id: 'arch_repo:firefox' }]), 'install→downgrade');
  assert.strictEqual(JSON.stringify(activityEntryActions(entries[1])), JSON.stringify([{ label: 'Reinstall', handler: 'installApp', id: 'flatpak:vlc' }]), 'uninstall→reinstall');
  assert.strictEqual(activityEntryActions(entries[3]).length, 0, 'failed entry → no actions');
  assert.strictEqual(activityEntryActions({ action: 'install', pkg_type: 'snap', success: true }).length, 0, 'unsupported type → no downgrade');

  // filter option discovery (All leads; known actions ordered; types sorted)
  assert.strictEqual(activityActionsPresent(entries).join(','), 'all,install,update,uninstall', 'actions present');
  assert.strictEqual(activityTypesPresent(entries).join(','), 'all,arch_repo,aur,flatpak', 'types present');

  // pacman.log disclosure is Arch/AUR-only; flatpak entries don't get it
  const { activityHasPacmanLog, renderPacmanLogLine } = hooks;
  assert.strictEqual(activityHasPacmanLog(entries[0]), true, 'arch_repo has pacman log');
  assert.strictEqual(activityHasPacmanLog(entries[2]), true, 'aur has pacman log');
  assert.strictEqual(activityHasPacmanLog(entries[1]), false, 'flatpak has no pacman log');
  const lineHTML = renderPacmanLogLine({ action: 'upgraded', version: '1.0-1 -> 1.1-1', timestamp: '2026-06-05T09:00:00-0400' });
  assert.ok(lineHTML.includes('activity-action upgraded') && lineHTML.includes('1.0-1 -&gt; 1.1-1'), 'log line renders action chip + escaped version');

  // error cleanup: a stringified pywebview JS error → just the message, not the stack
  const { cleanActivityError } = hooks;
  const raw = `{'name': 'ReferenceError', 'message': "Can't find variable: substatusEl", 'line': 478, 'stack': '@file:///x.js:478:20'}`;
  assert.strictEqual(cleanActivityError(raw), "Can't find variable: substatusEl", 'extracts message from stringified error');
  assert.strictEqual(cleanActivityError('plain failure text'), 'plain failure text', 'passes through plain text');
  assert.strictEqual(cleanActivityError(''), '', 'empty error → empty');
  assert.ok(cleanActivityError('x'.repeat(500)).endsWith('…'), 'long error truncated');
}

async function testShowTransactionPreviewUsesActionCopy() {
  // Uninstall routes to get_uninstall_preview and sets the Remove title + danger proceed button.
  const { document, hooks } = loadMainJs({
    get_uninstall_preview: async () => ({ status: 'ok', data: { action: 'uninstall', name: 'vim', source_label: 'Arch', deps: { direct: [], optional: [] } } }),
  });
  const pending = hooks.showTransactionPreview('arch_repo:vim', 'uninstall');
  await flushPromises();
  assert.strictEqual(document.getElementById('tx-preview-title').textContent, 'Remove vim?', 'remove title');
  const btn = document.getElementById('tx-preview-proceed-btn');
  assert.strictEqual(btn.textContent, 'Remove', 'proceed button label');
  assert.ok(btn.classList.contains('btn-danger'), 'proceed button is danger-styled for removal');
  hooks.resolveTxPreview(true);
  assert.strictEqual(await pending, true, 'proceed resolves true');
}

function testPermissionUpdatedToastSurfacesCopyableCommand() {
  // A permission edit that ran a flatpak override surfaces it as a copyable toast (nothing hidden).
  const { document, hooks } = loadMainJs();
  hooks.permissionUpdatedToast({ status: 'ok', command: 'flatpak override --user --share=network org.x.App' });
  const toasts = document.getElementById('toast-container').children;
  assert.strictEqual(toasts.length, 1, 'one toast shown');
  const toast = toasts[0];
  assert.ok(toast.classList.contains('toast-copyable'), 'toast is copyable');
  assert.ok(toast.innerHTML.includes('flatpak override --user --share=network org.x.App'), 'shows the exact command');
  assert.ok(toast.innerHTML.includes('toast-copy-hint'), 'shows the click-to-copy hint');

  // No command (a no-op / non-override result) → an ordinary, non-copyable toast.
  hooks.permissionUpdatedToast({ status: 'ok' });
  const plain = document.getElementById('toast-container').children[1];
  assert.ok(!plain.classList.contains('toast-copyable'), 'plain toast is not copyable');
  assert.ok(plain.innerHTML.includes('effective next launch'), 'falls back to the generic message');
}

function testPermsListEnsuresIconObserver() {
  // Regression: the Permissions list used to observe lazy icons only `if (window.iconObserver)` —
  // but that observer is created by the package grid, which never renders if you open Permissions
  // straight from the dashboard. Result: every app stuck on a letter avatar. The list must now
  // create the shared observer on demand.
  const { window, hooks } = loadMainJs();
  assert.ok(!window.iconObserver, 'no observer exists before any grid/perms render');
  hooks.setPermsPageApps([
    { id: 'com.x.App', name: 'App', icon_url: 'https://dl.flathub.org/icon.png' },
    { id: 'com.y.Two', name: 'Two', icon_url: '' },
  ]);
  hooks.renderPermsAppList();
  assert.ok(window.iconObserver, 'perms list creates the shared icon observer on demand');
  // ensureIconObserver is idempotent — repeated calls reuse the one instance.
  assert.strictEqual(hooks.ensureIconObserver(), window.iconObserver, 'observer is reused, not recreated');
}

(async () => {
  const tests = [
    testRenderCategoryPackagesStoresCurrentPackages,
    testSortDropdownRerendersOpenBrowseCategory,
    testStaleDetailMetaDoesNotOverwriteNewModal,
    testTopLevelBrowseFetchRendersCategories,
    testStaleFetchDoesNotOverwriteNewerResults,
    testDashboardShowsAttentionCenterNotPackages,
    testBrowseRendersSuggestedRowAboveCategories,
    testAttentionCenterBuildsCardsAndTones,
    testAttentionUpdatesCardStates,
    testAttentionCenterAndBadgeShareUpdatesFetch,
    testUpdatesViewSharesInFlightBadgeFetch,
    testExternalUrlHelpersRejectUnsafeValues,
    testDashboardHeaderGreetingAndMessage,
    testCommandPaletteFilterAndAvailability,
    testDensityClass,
    testTopbarContextDecision,
    testEmptyStateHTML,
    testSystemHealthChecks,
    testPacnewRisk,
    testStaleUtilityRenderDoesNotClobber,
    testRefreshCurrentViewRespectsUtilityViews,
    testAttentionCenterFailsOpenOnNullSummary,
    testTransactionPreviewRendersAllSections,
    testTransactionPreviewHandlesMissingFields,
    testTransactionPreviewEscapesNames,
    testShowInstallPreviewOpensModalThroughEnvelope,
    testShowInstallPreviewProceedsWhenBridgeReturnsNothing,
    testTransactionPreviewActionLabelsSizeRow,
    testTransactionPreviewUpdateShowsVersionDelta,
    testBuildUpdateAllPreviewData,
    testBuildSourceCompareHTML,
    testWhySourceHint,
    testBuildDependencySummaryHTML,
    testPackageActivitySectionClearsForNonInstalledPackages,
    testBuildPackageActivityHTML,
    testBuildAurCommentsHTML,
    testBuildInstalledFilesHTML,
    testComputeDetailTabs,
    testReputationPopupHtml,
    testRerankByFuzzy,
    testFilterLocalPackages,
    testInstallQueueHelpers,
    testBrowseLandingBuilders,
    testBuildMirrorOptionsHTML,
    testPkgbuildViewerBuilders,
    testPkgbuildMetaOnlyLinksSafeHttpUrls,
    testSummarizeFailureCategories,
    testPickActivityText,
    testStripProgressBarAndPercent,
    testTerminalFlowRunsWithoutError,
    testTerminalDoneWarnedState,
    testActivityFilterGroupAndActions,
    testShowTransactionPreviewUsesActionCopy,
    testPermissionUpdatedToastSurfacesCopyableCommand,
    testPermsListEnsuresIconObserver,
  ];
  for (const test of tests) {
    await test();
    console.log(`✓ ${test.name}`);
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
