import { app, esc, PHASE, resourceName, api, setNav, head } from "../core.js";
import { stopForm, wireStop, unresolved, isRunning } from "../flow.js";

/* Publish log */
export async function viewLog(jobId) {
  setNav("log");
  const jobs = jobId ? [{ job_id: jobId }] : (await api("/api/jobs")).filter((j) => ["APPROVED", "PUBLISHED_PAUSED"].includes(j.state) || (j.state === "FAILED" && j.failed_stage === "publish"));
  const details = await Promise.all(jobs.map((j) => api(`/api/jobs/${j.job_id}`)));
  const ops = details.flatMap((d) => d.operations.map((op) => ({
    ...op, running: isRunning(d.job), product: d.snapshot?.understanding?.product_name || `job ${d.job.job_id.slice(0, 6)}`,
  })));
  const n = (fn) => ops.filter(fn).length;
  const open = unresolved(ops).filter((o) => !o.running);
  const stopped = ops.filter((o) => o.abandoned);
  const rows = ops.map((o) => {
    const [label, cls] = o.abandoned ? ["Stopped", "b-paused"] : o.phase === "PREPARED" && o.running ? ["Sending", "b-progress"] : PHASE[o.phase];
    const remote = o.remote_id || (o.abandoned ? `stopped by ${o.resolution_actor}` : "—");
    return `<tr><td><a href="#/jobs/${esc(o.job_id)}">${esc(o.product)}</a><div class="hint">revision ${o.revision}</div></td><td class="mono hide-sm">${esc(o.operation_key)}</td><td>${esc(resourceName(o))}</td>
      <td><span class="badge ${cls}">${label}</span></td><td class="mono">${esc(remote)}</td></tr>`;
  }).join("");
  app.innerHTML = head(jobId ? `<a href="#/jobs/${esc(jobId)}">Back to review</a>` : "All jobs", "Publish log",
      "Every request AdLoom sends to Meta is saved before it is sent. Unknown results are checked, never re-sent automatically.") +
    `<div class="metrics">
      <div class="card metric"><span class="hint">Confirmed</span><b style="color:var(--success)">${n((o) => o.phase === "CONFIRMED")}</b></div>
      <div class="card metric"><span class="hint">Unknown</span><b style="color:var(--danger)">${open.length}</b>${stopped.length ? `<small>${stopped.length} stopped by the owner</small>` : ""}</div>
      <div class="card metric"><span class="hint">Failed · not sent</span><b style="color:var(--warning)">${n((o) => o.phase === "FAILED")}</b></div>
      <div class="card metric"><span class="hint">Ever set active by AdLoom</span><b>0</b><small>every create request is PAUSED</small></div>
    </div>` +
    open.map((o) => `<div class="note pink cv-check">${open.length > 1 ? "" : "1 request needs a check · "}${esc(o.product)} · ${esc(resourceName(o).toLowerCase())}
        <p>The connection dropped after sending <span class="mono">${esc(o.operation_key)}</span>. Looking it up on Meta needs the live connection, which is off in fixture mode. You can stop this attempt; anything created stays paused.</p>
        ${stopForm(o, o.job_id)}</div>`).join("") +
    (ops.length ? `<div class="card"><table><thead><tr><th>Video</th><th class="hide-sm">Operation key</th><th>Resource</th><th>Phase</th><th>Remote ID</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="card empty"><b>Nothing published yet</b><span class="hint">Approve a job, then create its paused ads. Each request shows up here.</span><a class="btn light" href="#/jobs">Open jobs</a></div>`);
  wireStop(app, () => viewLog(jobId));
}
