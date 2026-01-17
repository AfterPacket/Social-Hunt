const viewContainer = document.getElementById("viewContainer");
const viewTitle = document.getElementById("viewTitle");
const tokenStatus = document.getElementById("tokenStatus");

// ---- token helpers ----
function getToken() { return localStorage.getItem("socialhunt_token"); }
function setToken(token) {
  if (!token) localStorage.removeItem("socialhunt_token");
  else localStorage.setItem("socialhunt_token", token);
  renderTokenStatus();
}
function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { ...extra, "X-Plugin-Token": t } : { ...extra };
}
function renderTokenStatus() {
  tokenStatus.textContent = getToken() ? "Token: set" : "Token: not set";
}

const viewTitles = {
  dashboard: "Dashboard",
  search: "Search",
  reverse: "Reverse Image",
  history: "History",
  plugins: "Plugins",
  tokens: "Token",
  settings: "Settings",
};

async function loadView(name) {
  document.querySelectorAll('.menu-btn[data-view]').forEach(b => {
    b.classList.toggle('active', b.dataset.view === name);
  });

  viewTitle.textContent = viewTitles[name] || name;

  const res = await fetch(`/static/views/${name}.html?v=layout2`, { cache: 'no-store' });
  viewContainer.innerHTML = await res.text();

  if (name === 'dashboard') initDashboardView();
  if (name === 'search') initSearchView();
  if (name === 'reverse') initReverseView();
  if (name === 'history') initHistoryView();
  if (name === 'plugins') initPluginsView();
  if (name === 'tokens') initTokensView();
  if (name === 'settings') initSettingsView();
}

// ----------------------
// Local history (browser only)
// ----------------------
const HISTORY_MAX = 200;
const KEY_SEARCH_HISTORY = 'socialhunt_search_history';
const KEY_REVERSE_HISTORY = 'socialhunt_reverse_history';

function loadJsonArray(key) {
  try {
    const raw = localStorage.getItem(key);
    const v = raw ? JSON.parse(raw) : [];
    return Array.isArray(v) ? v : [];
  } catch (_) {
    return [];
  }
}

function saveJsonArray(key, arr) {
  const limited = Array.isArray(arr) ? arr.slice(0, HISTORY_MAX) : [];
  localStorage.setItem(key, JSON.stringify(limited));
}

function addSearchHistoryEntry({ username, providers, job_id }) {
  const items = loadJsonArray(KEY_SEARCH_HISTORY);
  items.unshift({
    ts: Date.now(),
    username,
    providers_count: (providers || []).length,
    job_id,
    results_count: null,
    state: 'running'
  });
  saveJsonArray(KEY_SEARCH_HISTORY, items);
}

function markSearchHistory(job_id, patch) {
  const items = loadJsonArray(KEY_SEARCH_HISTORY);
  const idx = items.findIndex(x => x && x.job_id === job_id);
  if (idx >= 0) {
    items[idx] = { ...items[idx], ...patch };
    saveJsonArray(KEY_SEARCH_HISTORY, items);
  }
}

function addReverseHistoryEntry({ image_url, links }) {
  const items = loadJsonArray(KEY_REVERSE_HISTORY);
  items.unshift({
    ts: Date.now(),
    image_url,
    links: Array.isArray(links) ? links : []
  });
  saveJsonArray(KEY_REVERSE_HISTORY, items);
}

// ----------------------
// Dashboard
// ----------------------
function initDashboardView() {
  const last = localStorage.getItem('socialhunt_last_job') || '';
  const el = document.getElementById('lastJob');
  if (el) el.textContent = last ? last : '(none yet)';

  const go = document.getElementById('goSearch');
  if (go) go.onclick = () => loadView('search');
}

// ----------------------
// Search (existing scan)
// ----------------------
function badge(status) {
  return `<span class="badge">${status}</span>`;
}

async function fetchProviders() {
  const res = await fetch('/api/providers');
  const data = await res.json();
  return data.providers || [];
}

async function fetchWhoami() {
  try {
    const res = await fetch('/api/whoami');
    const data = await res.json();
    return data;
  } catch (_) {
    return null;
  }
}

function renderProviders(names) {
  const box = document.getElementById('providers');
  box.innerHTML = names.map(n => `
    <label class="provider">
      <input type="checkbox" data-name="${n}" checked />
      <span>${n}</span>
    </label>
  `).join('');
}

