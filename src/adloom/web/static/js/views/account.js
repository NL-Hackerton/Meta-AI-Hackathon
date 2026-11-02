import { app, esc, won, when, jobBadge, api, toast, errorText, setNav } from "../core.js";
import { icon, jobName, thumb, row, allAds, backBar } from "../library.js";
import { setBell, unreadCount } from "../notify.js";

/* E5 MY */
export async function viewAccount() {
  setNav("me");
  const [{ profile }, jobs, notes, status] = await Promise.all([api("/api/profile"), api("/api/jobs"), api("/api/notifications"), api("/api/status")]);
  setBell(notes);
  const unread = unreadCount(notes);
  const toApprove = jobs.filter((j) => j.state === "AWAITING_APPROVAL" || j.state === "APPROVED").length;
  const metaLine = status.meta.connected ? "Meta connected" : "Meta not connected";
  const initial = profile ? esc(profile.business_name.trim().charAt(0).toUpperCase()) : icon("user", "gray");
  app.innerHTML = `<div class="head lv-head-row"><div><div class="crumb">This machine</div><h1>MY</h1></div></div>
    <div class="lv-account">
      <div class="stack">
        <div class="lv-profile">
          <div class="lv-who"><span class="lv-avatar" aria-hidden="true">${initial}</span>
            <div><b>${profile ? esc(profile.business_name) : "No business profile yet"}</b><small>${profile ? `${esc(profile.region)} · ${metaLine}` : metaLine}</small></div></div>
          <div class="lv-stats">
            <a href="#/jobs"><b>${jobs.length}</b><small>video${jobs.length === 1 ? "" : "s"}</small></a>
            <a href="#/ads"><b>${allAds(jobs).length}</b><small>ads paused</small></a>
            <a href="#/approve"><b>${toApprove}</b><small>to approve</small></a>
          </div>
        </div>
        ${profile ? "" : `<a class="lv-setup" href="#/welcome">${icon("user")}<span class="lv-text"><b>Set up your business</b><small>Area, budget and booking link for new jobs, and the language of the ad copy</small></span><span class="btn coral small">Start</span></a>`}
      </div>
      <div class="stack">
        <div class="card lv-list">
          ${row({ href: "#/me/profile", lead: icon("user"), title: "Business profile", detail: profile ? `${esc(profile.category)} · ${esc(profile.region)}${profile.destination_url ? " · booking link" : ""}` : "Name, area, booking link" })}
          ${row({ href: "#/me/meta", lead: icon("megaphone"), title: "Meta ad account", detail: status.meta.connected ? "Connected" : "Not connected · waiting for Meta approval" })}
          ${row({ href: "#/me/profile", lead: icon("chart"), title: "Ad defaults", detail: profile ? `${won(profile.daily_budget_krw)}/day · Traffic · always paused` : "Set a daily budget in your profile" })}
        </div>
        <div class="card lv-list">
          ${row({ href: "#/me/data", lead: icon("lock"), title: "Data & privacy", detail: "Where files live, deleting jobs" })}
          ${row({ href: "#/notifications", lead: icon("bell"), title: "Notifications", detail: unread ? `${unread} unread · ready, failed, published` : "Ready, failed, published", trail: unread ? `<span class="lv-count">${unread}</span>` : "" })}
          ${row({ href: "#/settings", lead: icon("gear"), title: "Settings", detail: "Model API, Meta account, safety locks" })}
          ${row({ href: "#/log", lead: icon("list"), title: "Publish log", detail: "Every call to Meta, step by step" })}
        </div>
      </div>
    </div>`;
}

/* E6 Data & privacy */
export async function viewData() {
  setNav("me");
  const [jobs, status] = await Promise.all([api("/api/jobs"), api("/api/status")]);
  const fixture = !status.live;
  const busy = Boolean(status.busy);
  const running = jobs.find((j) => j.run_state === "RUNNING" || j.run_state === "CANCEL_REQUESTED");
  const line = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
  const jobRow = (j) => `<li class="lv-row lv-del" data-job="${esc(j.job_id)}">
      ${thumb(j)}
      <span class="lv-text"><b>${esc(jobName(j))}</b><small>${esc(when(j.created_at))} · job ${esc(j.job_id.slice(0, 6))}${(j.published_ads || []).length ? " · 2 ads on Meta" : ""}</small></span>
      ${jobBadge(j)}
      <button class="btn light small" type="button" data-ask ${busy ? `disabled aria-describedby="busyNote"` : ""}>Delete</button>
      <div class="lv-confirm" hidden>
        <p><b>Delete this job from this machine?</b> Its source copy, renders, images and records are removed. This cannot be undone.${(j.published_ads || []).length ? " The 2 paused ads already created on Meta are not removed." : ""}</p>
        <p class="lv-err" role="alert"></p>
        <div class="lv-actions"><button class="btn danger small" type="button" data-delete>Delete job</button><button class="btn light small" type="button" data-cancel>Cancel</button></div>
      </div></li>`;
  app.innerHTML = backBar("#/me", "Data &amp; privacy") +
    `<div class="lv-data">
      <div class="stack">
        <div class="card"><h2>Where your data lives</h2><dl class="kv">
          ${line("Location", "The AdLoom data folder on this machine (<code>ADLOOM_DATA_DIR</code>)")}
          ${line("Uploads", "Copied into the job folder, then the upload copy is removed right away")}
          ${line("Profile", "<code>profile.json</code> in the same folder")}
          ${line("Notifications", "Read state is kept only in this browser")}
        </dl></div>
        <div class="card"><h2>Your videos on Meta Model API</h2><dl class="kv">
          ${line("Mode", `Standard · ${esc(status.spark_model)}`)}
          ${line("Now", fixture ? "Fixture mode · nothing is uploaded, no model runs" : "Live mode")}
          ${line("Deleted", "Live mode only: after each job finishes")}
          ${line("API key", status.model_api.key_present ? "Present on the server · never shown" : "Not set")}
        </dl></div>
        <div class="note yellow">Deleting never removes ads already created on Meta
          <p>Campaigns and ads stay in the ad account (paused) until you remove them in Ads Manager.</p></div>
      </div>
      <div class="card"><h2>Jobs on this machine · ${jobs.length}</h2>
        ${busy ? `<p class="note violet lv-gap" id="busyNote">Another job is being made${running ? ` · <a href="#/jobs/${esc(running.job_id)}">${esc(jobName(running))}</a>` : ""}<span class="lv-inline"> · deleting is paused until it finishes.</span></p>` : ""}
        ${jobs.length ? `<ul class="lv-dellist">${jobs.map(jobRow).join("")}</ul>` : `<p class="hint">No jobs stored. Nothing to delete.</p>`}
      </div>
    </div>`;
  app.querySelectorAll(".lv-del").forEach((li) => {
    const box = li.querySelector(".lv-confirm");
    const ask = li.querySelector("[data-ask]");
    ask.onclick = () => { box.hidden = false; ask.hidden = true; li.querySelector("[data-delete]").focus(); };
    li.querySelector("[data-cancel]").onclick = () => { box.hidden = true; ask.hidden = false; ask.focus(); };
    li.querySelector("[data-delete]").onclick = async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await api(`/api/jobs/${encodeURIComponent(li.dataset.job)}`, { method: "DELETE" });
        toast("Job deleted from this machine");
        await viewData();
      } catch (err) {
        li.querySelector(".lv-confirm .lv-err").textContent = errorText(err);
        button.disabled = false;
      }
    };
  });
}
