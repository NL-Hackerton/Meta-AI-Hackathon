import { app, esc, api, setNav } from "../core.js";
import { icon, jobName, dayLabel, groupBy, backBar } from "../library.js";
import { readIds, markRead, markAllRead, setBell } from "../notify.js";

const KIND = { ready: "check", failed: "alert", published: "megaphone", unknown: "alert", note_review: "pencil" };

/* E7 Notifications */
export async function viewNotifications() {
  setNav("notifications");
  const [items, jobs] = await Promise.all([api("/api/notifications"), api("/api/jobs")]);
  const names = Object.fromEntries(jobs.map((j) => [j.job_id, jobName(j)]));
  const firstAd = Object.fromEntries(jobs.filter((j) => (j.published_ads || []).length).map((j) => [j.job_id, j.published_ads[0].hook_id]));
  const render = () => {
    const read = readIds();
    const unread = items.filter((n) => !read.has(n.id)).length;
    setBell(items);
    const time = (iso) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    const entry = (n) => {
      const isUnread = !read.has(n.id);
      const href = n.kind === "published" && firstAd[n.job_id] ? `#/ads/${n.job_id}/${firstAd[n.job_id]}` : `#/jobs/${n.job_id}`;
      return `<a class="lv-row lv-note ${isUnread ? "unread" : ""}" href="${esc(href)}" data-id="${esc(n.id)}">
          ${icon(KIND[n.kind] || "bell", n.kind === "failed" || n.kind === "unknown" ? "pink" : undefined)}
          <span class="lv-text"><b>${esc(n.title)}</b><small>${esc(n.detail)}</small>
            <small>${esc(names[n.job_id] || `job ${n.job_id.slice(0, 6)}`)} · ${esc(time(n.at))}</small></span>
          ${isUnread ? `<span class="lv-unread"><span class="sr-only">Unread</span></span>` : ""}
          <span class="lv-chev" aria-hidden="true"></span></a>`;
    };
    app.innerHTML = backBar("#/me", "Notifications", `<button class="lv-link" type="button" id="markAll" ${unread ? "" : "disabled"}>Mark all read</button>`) +
      (items.length
        ? `<p class="sub lv-gap">${unread ? `${unread} unread` : "All caught up"} · read state is kept in this browser only.</p>
           <div class="lv-groups">${groupBy(items, (n) => dayLabel(n.at)).map(([label, list]) => `<section class="card lv-list"><h2 class="lv-group">${esc(label)}</h2>${list.map(entry).join("")}</section>`).join("")}</div>`
        : `<div class="card empty"><span class="lv-hero-icon bell" aria-hidden="true"></span><b>No notifications</b><span class="hint">You will see ready, failed and published jobs here.</span></div>`);
    document.getElementById("markAll").onclick = () => { markAllRead(items); render(); };
    app.querySelectorAll("[data-id]").forEach((a) => a.addEventListener("click", () => markRead([a.dataset.id])));
  };
  render();
}
