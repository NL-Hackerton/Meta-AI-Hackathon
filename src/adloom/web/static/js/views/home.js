import { app, esc, won, MAKING, jobBadge, api, setNav } from "../core.js";
import { icon, jobName, thumb, ago, row, allAds } from "../library.js";
import { setBell } from "../notify.js";

/* Home */
export async function viewHome() {
  setNav("home");
  const [{ profile }, jobs, notes] = await Promise.all([api("/api/profile"), api("/api/jobs"), api("/api/notifications")]);
  setBell(notes);
  const today = new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

  const unknownJobs = new Set(notes.filter((n) => n.kind === "unknown").map((n) => n.job_id));
  const toApprove = jobs.filter((j) => j.state === "AWAITING_APPROVAL");
  const toPublish = jobs.filter((j) => j.state === "APPROVED");
  const noteReview = jobs.filter((j) => j.note_status === "REVIEW_REQUIRED" && j.state !== "FAILED");
  const making = jobs.filter((j) => MAKING.includes(j.state) && j.note_status !== "REVIEW_REQUIRED");
  const failed = jobs.filter((j) => j.state === "FAILED" && !unknownJobs.has(j.job_id));
  const unknown = jobs.filter((j) => unknownJobs.has(j.job_id));
  const paused = allAds(jobs).length;

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const first = (list) => list.length === 1 ? `#/jobs/${list[0].job_id}` : null;
  const attention = [
    unknown.length && row({ href: first(unknown) || "#/jobs", lead: icon("alert"), cls: "danger",
      title: `${plural(unknown.length, "publish result")} unknown`, detail: "Check Meta before doing anything else · see the publish log" }),
    toApprove.length && row({ href: first(toApprove) || "#/approve", lead: icon("check"),
      title: `${plural(toApprove.length * 6, "ad video")} waiting for your approval`, detail: `${esc(jobName(toApprove[0]))} · ready ${ago(toApprove[0].updated_at)}` }),
    toPublish.length && row({ href: first(toPublish) || "#/approve", lead: icon("megaphone"),
      title: `${plural(toPublish.length, "approved job")} not published yet`, detail: "Publishing creates 2 paused ads" }),
    noteReview.length && row({ href: first(noteReview) || "#/jobs", lead: icon("pencil"),
      title: `Confirm what you said · ${plural(noteReview.length, "job")}`, detail: "Check the transcript before we make ads" }),
    making.length && row({ href: first(making) || "#/jobs", lead: icon("clock"),
      title: `${plural(making.length, "job")} making`, detail: "Safe to close this page" }),
    failed.length && row({ href: first(failed) || "#/jobs", lead: icon("alert"), cls: "danger",
      title: `${plural(failed.length, "job")} stopped`, detail: esc(failed[0].error?.detail || "Open to resume") }),
  ].filter(Boolean);

  const title = !profile ? `Turn the video you <em>already shot</em> into ads`
    : toApprove.length ? `One video,<br><em>${toApprove.length * 6} ads</em> ready`
    : making.length ? `Your ads are<br><em>being made</em>`
    : `One video,<br><em>6 ads</em> paused and ready`;
  const sub = profile ? `${esc(today)} · ${esc(profile.business_name)} · ${esc(profile.region)}` : `${esc(today)} · set up takes about a minute`;

  const hero = `<section class="lv-hero">
      <div class="lv-hero-text"><span class="crumb">${profile ? `Hi, ${esc(profile.business_name)}` : "Welcome to AdLoom"}</span>
        <h1>${title}</h1><p class="sub">${sub}</p></div>
      <span class="lv-phone" aria-hidden="true"></span>
    </section>`;
  const setup = profile ? "" : `<a class="lv-setup" href="#/welcome"><span>${icon("user")}</span><span class="lv-text"><b>Set up your business first</b><small>Name, area and budget are used for the copy and the end card. No account needed.</small></span><span class="btn coral small">Get started</span></a>`;
  const cta = `<a class="lv-cta" href="#/new">${icon("plus")}<b>Make ads from a video</b><span class="lv-chev" aria-hidden="true"></span></a>`;

  const latest = jobs[0];
  const latestCard = latest ? `<a class="card lv-latest" href="#/jobs/${esc(latest.job_id)}">
      ${thumb(latest, "lv-latest-thumb")}
      <span class="lv-text"><span class="hint">Latest · ${esc(ago(latest.updated_at))}</span><b>${esc(jobName(latest))}</b>
        <small>${esc(latest.headline || (latest.error ? latest.error.detail : "Six cuts from one video"))}</small>${jobBadge(latest)}</span>
    </a>` : `<div class="card lv-empty-mini"><b>No videos yet</b><span class="hint">Upload one 3–45 second phone video. We recut your real footage into 9:16, 4:5 and 1:1.</span></div>`;

  const tiles = `<div class="lv-tiles">
      <a class="card lv-tile" href="#/new"><b>New ad</b><small>Upload video</small>${icon("plus")}</a>
      <a class="card lv-tile" href="#/approve"><b>To approve</b><small class="${toApprove.length ? "hot" : ""}">${plural(toApprove.length, "job")}</small>${icon("check")}</a>
      <a class="card lv-tile" href="#/ads"><b>My ads</b><small>${paused} paused</small>${icon("megaphone")}</a>
    </div>`;

  app.innerHTML = `<div class="lv-home">
      <div class="lv-home-main">${hero}${setup}${cta}
        <div class="card lv-list"><h2>What needs you</h2>${attention.join("") || `<p class="hint lv-none">Nothing needs you right now.${profile && profile.daily_budget_krw ? ` New ads default to ${won(profile.daily_budget_krw)}/day.` : ""}</p>`}</div>
        <p class="note violet lv-pill-note"><span class="lv-tag">Note</span> Nothing goes live without approval. Ads start paused, and AdLoom never turns them on.</p>
      </div>
      <div class="lv-home-side">${latestCard}${tiles}</div>
    </div>`;
}
