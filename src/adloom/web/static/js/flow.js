"use strict";
// Shared helpers for the create → review → publish flow views.
import { esc, api, toast, errorText, stepList, NOTE_PENDING, needsNote } from "./core.js";
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

/** Repeats `fn` every `ms` while `alive()` holds; returns a stop function. */
export function poll(fn, ms, alive) {
  let stopped = false, timer = 0;
  const tick = async () => {
    if (stopped || !alive()) return;
    try { await fn(); } catch (_) { /* transient; the next tick retries */ }
    if (!stopped && alive()) timer = setTimeout(tick, ms);
  };
  timer = setTimeout(tick, ms);
  return () => { stopped = true; clearTimeout(timer); };
}

export const onRoute = (hash) => () => location.hash === hash;

export const actorName = () => localStorage.getItem("adloom.actor") || "";
export const rememberActor = (name) => localStorage.setItem("adloom.actor", name);

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
        ${startOver ? `<a class="btn light" href="#/new">Start over with a new video</a>` : ""}
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
  });
}

/** "Stop this attempt" form for one unresolved publish operation (UNKNOWN/PREPARED). */
export function stopForm(op, jobId) {
  return `<form class="cv-stop" data-stop-job="${esc(jobId)}" data-stop-key="${esc(op.operation_key)}">
      <label class="field">Your name, recorded with this decision
        <input class="input" name="actor" required maxlength="80" autocomplete="name" value="${esc(actorName())}" placeholder="Your name"></label>
      <p class="hint">Stopping marks this request as abandoned. AdLoom will never re-send it, and this job can no longer publish. Anything already created stays paused.</p>
      <button class="btn light">Stop attempt</button></form>`;
}

export function wireStop(root, after) {
  root.querySelectorAll("form[data-stop-key]").forEach((form) => form.onsubmit = async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const button = form.querySelector("button"), actor = form.actor.value.trim();
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Stopping`;
    try {
      await api(`/api/jobs/${form.dataset.stopJob}/publish/abandon`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operation_key: form.dataset.stopKey, actor }),
      });
      rememberActor(actor);
      toast("Attempt stopped. Nothing will be re-sent.");
      after();
    } catch (err) { toast(errorText(err), true); button.disabled = false; button.textContent = "Stop attempt"; }
  });
}

export const unresolved = (ops) => ops.filter((o) => (o.phase === "UNKNOWN" || o.phase === "PREPARED") && !o.abandoned);
