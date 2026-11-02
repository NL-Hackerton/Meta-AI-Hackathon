import { app, esc, won, short, when, MAKING, STATE, stateBadge, PHASE, RESOURCE, resourceName, api, toast, errorText, setNav, head, resume, STEPS, stepList } from "../core.js";

/* Review & approve */
export async function viewJob(jobId) {
  setNav("jobs");
  const d = await api(`/api/jobs/${jobId}`);
  const job = d.job, snap = d.snapshot, u = snap.understanding, plan = snap.publish_plan;
  const hooks = snap.render_plan ? snap.render_plan.hooks : (u ? u.hook_candidates.slice(0, 2) : []);
  const hookText = Object.fromEntries(hooks.map((h) => [h.id, h.text]));
  const order = ["9:16", "4:5", "1:1"];
  const variants = [...d.variants].sort((a, b) => a.hook_id.localeCompare(b.hook_id) || order.indexOf(a.aspect) - order.indexOf(b.aspect));
  const tiles = variants.map((v) => `<figure class="variant" style="margin:0">
      <video src="${esc(v.url)}" controls muted playsinline preload="metadata"></video>
      <figcaption class="meta"><span>${esc(v.aspect)} · Hook ${esc(v.hook_id.toUpperCase())}</span><span class="mono">${v.width}×${v.height} · ${(v.duration_us / 1e6).toFixed(1)} s</span></figcaption>
      <span class="hint">${esc(hookText[v.hook_id] || "")} · <span class="mono">${short(v.frame_hash)}</span></span></figure>`).join("");

  const warnings = [];
  for (const f of d.policy_flags || []) warnings.push(`<div class="flag"><span class="badge ${f.severity === "block" ? "b-danger" : "b-warn"}" style="justify-self:start">${f.severity === "block" ? "Blocks approval" : "Rewritten"}</span><s>${esc(f.original)}</s><span style="color:var(--text)">→ ${esc(f.rewrite)}</span></div>`);
  if (d.degraded) warnings.push(`<div class="flag"><span class="badge b-warn" style="justify-self:start">Center-crop fallback</span><span style="color:var(--text-2)">The product was not tracked well enough in one ratio. Check that it stays in frame.</span></div>`);
  if (d.clipped) warnings.push(`<div class="flag"><span class="badge b-warn" style="justify-self:start">Edge frames</span><span style="color:var(--text-2)">The product touches the frame edge in some frames.</span></div>`);
  for (const issue of (d.approval_issues || []).filter((i) => i !== "policy_block")) warnings.push(`<div class="flag"><span class="badge b-danger" style="justify-self:start">${esc(issue.replaceAll("_", " "))}</span><span style="color:var(--text-2)">Resolve this before approving.</span></div>`);
  if (d.approval_error) warnings.push(`<div class="flag"><span class="badge b-danger" style="justify-self:start">${esc(d.approval_error.code)}</span><span style="color:var(--text-2)">${esc(d.approval_error.detail)}</span></div>`);
  const blocked = (d.approval_issues || []).length > 0 || !!d.approval_error;

  let panel;
  if (job.state === "AWAITING_APPROVAL") {
    panel = `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">Ready to approve</h2>${warnings.length ? `<span class="badge ${blocked ? "b-danger" : "b-warn"}">${warnings.length} to check</span>` : `<span class="badge b-done">No issues</span>`}</div>
      <dl class="kv">
        <dt>Publishes</dt><dd>2 × 9:16 ads (Hook A, B)</dd>
        <dt>Status</dt><dd style="color:var(--coral-deep)">Campaign, ad set, ads · PAUSED</dd>
        <dt>Budget</dt><dd>${won(snap.brief.daily_budget_krw)} / day · ${esc(snap.brief.region)}</dd>
        <dt>Landing</dt><dd>${esc(snap.brief.destination_url || "Page only")}</dd>
        <dt>Fingerprint</dt><dd class="mono">sha256 ${short(d.content_digest)}</dd>
      </dl>
      <form id="approve" class="stack" style="gap:12px;margin-top:8px">
        <label class="field">Approved by<input class="input" name="actor" required maxlength="80" autocomplete="name" placeholder="Your name"></label>
        <label class="check"><input type="checkbox" name="seen" required>I watched all six videos and the copy is true for my business.</label>
        <div style="display:flex;gap:10px"><button class="btn" style="flex:1" ${blocked ? "disabled" : ""}>Approve revision ${job.revision}</button><a class="btn light" href="#/jobs/${jobId}/edit">Edit</a></div>
      </form></div>`;
  } else if (job.state === "APPROVED") {
    panel = `<div class="card"><h2>Approved</h2>
      <dl class="kv"><dt>By</dt><dd>${esc(d.approval?.actor)} · web</dd><dt>At</dt><dd>${d.approval ? when(d.approval.approved_at) : "—"}</dd><dt>Fingerprint</dt><dd class="mono">${short(d.approval?.content_digest)}</dd></dl>
      <p class="hint">Publishing re-checks this fingerprint. Editing anything clears the approval.</p>
      <div style="display:flex;gap:10px"><button class="btn coral" style="flex:1" id="publish">Create 2 paused ads</button><a class="btn light" href="#/jobs/${jobId}/edit">Edit</a></div></div>`;
  } else if (job.state === "PUBLISHED_PAUSED") {
    const r = snap.publish_result;
    panel = `<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">Published · paused</h2><span class="badge b-paused">fixture IDs</span></div>
      <dl class="kv"><dt>Campaign</dt><dd class="mono">${esc(r.campaign_id)} · ${esc(r.campaign_status)}</dd><dt>Ad set</dt><dd class="mono">${esc(r.adset_id)} · ${esc(r.adset_status)}</dd>
      ${r.ads.map((a) => `<dt>Ad · Hook ${esc(a.hook_id.toUpperCase())}</dt><dd class="mono">${esc(a.ad_id)} · ${esc(a.configured_status)}</dd>`).join("")}</dl>
      <p class="hint">Nothing runs until you turn it on in Ads Manager. AdLoom never sets ads active.</p>
      <a class="btn light wide" href="#/jobs/${jobId}/log">Open publish log</a></div>`;
  } else if (job.state === "FAILED") {
    panel = `<div class="card"><h2>Stopped at ${esc(job.failed_stage)}</h2><div class="note pink">${esc(job.error?.code)}<p>${esc(job.error?.detail)}</p></div>
      <p class="hint">Finished steps are kept. Resume runs only the failed step and what follows.</p><button class="btn wide" data-resume="${jobId}">Resume</button></div>`;
  } else {
    panel = `<div class="card"><h2>Making</h2>${stepList(Math.min(MAKING.indexOf(job.state), 3))}</div>`;
  }

  const copy = u ? `<div class="card copy"><h2>Copy</h2><dl class="kv">
      ${hooks.map((h) => `<dt>Hook ${esc(h.id.toUpperCase())}</dt><dd>${esc(h.text)}</dd>`).join("")}
      <dt>Headline</dt><dd>${esc(u.headline)}</dd><dt>Primary text</dt><dd>${esc(u.primary_text)}</dd><dt>Button</dt><dd>${esc((plan?.cta || u.cta).replaceAll("_", " ").toLowerCase())}</dd></dl></div>` : "";

  app.innerHTML = head(`<a href="#/jobs">Jobs</a> / ${esc(u?.product_name || "job " + jobId.slice(0, 6))} / revision ${job.revision}`,
      "Review & approve", "Check the six videos against your footage, fix copy if needed, then approve. Approval fingerprints exactly what you saw.",
      stateBadge(job.state)) +
    `<div class="grid2"><div class="stack">
       <div class="card"><h2>Six variants${variants.length ? " · H.264 · AAC" : ""}</h2>${variants.length ? `<div class="variants">${tiles}</div>` : `<p class="hint">Videos appear here once assembly finishes.</p>`}</div>
       ${copy}
     </div><div class="stack">${panel}
       ${warnings.length ? `<div class="note pink">What to check<div>${warnings.join("")}</div><p>Rule-based screen only. Not a Meta review result.</p></div>` : ""}
     </div></div>`;
  const form = document.getElementById("approve");
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      await api(`/api/jobs/${jobId}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actor: form.actor.value.trim(), digest: d.content_digest }) });
      toast("Approved revision " + job.revision);
      viewJob(jobId);
    } catch (err) { toast(errorText(err), true); button.disabled = false; }
  };
  const pub = document.getElementById("publish");
  if (pub) pub.onclick = async () => {
    pub.disabled = true;
    pub.innerHTML = `<span class="spinner"></span> Creating paused ads`;
    try { await api(`/api/jobs/${jobId}/publish`, { method: "POST" }); toast("Created 2 paused ads"); viewJob(jobId); }
    catch (err) { toast(errorText(err), true); viewJob(jobId); }
  };
  app.querySelectorAll("[data-resume]").forEach((b) => b.onclick = () => resume(b.dataset.resume, b));
  if (MAKING.includes(job.state)) setTimeout(() => { if (location.hash === `#/jobs/${jobId}`) viewJob(jobId); }, 1500);
}
