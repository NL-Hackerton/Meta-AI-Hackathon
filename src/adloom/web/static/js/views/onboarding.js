import { app, esc, won, api, toast, errorText, setNav } from "../core.js";
import { icon, progress } from "../library.js";

/* A1 Welcome · web Landing */
export async function viewWelcome() {
  setNav("home");
  const [{ profile }, status] = await Promise.all([api("/api/profile"), api("/api/status")]);
  const fixture = !status.live;
  app.innerHTML = `<div class="lv-welcome">
      <section class="lv-landing">
        <span class="lv-phone big" aria-hidden="true"></span>
        <div>
          <h1 class="lv-display">One phone video.<br><em>Six ads, paused and ready.</em></h1>
          <p class="sub lv-lead">AdLoom turns your real footage into 9:16, 4:5 and 1:1 ads with hooks, captions and copy — then creates them on Meta as paused, only after you approve.</p>
          <ul class="lv-bullets">
            <li>${icon("play")}<span><b>6 ad videos from one clip</b><small>A 3–45 second phone video and one line about it</small></span></li>
            <li>${icon("check")}<span><b>Nothing goes live without your approval</b><small>Approval fingerprints exactly the videos and copy you saw</small></span></li>
            <li>${icon("lock")}<span><b>No generated video</b><small>Every frame comes from your own footage and images</small></span></li>
          </ul>
          <div class="lv-actions">
            <a class="btn coral" href="#/me/profile">${profile ? "Edit business profile" : "Set up your business"}</a>
            <a class="btn light" href="${profile ? "#/" : "#/new"}">${profile ? "Go to home" : "Try a video first"}</a>
          </div>
        </div>
      </section>
      ${fixture ? `<div class="note yellow">This copy runs in fixture mode
          <p>Models and Meta are replaced by recorded fixtures: no inference runs, no ads are created, and every ID you see is a fixture ID. Only the bundled sample video completes the full flow.</p></div>` : ""}
      <div class="lv-duo">
        <div class="card lv-duo-card peach"><span class="crumb">Shop owners · on the phone</span><h2>Make ads from your own video</h2>
          <p class="sub">Shoot or pick a clip, say one line about it, check six results and approve. That is the whole flow.</p>
          <a class="btn coral small" href="#/new">Make ads from a video</a></div>
        <div class="card lv-duo-card dark"><span class="crumb">Agencies · on desktop</span><h2>Review every ad before it reaches Meta</h2>
          <p class="sub">Side-by-side source and crops, policy rewrites, approval fingerprints and the paused publish journal.</p>
          <a class="btn light small" href="#/jobs">Open jobs</a></div>
      </div>
    </div>`;
}

const CATEGORIES = ["Home services", "Food", "Beauty", "Retail", "Repair"];

function check(values) {
  const errors = {};
  if (values.business_name.length < 1 || values.business_name.length > 60) errors.business_name = "Enter 1–60 characters.";
  if (values.category.length < 1 || values.category.length > 40) errors.category = "Pick or type a category (1–40 characters).";
  if (values.region.length < 1 || values.region.length > 60) errors.region = "Enter the area you serve (1–60 characters).";
  if (!Number.isInteger(values.daily_budget_krw) || values.daily_budget_krw < 1000) errors.daily_budget_krw = "Use a whole number of at least ₩1,000.";
  if (values.destination_url !== null) {
    let ok = false;
    try { ok = new URL(values.destination_url).protocol === "https:"; } catch { ok = false; }
    if (!ok) errors.destination_url = "Use a full https:// link, or leave it empty.";
  }
  return errors;
}

