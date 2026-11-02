import { app, esc, won, when, MAKING, jobBadge, api, setNav, head } from "../core.js";
import { needsNote, isRunning, isInterrupted, STAGE_LABEL, poll, onRoute } from "../flow.js";

const runLabel = (j) => isRunning(j) ? `Running · ${STAGE_LABEL[j.pending_stage] || "starting"}` : isInterrupted(j) ? "Stopped mid-run · resume" : "Waiting to start";

/* Jobs */
let jobFilter = "all";
let query = "";

export async function viewJobs() {
  setNav("jobs");
  const jobs = await api("/api/jobs");
  const groups = {
    all: () => true,
    approve: (j) => j.state === "AWAITING_APPROVAL" || j.state === "APPROVED",
    making: (j) => MAKING.includes(j.state) && !needsNote(j),
    paused: (j) => j.state === "PUBLISHED_PAUSED",
    failed: (j) => j.state === "FAILED" || needsNote(j),
  };
  const count = (fn) => jobs.filter(fn).length;
  const paused = count(groups.paused);
  const oldestWaiting = jobs.filter(groups.approve).map((j) => j.updated_at).sort()[0];
  const making = jobs.find(groups.making);
  const attention = jobs.find(groups.failed);

  const action = (j) => needsNote(j) ? `<a class="btn small" href="#/jobs/${esc(j.job_id)}">Check</a>`
    : j.state === "AWAITING_APPROVAL" ? `<a class="btn small" href="#/jobs/${esc(j.job_id)}">Review</a>`
    : j.state === "FAILED" || isInterrupted(j) ? `<a class="btn light small" href="#/jobs/${esc(j.job_id)}">${j.failed_stage === "publish" ? "Check" : "Resume"}</a>`
    : `<a class="btn light small" href="#/jobs/${esc(j.job_id)}">Open</a>`;
  const notes = (j) => {
    if (needsNote(j)) return j.state === "FAILED" ? "Recording not understood · type it" : "Confirm what you said";
    if (j.error) return `${esc(j.error.code)} · ${esc(STAGE_LABEL[j.error.stage] || j.error.stage)}`;
    if (j.state === "PUBLISHED_PAUSED") return `2 ads · ${won(j.daily_budget_krw)}/day`;
    if (MAKING.includes(j.state)) return esc(runLabel(j));
    return esc(j.headline || "");
  };
  const matches = (j) => !query || `${j.product_name || ""} ${j.headline || ""} ${j.job_id} ${j.region || ""}`.toLowerCase().includes(query.toLowerCase());

  const rowsHtml = () => jobs.filter(groups[jobFilter]).filter(matches).map((j) => {
    const thumb = j.thumbnail_url ? `<img class="thumb" src="${esc(j.thumbnail_url)}" alt="">` : `<span class="thumb"></span>`;
    return `<tr><td>${thumb}</td><td>${esc(j.product_name || "Untitled video")}<div class="hint">job ${esc(j.job_id.slice(0, 6))}</div></td>
      <td class="hide-sm">${when(j.created_at)}</td><td class="hide-sm">r${j.revision}</td><td>${jobBadge(j)}</td>
      <td class="hide-sm">${notes(j)}</td><td>${action(j)}</td></tr>`;
  }).join("") || `<tr><td colspan="7" class="hint">No jobs in this view.</td></tr>`;
  const chip = (key, label) => `<button class="chip" data-filter="${key}" aria-pressed="${jobFilter === key}">${label}</button>`;
  app.innerHTML = head(`${jobs.length} job${jobs.length === 1 ? "" : "s"} on this machine`, "Jobs",
      "Every video you uploaded and where it stands. Nothing goes live without an approval.",
      `<a class="btn coral" href="#/new">New job</a>`) +
    `<div class="metrics">
      <div class="card metric"><span class="hint">To approve</span><b style="color:var(--coral)">${count(groups.approve)}</b><small>${oldestWaiting ? `oldest since ${when(oldestWaiting)}` : "nothing waiting"}</small></div>
      <div class="card metric"><span class="hint">Making</span><b style="color:var(--violet)">${count(groups.making)}</b><small>${making ? esc(runLabel(making)) : "idle"}</small></div>
      <div class="card metric"><span class="hint">Paused on Meta</span><b>${paused * 2} ads</b><small>${paused} campaign${paused === 1 ? "" : "s"} · fixture</small></div>
      <div class="card metric"><span class="hint">Needs attention</span><b style="color:var(--danger)">${count(groups.failed)}</b><small>${attention ? esc(needsNote(attention) ? "description to check" : `${attention.error?.code || "failed"} · ${STAGE_LABEL[attention.failed_stage] || ""}`) : "all clear"}</small></div>
    </div>` +
    (jobs.length === 0
      ? `<div class="card empty"><b>No videos yet</b><span class="hint">Upload one 3–45 second phone video to get six ad cuts.</span><a class="btn coral" href="#/new">New job</a></div>`
      : `<div class="card"><div class="cv-filterbar"><div class="chips">${chip("all", "All")}${chip("approve", "To approve")}${chip("making", "Making")}${chip("paused", "Paused")}${chip("failed", "Needs attention")}</div>
          <input class="input cv-search" type="search" id="search" placeholder="Search videos" aria-label="Search videos" value="${esc(query)}"></div>
        <div class="cv-table-wrap"><table class="cv-wraptable"><thead><tr><th></th><th>Video</th><th class="hide-sm">Created</th><th class="hide-sm">Revision</th><th>Status</th><th class="hide-sm">Notes</th><th>Action</th></tr></thead>
        <tbody id="jobRows">${rowsHtml()}</tbody></table></div></div>`);
  app.querySelectorAll("[data-filter]").forEach((b) => b.onclick = () => { jobFilter = b.dataset.filter; viewJobs(); });
  const search = document.getElementById("search");
  if (search) search.oninput = () => { query = search.value; document.getElementById("jobRows").innerHTML = rowsHtml(); };
  // While something is being made, keep the list current; re-render only when a job changes.
  if (jobs.some((j) => isRunning(j) || (MAKING.includes(j.state) && !needsNote(j) && !isInterrupted(j)))) {
    const sig = (list) => list.map((j) => `${j.job_id}|${j.state}|${j.run_state}|${j.pending_stage}|${j.revision}`).join();
    const seen = sig(jobs), hash = location.hash;
    const stop = poll(async () => {
      if (sig(await api("/api/jobs")) !== seen) { stop(); viewJobs(); }
    }, 2000, onRoute(hash));
  }
}
