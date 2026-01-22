const viewContainer = document.getElementById("viewContainer");
const viewTitle = document.getElementById("viewTitle");
const tokenStatus = document.getElementById("tokenStatus");

// ---- token helpers ----
function getToken() {
  return localStorage.getItem("socialhunt_token");
}
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
  "breach-search": "Breach Search", // Added breach search
  reverse: "Reverse Image",
  history: "History",
  plugins: "Plugins",
  tokens: "Token",
  settings: "Settings",
};

async function loadView(name) {
  document.querySelectorAll(".menu-btn[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });

  viewTitle.textContent = viewTitles[name] || name;

  const res = await fetch(`/static/views/${name}.html?v=layout3`, {
    cache: "no-store",
  });
  viewContainer.innerHTML = await res.text();

  if (name === "dashboard") initDashboardView();
  if (name === "search") initSearchView();
  if (name === "breach-search") initBreachSearchView(); // Initialize breach search
  if (name === "reverse") initReverseView();
  if (name === "history") initHistoryView();
  if (name === "plugins") initPluginsView();
  if (name === "tokens") initTokensView();
  if (name === "settings") initSettingsView();
}

// ----------------------
// Local history (browser only)
// ----------------------
const HISTORY_MAX = 200;
const KEY_SEARCH_HISTORY = "socialhunt_search_history";
const KEY_REVERSE_HISTORY = "socialhunt_reverse_history";

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
    state: "running",
  });
  saveJsonArray(KEY_SEARCH_HISTORY, items);
}

function markSearchHistory(job_id, patch) {
  const items = loadJsonArray(KEY_SEARCH_HISTORY);
  const idx = items.findIndex((x) => x && x.job_id === job_id);
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
    links: Array.isArray(links) ? links : [],
  });
  saveJsonArray(KEY_REVERSE_HISTORY, items);
}

// ----------------------
// Dashboard
// ----------------------
function initDashboardView() {
  const last = localStorage.getItem("socialhunt_last_job") || "";
  const el = document.getElementById("lastJob");
  if (el) el.textContent = last ? last : "(none yet)";

  const go = document.getElementById("goSearch");
  if (go) go.onclick = () => loadView("search");
}

// ----------------------
// Search
// ----------------------
function badge(status) {
  return `<span class="badge">${status}</span>`;
}

async function fetchProviders() {
  const res = await fetch("/api/providers");
  const data = await res.json();
  return data.providers || [];
}

async function fetchWhoami() {
  try {
    const res = await fetch("/api/whoami");
    if (!res.ok) return null; // Defensive check
    const data = await res.json();
    return data;
  } catch (_) {
    return null;
  }
}

function renderProviders(names) {
  const box = document.getElementById("providers");
  box.innerHTML = names
    .map(
      (n) => `
    <label class="provider">
      <input type="checkbox" data-name="${n}" checked />
      <span>${n}</span>
    </label>
  `,
    )
    .join("");
}

function selectedProviders() {
  return Array.from(
    document.querySelectorAll('input[type="checkbox"][data-name]'),
  )
    .filter((x) => x.checked)
    .map((x) => x.getAttribute("data-name"));
}

