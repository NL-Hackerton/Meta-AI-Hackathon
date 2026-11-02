"use strict";
export const app = document.getElementById("app");
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const won = (n) => "₩" + Number(n).toLocaleString("en-US");
export const short = (h) => h ? `${h.slice(0, 4)}…${h.slice(-4)}` : "—";
export const when = (iso) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
export const MAKING = ["CREATED", "UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED"];
export const STATE = {
  AWAITING_APPROVAL: ["Ready to approve", "b-done"],
  APPROVED: ["Approved", "b-progress"],
  PUBLISHED_PAUSED: ["Paused on Meta", "b-paused"],
  FAILED: ["Failed", "b-danger"],
};
export const stateBadge = (s) => { const [label, cls] = STATE[s] || ["Making", "b-progress"]; return `<span class="badge ${cls}">${label}</span>`; };
export const NOTE_PENDING = ["AUDIO_PENDING", "REVIEW_REQUIRED"];
export const needsNote = (job) => NOTE_PENDING.includes(job.note_status) && (job.state === "CREATED" || (job.state === "FAILED" && job.failed_stage === "input"));
export const jobBadge = (job) => needsNote(job) ? `<span class="badge b-warn">Check description</span>` : stateBadge(job.state);
export const PHASE = { CONFIRMED: ["Confirmed", "b-done"], PREPARED: ["Unknown", "b-danger"], UNKNOWN: ["Unknown", "b-danger"], FAILED: ["Failed · not sent", "b-warn"] };
export const RESOURCE = { campaign: "Campaign", adset: "Ad set", image: "Thumbnail", video: "Video", creative: "Creative", ad: "Ad" };
export const resourceName = (op) => RESOURCE[op.resource_kind] + (op.hook_id ? ` · Hook ${op.hook_id.toUpperCase()}` : "");

// Navigation lifecycle. Each hash change starts a new navigation; work started by the
// previous screen must not touch the new one.
let navId = 0;
let leaving = [];
let routing = false;
let after = [];
/** Starts a navigation: runs the previous screen's cleanups and returns the new id. */
export function beginNav() {
  const cleanups = leaving;
  leaving = [];
  after = [];
  routing = true;
  for (const fn of cleanups) { try { fn(); } catch (_) { /* cleanup must not block navigation */ } }
  // A toast belongs to the screen that raised it, unless it was raised to hand off to the
  // next screen (e.g. "Approved" right before navigating), which happens within a moment.
  const now = Date.now();
  document.querySelectorAll(".toast").forEach((el) => { if (now - Number(el.dataset.at) > 400) el.remove(); });
  return ++navId;
}
/** Ends a navigation once the new screen is interactive and runs its afterRender callbacks. */
export function endNav() {
  routing = false;
  const fns = after;
  after = [];
  for (const fn of fns) { try { fn(); } catch (_) { /* a failed focus/scroll must not break the screen */ } }
}
export const currentNav = () => navId;
/** Registers cleanup (stop timers, microphones, observers) for the current screen. */
export function onLeave(fn) { leaving.push(fn); }
/** Runs `fn` once the screen is interactive; focus and scroll targets for a new screen go here. */
export function afterRender(fn) {
  if (routing) after.push(fn);
  else requestAnimationFrame(fn);
}

/**
 * JSON request with the cross-site guard header. A response that arrives after the user has
 * left the screen that asked for it never settles, so stale code cannot render over the new
 * screen or show its toasts there. Pass `global: true` for work that outlives the screen.
 */
export async function api(path, options = {}) {
  const { global = false, ...init } = options;
  const started = navId;
  const headers = { ...(init.headers || {}), "X-AdLoom-Request": "1" };
  const stale = () => !global && started !== navId;
  let response, body;
  try {
    response = await fetch(path, { ...init, headers });
    body = await response.json().catch(() => ({}));
  } catch (err) {
    if (stale()) return new Promise(() => {});
    throw err;
  }
  if (stale()) return new Promise(() => {});
  if (!response.ok) {
    const error = new Error(body.error?.detail || `Request failed (${response.status})`);
    error.code = body.error?.code;
    throw error;
  }
  return body;
}
export function toast(message, error = false) {
  document.querySelectorAll(".toast").forEach((old) => old.remove());
  const el = document.createElement("div");
  el.className = "toast" + (error ? " error" : "");
  el.setAttribute("role", error ? "alert" : "status");
  el.textContent = message;
  el.dataset.at = String(Date.now());
  document.body.append(el);
  setTimeout(() => el.remove(), error ? 6000 : 4200);
}
const FRIENDLY = {
  E_JOB_BUSY: "Another job is being made. Try again when it finishes.",
};
export function errorText(err) {
  if (FRIENDLY[err.code]) return FRIENDLY[err.code];
  return err.code ? `${err.code} · ${err.message}` : err.message;
}
/** Marks the current section in both navs. Mobile tabs also stand for related screens. */
export function setNav(key) {
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const also = (a.dataset.also || "").split(" ").filter(Boolean);
    if (key && (a.dataset.nav === key || also.includes(key))) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}
export function head(crumb, title, sub, action = "") {
  return `<div class="head"><div><div class="crumb">${crumb}</div><h1>${title}</h1><p class="sub">${sub}</p></div>${action}</div>`;
}


export async function resume(jobId, button) {
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Resuming`;
  try { await api(`/api/jobs/${jobId}/resume`, { method: "POST" }); location.hash = `#/jobs/${jobId}`; }
  catch (err) { toast(errorText(err), true); button.disabled = false; button.textContent = "Resume"; }
}


export const STEPS = [
  ["Understand", "Muse Spark finds the product, key scenes and 3 hooks"],
  ["Track", "SAM 3.1 follows the product for each ratio"],
  ["Images & captions", "Thumbnails, end cards and spoken captions"],
  ["Assemble", "6 videos: 9:16, 4:5, 1:1 × hook A and B"],
  ["You approve", "Then 2 paused ads are created on Meta"],
];
export function stepList(activeIndex, failed = false) {
  return `<ol class="steps">${STEPS.map(([t, d], i) => {
    const cls = i < activeIndex ? "done" : i === activeIndex ? (failed ? "failed" : "active") : "";
    const mark = i < activeIndex ? "✓" : i + 1;
    const tail = i === activeIndex && !failed && i < 4 ? `<span class="spinner" aria-label="In progress"></span>` : "";
    return `<li class="${cls}"><i>${mark}</i><div><b>${t}</b><small>${d}</small></div>${tail}</li>`;
  }).join("")}</ol>`;
}
