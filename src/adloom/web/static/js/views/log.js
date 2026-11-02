import { app, esc, won, short, when, MAKING, STATE, stateBadge, PHASE, RESOURCE, resourceName, api, toast, errorText, setNav, head, resume, STEPS, stepList } from "../core.js";

/* Publish log */
export async function viewLog(jobId) {
  setNav("log");
  const jobs = jobId ? [{ job_id: jobId }] : (await api("/api/jobs")).filter((j) => ["APPROVED", "PUBLISHED_PAUSED", "FAILED"].includes(j.state));
  const details = await Promise.all(jobs.map((j) => api(`/api/jobs/${j.job_id}`)));
  const ops = details.flatMap((d) => d.operations.map((op) => ({ ...op, product: d.snapshot.understanding?.product_name || d.job.job_id.slice(0, 6) })));
  const n = (fn) => ops.filter(fn).length;
  const unknown = ops.filter((o) => o.phase === "UNKNOWN" || o.phase === "PREPARED");
  const rows = ops.map((o) => {
    const [label, cls] = PHASE[o.phase];
    return `<tr><td>${esc(o.product)}</td><td class="mono hide-sm">${esc(o.operation_key)}</td><td>${resourceName(o)}</td><td><span class="badge ${cls}">${label}</span></td><td class="mono">${esc(o.remote_id || "—")}</td></tr>`;
  }).join("");
  app.innerHTML = head(jobId ? `<a href="#/jobs/${jobId}">Back to review</a>` : "All jobs", "Publish log",
      "Every request AdLoom sends to Meta is saved before it is sent. Unknown results are checked, never re-sent automatically.") +
    `<div class="metrics">
      <div class="card metric"><span class="hint">Confirmed</span><b style="color:var(--success)">${n((o) => o.phase === "CONFIRMED")}</b></div>
      <div class="card metric"><span class="hint">Unknown</span><b style="color:var(--danger)">${unknown.length}</b></div>
      <div class="card metric"><span class="hint">Failed · not sent</span><b style="color:var(--warning)">${n((o) => o.phase === "FAILED")}</b></div>
      <div class="card metric"><span class="hint">Ever set active by AdLoom</span><b>0</b></div>
    </div>` +
    (unknown.length ? `<div class="note pink" style="margin-bottom:16px">${unknown.length} request${unknown.length > 1 ? "s need" : " needs"} a check<p>The connection dropped after sending. Look it up in Ads Manager before trying again. Anything created stays paused.</p></div>` : "") +
    (ops.length ? `<div class="card"><table><thead><tr><th>Video</th><th class="hide-sm">Operation key</th><th>Resource</th><th>Phase</th><th>Remote ID</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="card empty"><b>Nothing published yet</b><span class="hint">Approve a job, then create its paused ads. Each request shows up here.</span><a class="btn light" href="#/jobs">Open jobs</a></div>`);
}
