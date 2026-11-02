import { app, esc, won, short, when, MAKING, STATE, stateBadge, PHASE, RESOURCE, resourceName, api, toast, errorText, setNav, head, resume, STEPS, stepList } from "../core.js";

/* Settings */
export async function viewSettings() {
  setNav("settings");
  const s = await api("/api/status");
  const item = (title, detail, badge, cls) => `<div style="display:flex;gap:12px;align-items:center;padding:12px 0;border-top:1px solid var(--border)"><div style="flex:1"><b>${title}</b><div class="hint">${detail}</div></div><span class="badge ${cls}">${badge}</span></div>`;
  app.innerHTML = head("This machine", "Settings", "Accounts, spending and data. Live calls stay off until each item below is ready.") +
    `<div class="grid2" style="grid-template-columns:1fr 1fr">
      <div class="stack">
        <div class="card"><h2>Meta Model API</h2>
          ${item("API key", "Read from MODEL_API_KEY on the server · never shown here", s.live ? "Connected" : "Not used in fixture mode", s.live ? "b-done" : "b-warn")}
          ${item("Mode", `Standard only · ${esc(s.spark_model)} · contributor models are refused`, "Standard", "b-done")}
          ${item("Spending limit", "Required before any live call", "Not set", "b-danger")}
        </div>
        <div class="card"><h2>Data</h2>
          ${item("Uploaded videos", "Copied into the job folder on this machine; the upload copy is removed right away", "Local", "b-done")}
          ${item("Model API files", "Live mode only: deleted after the job finishes", "Pending approval", "b-warn")}
        </div>
      </div>
      <div class="stack">
        <div class="card"><h2>Meta ad account</h2>
          ${item("Ad account", "Needs KRW currency and ads_management", "Not connected", "b-danger")}
          ${item("Facebook Page", "pages_read_engagement", "Not connected", "b-danger")}
          ${item("Objective & button", "Traffic · Learn more", "Default", "b-done")}
        </div>
        <div class="card" style="background:var(--mint-soft)"><h2>Always on</h2>
          ${item("Paused only", "Campaigns, ad sets and ads are created paused", "Locked", "b-done")}
          ${item("Approval required", "Publishing checks the approved fingerprint", "Locked", "b-done")}
          ${item("No generated video", "Frames come only from your footage and images", "Locked", "b-done")}
        </div>
      </div></div>`;
}
