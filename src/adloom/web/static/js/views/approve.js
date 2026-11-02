import { app, esc, won, api, setNav, head } from "../core.js";
import { jobName, thumb, ago } from "../library.js";
import { refreshWhileRunning } from "../flow.js";

/* E4 Approve queue */
export async function viewApprove() {
  setNav("approve");
  const jobs = await api("/api/jobs");
  const queue = jobs.filter((j) => j.state === "AWAITING_APPROVAL" || j.state === "APPROVED")
    .sort((a, b) => (a.state === b.state ? 0 : a.state === "AWAITING_APPROVAL" ? -1 : 1));
  const card = (j) => {
    const waiting = j.state === "AWAITING_APPROVAL";
    const hooks = (j.hooks || []).map((h) => `<li><span class="lv-hook">${esc(h.id.toUpperCase())}</span>${esc(h.text)}</li>`).join("");
    return `<article class="card lv-queue">
        <a class="lv-queue-row" href="#/jobs/${esc(j.job_id)}">
          ${thumb(j, "lv-queue-thumb")}
          <div class="lv-text"><b>${esc(jobName(j))}</b>
            <small>${waiting ? "Ready" : "Approved"} ${esc(ago(j.updated_at))} · 6 videos · revision ${esc(j.revision)}${j.daily_budget_krw ? ` · ${won(j.daily_budget_krw)}/day` : ""}</small>
            <span class="badge ${waiting ? "b-done" : "b-progress"}">${waiting ? "Ready to approve" : "Approved · not published yet"}</span>
            ${hooks ? `<ul class="lv-hooks">${hooks}</ul>` : ""}
          </div>
        </a>
        <a class="btn ${waiting ? "coral" : ""} wide" href="#/jobs/${esc(j.job_id)}">${waiting ? "Review & approve" : "Open to publish"}</a>
      </article>`;
  };
  app.innerHTML = head(`${queue.length} waiting`, "To approve", "These are ready and waiting for you. Nothing is sent to Meta until you approve.") +
    (queue.length
      ? `<div class="lv-queue-grid">${queue.map(card).join("")}</div>`
      : `<div class="card empty">${`<span class="lv-hero-icon check" aria-hidden="true"></span>`}<b>Nothing to approve</b>
          <span class="hint">When your six videos are ready they show up here for review.</span>
          <a class="btn coral" href="#/new">Make ads from a video</a></div>`);
  refreshWhileRunning(jobs, viewApprove);
}
