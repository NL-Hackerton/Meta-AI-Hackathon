import { app, esc, when, api, setNav, head } from "../core.js";
import { jobName, thumb, groupBy, allAds, backBar } from "../library.js";

const monthLabel = (iso) => {
  const date = new Date(iso);
  const days = (Date.now() - date.getTime()) / 86400000;
  return days < 7 ? "This week" : date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
};

/* E1 My ads · E2 empty */
export async function viewAds() {
  setNav("ads");
  const jobs = await api("/api/jobs");
  const ads = allAds(jobs);
  const published = jobs.filter((j) => (j.published_ads || []).length);
  const waiting = jobs.filter((j) => j.state === "AWAITING_APPROVAL").length;
  if (!ads.length) {
    app.innerHTML = head("Paused ads on Meta", "My ads", "Ads appear here after you approve and publish a job.") +
      `<div class="card empty lv-empty"><span class="lv-hero-icon camera" aria-hidden="true"></span><b>No ads yet</b>
        <span class="hint">Shoot 3–45 seconds of your work and we will turn it into six ad videos.</span>
        ${waiting ? `<a class="btn coral" href="#/approve">Approve ${waiting} waiting job${waiting === 1 ? "" : "s"}</a>` : `<a class="btn coral" href="#/new">Make ads from a video</a>`}</div>`;
    return;
  }
  const hookText = (ad) => (ad.job.hooks || []).find((h) => h.id === ad.hook_id)?.text || "";
  const groups = groupBy(ads, (ad) => monthLabel(ad.job.updated_at));
  const item = (ad) => `<a class="lv-row lv-ad" href="#/ads/${esc(ad.job.job_id)}/${esc(ad.hook_id)}">
      ${thumb(ad.job)}
      <span class="lv-text"><b>${esc(jobName(ad.job))} · Hook ${esc(ad.hook_id.toUpperCase())}</b>
        <small>${esc(hookText(ad))}</small><small class="mono">ad ${esc(ad.ad_id)}</small></span>
      <span class="badge b-paused">${esc(ad.configured_status === "PAUSED" ? "Paused" : ad.configured_status)}</span>
      <span class="lv-chev" aria-hidden="true"></span></a>`;
  app.innerHTML = head(`${ads.length} ads · ${published.length} campaign${published.length === 1 ? "" : "s"}`, "My ads",
      "Every ad AdLoom created on Meta. All of them start paused — you turn them on in Ads Manager.") +
    `<p class="note yellow lv-gap">Fixture IDs<span class="lv-inline"> · these ads were created by the mock Meta provider, not on a real ad account.</span></p>
     <div class="lv-groups">${groups.map(([label, list]) => `<section class="card lv-list"><h2 class="lv-group">${esc(label)}</h2>${list.map(item).join("")}</section>`).join("")}</div>`;
}

/* E3 Ad detail */
export async function viewAd(jobId, hookId) {
  setNav("ads");
  const [jobs, detail] = await Promise.all([api("/api/jobs"), api(`/api/jobs/${encodeURIComponent(jobId)}`)]);
  const job = jobs.find((j) => j.job_id === jobId);
  const ad = job?.published_ads?.find((a) => a.hook_id === hookId);
  const result = detail.snapshot.publish_result;
  if (!job || !ad || !result) {
    app.innerHTML = backBar("#/ads", "Ad") + `<div class="card empty"><b>This ad is not published</b><span class="hint">Job ${esc(jobId.slice(0, 6))} has no paused ad for hook ${esc(hookId.toUpperCase())}.</span><a class="btn light" href="#/ads">Back to my ads</a></div>`;
    return;
  }
  const published = result.ads.find((a) => a.hook_id === hookId);
  const u = detail.snapshot.understanding;
  const plan = detail.snapshot.publish_plan;
  const hookText = (job.hooks || []).find((h) => h.id === hookId)?.text || "";
  const other = job.published_ads.filter((a) => a.hook_id !== hookId);
  const fixture = result.execution_mode !== "live";
  const history = [
    [result.checked_at, `Published ${result.ads.length} ads · paused`],
    detail.approval && [detail.approval.approved_at, `Approved revision ${detail.approval.revision} by ${detail.approval.actor}`],
    [job.created_at, "Job created"],
  ].filter(Boolean);
  const cta = (plan?.cta || u?.cta || "").replaceAll("_", " ").toLowerCase();
  app.innerHTML = backBar("#/ads", `${esc(jobName(job))} · Hook ${esc(hookId.toUpperCase())}`) +
    `<div class="lv-detail">
      <div class="lv-player card">
        <video src="${esc(ad.video_url)}" controls playsinline preload="metadata" aria-label="9:16 ad video, hook ${esc(hookId.toUpperCase())}"></video>
        <div class="lv-hooknav"><span class="badge b-paused">9:16 · Hook ${esc(hookId.toUpperCase())}</span>
          ${other.map((a) => `<a class="btn light small" href="#/ads/${esc(jobId)}/${esc(a.hook_id)}">See Hook ${esc(a.hook_id.toUpperCase())}</a>`).join("")}</div>
      </div>
      <div class="stack">
        <div class="card"><div class="lv-status"><h2>On Meta · paused</h2><span class="badge b-paused">${esc(published.configured_status === "PAUSED" ? "Paused" : published.configured_status)}</span></div>
          <p class="sub">${result.ads.length} ads were created ${esc(when(result.checked_at))}. AdLoom never activates ads — turn them on in Ads Manager when you are ready.</p>
          <div class="lv-actions"><a class="btn small" href="#/jobs/${esc(jobId)}/log">Publish log</a><a class="btn light small" href="#/jobs/${esc(jobId)}">Open job</a></div>
          ${fixture ? `<p class="note yellow lv-gap">Fixture IDs<span class="lv-inline"> · created by the mock Meta provider (${esc(result.execution_mode)} mode). Nothing exists in a real ad account.</span></p>` : ""}
        </div>
        <div class="card"><h2>Copy</h2><dl class="kv">
          <dt>Hook ${esc(hookId.toUpperCase())}</dt><dd>${esc(hookText)}</dd>
          ${u ? `<dt>Headline</dt><dd>${esc(u.headline)}</dd><dt>Primary text</dt><dd>${esc(u.primary_text)}</dd>` : ""}
          ${cta ? `<dt>Button</dt><dd>${esc(cta)}</dd>` : ""}</dl></div>
        <div class="card"><h2>IDs on Meta</h2><dl class="kv mono">
          <dt>Campaign</dt><dd>${esc(result.campaign_id)} · ${esc(result.campaign_status)}</dd>
          <dt>Ad set</dt><dd>${esc(result.adset_id)} · ${esc(result.adset_status)}</dd>
          <dt>Ad</dt><dd>${esc(published.ad_id)} · ${esc(published.configured_status)}</dd>
          <dt>Creative</dt><dd>${esc(published.creative_id)}</dd>
          <dt>Video</dt><dd>${esc(published.video_id)}</dd></dl></div>
        <div class="card"><h2>History</h2><dl class="kv lv-history">${history.map(([at, text]) => `<dt>${esc(when(at))}</dt><dd>${esc(text)}</dd>`).join("")}</dl></div>
      </div>
    </div>`;
}
