import { app, esc, won, short, when, MAKING, stateBadge, PHASE, resourceName, api, toast, errorText, setNav, head, stepList } from "../core.js";
import { ASPECTS, activeStep, isRunning, needsNote, failureCard, wireResume, stopForm, wireStop, unresolved, poll, onRoute, actorName, rememberActor } from "../flow.js";
import { sourcePanel, mountSource } from "../tracking.js";

const EDITABLE = ["AWAITING_APPROVAL", "APPROVED"];
const FIELD_LABEL = { primary_text: "Primary text", headline: "Headline", "hook:a": "Hook A", "hook:b": "Hook B", "hook:c": "Hook C (unused)" };
const FIELD_BODY = { primary_text: "primary_text", headline: "headline", "hook:a": "hook_a", "hook:b": "hook_b" };

/** Requests publish makes, in order (stages/publish.py). */
const PUBLISH_PLAN = [
  ["campaign", null, "Create campaign", "status PAUSED"],
  ["adset", null, "Create ad set", "daily budget · PAUSED"],
  ["image", null, "Upload thumbnail", "image · 9:16"],
  ["video", "a", "Upload video A", "video · 9:16 Hook A"],
  ["creative", "a", "Create creative A", "video + copy · Hook A"],
  ["ad", "a", "Create ad A", "PAUSED"],
  ["video", "b", "Upload video B", "video · 9:16 Hook B"],
  ["creative", "b", "Create creative B", "video + copy · Hook B"],
  ["ad", "b", "Create ad B", "PAUSED"],
];

const crumb = (d) => {
  const u = d.snapshot?.understanding, job = d.job;
  return `<a href="#/jobs">Jobs</a> / ${esc(u?.product_name || "New video")} · job ${esc(job.job_id.slice(0, 6))} · revision ${job.revision}`;
};
const flowStrip = (at) => `<ol class="cv-flow" aria-label="Progress">${["Source", "Review six videos", "Approve · publish paused"].map((t, i) =>
  `<li class="${i < at ? "done" : i === at ? "now" : ""}"${i === at ? ` aria-current="step"` : ""}><b>${i + 1}</b> ${t}</li>`).join("")}</ol>`;

export async function viewJob(jobId) {
  setNav("jobs");
  const hash = location.hash;
  const d = await api(`/api/jobs/${jobId}`);
  const job = d.job;
  const rerender = () => { if (onRoute(hash)()) viewJob(jobId); };
  if (needsNote(job)) return renderNote(d, hash);
  if (job.state !== "FAILED" && (MAKING.includes(job.state) || (isRunning(job) && job.pending_stage !== "publish"))) return renderMaking(d, hash, rerender);
  if (job.state === "FAILED" && job.failed_stage !== "publish") return renderFailed(d, hash, rerender);
  return renderReview(d, hash, rerender);
}

