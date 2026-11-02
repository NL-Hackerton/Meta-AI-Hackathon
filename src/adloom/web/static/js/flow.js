"use strict";
// Shared helpers for the create → review → publish flow views.
import { esc, api, toast, errorText, stepList, NOTE_PENDING, needsNote, currentNav, onLeave } from "./core.js";
import { refreshBell } from "./notify.js";
export { NOTE_PENDING, needsNote };

export const STAGE_STEP = { input: 0, understand: 0, track: 1, enrich: 2, assemble: 3, publish: 4 };
export const STAGE_LABEL = { input: "upload", understand: "understanding", track: "tracking", enrich: "images & captions", assemble: "assembly", publish: "publishing" };
const STATE_STEP = { CREATED: 0, UNDERSTOOD: 1, TRACKED: 2, ENRICHED: 3, RENDERED: 3, AWAITING_APPROVAL: 4, APPROVED: 4, PUBLISHED_PAUSED: 5 };
export const ASPECTS = ["9:16", "4:5", "1:1"];

export const isRunning = (job) => job.run_state === "RUNNING" || job.run_state === "CANCEL_REQUESTED";

/** Index into STEPS of the step that is running (or next to run) for this job head. */
export function activeStep(job) {
  if (job.state === "FAILED") return STAGE_STEP[job.failed_stage] ?? 0;
  if (isRunning(job) && job.pending_stage) return STAGE_STEP[job.pending_stage] ?? 0;
  return STATE_STEP[job.state] ?? 0;
}

/** Seconds as m:ss, or m:ss.cc when `fine`. */
export function clock(us, fine = false) {
  const total = Math.max(0, us) / 1e6;
  const m = Math.floor(total / 60), s = total - m * 60;
  return fine ? `${m}:${s.toFixed(2).padStart(5, "0")}` : `${m}:${String(Math.floor(s)).padStart(2, "0")}`;
}

/** Repeats `fn` every `ms` while `alive()` holds on this screen; returns a stop function. */
export function poll(fn, ms, alive) {
  const nav = currentNav();
  let stopped = false, timer = 0;
  const live = () => !stopped && nav === currentNav() && alive();
  const tick = async () => {
    if (!live()) return;
    try { await fn(); } catch (_) { /* transient; the next tick retries */ }
    if (live()) timer = setTimeout(tick, ms);
  };
  const stop = () => { stopped = true; clearTimeout(timer); };
  timer = setTimeout(tick, ms);
  onLeave(stop);
  return stop;
}

export const onRoute = (hash) => () => location.hash === hash;


/** While any job is running, re-renders the screen once the job list changes. */
export function refreshWhileRunning(jobs, rerender, alive = () => true) {
  if (!jobs.some(isRunning)) return;
  const sign = (list) => list.map((j) => `${j.job_id}:${j.state}:${j.run_state}:${j.pending_stage}`).join("|");
  const before = sign(jobs);
  const stop = poll(async () => {
    if (sign(await api("/api/jobs")) !== before) { stop(); rerender(); }
  }, 1500, alive);
}
export const actorName = () => localStorage.getItem("adloom.actor") || "";
export const rememberActor = (name) => localStorage.setItem("adloom.actor", name);
export const actorError = `<span class="cv-inline-err" data-actor-error role="alert" hidden>Enter your name. Spaces alone are not a name.</span>`;

/** Trimmed actor name from `form.actor`, or null after showing the inline message. */
export function checkActor(form) {
  const value = form.actor.value.trim(), msg = form.querySelector("[data-actor-error]");
  if (msg) msg.hidden = !!value;
  if (!value) { form.actor.setAttribute("aria-invalid", "true"); form.actor.focus(); return null; }
  form.actor.removeAttribute("aria-invalid");
  return value;
}

export const BUSY_REASON = "Another job is being made. This unlocks when it finishes.";
export const busyNote = () => `<div class="note yellow cv-busy" role="status">Another job is being made<p>Approve, publish, edit, resume and confirm stay locked until it finishes. This page updates on its own.</p></div>`;

