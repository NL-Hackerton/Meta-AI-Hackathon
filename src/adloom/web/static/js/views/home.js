import { app, esc, won, MAKING, jobBadge, needsNote, api, setNav } from "../core.js";
import { icon, jobName, thumb, ago, row, allAds } from "../library.js";
import { setBell } from "../notify.js";
import { refreshWhileRunning } from "../flow.js";

/* Home */
export async function viewHome() {
  setNav("home");
  const [{ profile }, jobs, notes] = await Promise.all([api("/api/profile"), api("/api/jobs"), api("/api/notifications")]);
  setBell(notes);
  const today = new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

  const STAGE = { input: "checking the video", understand: "understanding the video", track: "tracking the product", enrich: "making images and captions", assemble: "assembling the videos", publish: "publishing" };
  const unknownJobs = new Set(notes.filter((n) => n.kind === "unknown").map((n) => n.job_id));
  const running = jobs.filter((j) => j.run_state === "RUNNING" || j.run_state === "CANCEL_REQUESTED");
  const queue = jobs.filter((j) => j.state === "AWAITING_APPROVAL" || j.state === "APPROVED");
  const toApprove = jobs.filter((j) => j.state === "AWAITING_APPROVAL");
  const toPublish = jobs.filter((j) => j.state === "APPROVED");
  const noteCheck = jobs.filter(needsNote);
  const unknown = jobs.filter((j) => unknownJobs.has(j.job_id));
  const settled = (j) => !needsNote(j) && !unknownJobs.has(j.job_id);
  const interrupted = jobs.filter((j) => j.run_state === "INTERRUPTED" && settled(j));
  const failed = jobs.filter((j) => j.state === "FAILED" && j.run_state !== "INTERRUPTED" && settled(j));
  const making = jobs.filter((j) => MAKING.includes(j.state) && j.run_state !== "INTERRUPTED" && settled(j));
  const paused = allAds(jobs).length;

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const first = (list) => list.length === 1 ? `#/jobs/${list[0].job_id}` : null;
  const attention = [
    unknown.length && row({ href: first(unknown) || "#/jobs", lead: icon("alert"), cls: "danger",
      title: `${plural(unknown.length, "publish result")} unknown`, detail: "Check Meta before doing anything else · see the publish log" }),
    noteCheck.length && row({ href: first(noteCheck) || "#/jobs", lead: icon("pencil"),
      title: "Check what you said", detail: `${esc(jobName(noteCheck[0]))}${noteCheck.length > 1 ? ` and ${noteCheck.length - 1} more` : ""} · confirm or type the one-line description before we make ads` }),
    toApprove.length && row({ href: first(toApprove) || "#/approve", lead: icon("check"),
      title: `${plural(toApprove.length * 6, "ad video")} waiting for your approval`, detail: `${esc(jobName(toApprove[0]))} · ready ${ago(toApprove[0].updated_at)}` }),
    toPublish.length && row({ href: first(toPublish) || "#/approve", lead: icon("megaphone"),
      title: `${plural(toPublish.length, "approved job")} not published yet`, detail: "Publishing creates 2 paused ads" }),
    interrupted.length && row({ href: first(interrupted) || "#/jobs", lead: icon("clock"), cls: "danger",
      title: `${plural(interrupted.length, "job")} stopped partway`, detail: "Making was interrupted · open the job to resume" }),
    failed.length && row({ href: first(failed) || "#/jobs", lead: icon("alert"), cls: "danger",
      title: `${plural(failed.length, "job")} stopped`, detail: `Stopped while ${STAGE[failed[0].failed_stage] || "making ads"} · open the job to see why and resume` }),
    making.length && row({ href: first(making) || "#/jobs", lead: icon("clock"),
      title: `${plural(making.length, "job")} making`, detail: "Safe to close this page" }),
  ].filter(Boolean);
  const busy = running.length ? `<a class="note violet lv-busy" href="#/jobs/${esc(running[0].job_id)}"><span class="spinner" aria-hidden="true"></span><span><b>A job is being made</b> · ${esc(jobName(running[0]))}. Open it to follow along.</span></a>` : "";

  const title = !profile ? `Turn the video you <em>already shot</em> into ads`
    : toApprove.length ? `${toApprove.length === 1 ? "One video" : `${toApprove.length} videos`},<br><em>${toApprove.length * 6} ads</em> ready`
    : making.length ? `Your ads are<br><em>being made</em>`
    : `One video,<br><em>6 ads</em> paused and ready`;
  const sub = profile ? `${esc(today)} · ${esc(profile.business_name)} · ${esc(profile.region)}` : `${esc(today)} · set up takes about a minute`;

  const hero = `<section class="lv-hero">
      <div class="lv-hero-text"><span class="crumb">${profile ? `Hi, ${esc(profile.business_name)}` : "Welcome to AdLoom"}</span>
        <h1>${title}</h1><p class="sub">${sub}</p></div>
      <span class="lv-phone" aria-hidden="true"></span>
    </section>`;
  const setup = profile ? "" : `<a class="lv-setup" href="#/welcome"><span>${icon("user")}</span><span class="lv-text"><b>Set up your business first</b><small>Your area, daily budget and booking link fill in new jobs, and the language sets the ad copy. No account needed.</small></span><span class="btn coral small">Get started</span></a>`;
  const cta = `<a class="lv-cta" href="#/new">${icon("plus")}<b>Make ads from a video</b><span class="lv-chev" aria-hidden="true"></span></a>`;

  const latest = jobs[0];
  const latestCard = latest ? `<a class="card lv-latest" href="#/jobs/${esc(latest.job_id)}">
      ${thumb(latest, "lv-latest-thumb")}
      <span class="lv-text"><span class="hint">Latest · ${esc(ago(latest.updated_at))}</span><b>${esc(jobName(latest))}</b>
        <small>${esc(latest.headline || (needsNote(latest) ? "Check what you said" : latest.state === "FAILED" ? `Stopped while ${STAGE[latest.failed_stage] || "making ads"}` : "Six cuts from one video"))}</small>${jobBadge(latest)}</span>
    </a>` : `<div class="card lv-empty-mini"><b>No videos yet</b><span class="hint">Upload one 3–45 second phone video. We recut your real footage into 9:16, 4:5 and 1:1.</span></div>`;

  const tiles = `<div class="lv-tiles">
      <a class="card lv-tile" href="#/new"><b>New job</b><small>Upload video</small>${icon("plus")}</a>
      <a class="card lv-tile" href="#/approve"><b>To approve</b><small class="${queue.length ? "hot" : ""}">${plural(queue.length, "job")}</small>${icon("check")}</a>
      <a class="card lv-tile" href="#/ads"><b>My ads</b><small>${paused} paused</small>${icon("megaphone")}</a>
    </div>`;

  app.innerHTML = `<div class="lv-home">
      <div class="lv-home-main">${busy}${hero}${setup}${cta}
        <div class="card lv-list"><h2>What needs you</h2>${attention.join("") || `<p class="hint lv-none">Nothing needs you right now.${profile && profile.daily_budget_krw ? ` New ads default to ${won(profile.daily_budget_krw)}/day.` : ""}</p>`}</div>
        <p class="note violet lv-pill-note"><span class="lv-tag">Note</span> Nothing goes live without approval. Ads start paused, and AdLoom never turns them on.</p>
      </div>
      <div class="lv-home-side">${latestCard}${tiles}</div>
    </div>`;
  refreshWhileRunning(jobs, viewHome);
}