function renderResults(job, containerId) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`renderResults: container #${containerId} not found.`);
    return;
  }

  const results = job.results || [];
  const rows = results
    .map((r) => {
      const prof = r.profile || {};
      const avatar =
        prof.avatar_url && prof.avatar_url !== "undefined"
          ? `<img src="${prof.avatar_url}" alt="" class="avatar"/>`
          : "";
      const name = prof.display_name ? `${prof.display_name}` : "";
      const followers = prof.followers ?? prof.subscribers ?? "";
      const following = prof.following ?? "";
      const created = prof.created_at ?? "";
      const link = r.url
        ? `<a href="${r.url}" target="_blank" rel="noreferrer">${r.url}</a>`
        : "";
      let errorDisplay = "";
      if (r.error) {
        // Special handling for HIBP error/warning to make it prominent
        if (r.provider === "hibp" && !r.error.includes("API key not set")) {
          errorDisplay = `<div style="margin-top:6px; font-weight:bold; color: var(--danger);">${escapeHtml(r.error)}</div>`;
        } else {
          // Default error display for other providers (and HIBP missing key)
          errorDisplay = `<div class="muted" style="margin-top:6px; color: var(--warn);">${escapeHtml(r.error)}</div>`;
        }
      }

      const notes = [];
      if (typeof prof.breach_count === "number") {
        notes.push(`breaches: ${prof.breach_count}`);
        if (Array.isArray(prof.breaches) && prof.breaches.length) {
          notes.push(
            `(${prof.breaches.slice(0, 6).join(", ")}${prof.breaches.length > 6 ? "…" : ""})`,
          );
        }
      }
      if (typeof prof.paste_count === "number")
        notes.push(`pastes: ${prof.paste_count}`);
      if (prof.breach_error) notes.push(`breach error: ${prof.breach_error}`);
      if (prof.paste_error) notes.push(`paste error: ${prof.paste_error}`);
      if (prof.note) notes.push(String(prof.note));
      if (prof.pastes_note) notes.push(String(prof.pastes_note));
      if (prof.pastes_error) notes.push(`pastes: ${prof.pastes_error}`);
      if (r.error) notes.push(`info: ${r.error}`);
      if (prof.face_match) {
        if (prof.face_match.match) {
          notes.push("FACE MATCH");
        } else {
          notes.push(
            `NO FACE MATCH (reason: ${prof.face_match.reason || "unknown"})`,
          );
        }
      }
      if (prof.face_match_error) {
        notes.push(`FACE SEARCH ERROR: ${prof.face_match_error}`);
      }
      const noteHtml = notes.length
        ? `<div class=\"muted\" style=\"margin-top:6px\">${escapeHtml(notes.join(" "))}</div>`
        : "";

      return `
       <tr>
         <td>${r.provider}</td>
         <td>${badge(r.status)}</td>
         <td>${avatar}</td>
         <td>${name}</td>
         <td>${followers}</td>
         <td>${following}</td>
         <td>${created}</td>
         <td>${link}${noteHtml}${errorDisplay}</td>
         <td>${r.http_status ?? ""}</td>
         <td>${r.elapsed_ms ?? ""}</td>
       </tr>
     `;
    })
    .join("");

  container.innerHTML = `
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

// ----------------------
// Breach Search
// ----------------------
async function initBreachSearchView() {
  const termEl = document.getElementById("breachTerm");
  const startBtn = document.getElementById("startBreachScan");
  const statusEl = document.getElementById("breachStatus");

  startBtn.onclick = async () => {
    const term = (termEl?.value || "").trim();
    if (!term) {
      statusEl.textContent = "Enter a search term.";
      return;
    }

    statusEl.textContent = "Starting scan...";
    document.getElementById("breachResults").innerHTML = "";

    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: term,
        providers: ["breachvip", "hibp"], // Use both breachvip and hibp
      }),
    });

    const data = await res.json().catch(() => ({}));
    const jobId = data.job_id;
    if (!jobId) {
      statusEl.textContent = "Failed to start.";
      return;
    }

    // Add to history right away
    addSearchHistoryEntry({
      username: term,
      providers: ["breachvip", "hibp"],
      job_id: jobId,
    });

    statusEl.textContent = `Job ${jobId} running...`;

    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const jr = await fetch(`/api/jobs/${jobId}`);
      const job = await jr.json();

      if (job.state === "done") {
        const results = job.results || [];
        const foundCount = results.filter((r) => r.status === "found").length;
        const failedCount = results.filter(
          (r) =>
            r.status === "error" ||
            r.status === "unknown" ||
            r.status === "blocked",
        ).length;
        statusEl.textContent = `Done. (${foundCount} found, ${failedCount} failed)`;
        markSearchHistory(jobId, {
          state: "done",
          results_count: (job.results || []).length,
        });
        renderBreachView(job, "breachResults"); // Specialized view for breaches
        return;
      }
      if (job.state === "failed") {
        statusEl.textContent = "Failed: " + (job.error || "unknown");
        markSearchHistory(jobId, {
          state: "failed",
          error: job.error || "unknown",
        });
        return;
      }
      const results = job.results || [];
      const foundCount = results.filter((r) => r.status === "found").length;
      const failedCount = results.filter(
        (r) =>
          r.status === "error" ||
          r.status === "unknown" ||
          r.status === "blocked",
      ).length;
      statusEl.textContent = `Running... (${foundCount} found, ${failedCount} failed so far)`;
      if (job.results && job.results.length > 0) {
        renderBreachView(job, "breachResults"); // Update results as they come
      }
    }
  };
}

async function monitorJob(jobId) {
  const statusEl = document.getElementById("status");
  for (;;) {
    await new Promise((r) => setTimeout(r, 1000));
    const jr = await fetch(`/api/jobs/${jobId}`);
    const job = await jr.json();

    if (job.state === "done") {
      const results = job.results || [];
      const foundCount = results.filter((r) => r.status === "found").length;
      const failedCount = results.filter(
        (r) =>
          r.status === "error" ||
          r.status === "unknown" ||
          r.status === "blocked",
      ).length;
      statusEl.textContent = `Done. (${foundCount} found, ${failedCount} failed)`;
      markSearchHistory(jobId, {
        state: "done",
        results_count: (job.results || []).length,
      });
      renderResults(job, "results");
      return;
    }
    if (job.state === "failed") {
      statusEl.textContent = "Failed: " + (job.error || "unknown");
      markSearchHistory(jobId, {
        state: "failed",
        error: job.error || "unknown",
      });
      return;
    }
    const results = job.results || [];
    const foundCount = results.filter((r) => r.status === "found").length;
    const failedCount = results.filter(
      (r) =>
        r.status === "error" ||
        r.status === "unknown" ||
        r.status === "blocked",
    ).length;
    statusEl.textContent = `Running... (${foundCount} found, ${failedCount} failed so far)`;
    if (job.results && job.results.length > 0) {
      renderResults(job, "results");
    }
  }
}

window.loadJob = async function (jobId) {
  await loadView("search");
  const statusEl = document.getElementById("status");
  if (statusEl) statusEl.textContent = `Loading job ${jobId}...`;

  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error("Job not found");
    const job = await res.json();

    if (job.state === "running") {
      if (statusEl) statusEl.textContent = `Job ${jobId} running...`;
      renderResults(job, "results");
      await monitorJob(jobId);
    } else {
      renderResults(job, "results");
      if (statusEl)
        statusEl.textContent = `Loaded job ${jobId} (${job.state}).`;
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = "Error loading job: " + e.message;
  }
};

async function startScan() {
  const usernameEl = document.getElementById("username");
  const statusEl = document.getElementById("status");
  const enableFaceSearchEl = document.getElementById("enableFaceSearch");
  const faceImagesEl = document.getElementById("faceImages");

  const username = (usernameEl?.value || "").trim();
  if (!username) {
    statusEl.textContent = "Enter a username.";
    return;
  }

  const useFaceSearch = enableFaceSearchEl?.checked;
  const faceImages = faceImagesEl?.files || [];

  let res;
  if (useFaceSearch) {
    if (faceImages.length === 0) {
      statusEl.textContent = "Select at least one image file for face search.";
      return;
    }
    statusEl.textContent = "Starting face scan...";
    const formData = new FormData();
    formData.append("username", username);
    for (const file of faceImages) {
      formData.append("files", file);
    }
    res = await fetch("/api/face-search", {
      method: "POST",
      body: formData,
    });
  } else {
    const providers = selectedProviders();
    statusEl.textContent = "Starting scan...";
    res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, providers }),
    });
  }

  const data = await res.json().catch(() => ({}));
  const jobId = data.job_id;
  if (!jobId) {
    statusEl.textContent = "Failed to start.";
    return;
  }

  localStorage.setItem("socialhunt_last_job", jobId);
  addSearchHistoryEntry({
    username,
    providers: useFaceSearch ? ["face-search"] : selectedProviders(),
    job_id: jobId,
  });

  statusEl.textContent = `Job ${jobId} running...`;

  await monitorJob(jobId);
}

/**
 * Renders a specialized, detailed view for breach search results.
 * Handles both HIBP (breach list) and BreachVIP (detailed records).
 */
function renderBreachView(job, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const results = job.results || [];
  let html = "";

  // 0. Top Summary Stats
  const hibpCount =
    results.find((r) => r.provider === "hibp")?.profile?.breach_count || 0;
  const bvipCount =
    results.find((r) => r.provider === "breachvip")?.profile?.result_count || 0;

  if (hibpCount > 0 || bvipCount > 0) {
    html += `
      <div class="row" style="margin-bottom: 20px; gap: 15px;">
        ${
          hibpCount > 0
            ? `
          <div class="card" style="flex: 1; text-align: center; border-bottom: 3px solid var(--danger);">
            <div style="font-size: 2rem; font-weight: 800; color: var(--danger);">${hibpCount}</div>
            <div class="muted">Known Breaches (HIBP)</div>
          </div>
        `
            : ""
        }
        ${
          bvipCount > 0
            ? `
          <div class="card" style="flex: 1; text-align: center; border-bottom: 3px solid var(--good);">
            <div style="font-size: 2rem; font-weight: 800; color: var(--good);">${bvipCount}</div>
            <div class="muted">Detailed Records (BreachVIP)</div>
          </div>
        `
            : ""
        }
      </div>
    `;
  }

  // 1. Provider Errors / Skips (General)
  results.forEach((r) => {
    if (r.status !== "found" && r.status !== "not_found") {
      const isCloudflare =
        r.http_status === 403 || (r.error && r.error.includes("Cloudflare"));
      const color =
        r.status === "blocked" || (r.error && r.error.includes("API key"))
          ? "var(--warn)"
          : "var(--danger)";

      let manualLink = "";
      if (r.provider === "breachvip" && isCloudflare) {
        manualLink = `
          <div style="margin-top: 10px;">
            <a href="https://breach.vip/" target="_blank" class="btn small good" style="display: inline-block;">
              Open Breach.VIP (Manual Search)
            </a>
          </div>
        `;
      }

      html += `
        <div class="card" style="margin-bottom: 15px; border-left: 5px solid ${color}; padding: 12px 14px;">
          <div class="muted"><strong>${r.provider.toUpperCase()}:</strong> ${escapeHtml(r.error || `Status: ${r.status}`)}</div>
          ${manualLink}
        </div>
      `;
    }
  });

  // 2. Have I Been Pwned Matches
  const hibpResult = results.find((r) => r.provider === "hibp");
  if (hibpResult && hibpResult.status === "found") {
    const prof = hibpResult.profile || {};
    html += `
      <div class="card" style="margin-bottom: 20px; border-left: 5px solid var(--danger);">
        <div style="font-size: 1.2rem; font-weight: 800; color: var(--danger); margin-bottom: 8px;">
          ⚠️ Have I Been Pwned: ${prof.breach_count || 0} Breaches
        </div>
        <div class="muted" style="line-height: 1.6;">
          ${(prof.breaches || []).join(" • ")}
        </div>
      </div>
    `;
  }

  // 3. BreachVIP Detailed Records
  const bvip = results.find((r) => r.provider === "breachvip");
  if (bvip && bvip.status === "found") {
    const prof = bvip.profile || {};
    const raw = prof.raw_results || [];

    if (raw.length > 0) {
      // Determine columns dynamically from data
      const exclude = [
        "_id",
        "id",
        "index",
        "source",
        "breach",
        "database",
        "origin",
      ];
      const keys = new Set();
      raw.forEach((row) => {
        Object.keys(row).forEach((k) => {
          if (!exclude.includes(k) && row[k]) keys.add(k);
        });
      });
      const headerKeys = Array.from(keys).sort();

      html += `
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <div style="font-size: 1.1rem; font-weight: 800;">Detailed Breach Records</div>
            <div class="badge">${bvipCount} Results</div>
          </div>
          <div class="tablewrap">
            <table style="font-size: 13px; border-radius: 8px;">
              <thead>
                <tr>
                  <th>Source / Origin</th>
                  ${headerKeys.map((k) => `<th>${escapeHtml(k)}</th>`).join("")}
                </tr>
              </thead>
              <tbody>
                ${raw
                  .map((row) => {
                    const src =
                      row.source ||
                      row.breach ||
                      row.database ||
                      row.origin ||
                      "Unknown";
                    return `
                    <tr>
                      <td style="font-weight:bold; color: var(--good);">${escapeHtml(
                        src,
                      )}</td>
                      ${headerKeys
                        .map(
                          (k) => `<td>${escapeHtml(String(row[k] || ""))}</td>`,
                        )
                        .join("")}
                    </tr>
                  `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }
  }

  if (!html && job.state === "done") {
    html = `
      <div class="card" style="text-align: center; padding: 40px;">
        <div class="muted" style="font-size: 1.1rem;">No breach data found for "<strong>${escapeHtml(
          job.username,
        )}</strong>".</div>
      </div>
    `;
  }

  container.innerHTML = html;
}