/** Whether the server is running a command for any job (`/api/status` busy). */
export async function serverBusy() {
  try { return !!(await api("/api/status")).busy; } catch (_) { return false; }
}

/** Locks the matching controls in `root` with a reason, then calls `free()` once the server is idle. */
export function holdWhileBusy(root, selector, free) {
  root.querySelectorAll(selector).forEach((el) => {
    if (el.tagName === "A") { el.classList.add("cv-off"); el.setAttribute("aria-disabled", "true"); el.tabIndex = -1; el.addEventListener("click", (e) => e.preventDefault()); }
    else el.disabled = true;
    el.title = BUSY_REASON;
  });
  const stop = poll(async () => { if (!(await serverBusy())) { stop(); free(); } }, 2000, () => true);
}

export const isInterrupted = (job) => job.run_state === "INTERRUPTED";

/** C4-style failure card: steps with the failed one marked, the error, and a resume action. */
export function failureCard(job, { title = "We stopped at one step", openLink = false, startOver = true } = {}) {
  const stage = job.failed_stage || "input";
  const err = job.error || {};
  return `<div class="card cv-fail">
      <div class="cv-title"><h2>${esc(title)}</h2><span class="cv-flag danger">Needs attention</span></div>
      <p class="hint">Your upload and finished steps are saved. Resume picks up from the failed step.</p>
      ${stepList(STAGE_STEP[stage] ?? 0, true)}
      <div class="note pink cv-err"><span class="cv-tag">Error</span> ${esc(err.code || "E_UNKNOWN")} · ${esc(stage)}${err.retryable ? " · retry is safe" : ""}<p>${esc(err.detail || "")}</p></div>
      <div class="cv-actions">
        <button class="btn coral" data-resume-job="${esc(job.job_id)}">Resume from ${esc(STAGE_LABEL[stage] || stage)}</button>
        ${openLink ? `<a class="btn light" href="#/jobs/${esc(job.job_id)}">Open the job</a>` : ""}
        ${startOver ? `<a class="btn light" href="#/new">New job</a>` : ""}
      </div></div>`;
}

/** Wires resume buttons rendered by failureCard; calls `after(job)` once the run settles. */
export function wireResume(root, after) {
  root.querySelectorAll("[data-resume-job]").forEach((button) => button.onclick = async () => {
    const id = button.dataset.resumeJob;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Resuming`;
    try { await api(`/api/jobs/${id}/resume`, { method: "POST" }); }
    catch (err) { toast(errorText(err), true); }
    after(id);
    refreshBell();
  });
}

/** "Stop this attempt" form for one unresolved publish operation (UNKNOWN/PREPARED). */
export function stopForm(op, jobId) {
  return `<form class="cv-stop" data-stop-job="${esc(jobId)}" data-stop-key="${esc(op.operation_key)}" novalidate>
      <label class="field">Your name, recorded with this decision
        <input class="input" name="actor" required maxlength="80" autocomplete="name" value="${esc(actorName())}" placeholder="Your name"></label>
      ${actorError}
      <p class="hint">Stopping marks this request as abandoned. AdLoom will never re-send it, and this job can no longer publish. Anything already created stays paused.</p>
      <button class="btn light">Stop attempt</button></form>`;
}

export function wireStop(root, after) {
  root.querySelectorAll("form[data-stop-key]").forEach((form) => form.onsubmit = async (event) => {
    event.preventDefault();
    const actor = checkActor(form);
    if (!actor) return;
    const button = form.querySelector("button");
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Stopping`;
    try {
      await api(`/api/jobs/${form.dataset.stopJob}/publish/abandon`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operation_key: form.dataset.stopKey, actor }),
      });
      rememberActor(actor);
      toast("Attempt stopped. Nothing will be re-sent.");
      refreshBell();
      after();
    } catch (err) { toast(errorText(err), true); button.disabled = false; button.textContent = "Stop attempt"; }
  });
}

export const unresolved = (ops) => ops.filter((o) => (o.phase === "UNKNOWN" || o.phase === "PREPARED") && !o.abandoned);
