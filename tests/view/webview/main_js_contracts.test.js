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

  await hooks.renderBrowse();
  await flushPromises();

  const grid = document.getElementById('packages-grid');
  assert.ok(grid.innerHTML.includes('Suggested for you'), 'suggested header present');
  assert.ok(grid.innerHTML.includes('browse-suggested'), 'suggested row present');
  assert.ok(grid.innerHTML.includes('category-grid'), 'categories still present');
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

async function testAttentionCenterFailsOpenOnNullSummary() {
  const { hooks } = loadMainJs({});
  const html = hooks.buildAttentionCenterHTML(null, 'error');
  // null summary still renders all five cards, degraded to "couldn’t check"
  const cardCount = (html.match(/attention-card/g) || []).length;
  assert.strictEqual(cardCount, 5);
  assert.ok(html.includes('Couldn'), 'degrades to couldn’t check');
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
    testDashboardHeaderGreetingAndMessage,
    testAttentionCenterFailsOpenOnNullSummary,
  ];
  for (const test of tests) {
    await test();
    console.log(`✓ ${test.name}`);
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
