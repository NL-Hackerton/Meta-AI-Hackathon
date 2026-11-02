"use strict";
// Shared helpers for the home, library, account, onboarding and notification views.
import { esc } from "./core.js";

const ICON_PATHS = {
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  megaphone: '<path d="M4 10v4h3l7 4V6L7 10H4z"/><path d="M17 9a4 4 0 0 1 0 6"/>',
  chart: '<path d="M5 20V12M10 20V6M15 20v-9M20 20V4"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 10"/>',
  alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17v.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<rect x="4" y="5" width="16" height="14" rx="3"/><path d="M10 9.5v5l4-2.5z"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  pencil: '<path d="M4 20l1-4L16 5l3 3L8 19z"/>',
};
const TONES = { user: "violet", megaphone: "coral", chart: "violet", lock: "yellow", bell: "yellow", gear: "gray", check: "mint", alert: "pink", clock: "violet", plus: "coral", play: "coral", list: "gray", pencil: "violet" };

export function icon(name, tone = TONES[name]) {
  return `<span class="lv-icon ${tone}" aria-hidden="true"><svg viewBox="0 0 24 24">${ICON_PATHS[name]}</svg></span>`;
}

export const jobName = (job) => job.product_name || `Video ${job.job_id.slice(0, 6)}`;

export function thumb(job, cls = "lv-thumb") {
  return job.thumbnail_url ? `<img class="${cls}" src="${esc(job.thumbnail_url)}" alt="" loading="lazy">` : `<span class="${cls}" aria-hidden="true"></span>`;
}

export function ago(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.round(ms / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const hours = Math.round(min / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
export function dayLabel(iso) {
  const days = Math.round((startOfDay(new Date()) - startOfDay(new Date(iso))) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return new Date(iso).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function groupBy(items, keyOf) {
  const groups = new Map();
  for (const item of items) {
    const key = keyOf(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return [...groups];
}

// One tappable list row: leading visual, title, detail, trailing element.
export function row({ href, lead = "", title, detail = "", trail = "", cls = "" }) {
  const inner = `${lead}<span class="lv-text"><b>${title}</b>${detail ? `<small>${detail}</small>` : ""}</span>${trail}`;
  return href ? `<a class="lv-row ${cls}" href="${esc(href)}">${inner}<span class="lv-chev" aria-hidden="true"></span></a>` : `<div class="lv-row ${cls}">${inner}</div>`;
}

export function backBar(href, title, action = "") {
  return `<div class="lv-top"><a class="lv-back" href="${href}" aria-label="Back"></a><h1>${title}</h1>${action}</div>`;
}

export function progress(step, total) {
  return `<div class="lv-progress" role="img" aria-label="Step ${step} of ${total}"><span style="width:${(step / total) * 100}%"></span></div><span class="lv-step">${step} / ${total}</span>`;
}

export const allAds = (jobs) => jobs.flatMap((job) => (job.published_ads || []).map((ad) => ({ ...ad, job })));
