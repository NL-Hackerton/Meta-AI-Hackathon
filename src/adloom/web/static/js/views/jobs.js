import { app, esc, won, short, when, MAKING, STATE, stateBadge, PHASE, RESOURCE, resourceName, api, toast, errorText, setNav, head, resume, STEPS, stepList } from "../core.js";

/* Jobs */
export let jobFilter = "all";
export async function viewJobs() {
  setNav("jobs");
  const jobs = await api("/api/jobs");
  const count = (fn) => jobs.filter(fn).length;
  const groups = {
    all: () => true,
    approve: (j) => j.state === "AWAITING_APPROVAL" || j.state === "APPROVED",
    making: (j) => MAKING.includes(j.state),
    paused: (j) => j.state === "PUBLISHED_PAUSED",
    failed: (j) => j.state === "FAILED",
  };
  const rows = jobs.filter(groups[jobFilter]).map((j) => {
    const action = j.state === "AWAITING_APPROVAL" ? `<a class="btn small" href="#/jobs/${j.job_id}">Review</a>`
      : j.state === "FAILED" ? `<button class="btn light small" data-resume="${j.job_id}">Resume</button>`
      : `<a class="btn light small" href="#/jobs/${j.job_id}">Open</a>`;
    const notes = j.error ? `${esc(j.error.code)} · ${esc(j.error.stage)}` : j.state === "PUBLISHED_PAUSED" ? `2 ads · ${won(j.daily_budget_krw)}/day` : esc(j.headline || "");
    const thumb = j.thumbnail_url ? `<img class="thumb" src="${esc(j.thumbnail_url)}" alt="">` : `<span class="thumb"></span>`;
    return `<tr><td>${thumb}</td><td>${esc(j.product_name || "Untitled video")}<div class="hint">job ${esc(j.job_id.slice(0, 6))}</div></td>
      <td class="hide-sm">${when(j.created_at)}</td><td class="hide-sm">r${j.revision}</td><td>${stateBadge(j.state)}</td>
      <td class="hide-sm">${notes}</td><td>${action}</td></tr>`;
  }).join("");
  const chip = (key, label) => `<button class="chip" data-filter="${key}" aria-pressed="${jobFilter === key}">${label}</button>`;
  app.innerHTML = head(`${jobs.length} job${jobs.length === 1 ? "" : "s"} on this machine`, "Jobs",
      "Every video you uploaded and where it stands. Nothing goes live without an approval.",
      `<a class="btn coral" href="#/new">New job</a>`) +
    `<div class="metrics">
      <div class="card metric"><span class="hint">To approve</span><b style="color:var(--coral)">${count(groups.approve)}</b></div>
      <div class="card metric"><span class="hint">Making</span><b style="color:var(--violet)">${count(groups.making)}</b></div>
      <div class="card metric"><span class="hint">Paused on Meta</span><b>${count(groups.paused) * 2} ads</b><small>${count(groups.paused)} campaign${count(groups.paused) === 1 ? "" : "s"} · fixture</small></div>
      <div class="card metric"><span class="hint">Needs attention</span><b style="color:var(--danger)">${count(groups.failed)}</b></div>
    </div>` +
    (jobs.length === 0
      ? `<div class="card empty"><b>No videos yet</b><span class="hint">Upload one 3–45 second phone video to get six ad cuts.</span><a class="btn coral" href="#/new">New job</a></div>`
      : `<div class="card"><div class="chips">${chip("all", "All")}${chip("approve", "To approve")}${chip("making", "Making")}${chip("paused", "Paused")}${chip("failed", "Failed")}</div>
        <table><thead><tr><th></th><th>Video</th><th class="hide-sm">Created</th><th class="hide-sm">Revision</th><th>Status</th><th class="hide-sm">Notes</th><th>Action</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="7" class="hint">No jobs in this view.</td></tr>`}</tbody></table></div>`);
  app.querySelectorAll("[data-filter]").forEach((b) => b.onclick = () => { jobFilter = b.dataset.filter; viewJobs(); });
  app.querySelectorAll("[data-resume]").forEach((b) => b.onclick = () => resume(b.dataset.resume, b));
}
