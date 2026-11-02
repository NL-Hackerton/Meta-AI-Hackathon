"use strict";
import { api, app, esc, errorText, beginNav, endNav, currentNav, setNav } from "./core.js";
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

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const bar = document.getElementById("routebar");

async function route() {
  const id = beginNav();
  const parts = (location.hash.replace(/^#/, "") || "/").split("/").filter(Boolean);
  const found = match(parts);
  // Keep the old screen visible but inert while the next one loads, so nothing from it can
  // be clicked or read as the new screen. Only dim it when loading is slow enough to notice.
  app.setAttribute("aria-busy", "true");
  app.inert = true;
  bar.classList.add("on");
  const dim = setTimeout(() => app.classList.add("leaving"), 140);
  try {
    if (!found) throw new Error("This page does not exist");
    const view = await import(`./views/${found.module}.js`);
    if (id !== currentNav()) return;
    await view[found.fn](...found.params);
  } catch (err) {
    if (id !== currentNav()) return;
    setNav("");
    app.innerHTML = `<div class="card empty"><h1>Could not load this page</h1><span class="hint">${esc(errorText(err))}</span><a class="btn light" href="#/">Back to home</a></div>`;
  } finally {
    clearTimeout(dim);
  }
  if (id !== currentNav()) return;
  app.classList.remove("leaving");
  app.removeAttribute("aria-busy");
  app.inert = false;
  bar.classList.remove("on");
  window.scrollTo(0, 0);
  if (!reduceMotion.matches) {
    app.classList.remove("entering");
    void app.offsetWidth; // restart the enter animation
    app.classList.add("entering");
  }
  // Move focus into the new screen so keyboard and screen-reader users start at its title;
  // inert dropped any focus the old screen had. Views may override via afterRender.
  const heading = app.querySelector("h1");
  if (heading && !app.contains(document.activeElement)) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
  endNav();
  refreshBell();
}

app.addEventListener("animationend", () => app.classList.remove("entering"));
window.addEventListener("hashchange", route);
api("/api/status", { global: true })
  .then((s) => { document.getElementById("mode").textContent = s.live ? "live mode" : "fixture mode · no live calls"; })
  .catch(() => {});
route();
