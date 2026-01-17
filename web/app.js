// Social Hunt Dashboard (v5)
// Sidebar router + token storage + search/plugins/addons/reverse views

const el = (id) => document.getElementById(id);

let LAST_JOB_ID = "";
let CURRENT_VIEW = "dashboard";

// ---- token helpers ----
function getToken() {
  try { return localStorage.getItem("socialhunt_token") || ""; } catch (_) { return ""; }
}
function setToken(token) {
  try {
    if (!token) localStorage.removeItem("socialhunt_token");
    else localStorage.setItem("socialhunt_token", token);
  } catch (_) {
    // ignore
  }
  renderTokenStatus();
}
function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { ...extra, "x-plugin-token": t } : { ...extra };
}
function renderTokenStatus() {
  const pill = el("tokenStatus");
  if (!pill) return;
  pill.textContent = getToken() ? "Token: set" : "Token: not set";
}

function badge(status) {
  return `<span class="badge">${status}</span>`;
}

// ---- API helpers ----
async function fetchProviders() {
  const res = await fetch("/api/providers", { cache: "no-store" });
  const data = await res.json();
  return data.providers || [];
}

async function fetchAddons() {
  try {
    const res = await fetch("/api/addons", { cache: "no-store" });
    const data = await res.json();
    return { available: data.available || [], enabled: data.enabled || [] };
  } catch (_) {
    return { available: [], enabled: [] };
  }
}

async function fetchWhoami() {
  try {
    const res = await fetch("/api/whoami", { cache: "no-store" });
    return await res.json();
  } catch (_) {
    return null;
  }
}

async function fetchPluginsInventory() {
  try {
    const res = await fetch("/api/plugins", { cache: "no-store" });
    return await res.json();
  } catch (_) {
    return null;
  }
}

// ---- rendering ----
function renderProviders(names) {
  const box = el("providers");
  if (!box) return;

  box.innerHTML = names.map(n => `
    <label class="provider">
      <input type="checkbox" data-name="${n}" checked />
      <span>${n}</span>
    </label>
  `).join("");
}

