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

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), "X-AdLoom-Request": "1" };
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
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
  el.setAttribute("role", "status");
  el.textContent = message;
  document.body.append(el);
  setTimeout(() => el.remove(), 4200);
}
export function errorText(err) { return err.code ? `${err.code} · ${err.message}` : err.message; }
export function setNav(key) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.dataset.nav === key ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
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