async function initSearchView() {
  const loadBtn = document.getElementById("loadProviders");
  const allBtn = document.getElementById("selectAll");
  const noneBtn = document.getElementById("selectNone");
  const startBtn = document.getElementById("start");
  const statusEl = document.getElementById("status");
  const whoEl = document.getElementById("whoami");
  const enableFaceSearchEl = document.getElementById("enableFaceSearch");
  const faceSearchContainerEl = document.getElementById("faceSearchContainer");

  enableFaceSearchEl.onchange = () => {
    faceSearchContainerEl.style.display = enableFaceSearchEl.checked
      ? "block"
      : "none";
  };

  loadBtn.onclick = async () => {
    statusEl.textContent = "Loading providers...";
    let names = await fetchProviders();
    // Exclude breach-specific providers from general search
    names = names.filter((n) => n !== "hibp" && n !== "breachvip");
    renderProviders(names);
    statusEl.textContent = `Loaded ${names.length} providers.`;
  };

  allBtn.onclick = () => {
    document
      .querySelectorAll('input[type="checkbox"][data-name]')
      .forEach((x) => (x.checked = true));
  };

  noneBtn.onclick = () => {
    document
      .querySelectorAll('input[type="checkbox"][data-name]')
      .forEach((x) => (x.checked = false));
  };

  startBtn.onclick = startScan;

  // auto-load
  let names = await fetchProviders();
  // Exclude breach-specific providers from general search
  names = names.filter((n) => n !== "hibp" && n !== "breachvip");
  renderProviders(names);

  const who = await fetchWhoami();
  if (who && who.client_ip) {
    const via = who.via ? ` (${who.via})` : "";
    whoEl.textContent = `Your IP (as seen by the API): ${who.client_ip}${via}`;
  } else {
    whoEl.textContent = "";
  }
}