/* A3 Business profile */
export async function viewProfile() {
  setNav("me");
  const { profile } = await api("/api/profile");
  const p = profile || { business_name: "", category: "", region: "", daily_budget_krw: 10000, destination_url: null, language: "ko" };
  const field = (name, label, input, hint = "") => `<label class="field" for="pf-${name}">${label}${input}<span class="lv-err" id="err-${name}" role="alert"></span>${hint ? `<span class="hint">${hint}</span>` : ""}</label>`;
  app.innerHTML = `<div class="lv-onb">
      <div class="lv-onb-top"><a class="lv-back" href="${profile ? "#/me" : "#/welcome"}" aria-label="Back"></a>${profile ? "" : progress(1, 3)}</div>
      <h1>${profile ? "Business profile" : "Tell us about<br>your business"}</h1>
      <p class="sub">Used for copy tone, the ad end card and the defaults for new jobs. You can change it anytime.</p>
      <form class="card lv-form" id="profileForm" novalidate>
        ${field("business_name", "Business name", `<input class="input" id="pf-business_name" name="business_name" maxlength="60" autocomplete="organization" value="${esc(p.business_name)}" aria-describedby="err-business_name">`)}
        <div class="field"><span id="cat-label">What you do</span>
          <div class="chips" role="group" aria-labelledby="cat-label">${CATEGORIES.map((c) => `<button type="button" class="chip" data-cat="${esc(c)}" aria-pressed="${p.category === c}">${esc(c)}</button>`).join("")}</div>
          <input class="input" id="pf-category" name="category" maxlength="40" placeholder="Or type your own, e.g. Plumbing" value="${esc(p.category)}" aria-labelledby="cat-label" aria-describedby="err-category">
          <span class="lv-err" id="err-category" role="alert"></span></div>
        ${field("region", "Service area", `<input class="input" id="pf-region" name="region" maxlength="60" value="${esc(p.region)}" aria-describedby="err-region">`, "Used for ad targeting notes and copy")}
        <div class="lv-form2">
          ${field("daily_budget_krw", "Daily budget (KRW)", `<input class="input" id="pf-daily_budget_krw" name="daily_budget_krw" type="number" inputmode="numeric" min="1000" step="1000" value="${esc(p.daily_budget_krw)}" aria-describedby="err-daily_budget_krw">`, "Per ad set · ads still start paused")}
          ${field("language", "Copy language", `<select class="input" id="pf-language" name="language">${[["ko", "Korean"], ["en", "English"]].map(([v, l]) => `<option value="${v}" ${p.language === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}
        </div>
        ${field("destination_url", "Booking or website link", `<input class="input" id="pf-destination_url" name="destination_url" type="url" inputmode="url" placeholder="https://" value="${esc(p.destination_url || "")}" aria-describedby="err-destination_url">`, "Optional · where the Learn more button goes")}
        <p class="lv-err" id="err-form" role="alert"></p>
        <button class="btn coral wide" type="submit">${profile ? "Save" : "Continue"}</button>
      </form>
    </div>`;
  const form = document.getElementById("profileForm");
  const category = document.getElementById("pf-category");
  const syncChips = () => form.querySelectorAll("[data-cat]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.cat === category.value.trim())));
  form.querySelectorAll("[data-cat]").forEach((b) => b.onclick = () => { category.value = b.dataset.cat; syncChips(); });
  category.oninput = syncChips;
  form.onsubmit = async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const url = String(data.get("destination_url")).trim();
    const values = {
      business_name: String(data.get("business_name")).trim(),
      category: String(data.get("category")).trim(),
      region: String(data.get("region")).trim(),
      daily_budget_krw: Number(data.get("daily_budget_krw")),
      destination_url: url || null,
      language: String(data.get("language")),
    };
    const errors = check(values);
    form.querySelectorAll(".lv-err").forEach((el) => { el.textContent = ""; });
    form.querySelectorAll(".input").forEach((el) => el.removeAttribute("aria-invalid"));
    for (const [name, message] of Object.entries(errors)) {
      document.getElementById(`err-${name}`).textContent = message;
      document.getElementById(`pf-${name}`)?.setAttribute("aria-invalid", "true");
    }
    if (Object.keys(errors).length) { document.getElementById(`pf-${Object.keys(errors)[0]}`)?.focus(); return; }
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await api("/api/profile", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
      toast("Business profile saved");
      location.hash = profile ? "#/me" : "#/me/meta";
    } catch (err) {
      document.getElementById("err-form").textContent = errorText(err);
      button.disabled = false;
    }
  };
}

const PERMISSIONS = {
  ads_management: ["megaphone", "Manage ads", "Create paused campaigns, ad sets and ads"],
  pages_read_engagement: ["user", "Read your Page", "Show ads as your Facebook Page"],
};

/* A4 Connect Meta · A5 Ad account & Page */
export async function viewMeta() {
  setNav("me");
  const [{ profile }, status] = await Promise.all([api("/api/profile"), api("/api/status")]);
  const meta = status.meta;
  const perms = meta.permissions.map((p) => {
    const [ic, title, detail] = PERMISSIONS[p] || ["lock", p, "Requested permission"];
    return `<li>${icon(ic)}<span><b>${esc(title)}</b><small><code>${esc(p)}</code> · ${esc(detail)}</small></span></li>`;
  }).join("");
  const locked = meta.connected ? "Not available in this build" : "Available after connecting";
  app.innerHTML = `<div class="lv-onb">
      <div class="lv-onb-top"><a class="lv-back" href="${profile ? "#/me" : "#/me/profile"}" aria-label="Back"></a>${progress(2, 3)}</div>
      <h1>Connect your Meta<br>ad account</h1>
      <p class="sub">AdLoom creates campaigns, ad sets and ads for you — always paused. You turn them on yourself in Ads Manager.</p>
      <div class="lv-onb-grid">
        <div class="stack">
          <div class="card"><div class="lv-status"><h2>Connection</h2><span class="badge ${meta.connected ? "b-done" : "b-danger"}">${meta.connected ? "Connected" : "Not connected"}</span></div>
            <p class="sub">${esc(meta.detail)}</p></div>
          <div class="card"><h2>What AdLoom will ask Meta for</h2><ul class="lv-bullets">${perms}</ul></div>
          <div class="note mint">AdLoom never turns ads on and never changes ads that are already live.</div>
        </div>
        <div class="stack">
          <div class="card"><h2>Once access is approved</h2>
            <ol class="lv-ol"><li>You sign in with the Facebook account that manages your Page and grant the permissions above.</li>
              <li>You pick a KRW ad account and the Page ads run as.</li>
              <li>Approved jobs publish as one paused campaign with 2 paused ads (Hook A and B).</li></ol></div>
          <div class="card lv-locked"><h2>Where should ads go?</h2>
            <dl class="kv"><dt>Ad account</dt><dd><span class="badge b-paused">${locked}</span></dd><dt>Facebook Page</dt><dd><span class="badge b-paused">${locked}</span></dd></dl>
            <h2 class="lv-h2-gap">Defaults for new ads</h2>
            <dl class="kv"><dt>Daily budget</dt><dd>${profile ? `${won(profile.daily_budget_krw)} · per ad set` : `<a href="#/me/profile">Set in business profile</a>`}</dd>
              <dt>Objective</dt><dd>Traffic${profile?.destination_url ? ` · ${esc(profile.destination_url)}` : ""}</dd>
              <dt>Status</dt><dd class="lv-red">Always created paused</dd></dl></div>
        </div>
      </div>
      <div class="lv-actions">
        ${meta.connected ? "" : `<button class="btn coral" type="button" disabled aria-describedby="metaWhy">Continue with Meta</button>`}
        <a class="btn light" href="#/">${meta.connected ? "Done" : "Skip for now · keep fixture mode"}</a>
      </div>
      ${meta.connected ? "" : `<p class="hint" id="metaWhy">Connecting is turned off until Meta approves the app's permissions. Until then publishing creates fixture IDs only.</p>`}
    </div>`;
}