function renderAddons(data) {
  const box = el("addons");
  if (!box) return;

  const enabled = new Set((data.enabled || []).map(x => String(x)));
  const available = (data.available || []).map(x => String(x));

  if (!available.length) {
    box.innerHTML = `<div class="muted">No addons reported by API.</div>`;
    return;
  }

  box.innerHTML = `
    <table>
      <thead>
        <tr><th>Name</th><th>Status</th></tr>
      </thead>
      <tbody>
        ${available.map(n => {
          const on = enabled.has(n);
          return `<tr><td><code>${n}</code></td><td>${on ? "enabled" : "available"}</td></tr>`;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderPlugins(inv) {
  const box = el("pluginList");
  if (!box) return;

  if (!inv) {
    box.innerHTML = `<div class="muted">Plugins API unavailable.</div>`;
    return;
  }

  const webOn = !!inv.web_upload_enabled;
  const pyOn = !!inv.python_plugins_allowed;
  const root = inv.root || "plugins";

  const lists = [
    { title: "YAML provider packs", items: inv.yaml_providers || [] },
    { title: "Python providers", items: inv.python_providers || [] },
    { title: "Python addons", items: inv.python_addons || [] },
  ];

  const rows = lists.map(s => {
    const items = (s.items || []).length
      ? `<ul class="pluglist">${s.items.map(x => `<li><code>${x}</code></li>`).join("")}</ul>`
      : `<div class="muted">none</div>`;
    return `<div class="plugsec"><div class="plugtitle">${s.title}</div>${items}</div>`;
  }).join("");

  box.innerHTML = `
    <div class="muted" style="margin-bottom:8px;">
      Root: <code>${root}</code> · Web upload: <b>${webOn ? "on" : "off"}</b> · Python: <b>${pyOn ? "on" : "off"}</b>
    </div>
    ${rows}
  `;

  const dash = {
    plugins: el("dashPlugins"),
  };
  if (dash.plugins) {
    const count = (inv.yaml_providers || []).length + (inv.python_providers || []).length + (inv.python_addons || []).length;
    dash.plugins.textContent = `Plugins: ${count}`;
  }
}

function selectedProviders() {
  return Array.from(document.querySelectorAll('input[type="checkbox"][data-name]'))
    .filter(x => x.checked)
    .map(x => x.getAttribute("data-name"));
}

function renderResults(job) {
  const target = el("results");
  if (!target) return;

  const results = job.results || [];

  const rows = results.map(r => {
    const prof = r.profile || {};
    const avatar = prof.avatar_url ? `<img src="${prof.avatar_url}" alt="" class="avatar"/>` : "";
    const name = prof.display_name ? `${prof.display_name}` : "";
    const followers = (prof.followers ?? prof.subscribers ?? "");
    const following = (prof.following ?? "");
    const created = (prof.created_at ?? "");
    const link = r.url ? `<a href="${r.url}" target="_blank" rel="noreferrer">${r.url}</a>` : "";

    const meta = [];
    if (prof.bio_domains && Array.isArray(prof.bio_domains) && prof.bio_domains.length) meta.push(`domains: ${prof.bio_domains.join(", ")}`);
    if (prof.avatar_cluster_id) meta.push(`avatar cluster: ${prof.avatar_cluster_id}`);
    if (prof.avatar_fetch_error) meta.push(`avatar fetch: ${prof.avatar_fetch_error}`);

    const metaHtml = meta.length ? `<div class="muted tiny">${meta.join(" | ")}</div>` : "";
    const err = r.error ? `<div class="muted tiny">${r.error}</div>` : "";

    return `
      <tr>
        <td>${r.provider}</td>
        <td>${badge(r.status)}</td>
        <td>${avatar}</td>
        <td>${name}</td>
        <td>${followers}</td>
        <td>${following}</td>
        <td>${created}</td>
        <td>${link}${metaHtml}${err}</td>
        <td>${r.http_status ?? ""}</td>
        <td>${r.elapsed_ms ?? ""}</td>
      </tr>
    `;
  }).join("");

  target.innerHTML = `
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

function setLastJob(jobId) {
  LAST_JOB_ID = jobId || "";
  const last = el("lastJob");
  const copy = el("copyJob");
  if (last) last.textContent = LAST_JOB_ID ? `Last job: ${LAST_JOB_ID}` : "";
  if (copy) copy.style.display = LAST_JOB_ID ? "inline-block" : "none";
}

async function startScan() {
  const userInput = el("username");
  const status = el("status");
  if (!userInput || !status) return;

  const username = userInput.value.trim();
  if (!username) {
    status.textContent = "Enter a username.";
    return;
  }

  const providers = selectedProviders();
  status.textContent = "Starting scan...";

  const res = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, providers })
  });

  const data = await res.json().catch(() => ({}));
  const jobId = data.job_id;
  if (!jobId) {
    status.textContent = "Failed to start.";
    return;
  }

  status.textContent = `Job ${jobId} running...`;
  setLastJob(jobId);

  for (;;) {
    await new Promise(r => setTimeout(r, 1000));
    const jr = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
    const job = await jr.json().catch(() => ({}));

    if (job.state === "done") {
      status.textContent = "Done.";
      renderResults(job);
      setLastJob(jobId);
      return;
    }
    if (job.state === "failed") {
      status.textContent = "Failed: " + (job.error || "unknown");
      return;
    }
    status.textContent = `Running... (${(job.results || []).length} results so far)`;
  }
}

// ---- reverse image ----
function buildReverseLinks(imageUrl) {
  const u = encodeURIComponent(imageUrl);
  return [
    { name: "Google Images", url: `https://www.google.com/searchbyimage?image_url=${u}` },
    { name: "Google Lens (desktop)", url: `https://lens.google.com/uploadbyurl?url=${u}` },
    { name: "Bing Visual Search", url: `https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl=${u}` },
    { name: "TinEye", url: `https://tineye.com/search?url=${u}` },
    { name: "Yandex Images", url: `https://yandex.com/images/search?rpt=imageview&url=${u}` },
  ];
}

