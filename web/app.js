const el = (id) => document.getElementById(id);

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
    const data = await res.json();
    return data;
  } catch (_) {
    return null;
  }
}

function renderProviders(names) {
  const box = el("providers");
  box.innerHTML = names.map(n => `
    <label class="provider">
      <input type="checkbox" data-name="${n}" checked />
      <span>${n}</span>
    </label>
  `).join("");
}

function selectedProviders() {
  return Array.from(document.querySelectorAll('input[type="checkbox"][data-name]'))
    .filter(x => x.checked)
    .map(x => x.getAttribute("data-name"));
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
  }).join("");

  el("results").innerHTML = `
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
  const username = el("username").value.trim();
  if (!username) {
    el("status").textContent = "Enter a username.";
    return;
  }

  const providers = selectedProviders();
  el("status").textContent = "Starting scan...";

  const res = await fetch("/api/search", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ username, providers })
  });

  const data = await res.json();
  const jobId = data.job_id;
  if (!jobId) {
    el("status").textContent = "Failed to start.";
    return;
  }

  el("status").textContent = `Job ${jobId} running...`;

  for (;;) {
    await new Promise(r => setTimeout(r, 1000));
    const jr = await fetch(`/api/jobs/${jobId}`);
    const job = await jr.json();

    if (job.state === "done") {
      el("status").textContent = "Done.";
      renderResults(job);
      return;
    }
    if (job.state === "failed") {
      el("status").textContent = "Failed: " + (job.error || "unknown");
      return;
    }
    el("status").textContent = `Running... (${(job.results || []).length} results so far)`;
  }
}

el("loadProviders").addEventListener("click", async () => {
  el("status").textContent = "Loading providers...";
  const names = await fetchProviders();
  renderProviders(names);
  el("status").textContent = `Loaded ${names.length} providers.`;
});

el("selectAll").addEventListener("click", () => {
  document.querySelectorAll('input[type="checkbox"][data-name]').forEach(x => x.checked = true);
});

el("selectNone").addEventListener("click", () => {
  document.querySelectorAll('input[type="checkbox"][data-name]').forEach(x => x.checked = false);
});

el("start").addEventListener("click", startScan);

// auto-load
(async () => {
  const names = await fetchProviders();
  renderProviders(names);

  const who = await fetchWhoami();
  if (who && who.client_ip) {
    const via = who.via ? ` (${who.via})` : "";
    el("whoami").textContent = `Your IP (as seen by the API): ${who.client_ip}${via}`;
  } else {
    el("whoami").textContent = "";
  }
})();
