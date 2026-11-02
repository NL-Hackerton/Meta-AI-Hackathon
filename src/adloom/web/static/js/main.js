"use strict";
import { api, app, esc, errorText } from "./core.js";
import { refreshBell } from "./notify.js";

// Each route: pattern segments (":name" captures), module path, exported view function.
const ROUTES = [
  [[], "home", "viewHome"],
  [["welcome"], "onboarding", "viewWelcome"],
  [["jobs"], "jobs", "viewJobs"],
  [["new"], "create", "viewNew"],
  [["approve"], "approve", "viewApprove"],
  [["ads"], "ads", "viewAds"],
  [["ads", ":job", ":hook"], "ads", "viewAd"],
  [["log"], "log", "viewLog"],
  [["notifications"], "notifications", "viewNotifications"],
  [["me"], "account", "viewAccount"],
  [["me", "profile"], "onboarding", "viewProfile"],
  [["me", "meta"], "onboarding", "viewMeta"],
  [["me", "data"], "account", "viewData"],
  [["settings"], "settings", "viewSettings"],
  [["jobs", ":job"], "review", "viewJob"],
  [["jobs", ":job", "edit"], "edit", "viewEdit"],
  [["jobs", ":job", "log"], "log", "viewLog"],
];

function match(parts) {
  for (const [pattern, module, fn] of ROUTES) {
    if (pattern.length !== parts.length) continue;
    const params = [];
    if (pattern.every((seg, i) => (seg.startsWith(":") ? params.push(parts[i]) : seg === parts[i]))) {
      return { module, fn, params };
    }
  }
  return null;
}

async function route() {
  const parts = (location.hash.replace(/^#/, "") || "/").split("/").filter(Boolean);
  const found = match(parts);
  try {
    if (!found) throw new Error("This page does not exist");
    const view = await import(`./views/${found.module}.js`);
    await view[found.fn](...found.params);
  } catch (err) {
    app.innerHTML = `<div class="card empty"><b>Could not load this page</b><span class="hint">${esc(errorText(err))}</span><a class="btn light" href="#/">Back to home</a></div>`;
  }
  window.scrollTo(0, 0);
  refreshBell();
}

window.addEventListener("hashchange", route);
api("/api/status")
  .then((s) => { document.getElementById("mode").textContent = s.live ? "live mode" : "fixture mode · no live calls"; })
  .catch(() => {});
route();