async function generateReverseLinks() {
  const imageUrl = (el("reverseUrl")?.value || "").trim();
  const status = el("reverseStatus");
  const out = el("reverseResults");

  if (status) status.textContent = "";
  if (out) out.innerHTML = "";

  if (!imageUrl) {
    if (status) status.textContent = "Provide an image URL.";
    return;
  }
  if (!/^https?:\/\//i.test(imageUrl)) {
    if (status) status.textContent = "Image URL must start with http:// or https://";
    return;
  }

  const links = buildReverseLinks(imageUrl);
  if (status) status.textContent = `Links ready (${links.length}).`;

  if (!out) return;
  out.innerHTML = `
    <div class="linkgrid">
      ${links.map(l => `<a class="btnlink" href="${l.url}" target="_blank" rel="noreferrer">${l.name}</a>`).join(" ")}
    </div>
    <div class="muted tiny" style="margin-top:10px;">
      Note: these services may change behavior over time (and some Lens links may not work on mobile).
    </div>
  `;
}

// ---- plugins ----
async function uploadPlugin() {
  const status = el("pluginStatus");
  const file = el("pluginFile")?.files?.[0];

  if (status) status.textContent = "";
  if (!file) {
    if (status) status.textContent = "Choose a .zip or .yaml file.";
    return;
  }

  const tok = getToken();
  if (!tok) {
    if (status) status.textContent = "Token required. Set it under Token in the menu.";
    return;
  }

  const fd = new FormData();
  fd.append("plugin", file);

  if (status) status.textContent = "Uploading...";
  const res = await fetch("/api/plugins/upload", {
    method: "POST",
    headers: authHeaders(),
    body: fd,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (status) status.textContent = `Upload failed: ${data.detail || res.status}`;
    return;
  }

  if (status) status.textContent = `Installed ${((data.installed || []).length)} file(s) and reloaded.`;

  // refresh inventories
  const prov = (data.reloaded?.providers) || await fetchProviders();
  renderProviders(prov);

  renderAddons({
    available: data.reloaded?.addons_available || [],
    enabled: data.reloaded?.addons_enabled || [],
  });

  const inv = await fetchPluginsInventory();
  renderPlugins(inv);
}

async function reloadPlugins() {
  const status = el("pluginStatus");
  const tok = getToken();
  if (!tok) {
    if (status) status.textContent = "Token required. Set it under Token in the menu.";
    return;
  }

  if (status) status.textContent = "Reloading...";
  const res = await fetch("/api/plugins/reload", {
    method: "POST",
    headers: authHeaders(),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (status) status.textContent = `Reload failed: ${data.detail || res.status}`;
    return;
  }

  if (status) status.textContent = `Reloaded. ${((data.providers || []).length)} providers.`;
  renderProviders(data.providers || []);
  renderAddons({ available: data.addons_available || [], enabled: data.addons_enabled || [] });

  const inv = await fetchPluginsInventory();
  renderPlugins(inv);
}

// ---- view router ----
const viewTitles = {
  dashboard: "Dashboard",
  search: "Search",
  reverse: "Reverse Image",
  addons: "Addons",
  plugins: "Plugins",
  tokens: "Token",
  settings: "Settings",
};

async function loadView(name) {
  CURRENT_VIEW = name;

  // highlight active button
  document.querySelectorAll(".menu-btn[data-view]").forEach(b => {
    b.classList.toggle("active", b.dataset.view === name);
  });

  const title = el("viewTitle");
  if (title) title.textContent = viewTitles[name] || name;

  const container = el("viewContainer");
  if (!container) return;

  const res = await fetch(`/static/views/${name}.html?v=5`, { cache: "no-store" });
  container.innerHTML = await res.text();

  // in-view navigation buttons (dashboard)
  container.querySelectorAll("[data-nav]").forEach(btn => {
    btn.addEventListener("click", () => loadView(btn.getAttribute("data-nav")));
  });

  // per-view init hooks
  if (name === "dashboard") initDashboardView();
  if (name === "search") initSearchView();
  if (name === "reverse") initReverseView();
  if (name === "addons") initAddonsView();
  if (name === "plugins") initPluginsView();
  if (name === "tokens") initTokensView();
}

function initTokensView() {
  const input = el("tokenInput");
  const save = el("tokenSave");
  const clear = el("tokenClear");
  const msg = el("tokenSavedMsg");

  if (input) input.value = getToken() || "";

  if (save) {
    save.onclick = () => {
      const v = (input?.value || "").trim();
      setToken(v);
      if (msg) msg.textContent = v ? "Saved." : "Cleared.";
    };
  }

  if (clear) {
    clear.onclick = () => {
      if (input) input.value = "";
      setToken("");
      if (msg) msg.textContent = "Cleared.";
    };
  }
}

async function initSearchView() {
  const status = el("status");
  if (status) status.textContent = "Loading providers...";

  const names = await fetchProviders();
  renderProviders(names);

  if (status) status.textContent = `Loaded ${names.length} providers.`;

  el("loadProviders")?.addEventListener("click", async () => {
    if (status) status.textContent = "Loading providers...";
    const n = await fetchProviders();
    renderProviders(n);
    if (status) status.textContent = `Loaded ${n.length} providers.`;
  });

  el("selectAll")?.addEventListener("click", () => {
    document.querySelectorAll('input[type="checkbox"][data-name]').forEach(x => x.checked = true);
  });

  el("selectNone")?.addEventListener("click", () => {
    document.querySelectorAll('input[type="checkbox"][data-name]').forEach(x => x.checked = false);
  });

  el("start")?.addEventListener("click", startScan);

  el("copyJob")?.addEventListener("click", async () => {
    if (!LAST_JOB_ID) return;
    try { await navigator.clipboard.writeText(LAST_JOB_ID); } catch (_) {}
  });

  const who = await fetchWhoami();
  if (who && who.client_ip && el("whoami")) {
    const via = who.via ? ` (${who.via})` : "";
    el("whoami").textContent = `Your IP (as seen by the API): ${who.client_ip}${via}`;
  }
}

async function initAddonsView() {
  const addons = await fetchAddons();
  renderAddons(addons);

  const dash = el("dashAddons");
  if (dash) dash.textContent = `Addons: ${(addons.available || []).length}`;
}

async function initPluginsView() {
  const tok = getToken();
  const tokUsed = el("pluginTokenUsed");
  if (tokUsed) tokUsed.textContent = tok ? "set" : "(not set)";

  const inv = await fetchPluginsInventory();
  renderPlugins(inv);

  el("pluginUpload")?.addEventListener("click", uploadPlugin);
  el("pluginReload")?.addEventListener("click", reloadPlugins);
}

function initReverseView() {
  el("reverseBtn")?.addEventListener("click", generateReverseLinks);
}

async function initDashboardView() {
  // providers count
  try {
    const names = await fetchProviders();
    const pill = el("dashProviders");
    if (pill) pill.textContent = `Providers: ${names.length}`;
  } catch (_) {}

  // addons count
  try {
    const a = await fetchAddons();
    const pill = el("dashAddons");
    if (pill) pill.textContent = `Addons: ${(a.available || []).length}`;
  } catch (_) {}

  // plugins count
  try {
    const inv = await fetchPluginsInventory();
    const pill = el("dashPlugins");
    if (pill) {
      const count = inv ? ((inv.yaml_providers || []).length + (inv.python_providers || []).length + (inv.python_addons || []).length) : 0;
      pill.textContent = `Plugins: ${count}`;
    }
  } catch (_) {}

  const who = await fetchWhoami();
  const out = el("dashWhoami");
  if (out && who && who.client_ip) {
    const via = who.via ? ` (${who.via})` : "";
    out.textContent = `Your IP (as seen by the API): ${who.client_ip}${via}`;
  }
}

// ---- boot ----
window.addEventListener("DOMContentLoaded", () => {
  renderTokenStatus();

  // menu clicks
  document.querySelectorAll(".menu-btn[data-view]").forEach(btn => {
    btn.addEventListener("click", () => loadView(btn.dataset.view));
  });

  // logout
  document.querySelector("[data-action='logout']")?.addEventListener("click", () => {
    setToken("");
    location.reload();
  });

  loadView("dashboard");
});