// ----------------------
// Reverse image
// ----------------------
function initReverseView() {
  const img = document.getElementById("imageUrl");
  const out = document.getElementById("reverseOut");
  const btn = document.getElementById("reverseGo");
  const uploadBtn = document.getElementById("reverseUploadGo");
  const uploadFile = document.getElementById("reverseUploadFile");

  function render(links, previewUrl, warning) {
    const linkHtml = (links || [])
      .map(
        (x) =>
          `<div class="linkrow"><a target="_blank" rel="noreferrer" href="${x.url}">${x.name}</a></div>`,
      )
      .join("");

    let previewHtml = "";
    if (previewUrl) {
      previewHtml = `
      <div style="margin-bottom:10px">
        <a href="${previewUrl}" target="_blank">
          <img src="${previewUrl}" style="max-height:100px;border-radius:4px;border:1px solid #444">
        </a>
        <div style="margin-top:8px; display:flex; gap:8px;">
            <input type="text" readonly value="${escapeHtml(
              previewUrl,
            )}" style="flex:1; padding:4px;" onclick="this.select()">
            <button class="btn small" onclick="navigator.clipboard.writeText(this.previousElementSibling.value).then(()=>alert('Copied!'))">Copy URL</button>
        </div>
        <p class="muted" style="font-size:0.8em; margin-top:4px">
            Use "Copy URL" for manual uploads (PimEyes, FaceCheck.ID).
        </p>
      </div>`;
    }

    const warningHtml = warning
      ? `<div class="warning" style="margin-bottom:10px; border:1px solid #c77; background:#411; padding:8px; border-radius:4px;">${escapeHtml(
          warning,
        )}</div>`
      : "";

    out.innerHTML = warningHtml + previewHtml + linkHtml;
  }

  if (btn) {
    btn.onclick = async () => {
      const image_url = img.value.trim();
      if (!image_url) return alert("Paste an image URL.");

      out.innerHTML = '<div class="muted">Searching...</div>';

      const r = await fetch("/api/reverse_image_links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_url }),
      });

      const j = await r.json().catch(() => ({}));
      if (!r.ok) return alert(j.detail || `Failed (${r.status})`);

      // Save local history
      addReverseHistoryEntry({ image_url, links: j.links || [] });

      render(j.links, image_url);
    };
  }

  if (uploadBtn) {
    uploadBtn.onclick = async () => {
      const file = uploadFile?.files[0];
      if (!file) return alert("Select an image file.");

      out.innerHTML = '<div class="muted">Uploading...</div>';

      const fd = new FormData();
      fd.append("file", file);

      const r = await fetch("/api/reverse_image_upload", {
        method: "POST",
        body: fd,
      });

      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        out.innerHTML = `<div class="danger">Error: ${escapeHtml(
          j.detail || "Upload failed",
        )}</div>`;
        return;
      }

      // Save local history
      addReverseHistoryEntry({ image_url: j.image_url, links: j.links || [] });

      const warn = j.is_private_ip
        ? "Warning: Your server appears to be on a private IP (localhost). External engines (Google Lens, etc.) cannot download this image. Use a public URL or a tunnel."
        : null;

      render(j.links, j.image_url, warn);
    };
  }
}