/* C2/C3 · confirm what you said */
function renderNote(d, hash) {
  const job = d.job, failed = job.state === "FAILED";
  const proposal = d.note_proposal || "";
  app.innerHTML = head(crumb(d), failed ? "Type what the video is about" : "Is this what you said?",
      failed ? "We could not turn your recording into text. Type the one-line description instead; nothing you said is used." : "Edit anything that is off. Only this confirmed text is used to write your ads.",
      `<span class="badge b-warn">Check description</span>`) +
    `<div class="grid2"><form class="stack" id="noteForm">
        <div class="card stack">
          ${failed ? `<div class="note pink">${esc(job.error?.code || "")}<p>${esc(job.error?.detail || "Transcription failed.")}</p></div>` : `<h2 style="margin:0">What we heard</h2>`}
          <label class="field">${failed ? "One-line description" : "Your description, as text"}
            <textarea class="input cv-said" name="text" maxlength="200" required placeholder="What you sell, where, and what makes it worth a call">${esc(proposal)}</textarea>
            <span class="counter" data-count>${proposal.length} / 200 characters</span></label>
          <div class="note violet cv-why"><span class="cv-tag violet">Why</span> Prices, discounts and guarantees are only used if you typed or confirmed them here.</div>
        </div>
        <button class="btn coral wide" id="useNote">Use this description</button>
        <a class="btn light wide" href="#/new">Start over with a new recording</a>
      </form>
      <div class="stack"><div id="noteProgress" class="card"><h2>What happens next</h2>${stepList(-1)}</div>${sourcePanel(d, { title: "Your video", stats: false })}</div></div>`;
  mountSource(app, d);
  const form = document.getElementById("noteForm"), area = form.text, count = form.querySelector("[data-count]");
  area.oninput = () => { count.textContent = `${area.value.length} / 200 characters`; count.classList.toggle("over", area.value.length > 200); };
  form.onsubmit = async (event) => {
    event.preventDefault();
    const text = area.value.trim();
    if (!text) { area.focus(); toast("Write at least a few words.", true); return; }
    const button = document.getElementById("useNote"), box = document.getElementById("noteProgress");
    button.disabled = true; area.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Making 6 ads`;
    box.innerHTML = `<div class="cv-title"><h2>Making your ads</h2><span class="badge b-progress">Making</span></div>${stepList(0)}`;
    const stop = poll(async () => {
      const now = await api(`/api/jobs/${job.job_id}`);
      box.innerHTML = `<div class="cv-title"><h2>Making your ads</h2><span class="badge b-progress">Making</span></div>${stepList(activeStep(now.job))}`;
    }, 1000, onRoute(hash));
    try {
      await api(`/api/jobs/${job.job_id}/confirm-note`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      toast("Six videos are ready to review");
    } catch (err) { toast(errorText(err), true); }
    stop();
    if (onRoute(hash)()) viewJob(job.job_id);
  };
}

/* 03 · Making */
function renderMaking(d, hash, rerender) {
  const job = d.job, running = isRunning(job);
  app.innerHTML = head(crumb(d), "Making your ads", "Following the product and reframing to 3 ratios. You can leave this page; the job keeps running.",
      `<span class="badge b-progress">${running ? "Making" : "Paused"}</span>`) + flowStrip(0) +
    `<div class="grid2"><div class="stack">${sourcePanel(d)}</div><div class="stack">
       <div class="card"><h2>Steps</h2>${stepList(activeStep(job))}
         ${running ? "" : `<p class="hint">This run stopped before finishing. Finished steps are saved.</p><button class="btn wide" data-resume-job="${esc(job.job_id)}">Resume</button>`}</div>
       <div class="note violet">The dashed box is the product. Missed frames are filled in; weak tracking falls back to a center crop, and we tell you.</div>
     </div></div>`;
  mountSource(app, d);
  wireResume(app, rerender);
  if (running) {
    const seen = `${job.state}|${job.pending_stage}|${job.manifest_seq}`;
    const stop = poll(async () => {
      const now = (await api(`/api/jobs/${job.job_id}`)).job;
      if (`${now.state}|${now.pending_stage}|${now.manifest_seq}` !== seen) { stop(); rerender(); }
    }, 1200, onRoute(hash));
  }
}

/* C4 · a making step failed */
function renderFailed(d, hash, rerender) {
  app.innerHTML = head(crumb(d), "We stopped at one step", "Your upload and finished steps are saved. Resume picks up from the failed step.", `<span class="badge b-danger">Needs attention</span>`) +
    flowStrip(0) + `<div class="grid2"><div class="stack">${sourcePanel(d)}</div><div class="stack">${failureCard(d.job)}</div></div>`;
  mountSource(app, d);
  wireResume(app, rerender);
}

function variantsCard(d) {
  const hooks = Object.fromEntries((d.snapshot.render_plan?.hooks || []).map((h) => [h.id, h.text]));
  const crops = Object.fromEntries((d.snapshot.crops || []).map((c) => [c.aspect, c]));
  const variants = [...d.variants].sort((a, b) => ASPECTS.indexOf(a.aspect) - ASPECTS.indexOf(b.aspect) || a.hook_id.localeCompare(b.hook_id));
  if (!variants.length) return `<div class="card cv-variants"><h2>Six variants</h2><p class="hint">Videos appear here once assembly finishes.</p></div>`;
  const tiles = variants.map((v) => {
    const crop = crops[v.aspect], edge = crop?.clipped_frames?.length || 0;
    const quality = crop?.degraded ? `<span class="badge b-warn">Center crop</span>` : edge ? `<span class="badge b-danger">Edge in ${edge} frames</span>` : `<span class="badge b-done">Ready</span>`;
    const use = v.aspect === "9:16" ? `<span class="badge b-paused">Publish · paused</span>` : `<span class="badge b-warn">File only</span>`;
    return `<figure class="variant cv-tile" data-aspect="${esc(v.aspect)}">
        <video src="${esc(v.url)}" controls muted playsinline preload="metadata" aria-label="${esc(v.aspect)} Hook ${esc(v.hook_id.toUpperCase())}"></video>
        <figcaption class="meta"><span>${esc(v.aspect)} · Hook ${esc(v.hook_id.toUpperCase())}</span><span class="mono">${v.width}×${v.height} · ${(v.duration_us / 1e6).toFixed(1)} s</span></figcaption>
        <span class="hint">${esc(hooks[v.hook_id] || "")}</span>
        <span class="cv-badges">${quality}${use}</span>
        <span class="hint mono">frame ${short(v.frame_hash)} · <a href="${esc(v.url)}" download>Download</a></span></figure>`;
  }).join("");
  const initial = matchMedia("(max-width: 960px)").matches ? "9:16" : "all";
  const chip = (key, label) => `<button type="button" class="chip" data-ratio="${key}" aria-pressed="${key === initial}">${label}</button>`;
  return `<div class="card cv-variants"><div class="cv-title"><h2>Six variants · H.264 · AAC</h2><span class="hint">Same frame hash on re-render</span></div>
      <div class="chips">${chip("all", "All 6")}${chip("9:16", "9:16 · to publish")}${chip("4:5", "4:5")}${chip("1:1", "1:1")}</div>
      <div class="variants" data-show="${initial}">${tiles}</div></div>`;
}

function copyCard(d) {
  const u = d.snapshot.understanding, plan = d.snapshot.publish_plan;
  if (!u) return "";
  const hooks = d.snapshot.render_plan?.hooks || u.hook_candidates.slice(0, 2);
  const editable = EDITABLE.includes(d.job.state);
  return `<div class="card copy cv-copy"><div class="cv-title"><h2>Ad copy</h2>${editable ? `<a class="cv-link" href="#/jobs/${esc(d.job.job_id)}/edit">Edit</a>` : ""}</div><dl class="kv">
      ${hooks.map((h) => `<dt>Hook ${esc(h.id.toUpperCase())}</dt><dd>${esc(h.text)}</dd>`).join("")}
      <dt>Headline</dt><dd>${esc(u.headline)}</dd><dt>Primary text</dt><dd>${esc(u.primary_text)}</dd>
      <dt>Button</dt><dd>${esc((plan?.cta || u.cta).replaceAll("_", " ").toLowerCase())}</dd></dl></div>`;
}

function warningsNote(d) {
  const items = [];
  for (const issue of (d.approval_issues || []).filter((i) => i !== "policy_block")) items.push(`<div class="flag"><span class="badge b-danger" style="justify-self:start">${esc(issue.replaceAll("_", " "))}</span><span style="color:var(--text-2)">Resolve this before approving.</span></div>`);
  if (d.approval_error) items.push(`<div class="flag"><span class="badge b-danger" style="justify-self:start">${esc(d.approval_error.code)}</span><span style="color:var(--text-2)">${esc(d.approval_error.detail)}</span></div>`);
  if (d.clipped) items.push(`<div class="flag"><span class="badge b-warn" style="justify-self:start">Edge frames</span><span style="color:var(--text-2)">The product touches the frame edge in some frames. Check the marked variants.</span></div>`);
  const inBlockedCard = d.job.state === "AWAITING_APPROVAL" && (d.approval_issues || []).includes("policy_block");
  for (const f of (d.policy_flags || []).filter((x) => !inBlockedCard || x.severity !== "block")) {
    items.push(`<div class="flag"><span class="badge ${f.severity === "block" ? "b-danger" : "b-warn"}" style="justify-self:start">${esc(FIELD_LABEL[f.field] || f.field)} · ${f.severity === "block" ? "blocks approval" : "rewritten"}</span><s>${esc(f.original)}</s><span style="color:var(--text)">→ ${esc(f.rewrite)}</span></div>`);
  }
  if (!items.length) return "";
  return `<div class="note pink cv-warn">${items.length} to check<div>${items.join("")}</div><p>Rule-based screen only. Not a Meta review result.</p></div>`;
}

function cropNote(d) {
  const t = d.tracking;
  const fallback = t ? ASPECTS.filter((a) => t.degraded?.[a]) : [];
  if (!fallback.length) return "";
  const editable = EDITABLE.includes(d.job.state);
  return `<div class="card cv-c5"><div class="cv-title"><h2>Ready, with one note</h2><span class="cv-flag danger">Center crop</span></div>
      <p class="hint">The product was found in only ${Math.round(t.coverage * 100)}% of frames, so ${esc(fallback.join(", "))} use${fallback.length === 1 ? "s" : ""} a steady center crop instead of following it.</p>
      <p class="hint">Want it to follow the product? Tell AdLoom what to follow, or re-shoot with the product closer to the camera.</p>
      ${editable ? `<a class="btn light wide" href="#/jobs/${esc(d.job.job_id)}/edit" data-focus-product>Pick the product</a>` : ""}</div>`;
}

/** D4 · approval blocked by flagged phrases. */
function blockedCard(d) {
  const flags = (d.policy_flags || []).filter((f) => f.severity === "block");
  const fields = ["hook:a", "hook:b", "primary_text", "headline"];
  const count = (field) => flags.filter((f) => f.field === field).length;
  return `<div class="card cv-blocked"><div class="cv-title"><h2>Fix ${flags.length} phrase${flags.length === 1 ? "" : "s"} to approve</h2><span class="cv-flag danger">Blocked</span></div>
      <p class="hint">Approval stays locked until the flagged text is changed.</p>
      ${flags.map((f, i) => `<div class="cv-fix"><b>${esc(FIELD_LABEL[f.field] || f.field)} · rule ${esc(f.rule_id)}</b>
          <div class="cv-fixbox"><s>${esc(f.original)}</s><span>→ ${esc(f.rewrite)}</span></div>
          <div class="cv-actions">${FIELD_BODY[f.field] ? `<button type="button" class="btn small" data-suggest="${i}">Use suggestion</button>` : ""}<a class="btn light small" href="#/jobs/${esc(d.job.job_id)}/edit">Write my own</a></div></div>`).join("")}
      <ul class="cv-checks">${fields.map((f) => `<li class="${count(f) ? "bad" : ""}">${esc(FIELD_LABEL[f])} · ${count(f) ? `${count(f)} issue${count(f) > 1 ? "s" : ""}` : "no issues"}</li>`).join("")}</ul>
      <button class="btn wide" disabled>Approve · locked until fixed</button></div>`;
}

function approveCard(d) {
  const job = d.job, brief = d.snapshot.brief;
  const blockedByPolicy = (d.approval_issues || []).includes("policy_block");
  if (blockedByPolicy) return blockedCard(d);
  const blocked = (d.approval_issues || []).length > 0 || !!d.approval_error;
  return `<div class="card cv-approve" id="approveCard" role="dialog" aria-modal="false" aria-labelledby="approveTitle">
      <button type="button" class="cv-grab" data-close aria-label="Close"></button>
      <div class="cv-title"><h2 id="approveTitle">Approve these ads?</h2>${blocked ? `<span class="cv-flag danger">Blocked</span>` : `<span class="badge b-done">Ready</span>`}</div>
      <p class="hint">Ads are created exactly as below. Any later change needs a new approval.</p>
      <dl class="kv">
        <dt>Ads</dt><dd>2 × 9:16 (Hook A, B)</dd>
        <dt>Status</dt><dd style="color:var(--coral-deep)">Paused · never auto-activated</dd>
        <dt>Daily budget</dt><dd>${won(brief.daily_budget_krw)} · 1 ad set</dd>
        <dt>Audience</dt><dd>South Korea · ${esc(brief.region)} noted</dd>
        <dt>Landing</dt><dd>${esc(brief.destination_url || "Page only")}</dd>
        <dt>Other 4</dt><dd>4:5 and 1:1 are download-only</dd>
        <dt>Fingerprint</dt><dd class="mono">sha256 ${short(d.content_digest)}</dd>
      </dl>
      <form id="approve" class="stack" style="gap:12px;margin-top:12px">
        <label class="field">Approved by<input class="input" name="actor" required maxlength="80" autocomplete="name" value="${esc(actorName())}" placeholder="Your name"></label>
        <label class="check"><input type="checkbox" name="seen" required>I reviewed all 6 videos and the copy, and it is true for my business.</label>
        <div class="cv-actions"><button class="btn coral" style="flex:1" ${blocked ? "disabled" : ""}>Approve revision ${job.revision}</button><a class="btn light" href="#/jobs/${esc(job.job_id)}/edit">Edit</a></div>
        <p class="hint" style="margin:0">Approval stores fingerprints of the reviewed videos and copy. If files change, publishing stops.</p>
      </form></div>`;
}

function approvedCard(d) {
  const a = d.approval, job = d.job;
  return `<div class="card"><div class="cv-title"><h2>Approved</h2><span class="badge b-progress">revision ${job.revision}</span></div>
      <dl class="kv"><dt>By</dt><dd>${esc(a?.actor || "—")} · ${esc(a?.channel || "web")}</dd><dt>At</dt><dd>${a ? when(a.approved_at) : "—"}</dd><dt>Fingerprint</dt><dd class="mono">${short(a?.content_digest)}</dd></dl>
      <p class="hint">Publishing re-checks this fingerprint. Editing anything clears the approval.</p>
      <div class="cv-actions"><button class="btn coral" style="flex:1" id="publish">Create 2 paused ads</button><a class="btn light" href="#/jobs/${esc(job.job_id)}/edit">Edit</a></div></div>`;
}

/** Ordered request journal for the job's current revision. */
function journal(d, running) {
  const ops = d.operations.filter((o) => o.revision === d.job.revision);
  return `<ol class="cv-journal">${PUBLISH_PLAN.map(([kind, hook, title, sub]) => {
    const op = ops.find((o) => o.resource_kind === kind && (o.hook_id || null) === hook);
    let cls = "", status = running ? "Waiting" : "Not sent";
    if (op?.abandoned) { cls = "stopped"; status = "Stopped"; }
    else if (op?.phase === "CONFIRMED") { cls = "done"; status = "Done"; }
    else if (op?.phase === "PREPARED") { cls = running ? "active" : "unknown"; status = running ? "Sending" : "Unknown"; }
    else if (op?.phase === "UNKNOWN") { cls = "unknown"; status = "Unknown"; }
    else if (op?.phase === "FAILED") { cls = "failed"; status = "Failed · not sent"; }
    const detail = kind === "adset" ? `${won(d.snapshot.brief.daily_budget_krw)}/day · PAUSED` : sub;
    return `<li class="${cls}"><i>${cls === "done" ? "✓" : cls === "unknown" || cls === "failed" ? "!" : ""}</i><div><b>${title}</b><small>${esc(detail)}${op?.remote_id ? ` · <span class="mono">${esc(op.remote_id)}</span>` : ""}</small></div><span>${status}</span></li>`;
  }).join("")}</ol>`;
}

function publishingCard(d) {
  return `<div class="card"><div class="cv-title"><h2>Creating 2 paused ads</h2><span class="badge b-progress">Publishing</span></div>
      <p class="hint">Each request is saved before it is sent, so a lost connection can be checked instead of sent twice.</p>${journal(d, true)}
      <div class="note yellow">Fixture mode · mock IDs only. Live publishing turns on after the Meta account is approved.</div></div>`;
}

/** D6 / stopped / retry states for a job that failed while publishing. */
function publishFailedCard(d) {
  const open = unresolved(d.operations), stopped = d.operations.filter((o) => o.abandoned);
  const job = d.job;
  if (open.length) {
    return `<div class="card cv-d6"><div class="cv-title"><h2>We lost the reply for ${open.length === 1 ? "one request" : `${open.length} requests`}</h2><span class="cv-flag danger">Unknown</span></div>
        <p class="hint">Meta may have created ${open.map((o) => esc(resourceName(o).toLowerCase())).join(", ")} anyway. AdLoom will not send ${open.length === 1 ? "it" : "them"} again on its own.</p>
        <h3 class="cv-sub">Request journal</h3>${journal(d, false)}
        <p class="hint">Looking the request up on Meta needs the live Meta connection, which is off in fixture mode. If you do not want to wait, stop this attempt.</p>
        ${open.map((o) => `<div class="cv-stopbox"><b>Stop this attempt · ${esc(resourceName(o))}</b>${stopForm(o, job.job_id)}</div>`).join("")}
        <div class="note mint">Nothing created here is ever active. Any paused leftovers stay visible in Ads Manager.</div></div>`;
  }
  if (stopped.length) {
    const by = [...new Set(stopped.map((o) => o.resolution_actor).filter(Boolean))].join(", ");
    return `<div class="card"><div class="cv-title"><h2>Publishing stopped</h2><span class="badge b-paused">Abandoned</span></div>
        <p class="hint">${esc(by || "The owner")} stopped the attempt for ${stopped.map((o) => esc(resourceName(o).toLowerCase())).join(", ")}. This job can no longer publish; anything already created stays paused.</p>
        ${journal(d, false)}
        <a class="btn coral wide" href="#/new">Start a new job</a></div>`;
  }
  return `<div class="card"><div class="cv-title"><h2>Publishing stopped</h2><span class="cv-flag danger">Needs attention</span></div>
      <div class="note pink">${esc(job.error?.code || "")}<p>${esc(job.error?.detail || "")}</p></div>
      ${journal(d, false)}
      <p class="hint">No request has an unknown result, so retrying is safe. Confirmed requests are not sent again.</p>
      <button class="btn coral wide" id="publish">Try publishing again</button></div>`;
}

/* 06 · Published · paused */
function publishedCard(d) {
  const r = d.snapshot.publish_result;
  const hooks = Object.fromEntries((d.snapshot.render_plan?.hooks || []).map((h) => [h.id, h.text]));
  if (!r) return `<div class="card"><h2>Published · paused</h2><p class="hint">The publish result file is missing. Open the publish log for each request.</p></div>`;
  return `<div class="card cv-published"><div class="cv-title"><h2>2 ads are on Meta, paused</h2><span class="badge b-warn">${esc(r.execution_mode)} IDs</span></div>
      <p class="hint">Nothing is spent until you turn them on in Ads Manager. AdLoom never sets ads active.</p>
      <ul class="cv-tree">
        <li><div><b>Campaign</b><small class="mono">${esc(r.campaign_id)}</small></div><span class="badge b-paused">${esc(r.campaign_status)}</span></li>
        <li class="l2"><div><b>Ad set</b><small>${won(d.snapshot.brief.daily_budget_krw)}/day · South Korea · <span class="mono">${esc(r.adset_id)}</span></small></div><span class="badge b-paused">${esc(r.adset_status)}</span></li>
        ${r.ads.map((a) => `<li class="l3"><div><b>Ad · Hook ${esc(a.hook_id.toUpperCase())}</b><small>${esc(hooks[a.hook_id] || "")} · <span class="mono">${esc(a.ad_id)}</span></small></div><span class="badge b-paused">${esc(a.configured_status)}</span></li>`).join("")}
      </ul>
      <p class="hint">Checked ${when(r.checked_at)}. Edits after publishing start a new job; live ads are never changed silently.</p>
      <a class="btn light wide" href="#/jobs/${esc(d.job.job_id)}/log">Open publish log</a></div>`;
}

function journalTable(d) {
  if (!d.operations.length) return "";
  const rank = (o) => PUBLISH_PLAN.findIndex(([kind, hook]) => kind === o.resource_kind && hook === (o.hook_id || null));
  const rows = [...d.operations].sort((a, b) => b.revision - a.revision || rank(a) - rank(b)).map((o) => {
    const [label, cls] = o.abandoned ? ["Stopped", "b-paused"] : PHASE[o.phase];
    return `<tr><td class="mono hide-sm">${esc(o.operation_key)}</td><td>${esc(resourceName(o))}</td><td><span class="badge ${cls}">${label}</span></td><td class="mono">${esc(o.remote_id || (o.abandoned ? `by ${o.resolution_actor}` : "—"))}</td></tr>`;
  }).join("");
  return `<div class="card cv-jtable"><div class="cv-title"><h2>Publish journal</h2><span class="hint">UNKNOWN requests are never re-sent automatically</span></div>
      <table><thead><tr><th class="hide-sm">Operation key</th><th>Resource</th><th>Phase</th><th>Remote ID</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* 04 Review · 05 Approve sheet · D4–D6 · 06 Published */
function renderReview(d, hash, rerender) {
  const job = d.job;
  const publishing = isRunning(job) && job.pending_stage === "publish";
  let panel, step = 1, title = "Review & approve";
  let sub = "Check the six videos against your footage, fix copy if needed, then approve. Approval fingerprints exactly what you saw.";
  if (publishing) { panel = publishingCard(d); step = 2; title = "Publishing to Meta"; sub = "Each request is saved before it is sent. Unknown results are never re-sent automatically."; }
  else if (job.state === "AWAITING_APPROVAL") panel = approveCard(d);
  else if (job.state === "APPROVED") { panel = approvedCard(d); step = 2; }
  else if (job.state === "PUBLISHED_PAUSED") { panel = publishedCard(d); step = 3; title = "Published · paused"; sub = "Both 9:16 ads exist on Meta, paused. Nothing is spent until you turn them on in Ads Manager."; }
  else { panel = publishFailedCard(d); step = 2; title = "Publishing to Meta"; sub = "Each request is saved before it is sent. Unknown results are never re-sent automatically."; }
  const sheet = job.state === "AWAITING_APPROVAL" && !(d.approval_issues || []).includes("policy_block");

  const blockedBadge = job.state === "AWAITING_APPROVAL" && (d.approval_issues || []).length > 0;
  app.innerHTML = head(crumb(d), title, sub, blockedBadge ? `<span class="badge b-danger">Blocked</span>` : stateBadge(job.state)) +
    flowStrip(step) +
    `<div class="grid2 cv-review"><div class="stack">
        <div class="cv-o-source">${sourcePanel(d)}</div>
        <div class="cv-o-variants">${variantsCard(d)}</div>
        <div class="cv-o-copy">${copyCard(d)}</div>
      </div><div class="stack">
        <div class="cv-o-panel${sheet ? " cv-sheet" : ""}" id="panel">${panel}</div>
        <div class="cv-o-warn">${warningsNote(d)}${cropNote(d)}</div>
      </div></div>
      ${journalTable(d)}
      ${sheet ? `<div class="cv-mbar"><button class="btn coral wide" id="openSheet">Approve as is</button><a class="btn light wide" href="#/jobs/${esc(job.job_id)}/edit">Edit copy or scenes</a></div><div class="cv-backdrop" data-close hidden></div>` : ""}`;
  mountSource(app, d);

  app.querySelectorAll("[data-ratio]").forEach((chip) => chip.onclick = () => {
    app.querySelectorAll("[data-ratio]").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    app.querySelector(".cv-variants .variants").dataset.show = chip.dataset.ratio;
  });

  const panelEl = document.getElementById("panel"), backdrop = app.querySelector(".cv-backdrop");
  const setSheet = (open) => {
    panelEl.classList.toggle("open", open);
    if (backdrop) backdrop.hidden = !open;
    document.body.classList.toggle("cv-locked", open);
    if (open) panelEl.querySelector("input[name=actor]")?.focus();
  };
  document.getElementById("openSheet")?.addEventListener("click", () => setSheet(true));
  app.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => setSheet(false)));
  window.addEventListener("hashchange", () => document.body.classList.remove("cv-locked"), { once: true });
  panelEl.addEventListener("keydown", (e) => { if (e.key === "Escape") setSheet(false); });

  const form = document.getElementById("approve");
  if (form) form.onsubmit = async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const button = form.querySelector("button.coral"), actor = form.actor.value.trim();
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Approving`;
    try {
      await api(`/api/jobs/${job.job_id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actor, digest: d.content_digest }) });
      rememberActor(actor);
      setSheet(false);
      toast(`Approved revision ${job.revision}`);
      rerender();
    } catch (err) { toast(errorText(err), true); button.disabled = false; button.textContent = `Approve revision ${job.revision}`; }
  };

  app.querySelectorAll("[data-suggest]").forEach((button) => button.onclick = async () => {
    const flag = d.policy_flags.filter((f) => f.severity === "block")[Number(button.dataset.suggest)];
    app.querySelectorAll("[data-suggest]").forEach((b) => b.disabled = true);
    button.innerHTML = `<span class="spinner"></span> Re-assembling`;
    try {
      await api(`/api/jobs/${job.job_id}/edit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [FIELD_BODY[flag.field]]: flag.rewrite }) });
      toast("Suggestion applied as a new revision");
    } catch (err) { toast(errorText(err), true); }
    rerender();
  });

  const pub = document.getElementById("publish");
  if (pub) pub.onclick = async () => {
    pub.disabled = true;
    pub.innerHTML = `<span class="spinner"></span> Creating paused ads`;
    panelEl.innerHTML = publishingCard({ ...d, operations: d.operations });
    const stop = poll(async () => {
      const now = await api(`/api/jobs/${job.job_id}`);
      panelEl.innerHTML = publishingCard(now);
    }, 500, onRoute(hash));
    try { await api(`/api/jobs/${job.job_id}/publish`, { method: "POST" }); toast("Created 2 paused ads"); }
    catch (err) { toast(errorText(err), true); }
    stop();
    rerender();
  };

  wireStop(app, rerender);
  app.querySelector("[data-focus-product]")?.addEventListener("click", () => sessionStorage.setItem("adloom.focus", "product"));
  if (publishing) {
    const stop = poll(async () => {
      const now = await api(`/api/jobs/${job.job_id}`);
      if (!isRunning(now.job)) { stop(); rerender(); } else panelEl.innerHTML = publishingCard(now);
    }, 800, onRoute(hash));
  }
}
