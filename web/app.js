const viewContainer = document.getElementById("viewContainer");
const viewTitle = document.getElementById("viewTitle");
const tokenStatus = document.getElementById("tokenStatus");
const menuToggle = document.getElementById("menuToggle");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");

// ---- toasts ----
let toastEl = null;
let toastTimer = null;
function showToast(message, duration = 2000) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "toast";
    toastEl.setAttribute("role", "status");
    toastEl.setAttribute("aria-live", "polite");
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = message;
  toastEl.style.display = "block";
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    if (toastEl) toastEl.remove();
    toastEl = null;
  }, duration);
}

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

function getCacheBust() {
  return localStorage.getItem("sh_cache_bust") || "2.2.2";
}

const viewTitles = {
  dashboard: "Dashboard",
  search: "Search",
  "breach-search": "Breach Search",
  reverse: "Reverse Image",
  history: "History",
  "secure-notes": "Secure Notes",
  demask: "Demasking",
  iopaint: "IOPaint Inpainting",
  deepmosaic: "DeepMosaic", // Add this line
  plugins: "Plugins",
  tokens: "Token",
  settings: "Settings",
};

// Update the loadView function (around line 39)
async function loadView(name) {
  document.querySelectorAll(".menu-btn[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });

  const demaskSubmenu = document.getElementById("demaskSubmenu");
  const demaskToggle = document.querySelector(
    '.menu-toggle-btn[data-menu-toggle="demask"]',
  );
  const demaskBtn = document.querySelector('.menu-btn[data-view="demask"]');
  const isDemaskGroup =
    name === "demask" || name === "iopaint" || name === "deepmosaic";
  if (demaskSubmenu && demaskToggle) {
    demaskSubmenu.classList.toggle("is-open", isDemaskGroup);
    demaskToggle.setAttribute(
      "aria-expanded",
      isDemaskGroup ? "true" : "false",
    );
  }
  if (demaskBtn) {
    demaskBtn.classList.toggle("active", name === "demask");
    demaskBtn.classList.toggle(
      "active-parent",
      name === "iopaint" || name === "deepmosaic",
    );
  }

  viewTitle.textContent = viewTitles[name] || name;

  const res = await fetch(`/static/views/${name}.html?v=${getCacheBust()}`, {
    cache: "no-store",
  });
  viewContainer.innerHTML = await res.text();

  if (name === "dashboard") initDashboardView();
  if (name === "search") initSearchView();
  if (name === "breach-search") initBreachSearchView();
  if (name === "reverse") initReverseView();
  if (name === "history") initHistoryView();
  if (name === "plugins") initPluginsView();
  if (name === "tokens") initTokensView();
  if (name === "settings") initSettingsView();
  if (name === "secure-notes") initSecureNotesView();
  if (name === "demask") initDemaskView();
  if (name === "iopaint") initIOPaintView(); // Add this line
  if (name === "deepmosaic") initDeepMosaicView(); // Add this line
}

// ----------------------
// Local history (browser only)
// ----------------------
const HISTORY_MAX = 200;
const KEY_SEARCH_HISTORY = "socialhunt_search_history";
const KEY_REVERSE_HISTORY = "sh_reverse_history";
const KEY_DEMASK_HISTORY = "sh_demask_history";
const RESULTS_RENDER_LIMIT = 300;
const RESULTS_RENDER_INTERVAL_MS = 2000;
const RESULTS_POLL_INTERVAL_MS = 2000;

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

function addSearchHistoryEntry({
  username,
  providers,
  job_id,
  type = "search",
}) {
  const items = loadJsonArray(KEY_SEARCH_HISTORY);
  items.unshift({
    ts: Date.now(),
    username,
    providers_count: (providers || []).length,
    job_id,
    results_count: null,
    state: "running",
    type,
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

function addDemaskHistoryEntry(original_src, result_data_url) {
  const items = loadJsonArray(KEY_DEMASK_HISTORY);
  items.unshift({
    ts: Math.floor(Date.now() / 1000),
    original: original_src,
    result: result_data_url,
  });
  saveJsonArray(KEY_DEMASK_HISTORY, items);
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
  const res = await fetch("/sh-api/providers");
  const data = await res.json();
  return data.providers || [];
}

async function fetchJob(jobId, opts = {}) {
  const params = new URLSearchParams();
  if (typeof opts.limit === "number" && opts.limit >= 0) {
    params.set("limit", String(opts.limit));
  }
  const qs = params.toString();
  const url = qs ? `/sh-api/jobs/${jobId}?${qs}` : `/sh-api/jobs/${jobId}`;
  const res = await fetch(url, opts.headers ? { headers: opts.headers } : {});
  if (!res.ok) throw new Error("Job not found");
  return await res.json();
}

async function fetchWhoami() {
  try {
    const res = await fetch("/sh-api/whoami");
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

function renderResults(job, containerId, opts = {}) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`renderResults: container #${containerId} not found.`);
    return;
  }

  const results = job.results || [];
  const total =
    typeof opts.total === "number" && opts.total >= 0
      ? opts.total
      : results.length;
  const limit =
    typeof opts.limit === "number" && opts.limit >= 0
      ? opts.limit
      : results.length;
  const renderResults = results.slice(0, limit);
  const isPartial = renderResults.length < total;
  const rows = renderResults
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

  const dlBtn =
    job.state === "done"
      ? `
    <div style="margin-bottom: 12px; display: flex; justify-content: flex-end; gap: 8px;">
      <button class="btn" id="note-btn-${job.job_id}">Save to Notes</button>
      <button class="btn" id="dl-btn-csv-${job.job_id}">Download CSV</button>
      <button class="btn" id="dl-btn-${job.job_id}">Download JSON</button>
    </div>
  `
      : "";

  const partialNote = isPartial
    ? `
      <div class="muted" style="margin-bottom: 10px;">
        Showing first ${renderResults.length} of ${total} results while scan is running.
        Full results will render when done. You can also download JSON/CSV after completion.
      </div>
    `
    : "";

  container.innerHTML = `
    ${dlBtn}
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
    ${partialNote}
  `;

  const btn = document.getElementById(`dl-btn-${job.job_id}`);
  if (btn) {
    btn.onclick = async () => {
      btn.textContent = "Downloading...";
      btn.disabled = true;
      try {
        const fullJob = await fetchJob(job.job_id);
        fullJob.type = "search";
        downloadJob(fullJob, "json");
      } catch (e) {
        alert("Error downloading: " + e.message);
      } finally {
        btn.textContent = "Download JSON";
        btn.disabled = false;
      }
    };
  }
  const btnCsv = document.getElementById(`dl-btn-csv-${job.job_id}`);
  if (btnCsv) {
    btnCsv.onclick = async () => {
      btnCsv.textContent = "Downloading...";
      btnCsv.disabled = true;
      try {
        const fullJob = await fetchJob(job.job_id);
        fullJob.type = "search";
        downloadJob(fullJob, "csv");
      } catch (e) {
        alert("Error downloading: " + e.message);
      } finally {
        btnCsv.textContent = "Download CSV";
        btnCsv.disabled = false;
      }
    };
  }
  const btnNote = document.getElementById(`note-btn-${job.job_id}`);
  if (btnNote) {
    btnNote.onclick = async () => {
      btnNote.textContent = "Saving...";
      btnNote.disabled = true;
      try {
        let fullJob = job;
        // If results seem truncated, fetch full
        if ((job.results || []).length < (job.results_count || 0)) {
          fullJob = await fetchJob(job.job_id);
        }
        const text = (fullJob.results || [])
          .map((r) => {
            const p = r.profile || {};
            return `[${r.provider}] ${r.status} - ${r.url || "No URL"}\n   Name: ${p.display_name || ""}\n   Note: ${p.note || r.error || ""}`;
          })
          .join("\n\n");
        const title = `Search: ${fullJob.username || "results"}`;
        if (window.addNoteDirectly) {
          window.addNoteDirectly(title, text);
        } else {
          alert("Please go to Secure Notes and unlock them first.");
        }
      } catch (e) {
        alert("Error saving note: " + e.message);
      } finally {
        btnNote.textContent = "Save to Notes";
        btnNote.disabled = false;
      }
    };
  }
}

// ----------------------
// Breach Search
// ----------------------
async function initBreachSearchView() {
  const termEl = document.getElementById("breachTerm");
  const startBtn = document.getElementById("startBreachScan");
  const statusEl = document.getElementById("breachStatus");

  startBtn.onclick = async () => {
    let term = (termEl?.value || "").trim();

    // Auto-normalize phone numbers (strip spaces, dashes, etc. if result is purely numeric)
    const stripped = term.replace(/[\s\-\(\)\+]/g, "");
    if (stripped.length >= 7 && /^\d+$/.test(stripped)) {
      term = stripped;
    }

    if (!term) {
      statusEl.textContent = "Enter a search term.";
      return;
    }

    statusEl.textContent = "Starting scan...";
    document.getElementById("breachResults").innerHTML = "";

    const res = await fetch("/sh-api/search", {
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
      type: "breach",
    });

    statusEl.textContent = `Job ${jobId} running...`;
    await monitorJob(jobId, "breachResults", "breachStatus", true);
  };
}

async function monitorJob(
  jobId,
  containerId = "results",
  statusId = "status",
  isBreach = false,
) {
  const statusEl = document.getElementById(statusId);
  if (!statusEl) return;
  let lastRenderAt = 0;
  let lastRenderCount = -1;
  let pollMs = RESULTS_POLL_INTERVAL_MS;
  let errorCount = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, pollMs));
    if (!document.body.contains(statusEl)) break;

    let job;
    try {
      job = await fetchJob(jobId, { limit: RESULTS_RENDER_LIMIT });
      errorCount = 0;
    } catch (e) {
      if (++errorCount > 5) {
        statusEl.textContent = "Error: Connection lost.";
        break;
      }
      continue;
    }

    if (!job || !job.state) continue;

    if (job.state === "done") {
      const finalJob = await fetchJob(jobId);
      const results = finalJob.results || [];
      const foundCount =
        finalJob.found_count ??
        results.filter((r) => r.status === "found").length;
      const failedCount =
        finalJob.failed_count ??
        results.filter(
          (r) =>
            r.status === "error" ||
            r.status === "unknown" ||
            r.status === "blocked" ||
            r.status === "not_found",
        ).length;
      statusEl.textContent = `Done. (${foundCount} found, ${failedCount} failed)`;
      markSearchHistory(jobId, {
        state: "done",
        results_count: results.length,
        found_count: foundCount,
        failed_count: failedCount,
      });
      if (isBreach) renderBreachView(finalJob, containerId);
      else renderResults(finalJob, containerId);
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
    const resultsCount =
      job.results_count ??
      job.results_total ??
      (Array.isArray(results) ? results.length : 0);
    const foundCount =
      job.found_count ?? results.filter((r) => r.status === "found").length;
    const failedCount =
      job.failed_count ??
      results.filter(
        (r) =>
          r.status === "error" ||
          r.status === "unknown" ||
          r.status === "blocked" ||
          r.status === "not_found",
      ).length;
    const totalProviders = job.providers_count;
    const progressText =
      typeof totalProviders === "number" && totalProviders > 0
        ? ` (${resultsCount}/${totalProviders} done)`
        : "";
    statusEl.textContent = `Running... (${foundCount} found, ${failedCount} failed so far)${progressText}`;
    if (results.length > 0) {
      const now = Date.now();
      const count = resultsCount;
      const shouldRender =
        count !== lastRenderCount &&
        now - lastRenderAt >= RESULTS_RENDER_INTERVAL_MS;
      if (shouldRender) {
        if (isBreach) renderBreachView(job, containerId);
        else {
          const limit =
            results.length > RESULTS_RENDER_LIMIT
              ? RESULTS_RENDER_LIMIT
              : results.length;
          const total =
            job.results_total ??
            job.results_count ??
            (Array.isArray(results) ? results.length : 0);
          renderResults(job, containerId, { limit, total });
        }
        lastRenderAt = now;
        lastRenderCount = count;
      }
    }

    pollMs =
      typeof totalProviders === "number" && totalProviders > 500
        ? 3000
        : RESULTS_POLL_INTERVAL_MS;

    if (job.state !== "running" && job.state !== "pending") break;
  }
}

window.loadJob = async function (jobId) {
  const items = loadJsonArray(KEY_SEARCH_HISTORY);
  const entry = items.find((x) => x && x.job_id === jobId);
  const type = entry?.type || "search";
  const viewName = type === "breach" ? "breach-search" : "search";
  const containerId = type === "breach" ? "breachResults" : "results";
  const statusId = type === "breach" ? "breachStatus" : "status";
  const isBreach = type === "breach";

  await loadView(viewName);
  const statusEl = document.getElementById(statusId);
  if (statusEl) statusEl.textContent = `Loading job ${jobId}...`;

  try {
    const job = await fetchJob(jobId, {
      headers: authHeaders(),
      limit: RESULTS_RENDER_LIMIT,
    });

    if (job.state === "running") {
      if (statusEl) statusEl.textContent = `Job ${jobId} running...`;
      if (isBreach) renderBreachView(job, containerId);
      else {
        const count = job.results_total ?? (job.results || []).length;
        const limit =
          (job.results || []).length > RESULTS_RENDER_LIMIT
            ? RESULTS_RENDER_LIMIT
            : (job.results || []).length;
        renderResults(job, containerId, { limit, total: count });
      }
      await monitorJob(jobId, containerId, statusId, isBreach);
    } else {
      const finalJob =
        job.state === "done"
          ? await fetchJob(jobId, { headers: authHeaders() })
          : job;
      if (isBreach) renderBreachView(finalJob, containerId);
      else renderResults(finalJob, containerId);
      if (statusEl)
        statusEl.textContent = `Loaded job ${jobId} (${finalJob.state}).`;
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
    res = await fetch("/sh-api/face-search", {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });
  } else {
    const providers = selectedProviders();
    statusEl.textContent = "Starting scan...";
    res = await fetch("/sh-api/search", {
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
    type: "search",
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

  if (job.state === "done" && results.length > 0) {
    html += `
      <div style="margin-bottom: 12px; display: flex; justify-content: flex-end; gap: 8px;">
        <button class="btn" id="note-breach-${job.job_id}">Save to Notes</button>
        <button class="btn" id="dl-breach-csv-${job.job_id}">Download CSV</button>
        <button class="btn" id="dl-breach-${job.job_id}">Download JSON</button>
      </div>
    `;
  }

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
      if (prof.demo_mode) {
        html += `
          <div class="card" style="border-left: 4px solid var(--warn); background: rgba(255, 193, 7, 0.05);">
            <div style="color: var(--warn); font-weight: 800; margin-bottom: 5px;">DEMO MODE ACTIVE</div>
            <div class="muted" style="font-size: 0.9rem;">
              Personal information has been censored and results are limited to 5 records for demonstration purposes.
            </div>
          </div>
        `;
      }
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

      const isTruncated = raw.length > 500;
      const displayRows = isTruncated ? raw.slice(0, 500) : raw;

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
                ${displayRows
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
                        .map((k) => {
                          const val = row[k];
                          let display =
                            val && typeof val === "object"
                              ? JSON.stringify(val)
                              : String(val || "");

                          // Data truncation to prevent UI hangs on massive fields
                          if (display.length > 256) {
                            display = display.substring(0, 253) + "...";
                          }
                          return `<td>${escapeHtml(display)}</td>`;
                        })
                        .join("")}
                    </tr>
                  `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
          ${
            isTruncated
              ? `<div class="muted" style="text-align:center; padding: 10px;">Showing first 500 of ${raw.length} results. Export for full data.</div>`
              : ""
          }
        </div>
      `;
    }
  }

  if (job.state === "running") {
    html += `
      <div class="card" style="text-align: center; padding: 20px; border: 1px dashed var(--border);">
        <div class="muted" style="font-size: 1rem;">
          <span class="spinner"></span> Still scanning for additional data...
        </div>
      </div>
    `;
  }

  if (!html) {
    if (job.state === "done") {
      html = `
        <div class="card" style="text-align: center; padding: 40px;">
          <div class="muted" style="font-size: 1.1rem;">No breach data found for "<strong>${escapeHtml(
            job.username,
          )}</strong>".</div>
        </div>
      `;
    } else {
      html = `
        <div class="card" style="text-align: center; padding: 40px;">
          <div class="muted" style="font-size: 1.1rem;">
            <span class="spinner"></span> Searching for breach data...
          </div>
        </div>
      `;
    }
  }

  container.innerHTML = html;

  const btn = document.getElementById(`dl-breach-${job.job_id}`);
  if (btn) {
    btn.onclick = async () => {
      btn.textContent = "Downloading...";
      btn.disabled = true;
      try {
        const fullJob = await fetchJob(job.job_id);
        fullJob.type = "breach-search";
        downloadJob(fullJob, "json");
      } catch (e) {
        alert("Error downloading: " + e.message);
      } finally {
        btn.textContent = "Download JSON";
        btn.disabled = false;
      }
    };
  }
  const btnCsv = document.getElementById(`dl-breach-csv-${job.job_id}`);
  if (btnCsv) {
    btnCsv.onclick = async () => {
      btnCsv.textContent = "Downloading...";
      btnCsv.disabled = true;
      try {
        const fullJob = await fetchJob(job.job_id);
        fullJob.type = "breach-search";
        downloadJob(fullJob, "csv");
      } catch (e) {
        alert("Error downloading: " + e.message);
      } finally {
        btnCsv.textContent = "Download CSV";
        btnCsv.disabled = false;
      }
    };
  }
  const btnNote = document.getElementById(`note-breach-${job.job_id}`);
  if (btnNote) {
    btnNote.onclick = async () => {
      btnNote.textContent = "Saving...";
      btnNote.disabled = true;
      try {
        let text = `Breach Search: ${job.username || job.term}\n\n`;
        const hibp = (job.results || []).find((r) => r.provider === "hibp");
        if (hibp && hibp.profile?.breaches) {
          text += `HIBP Breaches:\n- ${hibp.profile.breaches.join("\n- ")}\n\n`;
        }
        const bvip = (job.results || []).find(
          (r) => r.provider === "breachvip",
        );
        if (bvip && bvip.profile?.raw_results) {
          text += `BreachVIP Detailed Records:\n`;
          bvip.profile.raw_results.forEach((row) => {
            text += `--- ${row.source || row.breach || "Record"} ---\n`;
            Object.entries(row).forEach(([k, v]) => {
              if (v && typeof v !== "object") text += `${k}: ${v}\n`;
            });
            text += "\n";
          });
        }
        if (window.addNoteDirectly) {
          window.addNoteDirectly(`Breach: ${job.username || job.term}`, text);
        } else {
          alert("Please go to Secure Notes and unlock them first.");
        }
      } catch (e) {
        alert("Error saving note: " + e.message);
      } finally {
        btnNote.textContent = "Save to Notes";
        btnNote.disabled = false;
      }
    };
  }
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

      const r = await fetch("/sh-api/reverse_image_links", {
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

      const r = await fetch("/sh-api/reverse_image_upload", {
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
  const demaskBody = document.getElementById("demaskHistoryBody");
  const searchEmpty = document.getElementById("searchHistoryEmpty");
  const reverseEmpty = document.getElementById("reverseHistoryEmpty");
  const demaskEmpty = document.getElementById("demaskHistoryEmpty");
  const clearSearch = document.getElementById("searchHistoryClear");
  const clearReverse = document.getElementById("reverseHistoryClear");
  const clearDemask = document.getElementById("demaskHistoryClear");
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
          let resText =
            (x.results_count ?? "") + (x.state ? ` (${x.state})` : "");
          if (x.found_count !== undefined && x.failed_count !== undefined) {
            resText = `${x.found_count} found, ${x.failed_count} failed`;
          }
          let action = escapeHtml(resText);
          if (x.job_id) {
            action += ` <button class="btn small" style="margin-left:10px" onclick="loadJob('${escapeHtml(
              x.job_id,
            )}')">View</button>`;
          }

          const typeBadge =
            x.type === "breach"
              ? `<span class="badge" style="color:var(--danger); border-color:rgba(255,100,100,0.2); background:rgba(255,100,100,0.05); margin-right:6px;">Breach</span>`
              : `<span class="badge" style="margin-right:6px;">Search</span>`;

          return `<tr>
          <td>${escapeHtml(fmtWhen(x.ts))}</td>
          <td>${typeBadge}${escapeHtml(x.username || "")}</td>
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

    // Demask
    const demasks = loadJsonArray(KEY_DEMASK_HISTORY);
    if (demaskEmpty)
      demaskEmpty.style.display = demasks.length ? "none" : "block";
    if (demaskBody) {
      demaskBody.innerHTML = demasks
        .map((x) => {
          return `<tr>
          <td>${escapeHtml(fmtWhen(x.ts))}</td>
          <td><img src="${x.original}" style="max-height:50px; cursor:pointer; border-radius:4px" onclick="window.open(this.src)"></td>
          <td><img src="${x.result}" style="max-height:50px; cursor:pointer; border-radius:4px" onclick="window.open(this.src)"></td>
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
  if (clearDemask) {
    clearDemask.onclick = () => {
      localStorage.removeItem(KEY_DEMASK_HISTORY);
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
      const r = await fetch("/sh-api/admin/status", { cache: "no-store" });
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

      const r = await fetch("/sh-api/admin/token", {
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
  const listContainer = document.getElementById("installedPlugins");
  const refreshListBtn = document.getElementById("pluginRefreshList");

  function setOut(msg) {
    if (outEl) outEl.textContent = msg;
  }

  async function refreshList() {
    if (!listContainer) return;
    if (!getToken()) {
      listContainer.innerHTML = '<p class="muted">Admin token required.</p>';
      return;
    }
    listContainer.innerHTML = '<p class="muted">Loading...</p>';
    try {
      const r = await fetch("/sh-api/plugin/list", { headers: authHeaders() });
      const j = await r.json();
      if (!r.ok) {
        listContainer.innerHTML = `<p class="error">${
          j.detail || "Failed to load"
        }</p>`;
        return;
      }
      renderList(j);
    } catch (e) {
      listContainer.innerHTML = `<p class="error">Error: ${e.message}</p>`;
    }
  }

  function renderList(data) {
    let html = "";

    const groups = [
      {
        title: "YAML Providers",
        items: data.yaml_providers || [],
      },
      {
        title: "Python Providers",
        items: data.python_providers || [],
      },
      {
        title: "Python Addons",
        items: data.python_addons || [],
      },
    ];

    groups.forEach((g) => {
      if (g.items.length === 0) return;
      html += `<h4>${g.title}</h4><ul style="list-style:none; padding:0;">`;
      g.items.forEach((item) => {
        html += `
             <li style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px; padding:8px; border-bottom:1px solid var(--border);">
                <span style="font-family:monospace;">${escapeHtml(item)}</span>
                <button class="btn danger small delete-plugin-btn" data-name="${escapeHtml(
                  item,
                )}">Delete</button>
             </li>`;
      });
      html += `</ul>`;
    });

    if (!html) html = '<p class="muted">No plugins installed.</p>';
    listContainer.innerHTML = html;

    listContainer.querySelectorAll(".delete-plugin-btn").forEach((btn) => {
      btn.onclick = async () => {
        const name = btn.getAttribute("data-name");
        if (!confirm(`Delete plugin "${name}"? This cannot be undone.`)) return;

        const r = await fetch("/sh-api/plugin/delete", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ name }),
        });
        const j = await r.json().catch(() => ({}));
        if (r.ok) {
          refreshList();
        } else {
          alert(j.detail || "Delete failed");
        }
      };
    });
  }

  if (refreshListBtn) refreshListBtn.onclick = refreshList;
  if (getToken()) refreshList();

  uploadBtn.onclick = async () => {
    if (!getToken()) return alert("Set token first (Token page).");
    if (!fileEl.files?.length) return alert("Choose a plugin file.");

    const fd = new FormData();
    fd.append("file", fileEl.files[0]);

    const r = await fetch("/sh-api/plugin/upload", {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });

    const j = await r.json().catch(() => ({}));
    if (!r.ok) return alert(j.detail || `Upload failed (${r.status})`);

    setOut(JSON.stringify(j, null, 2));
    refreshList();
  };

  reloadBtn.onclick = async () => {
    if (!getToken()) return alert("Set token first (Token page).");
    const r = await fetch("/sh-api/providers/reload", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return alert(j.detail || `Reload failed (${r.status})`);
    setOut(JSON.stringify(j, null, 2));
    refreshList();
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
  const themeSelect = document.getElementById("themeSelect");
  const saveThemeBtn = document.getElementById("saveTheme");
  const updateBtn = document.getElementById("updateBtn"); // Assuming this exists now
  const updateLog = document.getElementById("updateLog"); // Assuming this exists now
  const restartBtn = document.getElementById("restartBtn");
  const demoModeToggle = document.getElementById("demoModeToggle");
  const saveDemoModeBtn = document.getElementById("saveDemoMode");
  let demoModeSaving = false;
  let originalSettingKeys = new Set();

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
    const r = await fetch("/sh-api/settings", { headers: authHeaders() });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      showMsg(j.detail || `Failed (${r.status})`);
      return;
    }

    const settings = j.settings || {};
    originalSettingKeys = new Set(Object.keys(settings));

    if (settings.public_url && publicUrlInput) {
      publicUrlInput.value = settings.public_url.value || "";
    }

    if (settings.theme && themeSelect) {
      themeSelect.value = settings.theme.value || "default";
    }

    if (demoModeToggle) {
      const raw = settings.demo_mode?.value;
      const enabled =
        raw === true ||
        raw === 1 ||
        raw === "1" ||
        (typeof raw === "string" && raw.toLowerCase() === "true");
      demoModeToggle.checked = !!enabled;
    }

    for (const [k, meta] of Object.entries(settings)) {
      if (
        k === "public_url" ||
        k === "theme" ||
        k === "replicate_api_token" ||
        k === "demo_mode"
      )
        continue; // Handled separately
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
    const presentKeys = new Set();
    const secretKeys = new Set();

    for (const tr of rows) {
      const k = tr.querySelector(".s-key").value.trim();
      const v = tr.querySelector(".s-val").value;
      const secret = tr.querySelector(".s-secret").checked;
      if (!k) continue;
      presentKeys.add(k);
      if (secret) secretKeys.add(k);

      // If secret and user left placeholder, don't overwrite
      if (secret && (v === "•••••• (set)" || v.trim() === "")) continue;
      out[k] = v;
    }

    const skipDelete = new Set([
      "public_url",
      "theme",
      "replicate_api_token",
      "demo_mode",
    ]);

    for (const key of originalSettingKeys) {
      if (skipDelete.has(key)) continue;
      if (!presentKeys.has(key)) {
        out[key] = null;
      }
    }

    out.__secret_keys = Array.from(secretKeys);

    const r = await fetch("/sh-api/settings", {
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
      const r = await fetch("/sh-api/settings", {
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

  async function saveThemeSelection(theme) {
    const r = await fetch("/sh-api/settings", {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ settings: { theme } }),
    });

    if (r.ok) {
      if (theme && theme !== "default") {
        document.body.setAttribute("data-theme", theme);
      } else {
        document.body.removeAttribute("data-theme");
      }
      showToast("Theme saved.");
    } else {
      showToast("Failed to update theme.");
    }
  }

  if (themeSelect) {
    themeSelect.addEventListener("change", () => {
      const theme = themeSelect.value;
      saveThemeSelection(theme);
    });
  }

  if (saveThemeBtn) {
    saveThemeBtn.onclick = () => {
      const theme = themeSelect ? themeSelect.value : "default";
      saveThemeSelection(theme);
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
        const r = await fetch("/sh-api/admin/update", {
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

  if (restartBtn) {
    restartBtn.onclick = async () => {
      if (
        !confirm("Restart the server now? This will disconnect your session.")
      )
        return;

      restartBtn.disabled = true;
      if (updateLog) {
        updateLog.style.display = "block";
        updateLog.textContent = "Restarting server...";
      }

      try {
        const r = await fetch("/sh-api/admin/restart", {
          method: "POST",
          headers: authHeaders(),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) {
          const msg = j.detail || j.error || `Restart failed (${r.status})`;
          if (updateLog) updateLog.textContent = msg;
          alert(msg);
          restartBtn.disabled = false;
          return;
        }
        if (updateLog) {
          updateLog.textContent = j.message || "Restarting server...";
        }
      } catch (e) {
        if (updateLog) updateLog.textContent = "Error: " + e.message;
        restartBtn.disabled = false;
      }
    };
  }

  async function updateDemoMode() {
    if (!demoModeToggle) return;
    if (!getToken()) {
      demoModeToggle.checked = !demoModeToggle.checked;
      return alert("Set token first (Token page).");
    }
    if (demoModeSaving) return;
    demoModeSaving = true;
    const demo_mode = demoModeToggle.checked;
    const originalText = saveDemoModeBtn ? saveDemoModeBtn.textContent : "";
    if (saveDemoModeBtn) {
      saveDemoModeBtn.disabled = true;
      saveDemoModeBtn.textContent = "Saving...";
    }
    try {
      const r = await fetch("/sh-api/settings", {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ settings: { demo_mode } }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        demoModeToggle.checked = !demo_mode;
        return showMsg(j.detail || `Save failed (${r.status})`);
      }
      showMsg("Demo mode updated. Reloading...");
      localStorage.setItem("sh_cache_bust", String(Date.now()));
      setTimeout(() => {
        window.location.replace(`/?v=${Date.now()}`);
      }, 300);
    } finally {
      demoModeSaving = false;
      if (saveDemoModeBtn) {
        saveDemoModeBtn.disabled = false;
        saveDemoModeBtn.textContent = originalText || "Save";
      }
    }
  }

  if (demoModeToggle) {
    if (saveDemoModeBtn) saveDemoModeBtn.onclick = updateDemoMode;
    demoModeToggle.addEventListener("change", updateDemoMode);
  }

  load();
}

// ----------------------
// Secure Notes
// ----------------------
async function initSecureNotesView() {
  const authDiv = document.getElementById("notesAuth");
  const managerDiv = document.getElementById("notesManager");
  const masterPasswordInput = document.getElementById("masterPassword");
  const unlockBtn = document.getElementById("unlockNotesBtn");
  const resetBtn = document.getElementById("resetNotesBtn");

  const notesList = document.getElementById("notesList");
  const noteEditor = document.getElementById("noteEditor");
  const noNoteSelected = document.getElementById("noNoteSelected");

  const noteTitleInput = document.getElementById("noteTitle");
  const noteContentInput = document.getElementById("noteContent");
  const saveNoteBtn = document.getElementById("saveNoteBtn");
  const closeNoteBtn = document.getElementById("closeNoteBtn");
  const deleteNoteBtn = document.getElementById("deleteNoteBtn");
  const createNewNoteBtn = document.getElementById("createNewNoteBtn");
  const exportNotesBtn = document.getElementById("exportNotesBtn");
  const importNotesBtn = document.getElementById("importNotesBtn");
  const importFileInput = document.getElementById("importFile");
  const lockNotesBtn = document.getElementById("lockNotesBtn");
  const noteStatus = document.getElementById("noteStatus");

  let currentKey = null;
  let notes = [];
  let currentNoteId = null;

  const STORAGE_KEY = "sh_secure_notes_blob";

  // --- Encryption Helpers ---
  async function deriveKey(password, salt) {
    const enc = new TextEncoder();
    const baseKey = await crypto.subtle.importKey(
      "raw",
      enc.encode(password),
      "PBKDF2",
      false,
      ["deriveKey"],
    );
    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt: salt,
        iterations: 100000,
        hash: "SHA-256",
      },
      baseKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  }

  async function encrypt(data, key) {
    const enc = new TextEncoder();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encrypted = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      enc.encode(JSON.stringify(data)),
    );
    return {
      iv: btoa(String.fromCharCode(...iv)),
      data: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
    };
  }

  async function decrypt(encryptedObj, key) {
    const iv = new Uint8Array(
      atob(encryptedObj.iv)
        .split("")
        .map((c) => c.charCodeAt(0)),
    );
    const data = new Uint8Array(
      atob(encryptedObj.data)
        .split("")
        .map((c) => c.charCodeAt(0)),
    );
    const decrypted = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv },
      key,
      data,
    );
    return JSON.parse(new TextDecoder().decode(decrypted));
  }

  // --- Logic ---
  let currentSalt = null;

  async function saveToDisk() {
    if (!currentKey || !currentSalt) return;
    const encrypted = await encrypt(notes, currentKey);
    const blob = {
      salt: btoa(String.fromCharCode(...currentSalt)),
      iv: encrypted.iv,
      data: encrypted.data,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(blob));
  }

  function renderList() {
    if (!notes.length) {
      notesList.innerHTML =
        '<div class="muted" style="text-align: center; padding: 20px;">No notes found.</div>';
      return;
    }
    notesList.innerHTML = notes
      .map(
        (n) => `
      <div class="note-item ${n.id === currentNoteId ? "active" : ""}" data-id="${n.id}">
        ${escapeHtml(n.title || "Untitled Note")}
      </div>
    `,
      )
      .join("");

    notesList.querySelectorAll(".note-item").forEach((el) => {
      el.onclick = () => selectNote(el.dataset.id);
    });
  }

  function selectNote(id) {
    currentNoteId = id;
    const note = notes.find((n) => n.id === id);
    if (!note) return;

    noNoteSelected.style.display = "none";
    noteEditor.style.display = "block";
    noteTitleInput.value = note.title || "";
    noteContentInput.value = note.content || "";
    noteStatus.textContent = "";
    renderList();
  }

  masterPasswordInput.onkeydown = (e) => {
    if (e.key === "Enter") unlockBtn.click();
  };

  if (resetBtn) {
    resetBtn.onclick = () => {
      if (
        confirm(
          "Are you sure you want to delete ALL secure notes and reset storage? This cannot be undone.",
        )
      ) {
        localStorage.removeItem(STORAGE_KEY);
        alert("Storage reset. You can now initialize a new master password.");
        location.reload();
      }
    };
  }

  unlockBtn.onclick = async () => {
    const pwd = masterPasswordInput.value;
    if (!pwd) return alert("Enter a password.");

    const raw = localStorage.getItem(STORAGE_KEY);
    try {
      if (raw) {
        const blob = JSON.parse(raw);
        currentSalt = new Uint8Array(
          atob(blob.salt)
            .split("")
            .map((c) => c.charCodeAt(0)),
        );
        currentKey = await deriveKey(pwd, currentSalt);
        notes = await decrypt(blob, currentKey);
      } else {
        // Initialize new
        currentSalt = crypto.getRandomValues(new Uint8Array(16));
        currentKey = await deriveKey(pwd, currentSalt);
        notes = [];
        await saveToDisk();
      }
      authDiv.style.display = "none";
      managerDiv.style.display = "block";
      renderList();
    } catch (e) {
      console.error(e);
      alert("Invalid password or corrupted data.");
    }
  };

  createNewNoteBtn.onclick = () => {
    const id = crypto.randomUUID();
    notes.unshift({
      id,
      title: "New Note",
      content: "",
      ts: new Date().getTime(),
    });
    selectNote(id);
    saveToDisk();
  };

  saveNoteBtn.onclick = async () => {
    const note = notes.find((n) => n.id === currentNoteId);
    if (!note) return;
    note.title = noteTitleInput.value;
    note.content = noteContentInput.value;
    note.ts = new Date().getTime();
    await saveToDisk();
    noteStatus.textContent = "Saved at " + new Date().toLocaleTimeString();
    renderList();
  };

  deleteNoteBtn.onclick = async () => {
    if (!confirm("Delete this note?")) return;
    notes = notes.filter((n) => n.id !== currentNoteId);
    currentNoteId = null;
    noteEditor.style.display = "none";
    noNoteSelected.style.display = "block";
    await saveToDisk();
    renderList();
  };

  closeNoteBtn.onclick = () => {
    currentNoteId = null;
    noteEditor.style.display = "none";
    noNoteSelected.style.display = "block";
    renderList();
  };

  exportNotesBtn.onclick = () => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return alert("No notes to export.");
    const blob = new Blob([raw], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sh_secure_notes_backup_${new Date().getTime()}.json`;
    a.click();
  };

  importNotesBtn.onclick = () => {
    importFileInput.click();
  };

  importFileInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (ev) => {
      try {
        const importedData = JSON.parse(ev.target.result);
        if (!importedData.salt || !importedData.iv || !importedData.data) {
          throw new Error("Invalid file format.");
        }

        if (
          !confirm(
            "Importing this backup will overwrite your current notes. Continue?",
          )
        )
          return;

        // Try to decrypt the imported file with current key to verify password
        const salt = new Uint8Array(
          atob(importedData.salt)
            .split("")
            .map((c) => c.charCodeAt(0)),
        );

        // Note: Decryption will only work if master password matches the one used for the backup
        // We attempt decryption here to validate.
        const decrypted = await decrypt(importedData, currentKey);

        // If successful, update local state
        notes = decrypted;
        currentSalt = salt;
        await saveToDisk();
        renderList();
        alert("Import successful!");
      } catch (err) {
        console.error(err);
        alert(
          "Import failed: Password mismatch or corrupted file. Ensure you are using the same master password that was used for the backup.",
        );
      }
      importFileInput.value = "";
    };
    reader.readAsText(file);
  };

  lockNotesBtn.onclick = () => {
    currentKey = null;
    notes = [];
    currentNoteId = null;
    masterPasswordInput.value = "";
    authDiv.style.display = "block";
    managerDiv.style.display = "none";
    window.addNoteDirectly = null;
  };

  window.addNoteDirectly = async (title, content) => {
    if (!currentKey) {
      alert("Please unlock your Secure Notes first.");
      return;
    }
    const id = crypto.randomUUID();
    notes.unshift({ id, title, content, ts: new Date().getTime() });
    await saveToDisk();
    alert("Saved to Secure Notes!");
  };
}

// ----------------------
// Demasking
// ----------------------
async function initDemaskView() {
  const uploadInput = document.getElementById("demaskUpload");
  const previewContainer = document.getElementById("demaskPreviewContainer");
  const originalPreview = document.getElementById("demaskOriginalPreview");
  const startBtn = document.getElementById("startDemaskBtn");
  const statusEl = document.getElementById("demaskStatus");
  const resultContainer = document.getElementById("demaskResultContainer");
  const placeholder = document.getElementById("demaskPlaceholder");
  const resultImg = document.getElementById("demaskResultImg");
  const actions = document.getElementById("demaskActions");
  const downloadBtn = document.getElementById("downloadDemaskBtn");
  const saveToNotesBtn = document.getElementById("saveDemaskToNotesBtn");

  if (!uploadInput) return;

  uploadInput.onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      originalPreview.src = ev.target.result;
      previewContainer.style.display = "block";
      startBtn.disabled = false;
    };
    reader.readAsDataURL(file);
  };

  startBtn.onclick = async () => {
    const file = uploadInput.files[0];
    if (!file) return;

    statusEl.textContent = "Processing... (This may take a minute)";
    startBtn.disabled = true;
    placeholder.innerHTML =
      '<span class="spinner"></span> Analyzing and Inpainting...';
    resultImg.style.display = "none";
    actions.style.display = "none";

    const fd = new FormData();
    fd.append("file", file);

    try {
      const res = await fetch("/sh-api/demask", {
        method: "POST",
        headers: authHeaders(),
        body: fd,
      });

      if (!res.ok) {
        const errorText = await res.text();
        let errorMessage = "Demasking failed";
        try {
          const errorJson = JSON.parse(errorText);
          errorMessage = errorJson.detail || errorMessage;
        } catch (e) {
          errorMessage = errorText || errorMessage;
        }
        throw new Error(errorMessage);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      // Add to history
      const reader = new FileReader();
      reader.onloadend = () => {
        addDemaskHistoryEntry(originalPreview.src, reader.result);
      };
      reader.readAsDataURL(blob);

      resultImg.src = url;
      resultImg.style.display = "block";
      placeholder.style.display = "none";
      actions.style.display = "flex";
      statusEl.textContent = "Processing complete.";

      downloadBtn.onclick = () => {
        const a = document.createElement("a");
        a.href = url;
        a.download = `demasked_${new Date().getTime()}.png`;
        a.click();
      };

      saveToNotesBtn.onclick = () => {
        if (window.addNoteDirectly) {
          const noteText = `Demasking Result\nOriginal: ${file.name}\nProcessed: AI generated reconstruction of facial features.`;
          window.addNoteDirectly("Demasking Analysis", noteText);
        } else {
          alert("Please unlock your Secure Notes first.");
        }
      };
    } catch (e) {
      statusEl.textContent = "Error: " + e.message;
      placeholder.innerHTML =
        '<div class="danger">Failed to process image.</div>';
      placeholder.style.display = "block";
    } finally {
      startBtn.disabled = false;
    }
  };
}

// ----------------------
// IOPaint Inpainting
// ----------------------
async function initIOPaintView() {
  // Elements
  const statusText = document.getElementById("statusText");
  const serverControls = document.getElementById("serverControls");
  const serverInfo = document.getElementById("serverInfo");
  const serverPort = document.getElementById("serverPort");
  const startServerBtn = document.getElementById("startServerBtn");
  const stopServerBtn = document.getElementById("stopServerBtn");
  const openIOPaintBtn = document.getElementById("openIOPaintBtn");
  const modelSelect = document.getElementById("modelSelect");
  const deviceSelect = document.getElementById("deviceSelect");
  const portInput = document.getElementById("portInput");

  if (!statusText) return; // Safety check

  // Check IOPaint installation
  async function checkIOPaintInstallation() {
    try {
      const response = await fetch("/sh-api/iopaint/check");
      const data = await response.json();

      if (!data.installed) {
        statusText.innerHTML =
          '<span style="color: var(--danger);">IOPaint not installed</span>';
        showToast(
          "IOPaint is not installed. Install it with: pip install iopaint",
          "danger",
        );
        return false;
      }

      return true;
    } catch (error) {
      statusText.innerHTML =
        '<span style="color: var(--danger);">Error checking installation</span>';
      console.error("Error checking IOPaint:", error);
      return false;
    }
  }

  // Check server status
  async function checkServerStatus() {
    try {
      const response = await fetch("/sh-api/iopaint/status");
      const data = await response.json();

      if (data.running) {
        statusText.innerHTML = `<span style="color: var(--good);">Running on port ${data.port}</span>`;
        if (serverControls) serverControls.style.display = "none";
        if (serverInfo) serverInfo.style.display = "block";
        if (serverPort) serverPort.textContent = data.port;
        if (portInput) portInput.value = data.port;
      } else {
        statusText.innerHTML =
          '<span style="color: var(--muted);">Stopped</span>';
        if (serverControls) serverControls.style.display = "block";
        if (serverInfo) serverInfo.style.display = "none";

        // Check available devices
        await checkAvailableDevices();
      }
    } catch (error) {
      statusText.innerHTML =
        '<span style="color: var(--danger);">Error checking status</span>';
      console.error("Error checking server status:", error);
    }
  }

  // Check available devices
  async function checkAvailableDevices() {
    try {
      const response = await fetch("/sh-api/iopaint/devices");
      const data = await response.json();

      // Update device select options
      if (deviceSelect) {
        const cudaOption = deviceSelect.querySelector('option[value="cuda"]');
        const mpsOption = deviceSelect.querySelector('option[value="mps"]');

        if (cudaOption) {
          cudaOption.disabled = !data.cuda;
          if (!data.cuda) {
            cudaOption.textContent = "CUDA (Not Available)";
          }
        }

        if (mpsOption) {
          mpsOption.disabled = !data.mps;
          if (!data.mps) {
            mpsOption.textContent = "MPS (Not Available)";
          }
        }

        // Select best available device
        if (data.cuda) {
          deviceSelect.value = "cuda";
        } else if (data.mps) {
          deviceSelect.value = "mps";
        } else {
          deviceSelect.value = "cpu";
        }
      }
    } catch (error) {
      console.error("Error checking devices:", error);
    }
  }

  // Start server
  async function startServer() {
    if (!startServerBtn) return;
    startServerBtn.disabled = true;
    startServerBtn.innerHTML = '<span class="spinner"></span> Starting...';

    try {
      const response = await fetch("/sh-api/iopaint/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: modelSelect ? modelSelect.value : "lama",
          device: deviceSelect ? deviceSelect.value : "cpu",
          port: portInput ? parseInt(portInput.value) : 8080,
        }),
      });

      const data = await response.json();

      if (data.success) {
        showToast("IOPaint server started successfully", "good");
        // Wait a moment for server to initialize
        setTimeout(checkServerStatus, 1000);
      } else {
        showToast(`Failed to start server: ${data.error}`, "danger");
        startServerBtn.disabled = false;
        startServerBtn.innerHTML = "Start Server";
      }
    } catch (error) {
      showToast(`Error starting server: ${error.message}`, "danger");
      startServerBtn.disabled = false;
      startServerBtn.innerHTML = "Start Server";
    }
  }

  // Stop server
  async function stopServer() {
    if (!stopServerBtn) return;
    stopServerBtn.disabled = true;
    stopServerBtn.innerHTML = '<span class="spinner"></span> Stopping...';

    try {
      const response = await fetch("/sh-api/iopaint/stop", {
        method: "POST",
      });

      const data = await response.json();

      if (data.success) {
        showToast("IOPaint server stopped", "good");
        setTimeout(checkServerStatus, 500);
      } else {
        showToast(`Failed to stop server: ${data.error}`, "danger");
      }
    } catch (error) {
      showToast(`Error stopping server: ${error.message}`, "danger");
    } finally {
      stopServerBtn.disabled = false;
      stopServerBtn.innerHTML = "Stop Server";
    }
  }

  // Open IOPaint WebUI
  function openIOPaint() {
    const port = serverPort
      ? serverPort.textContent
      : portInput
        ? portInput.value
        : "8080";
    void port;
    window.open("/iopaint/", "_blank");
  }

  // Add toast function if not exists
  window.showToast =
    window.showToast ||
    function (message, type = "") {
      const toast = document.createElement("div");
      toast.className = "toast";
      if (type) toast.classList.add(type);
      toast.textContent = message;
      document.body.appendChild(toast);

      setTimeout(() => {
        toast.remove();
      }, 3000);
    };

  // Event listeners
  if (startServerBtn) startServerBtn.addEventListener("click", startServer);
  if (stopServerBtn) stopServerBtn.addEventListener("click", stopServer);
  if (openIOPaintBtn) openIOPaintBtn.addEventListener("click", openIOPaint);

  // Initialize
  async function init() {
    const installed = await checkIOPaintInstallation();
    if (installed) {
      await checkServerStatus();

      // Check status every 10 seconds
      setInterval(checkServerStatus, 10000);
    }
  }

  init();
}

// DeepMosaic View
async function initDeepMosaicView() {
  const uploadInput = document.getElementById("dmUpload");
  const previewDiv = document.getElementById("dmPreview");
  const processBtn = document.getElementById("dmProcessBtn");
  const statusDiv = document.getElementById("dmStatus");
  const statusText = document.getElementById("dmStatusText");
  const progressDiv = document.getElementById("dmProgress");
  const resultsDiv = document.getElementById("dmResults");
  const resultPreview = document.getElementById("dmResultPreview");
  const downloadBtn = document.getElementById("dmDownloadBtn");
  const saveNotesBtn = document.getElementById("dmSaveNotesBtn");
  const clearBtn = document.getElementById("dmClearBtn");
  const statusInfoDiv = document.getElementById("dmStatusContent");
  const refreshStatusBtn = document.getElementById("dmRefreshStatus");

  let currentJobId = null;
  let currentFileType = null;

  // Check DeepMosaic status
  async function checkDeepMosaicStatus() {
    try {
      statusInfoDiv.innerHTML =
        '<div class="spinner"></div> Checking DeepMosaic status...';
      const response = await fetch("/sh-api/deepmosaic/status");
      const data = await response.json();

      if (data.available) {
        statusInfoDiv.innerHTML = `
                    <div style="color: var(--good); font-weight: bold;">
                        ✓ DeepMosaic Available
                    </div>
                    <div class="muted" style="font-size: 12px; margin-top: 5px;">
                        AI mosaic processing ready
                    </div>
                `;
        processBtn.disabled = false;
      } else {
        statusInfoDiv.innerHTML = `
                    <div style="color: var(--danger); font-weight: bold;">
                        ✗ DeepMosaic Not Available
                    </div>
                    <div class="muted" style="font-size: 12px; margin-top: 5px;">
                        ${data.message || "DeepMosaic module not found"}
                    </div>
                `;
        processBtn.disabled = true;
      }
    } catch (error) {
      statusInfoDiv.innerHTML = `
                <div style="color: var(--danger); font-weight: bold;">
                    ✗ Connection Error
                </div>
                <div class="muted" style="font-size: 12px; margin-top: 5px;">
                    Failed to check DeepMosaic status
                </div>
            `;
      processBtn.disabled = true;
    }
  }

  // File upload preview
  if (uploadInput) {
    uploadInput.onchange = function (e) {
      const file = e.target.files[0];
      if (!file) return;

      previewDiv.innerHTML = "";

      const isVideo = file.type.startsWith("video/");
      currentFileType = isVideo ? "video" : "image";

      const reader = new FileReader();
      reader.onload = function (e) {
        if (isVideo) {
          previewDiv.innerHTML = `
                        <video controls style="max-width: 300px; max-height: 200px; border-radius: 8px;">
                            <source src="${e.target.result}" type="${file.type}">
                            Your browser does not support video tag.
                        </video>
                        <div class="muted" style="margin-top: 5px;">
                            ${file.name} (${Math.round(file.size / 1024)} KB)
                        </div>
                    `;
        } else {
          previewDiv.innerHTML = `
                        <img src="${e.target.result}" style="max-width: 300px; max-height: 200px; border-radius: 8px;">
                        <div class="muted" style="margin-top: 5px;">
                            ${file.name} (${Math.round(file.size / 1024)} KB)
                        </div>
                    `;
        }
      };
      reader.readAsDataURL(file);
    };
  }

  // Process button
  if (processBtn) {
    processBtn.onclick = async function () {
      const file = uploadInput.files[0];
      if (!file) {
        alert("Please select a file first");
        return;
      }

      const mode = document.querySelector('input[name="dmMode"]:checked').value;
      const mosaicType = document.getElementById("dmMosaicType").value;
      const quality = document.getElementById("dmQuality").value;

      // Disable button and show status
      processBtn.disabled = true;
      processBtn.textContent = "Processing...";
      statusDiv.style.display = "block";
      statusText.textContent = "Uploading and processing...";
      progressDiv.innerHTML =
        '<div class="spinner"></div> Starting DeepMosaic...';

      // Prepare form data
      const formData = new FormData();
      formData.append("file", file);
      formData.append("mode", mode);
      formData.append("mosaic_type", mosaicType);
      formData.append("quality", quality);

      try {
        const response = await fetch("/sh-api/deepmosaic/process", {
          method: "POST",
          headers: authHeaders(),
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`Server error: ${response.status}`);
        }

        // Get the blob (image or video)
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        // Extract job ID from filename
        const filename = response.headers.get("content-disposition");
        const jobMatch = filename && filename.match(/deepmosaic_(\w+)_/);
        currentJobId = jobMatch ? jobMatch[1] : Date.now().toString();

        // Show results
        resultsDiv.style.display = "block";
        if (blob.type.startsWith("video/")) {
          resultPreview.innerHTML = `
                        <h4>Processed Video</h4>
                        <video controls style="max-width: 400px; max-height: 300px; border-radius: 8px;">
                            <source src="${url}" type="${blob.type}">
                            Your browser does not support video tag.
                        </video>
                    `;
        } else {
          resultPreview.innerHTML = `
                        <h4>Processed Image</h4>
                        <img src="${url}" style="max-width: 400px; max-height: 300px; border-radius: 8px;">
                    `;
        }

        // Update status
        statusText.textContent = "Processing complete!";
        progressDiv.innerHTML = `
                    <div style="color: var(--good); font-weight: bold;">
                        ✓ DeepMosaic processing completed successfully
                    </div>
                `;

        // Setup download button
        downloadBtn.onclick = function () {
          const a = document.createElement("a");
          a.href = url;
          a.download = `deepmosaic_${mode}_${file.name}`;
          a.click();
        };

        // Setup save to notes button
        saveNotesBtn.onclick = function () {
          if (window.addNoteDirectly) {
            const noteContent = `
DeepMosaic Processing:
- File: ${file.name}
- Mode: ${mode}
- Mosaic Type: ${mosaicType}
- Quality: ${quality}
- Timestamp: ${new Date().toLocaleString()}

Results saved with job ID: ${currentJobId}
                        `;
            window.addNoteDirectly(`DeepMosaic: ${file.name}`, noteContent);
          } else {
            alert("Please unlock Secure Notes first");
          }
        };
      } catch (error) {
        statusText.textContent = "Error during processing";
        progressDiv.innerHTML = `
                    <div style="color: var(--danger); font-weight: bold;">
                        ✗ Error: ${error.message}
                    </div>
                `;
      } finally {
        processBtn.disabled = false;
        processBtn.textContent = "Start Processing";
      }
    };
  }

  // Clear button
  if (clearBtn) {
    clearBtn.onclick = function () {
      uploadInput.value = "";
      previewDiv.innerHTML = "";
      statusDiv.style.display = "none";
      resultsDiv.style.display = "none";
      currentJobId = null;
    };
  }

  // Refresh status button
  if (refreshStatusBtn) {
    refreshStatusBtn.onclick = checkDeepMosaicStatus;
  }

  // Initial status check
  checkDeepMosaicStatus();
}

// ----------------------
// Init
// Init
// ----------------------
function downloadJob(job, format = "json") {
  const type = job.type || "search";
  const name = job.username || job.term || "results";
  const baseName = `${type}_${name}_${new Date().getTime()}`;
  let blob;
  let filename;

  if (format === "csv") {
    filename = `${baseName}.csv`;
    let csvContent = "";
    if (type === "breach-search") {
      const results = job.results || [];
      // 1. HIBP Summary
      const hibp = results.find((r) => r.provider === "hibp");
      if (hibp && hibp.profile?.breaches?.length) {
        csvContent += "--- HIBP Breaches ---\n";
        csvContent += hibp.profile.breaches.join("\n") + "\n\n";
      }

      // 2. BreachVIP Detailed
      const bvip = results.find((r) => r.provider === "breachvip");
      const raw = bvip?.profile?.raw_results || [];
      if (raw.length > 0) {
        csvContent += "--- Detailed Records ---\n";
        const allKeys = new Set();
        raw.forEach((row) => Object.keys(row).forEach((k) => allKeys.add(k)));
        const keys = Array.from(allKeys);
        csvContent += keys.join(",") + "\n";
        raw.forEach((row) => {
          csvContent +=
            keys
              .map((k) => `"${String(row[k] ?? "").replace(/"/g, '""')}"`)
              .join(",") + "\n";
        });
      }
      if (!csvContent) csvContent = "No breach data found.";
    } else {
      const rows = job.results || [];
      csvContent =
        "Provider,Status,URL,Display Name,Followers,Following,Created,Notes\n";
      rows.forEach((r) => {
        const p = r.profile || {};
        const notes = [];
        if (p.note) notes.push(p.note);
        if (r.error) notes.push(r.error);
        if (p.face_match)
          notes.push(p.face_match.match ? "FACE MATCH" : "NO FACE MATCH");

        csvContent +=
          [
            r.provider,
            r.status,
            r.url || "",
            p.display_name || "",
            p.followers ?? "",
            p.following ?? "",
            p.created_at ?? "",
            notes.join(" | "),
          ]
            .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
            .join(",") + "\n";
      });
    }
    blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  } else {
    filename = `${baseName}.json`;
    blob = new Blob([JSON.stringify(job, null, 2)], {
      type: "application/json",
    });
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

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

function closeSidebar() {
  document.body.classList.remove("sidebar-open");
}

document.querySelectorAll(".menu-btn[data-view]").forEach((btn) => {
  btn.onclick = () => {
    loadView(btn.dataset.view);
    closeSidebar();
  };
});

document
  .querySelectorAll(".menu-toggle-btn[data-menu-toggle]")
  .forEach((btn) => {
    btn.onclick = () => {
      const target = btn.getAttribute("data-menu-toggle");
      if (target !== "demask") return;
      const submenu = document.getElementById("demaskSubmenu");
      if (!submenu) return;
      const isOpen = submenu.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    };
  });

if (menuToggle) {
  menuToggle.onclick = () => {
    document.body.classList.toggle("sidebar-open");
  };
}

if (sidebarBackdrop) {
  sidebarBackdrop.onclick = closeSidebar;
}

renderTokenStatus();

// Load theme on init
fetch("/sh-api/public/theme")
  .then((res) => res.json())
  .then((j) => {
    if (j.theme && j.theme !== "default") {
      document.body.setAttribute("data-theme", j.theme);
    } else {
      document.body.removeAttribute("data-theme");
    }
  })
  .catch(() => {});

if (!getToken()) {
  window.location.replace("/login");
} else {
  fetch("/sh-api/auth/verify", { method: "POST", headers: authHeaders() })
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

// Check for demo mode
fetchWhoami().then((data) => {
  if (data && data.demo_mode) {
    const badge = document.getElementById("demoBadge");
    if (badge) badge.style.display = "inline-flex";
  }
});