// ----------------------
// History
// ----------------------
function fmtWhen(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch (_) {
    return "";
  }
}

function initHistoryView() {
  const searchBody = document.getElementById("searchHistoryBody");
  const reverseBody = document.getElementById("reverseHistoryBody");
  const searchEmpty = document.getElementById("searchHistoryEmpty");
  const reverseEmpty = document.getElementById("reverseHistoryEmpty");
  const clearSearch = document.getElementById("searchHistoryClear");
  const clearReverse = document.getElementById("reverseHistoryClear");
  const refreshBtn = document.getElementById("historyRefresh");

  function render() {
    // Search
    const searches = loadJsonArray(KEY_SEARCH_HISTORY);
    if (searchEmpty)
      searchEmpty.style.display = searches.length ? "none" : "block";
    if (searchBody) {
      searchBody.innerHTML = searches
        .map((x) => {
          const providers = x.providers_count ?? "";
          const job = x.job_id ? escapeHtml(x.job_id) : "";
          const results =
            (x.results_count ?? "") +
            (x.state ? ` (${escapeHtml(x.state)})` : "");

          let action = escapeHtml(String(results));
          if (x.job_id) {
            action += ` <button class="btn small" style="margin-left:10px" onclick="loadJob('${escapeHtml(
              x.job_id,
            )}')">View</button>`;
          }

          return `<tr>
          <td>${escapeHtml(fmtWhen(x.ts))}</td>
          <td>${escapeHtml(x.username || "")}</td>
          <td>${escapeHtml(String(providers))}</td>
          <td>${job}</td>
          <td>${action}</td>
        </tr>`;
        })
        .join("");
    }

    // Reverse
    const reverses = loadJsonArray(KEY_REVERSE_HISTORY);
    if (reverseEmpty)
      reverseEmpty.style.display = reverses.length ? "none" : "block";
    if (reverseBody) {
      reverseBody.innerHTML = reverses
        .map((x) => {
          const img = x.image_url || "";
          const links = Array.isArray(x.links) ? x.links : [];
          const linkHtml = links
            .slice(0, 4)
            .map((l) => {
              const name = escapeHtml(l.name || "Link");
              const url = escapeHtml(l.url || "#");
              return `<a class="mini-link" target="_blank" rel="noreferrer" href="${url}">${name}</a>`;
            })
            .join(" ");
          const more =
            links.length > 4
              ? ` <span class="muted">+${links.length - 4} more</span>`
              : "";
          return `<tr>
          <td>${escapeHtml(fmtWhen(x.ts))}</td>
          <td>${escapeHtml(img)}</td>
          <td>${linkHtml}${more}</td>
        </tr>`;
        })
        .join("");
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
// Tokens
// ----------------------
function initTokensView() {
  const input = document.getElementById("tokenInput");
  const save = document.getElementById("tokenSave");
  const clear = document.getElementById("tokenClear");

  const statusEl = document.getElementById("adminStatus");
  const serverTokenInput = document.getElementById("serverTokenInput");
  const bootstrapSecretInput = document.getElementById("bootstrapSecretInput");
  const serverTokenSet = document.getElementById("serverTokenSet");

  input.value = getToken() || "";
  save.onclick = () => setToken(input.value.trim());
  clear.onclick = () => {
    input.value = "";
    setToken("");
  };

  async function loadStatus() {
    try {
      const r = await fetch("/api/admin/status", { cache: "no-store" });
      const j = await r.json().catch(() => ({}));
      if (statusEl) statusEl.textContent = JSON.stringify(j, null, 2);

      // If bootstrap secret is not required, hide the field to reduce confusion
      if (bootstrapSecretInput && !j.bootstrap_secret_required) {
        bootstrapSecretInput.style.display = "none";
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = "Failed to load status.";
    }
  }

  if (serverTokenSet) {
    serverTokenSet.onclick = async () => {
      const newTok = (serverTokenInput?.value || "").trim();
      if (!newTok) return alert("Enter a new server admin token.");

      const headers = authHeaders({ "Content-Type": "application/json" });
      const boot = (bootstrapSecretInput?.value || "").trim();
      if (boot) headers["X-Bootstrap-Secret"] = boot;

      const r = await fetch("/api/admin/token", {
        method: "PUT",
        headers,
        body: JSON.stringify({ token: newTok }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) return alert(j.detail || `Failed (${r.status})`);

      // Store locally too so the next privileged request works
      setToken(newTok);
      input.value = newTok;
      alert("Server token set.");
      await loadStatus();
    };
  }

  loadStatus();
}

// ----------------------
// Plugins
// ----------------------
function initPluginsView() {
  const fileEl = document.getElementById("pluginFile");
  const uploadBtn = document.getElementById("pluginUpload");
  const reloadBtn = document.getElementById("pluginReload");
  const outEl = document.getElementById("pluginOut");

  function setOut(msg) {
    if (outEl) outEl.textContent = msg;
  }

  uploadBtn.onclick = async () => {
    if (!getToken()) return alert("Set token first (Token page).");
    if (!fileEl.files?.length) return alert("Choose a plugin file.");

    const fd = new FormData();
    fd.append("file", fileEl.files[0]);

    const r = await fetch("/api/plugin/upload", {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });

    const j = await r.json().catch(() => ({}));
    if (!r.ok) return alert(j.detail || `Upload failed (${r.status})`);

    setOut(JSON.stringify(j, null, 2));
  };

  reloadBtn.onclick = async () => {
    if (!getToken()) return alert("Set token first (Token page).");
    const r = await fetch("/api/providers/reload", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
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
  const tableBody = document.querySelector("#settingsTable tbody");
  const addBtn = document.getElementById("settingsAdd");
  const saveBtn = document.getElementById("settingsSave");
  const reloadBtn = document.getElementById("settingsReload");
  const msgEl = document.getElementById("settingsMsg");
  const publicUrlInput = document.getElementById("public_url");
  const savePublicUrlBtn = document.getElementById("saveSettings");
  const updateBtn = document.getElementById("updateBtn"); // Assuming this exists now
  const updateLog = document.getElementById("updateLog"); // Assuming this exists now

  function showMsg(txt) {
    msgEl.style.display = "block";
    msgEl.textContent = txt;
  }

  function rowHtml(key = "", val = "", secret = false, isSet = false) {
    const displayVal = secret ? (isSet ? "•••••• (set)" : "") : (val ?? "");
    return `
      <tr>
        <td><input class="input s-key" placeholder="e.g. hibp_api_key" value="${escapeHtml(key)}"></td>
        <td><input class="input s-val" placeholder="value" value="${escapeHtml(displayVal)}"></td>
        <td style="text-align:center"><input type="checkbox" class="s-secret" ${secret ? "checked" : ""}></td>
        <td><button class="btn danger s-del" type="button">Remove</button></td>
      </tr>
    `;
  }

  function bindRowEvents() {
    tableBody.querySelectorAll(".s-del").forEach((btn) => {
      btn.onclick = () => btn.closest("tr").remove();
    });
  }

  async function load() {
    if (!getToken()) {
      tableBody.innerHTML = "";
      showMsg("Set token first (Token page).");
      return;
    }

    tableBody.innerHTML = "";
    const r = await fetch("/api/settings", { headers: authHeaders() });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      showMsg(j.detail || `Failed (${r.status})`);
      return;
    }

    const settings = j.settings || {};

    if (settings.public_url && publicUrlInput) {
      publicUrlInput.value = settings.public_url.value || "";
    }

    for (const [k, meta] of Object.entries(settings)) {
      if (k === "public_url") continue; // Handled separately
      tableBody.insertAdjacentHTML(
        "beforeend",
        rowHtml(k, meta.value, meta.secret, meta.is_set),
      );
    }

    bindRowEvents();
    showMsg("Loaded.");
  }

  addBtn.onclick = () => {
    tableBody.insertAdjacentHTML("beforeend", rowHtml());
    bindRowEvents();
  };

  saveBtn.onclick = async () => {
    if (!getToken()) return alert("Set token first (Token page).");

    const rows = [...tableBody.querySelectorAll("tr")];
    const out = {};

    for (const tr of rows) {
      const k = tr.querySelector(".s-key").value.trim();
      const v = tr.querySelector(".s-val").value;
      const secret = tr.querySelector(".s-secret").checked;
      if (!k) continue;

      // If secret and user left placeholder, don't overwrite
      if (secret && (v === "•••••• (set)" || v.trim() === "")) continue;
      out[k] = v;
    }

    const r = await fetch("/api/settings", {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ settings: out }),
    });

    const j = await r.json().catch(() => ({}));
    if (!r.ok) return showMsg(j.detail || `Save failed (${r.status})`);

    showMsg("Saved. Reloading…");
    await load();
  };

  reloadBtn.onclick = load;

  if (savePublicUrlBtn) {
    savePublicUrlBtn.onclick = async () => {
      const val = publicUrlInput.value.trim();
      const r = await fetch("/api/settings", {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ settings: { public_url: val } }),
      });

      if (r.ok) {
        alert("Public URL saved.");
        load();
      } else {
        alert("Failed to save.");
      }
    };
  }

  // UPDATE SYSTEM (Re-added)
  if (updateBtn) {
    updateBtn.onclick = async () => {
      if (!confirm("Are you sure you want to pull updates from GitHub?"))
        return;

      updateBtn.disabled = true;
      updateLog.style.display = "block";
      updateLog.textContent = "Updating...";

      try {
        const r = await fetch("/api/admin/update", {
          method: "POST",
          headers: authHeaders(),
        });
        const j = await r.json();

        if (j.ok) {
          updateLog.textContent =
            (j.stdout || "") + "\n" + (j.message || "Update finished.");
          alert(
            "Update successful. Please restart the server manually if necessary.",
          );
        } else {
          updateLog.textContent =
            (j.stderr || "") + "\n" + (j.error || "Update failed.");
          alert("Update failed.");
        }
      } catch (e) {
        updateLog.textContent = "Error: " + e.message;
      } finally {
        updateBtn.disabled = false;
      }
    };
  }

  load();
}

// ----------------------
// Init
// ----------------------
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const logoutBtn = document.querySelector("[data-action='logout']");
if (logoutBtn) {
  logoutBtn.onclick = () => {
    setToken("");
    location.reload();
  };
}

document.querySelectorAll(".menu-btn[data-view]").forEach((btn) => {
  btn.onclick = () => loadView(btn.dataset.view);
});

renderTokenStatus();

if (!getToken()) {
  window.location.replace("/login");
} else {
  fetch("/api/auth/verify", { method: "POST", headers: authHeaders() })
    .then((res) => {
      if (res.ok) {
        loadView("dashboard");
      } else {
        setToken("");
        window.location.replace("/login");
      }
    })
    .catch(() => loadView("dashboard"));
}