function selectedProviders() {
  return Array.from(document.querySelectorAll('input[type="checkbox"][data-name]'))
    .filter(x => x.checked)
    .map(x => x.getAttribute('data-name'));
}

function renderResults(job) {
  const results = job.results || [];

  const rows = results.map(r => {
    const prof = r.profile || {};
    const avatar = prof.avatar_url ? `<img src="${prof.avatar_url}" alt="" class="avatar"/>` : "";
    const name = prof.display_name ? `${prof.display_name}` : "";
    const followers = (prof.followers ?? prof.subscribers ?? "");
    const following = (prof.following ?? "");
    const created = (prof.created_at ?? "");
    const link = r.url ? `<a href="${r.url}" target="_blank" rel="noreferrer">${r.url}</a>` : "";
    const err = r.error ? `<div class="muted">${r.error}</div>` : "";
    return `
      <tr>
        <td>${r.provider}</td>
        <td>${badge(r.status)}</td>
        <td>${avatar}</td>
        <td>${name}</td>
        <td>${followers}</td>
        <td>${following}</td>
        <td>${created}</td>
        <td>${link}${err}</td>
        <td>${r.http_status ?? ""}</td>
        <td>${r.elapsed_ms ?? ""}</td>
      </tr>
    `;
  }).join('');

  document.getElementById('results').innerHTML = `
    <div class="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Status</th>
            <th>Avatar</th>
            <th>Name</th>
            <th>Followers</th>
            <th>Following</th>
            <th>Created</th>
            <th>URL / Notes</th>
            <th>HTTP</th>
            <th>ms</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

async function startScan() {
  const usernameEl = document.getElementById('username');
  const statusEl = document.getElementById('status');
  const username = (usernameEl?.value || '').trim();
  if (!username) {
    statusEl.textContent = 'Enter a username.';
    return;
  }

  const providers = selectedProviders();
  statusEl.textContent = 'Starting scan...';

  const res = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, providers })
  });

  const data = await res.json().catch(() => ({}));
  const jobId = data.job_id;
  if (!jobId) {
    statusEl.textContent = 'Failed to start.';
    return;
  }

  localStorage.setItem('socialhunt_last_job', jobId);
  addSearchHistoryEntry({ username, providers, job_id: jobId });

  statusEl.textContent = `Job ${jobId} running...`;

  for (;;) {
    await new Promise(r => setTimeout(r, 1000));
    const jr = await fetch(`/api/jobs/${jobId}`);
    const job = await jr.json();

    if (job.state === 'done') {
      statusEl.textContent = 'Done.';
      markSearchHistory(jobId, { state: 'done', results_count: (job.results || []).length });
      renderResults(job);
      return;
    }
    if (job.state === 'failed') {
      statusEl.textContent = 'Failed: ' + (job.error || 'unknown');
      markSearchHistory(jobId, { state: 'failed', error: job.error || 'unknown' });
      return;
    }
    statusEl.textContent = `Running... (${(job.results || []).length} results so far)`;
  }
}

async function initSearchView() {
  const loadBtn = document.getElementById('loadProviders');
  const allBtn = document.getElementById('selectAll');
  const noneBtn = document.getElementById('selectNone');
  const startBtn = document.getElementById('start');
  const statusEl = document.getElementById('status');
  const whoEl = document.getElementById('whoami');

  loadBtn.onclick = async () => {
    statusEl.textContent = 'Loading providers...';
    const names = await fetchProviders();
    renderProviders(names);
    statusEl.textContent = `Loaded ${names.length} providers.`;
  };

  allBtn.onclick = () => {
    document.querySelectorAll('input[type="checkbox"][data-name]').forEach(x => x.checked = true);
  };

  noneBtn.onclick = () => {
    document.querySelectorAll('input[type="checkbox"][data-name]').forEach(x => x.checked = false);
  };

  startBtn.onclick = startScan;

  // auto-load
  const names = await fetchProviders();
  renderProviders(names);

  const who = await fetchWhoami();
  if (who && who.client_ip) {
    const via = who.via ? ` (${who.via})` : '';
    whoEl.textContent = `Your IP (as seen by the API): ${who.client_ip}${via}`;
  } else {
    whoEl.textContent = '';
  }
}

// ----------------------
// Reverse image
// ----------------------
function initReverseView() {
  const img = document.getElementById('imageUrl');
  const out = document.getElementById('reverseOut');
  const btn = document.getElementById('reverseGo');

  btn.onclick = async () => {
    const image_url = img.value.trim();
    if (!image_url) return alert('Paste an image URL.');

    const r = await fetch('/api/reverse_image_links', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_url })
    });

    const j = await r.json().catch(() => ({}));
    if (!r.ok) return alert(j.detail || `Failed (${r.status})`);

    // Save local history
    addReverseHistoryEntry({ image_url, links: (j.links || []) });

    out.innerHTML = (j.links || []).map(x =>
      `<div class="linkrow"><a target="_blank" rel="noreferrer" href="${x.url}">${x.name}</a></div>`
    ).join('');
  };
}

// ----------------------
// History
// ----------------------
function fmtWhen(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch (_) {
    return '';
  }
}

function initHistoryView() {
  const searchBody = document.getElementById('searchHistoryBody');
  const reverseBody = document.getElementById('reverseHistoryBody');
  const searchEmpty = document.getElementById('searchHistoryEmpty');
  const reverseEmpty = document.getElementById('reverseHistoryEmpty');
  const clearSearch = document.getElementById('searchHistoryClear');
  const clearReverse = document.getElementById('reverseHistoryClear');
  const refreshBtn = document.getElementById('historyRefresh');

  function render() {
    // Search
    const searches = loadJsonArray(KEY_SEARCH_HISTORY);
    if (searchEmpty) searchEmpty.style.display = searches.length ? 'none' : 'block';
    if (searchBody) {
      searchBody.innerHTML = searches.map(x => {
        const providers = x.providers_count ?? '';
        const job = x.job_id ? escapeHtml(x.job_id) : '';
        const results = (x.results_count ?? '') + (x.state ? ` (${escapeHtml(x.state)})` : '');
        return `<tr>
          <td>${escapeHtml(fmtWhen(x.ts))}</td>
          <td>${escapeHtml(x.username || '')}</td>
          <td>${escapeHtml(String(providers))}</td>
          <td>${job}</td>
          <td>${escapeHtml(String(results))}</td>
        </tr>`;
      }).join('');
    }

    // Reverse
    const reverses = loadJsonArray(KEY_REVERSE_HISTORY);
    if (reverseEmpty) reverseEmpty.style.display = reverses.length ? 'none' : 'block';
    if (reverseBody) {
      reverseBody.innerHTML = reverses.map(x => {
        const img = x.image_url || '';
        const links = Array.isArray(x.links) ? x.links : [];
        const linkHtml = links.slice(0, 4).map(l => {
          const name = escapeHtml(l.name || 'Link');
          const url = escapeHtml(l.url || '#');
          return `<a class="mini-link" target="_blank" rel="noreferrer" href="${url}">${name}</a>`;
        }).join(' ');
        const more = links.length > 4 ? ` <span class="muted">+${links.length - 4} more</span>` : '';
        return `<tr>
          <td>${escapeHtml(fmtWhen(x.ts))}</td>
          <td>${escapeHtml(img)}</td>
          <td>${linkHtml}${more}</td>
        </tr>`;
      }).join('');
    }
  }

  if (clearSearch) {
    clearSearch.onclick = () => {
      localStorage.removeItem(KEY_SEARCH_HISTORY);
      render();
    };
  }
  if (clearReverse) {
    clearReverse.onclick = () => {
      localStorage.removeItem(KEY_REVERSE_HISTORY);
      render();
    };
  }
  if (refreshBtn) refreshBtn.onclick = render;

  render();
}

// ----------------------
// Token
// ----------------------
function initTokensView() {
  const input = document.getElementById('tokenInput');
  const save = document.getElementById('tokenSave');
  const clear = document.getElementById('tokenClear');

  input.value = getToken() || '';
  save.onclick = () => setToken(input.value.trim());
  clear.onclick = () => { input.value = ''; setToken(''); };
}

// ----------------------
// Plugins
// ----------------------
function initPluginsView() {
  const fileEl = document.getElementById('pluginFile');
  const uploadBtn = document.getElementById('pluginUpload');
  const reloadBtn = document.getElementById('pluginReload');
  const outEl = document.getElementById('pluginOut');

  function setOut(msg) {
    if (outEl) outEl.textContent = msg;
  }

  uploadBtn.onclick = async () => {
    if (!getToken()) return alert('Set token first (Token page).');
    if (!fileEl.files?.length) return alert('Choose a plugin file.');

    const fd = new FormData();
    fd.append('file', fileEl.files[0]);

    const r = await fetch('/api/plugin/upload', {
      method: 'POST',
      headers: authHeaders(),
      body: fd
    });

    const j = await r.json().catch(() => ({}));
    if (!r.ok) return alert(j.detail || `Upload failed (${r.status})`);

    setOut(JSON.stringify(j, null, 2));
  };

  reloadBtn.onclick = async () => {
    if (!getToken()) return alert('Set token first (Token page).');
    const r = await fetch('/api/providers/reload', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return alert(j.detail || `Reload failed (${r.status})`);
    setOut(JSON.stringify(j, null, 2));
  };
}

// ----------------------
// Settings (dynamic)
// ----------------------
function initSettingsView() {
  const tableBody = document.querySelector('#settingsTable tbody');
  const addBtn = document.getElementById('settingsAdd');
  const saveBtn = document.getElementById('settingsSave');
  const reloadBtn = document.getElementById('settingsReload');
  const msgEl = document.getElementById('settingsMsg');

  function showMsg(txt) {
    msgEl.style.display = 'block';
    msgEl.textContent = txt;
  }

  function rowHtml(key = '', val = '', secret = false, isSet = false) {
    const displayVal = secret ? (isSet ? '•••••• (set)' : '') : (val ?? '');
    return `
      <tr>
        <td><input class="input s-key" placeholder="e.g. hibp_api_key" value="${escapeHtml(key)}"></td>
        <td><input class="input s-val" placeholder="value" value="${escapeHtml(displayVal)}"></td>
        <td style="text-align:center"><input type="checkbox" class="s-secret" ${secret ? 'checked' : ''}></td>
        <td><button class="btn danger s-del" type="button">Remove</button></td>
      </tr>
    `;
  }

  function bindRowEvents() {
    tableBody.querySelectorAll('.s-del').forEach(btn => {
      btn.onclick = () => btn.closest('tr').remove();
    });
  }

  async function load() {
    if (!getToken()) {
      tableBody.innerHTML = '';
      showMsg('Set token first (Token page).');
      return;
    }

    tableBody.innerHTML = '';
    const r = await fetch('/api/settings', { headers: authHeaders() });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      showMsg(j.detail || `Failed (${r.status})`);
      return;
    }

    const settings = j.settings || {};
    for (const [k, meta] of Object.entries(settings)) {
      tableBody.insertAdjacentHTML('beforeend', rowHtml(k, meta.value, meta.secret, meta.is_set));
    }

    bindRowEvents();
    showMsg('Loaded.');
  }

  addBtn.onclick = () => {
    tableBody.insertAdjacentHTML('beforeend', rowHtml());
    bindRowEvents();
  };

  saveBtn.onclick = async () => {
    if (!getToken()) return alert('Set token first (Token page).');

    const rows = [...tableBody.querySelectorAll('tr')];
    const out = {};

    for (const tr of rows) {
      const k = tr.querySelector('.s-key').value.trim();
      const v = tr.querySelector('.s-val').value;
      const secret = tr.querySelector('.s-secret').checked;
      if (!k) continue;

      // If secret and user left placeholder, don't overwrite
      if (secret && (v === '•••••• (set)' || v.trim() === '')) continue;
      out[k] = v;
    }

    const r = await fetch('/api/settings', {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ settings: out })
    });

    const j = await r.json().catch(() => ({}));
    if (!r.ok) return showMsg(j.detail || `Save failed (${r.status})`);

    showMsg('Saved. Reloading…');
    await load();
  };

  reloadBtn.onclick = load;

  load();
}

function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

// logout
const logoutBtn = document.querySelector("[data-action='logout']");
if (logoutBtn) {
  logoutBtn.onclick = () => {
    setToken('');
    location.reload();
  };
}

// menu clicks
document.querySelectorAll('.menu-btn[data-view]').forEach(btn => {
  btn.onclick = () => loadView(btn.dataset.view);
});

renderTokenStatus();
loadView('dashboard');
