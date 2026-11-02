import { app, esc, won, api, setNav, head } from "../core.js";

/* Settings */
export async function viewSettings() {
  setNav("me");
  const [s, { profile }] = await Promise.all([api("/api/status"), api("/api/profile")]);
  const item = (title, detail, badge, cls) => `<div class="lv-setting"><div><b>${title}</b><div class="hint">${detail}</div></div><span class="badge ${cls}">${badge}</span></div>`;
  const keyBadge = s.model_api.key_present ? ["Key present", "b-done"] : ["Not set", "b-warn"];
  const metaBadge = s.meta.connected ? ["Connected", "b-done"] : ["Not connected", "b-danger"];
  app.innerHTML = head(profile ? esc(profile.business_name) : "This machine", "Settings", "Accounts, spending and data. Live calls stay off until each item below is ready.") +
    `<div class="lv-settings">
      <div class="stack">
        <div class="card"><h2>Meta Model API</h2>
          ${item("API key", `Read from MODEL_API_KEY on the server · never shown here${s.live ? "" : " · not used in fixture mode"}`, ...keyBadge)}
          ${item("Mode", `Standard only · ${esc(s.spark_model)} · contributor models are refused`, "Standard", "b-done")}
          ${item("Spending limit", "Required before any live call", "Not set", "b-danger")}
          ${item("Uploaded files", "Live mode only: deleted after each job finishes", s.live ? "Auto-delete" : "Not uploaded", s.live ? "b-done" : "b-paused")}
        </div>
        <div class="card"><h2>Defaults for new jobs</h2>
          ${profile
            ? `${item("Daily budget", "Per ad set · edit in your business profile", esc(won(profile.daily_budget_krw)), "b-done")}
               ${item("Area", esc(profile.region), esc(profile.language === "ko" ? "Korean copy" : "English copy"), "b-done")}
               ${item("Link", esc(profile.destination_url || "No booking link · ads use the page you enter per job"), profile.destination_url ? "Set" : "Not set", profile.destination_url ? "b-done" : "b-warn")}`
            : item("Business profile", "Needed for job defaults and the end card", "Not set", "b-warn")}
          <a class="btn light small lv-gap-top" href="#/me/profile">${profile ? "Edit business profile" : "Set up business profile"}</a>
        </div>
      </div>
      <div class="stack">
        <div class="card"><h2>Meta ad account</h2>
          ${item("Connection", esc(s.meta.detail), ...metaBadge)}
          ${s.meta.permissions.map((p) => item(esc(p), p === "ads_management" ? "Create paused campaigns, ad sets and ads · needs a KRW ad account" : p === "pages_read_engagement" ? "Run ads as your Facebook Page" : "Requested permission", s.meta.connected ? "Granted" : "Not granted", s.meta.connected ? "b-done" : "b-danger")).join("")}
          ${item("Objective & button", "Traffic · Learn more", "Default", "b-done")}
          <a class="btn light small lv-gap-top" href="#/me/meta">Connection details</a>
        </div>
        <div class="card lv-mint"><h2>Always on</h2>
          ${item("Paused only", "Campaigns, ad sets and ads are created paused", "Locked", "b-done")}
          ${item("Approval required", "Publishing checks the approved fingerprint", "Locked", "b-done")}
          ${item("No generated video", "Frames come only from your footage and images", "Locked", "b-done")}
        </div>
      </div></div>`;
}
