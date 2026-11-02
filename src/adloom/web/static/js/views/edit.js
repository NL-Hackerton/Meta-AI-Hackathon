import { app, esc, api, toast, errorText, setNav, head, stepList } from "../core.js";
import { activeStep, poll, onRoute, clock } from "../flow.js";
import { sourcePanel, mountSource, spanText } from "../tracking.js";

const COPY = [
  ["hook_a", "Hook A · first 3 s", 22, "hook:a"],
  ["hook_b", "Hook B · first 3 s", 22, "hook:b"],
  ["headline", "Headline", 40, "headline"],
  ["primary_text", "Primary text", 125, "primary_text"],
];

/* D1 Edit copy · D2 Pick the product · D3 Choose scenes · web Edit revision */
export async function viewEdit(jobId) {
  setNav("jobs");
  const hash = location.hash;
  const d = await api(`/api/jobs/${jobId}`);
  const u = d.snapshot?.understanding, job = d.job;
  if (!u || !["AWAITING_APPROVAL", "APPROVED"].includes(job.state)) { location.hash = `#/jobs/${jobId}`; return; }
  const hooks = d.snapshot.render_plan ? d.snapshot.render_plan.hooks : u.hook_candidates;
  const original = {
    hook_a: hooks[0].text, hook_b: hooks[1].text, headline: u.headline, primary_text: u.primary_text,
    product: d.tracking?.prompt || u.sam_prompt,
    moments: (d.moments || []).filter((m) => m.selected).map((m) => m.index),
  };
  const flags = d.policy_flags || [];
  const duration = d.snapshot.media.duration_us;
  const moments = (d.moments || []).map((m) => ({ ...m }));

  const field = ([name, label, max, flagKey], area = name === "primary_text") => {
    const value = original[name];
    const flag = flags.find((f) => f.field === flagKey);
    return `<label class="field">${label}
        ${area ? `<textarea class="input" name="${name}" maxlength="${max}" required>${esc(value)}</textarea>` : `<input class="input" name="${name}" maxlength="${max}" required value="${esc(value)}">`}
        <span class="counter" data-for="${name}">${value.length} / ${max}</span></label>
      ${flag ? `<div class="cv-inflag" data-flag-for="${name}"><b>“${esc(flag.original)}” is flagged · rule ${esc(flag.rule_id)}</b><span>Suggestion: “${esc(flag.rewrite)}”</span>
        <button type="button" class="btn light small" data-apply="${name}" data-text="${esc(flag.rewrite)}">Apply suggestion</button></div>` : ""}`;
  };

  app.innerHTML = head(`<a href="#/jobs">Jobs</a> / <a href="#/jobs/${esc(jobId)}">${esc(u.product_name)}</a> / revision ${job.revision}`, "Edit before approving",
      "Changes create a new revision. Only affected steps re-run, and the previous approval is cleared.",
      `<button class="btn" form="edit" id="save" disabled>No changes yet</button>`) +
    `<form class="grid2" id="edit" novalidate><div class="stack">
       ${sourcePanel(d, { title: "Scenes and product", stats: false, moments })}
       <div class="card stack" id="scenes"><div class="cv-title"><h2 style="margin:0">Choose scenes</h2><span class="hint" data-total></span></div>
         <p class="hint" style="margin:0">The ad uses these parts of your clip in order, plus a 2-second end card. Keep at least one.</p>
         <div class="cv-scenes">${moments.map((m) => `<button type="button" class="cv-scene" data-moment="${m.index}" aria-pressed="${m.selected}">
             <b>Scene ${m.index + 1} · ${clock(m.start_us)}–${clock(m.end_us)}</b><small>${esc(m.reason)}</small></button>`).join("") || `<p class="hint">No key scenes were found for this video.</p>`}</div>
         <span class="hint cv-bad" data-scene-hint hidden>Keep at least one scene.</span>
       </div>
       <div class="card stack" id="product"><h2 style="margin:0">What to follow</h2>
         <label class="field">Product SAM 3.1 tracks in every frame
           <input class="input" name="product" maxlength="80" required value="${esc(original.product)}">
           <span class="counter" data-for="product">${original.product.length} / 80</span></label>
         <p class="hint" style="margin:0">${d.tracking ? `Found in ${Math.round(d.tracking.coverage * 100)}% of frames now. ` : ""}Name the object plainly, e.g. “gold square” or “faucet”. Changing it re-runs tracking.</p>
       </div>
     </div><div class="stack">
       <div class="card stack"><div class="cv-title"><h2 style="margin:0">Copy</h2><button type="button" class="cv-link" id="reset">Reset</button></div>
         ${COPY.map((c) => field(c)).join("")}
       </div>
       <div class="card cv-impact" id="impact"></div>
       <a class="btn light wide" href="#/jobs/${esc(jobId)}">Cancel</a>
     </div></form>`;

  const form = document.getElementById("edit"), save = document.getElementById("save");
  const source = mountSource(app, d);
  const selected = () => moments.filter((m) => m.selected).map((m) => m.index);

  const changes = () => {
    const body = {};
    for (const [name] of COPY) if (form[name].value.trim() !== original[name]) body[name] = form[name].value.trim();
    if (form.product.value.trim() !== original.product) body.product = form.product.value.trim();
    const now = selected();
    if (now.join() !== original.moments.join()) body.moments = now;
    return body;
  };
  const row = (label, changed, yes, no) => `<dt>${label}</dt><dd class="${changed ? "cv-hot" : ""}">${changed ? yes : no}</dd>`;
  const update = () => {
    const c = changes(), any = Object.keys(c).length > 0;
    const hooksChanged = "hook_a" in c || "hook_b" in c, copyChanged = "headline" in c || "primary_text" in c;
    const usedUs = moments.filter((m) => m.selected).reduce((s, m) => s + m.end_us - m.start_us, 0);
    document.querySelector("[data-total]").textContent = `${clock(usedUs)} of ${clock(duration)} + 2 s end card`;
    const from = "product" in c ? "Tracking" : any ? "Assembly" : "—";
    document.getElementById("impact").innerHTML = `<h2>What will re-run</h2><dl class="kv">
        ${row("Hook text", hooksChanged, "Rules re-checked · 6 videos re-assembled", "No change")}
        ${row("Ad text", copyChanged, "Rules re-checked · 6 videos re-assembled", "No change")}
        ${row("Scenes", "moments" in c, `Uses ${esc(spanText(moments))} · 6 videos re-assembled`, "No change")}
        ${row("Product", "product" in c, "Tracking, images & captions and 6 videos re-run", "Crops reuse saved tracks")}
        ${row("Starts from", any, from, "Nothing to re-run")}
        <dt>Approval</dt><dd style="color:var(--coral-deep)">${any ? "Cleared · approve again" : job.state === "APPROVED" ? "Kept until you save" : "Not approved yet"}</dd></dl>`;
    save.disabled = !any;
    save.textContent = any ? `Save as revision ${job.revision + 1}` : "No changes yet";
    form.querySelectorAll("[data-flag-for]").forEach((el) => {
      const flag = flags.find((f) => COPY.find((x) => x[0] === el.dataset.flagFor)[3] === f.field);
      el.hidden = !flag || form[el.dataset.flagFor].value.trim() !== flag.original;
    });
  };

  form.querySelectorAll("input,textarea").forEach((el) => el.addEventListener("input", () => {
    const counter = form.querySelector(`[data-for="${el.name}"]`);
    if (counter) counter.textContent = `${el.value.length} / ${el.maxLength}`;
    update();
  }));
  form.querySelectorAll("[data-apply]").forEach((b) => b.onclick = () => {
    const el = form[b.dataset.apply];
    el.value = b.dataset.text;
    el.dispatchEvent(new Event("input"));
  });
  form.querySelectorAll("[data-moment]").forEach((chip) => chip.onclick = () => {
    const m = moments.find((x) => x.index === Number(chip.dataset.moment));
    const hint = form.querySelector("[data-scene-hint]");
    if (m.selected && selected().length === 1) { hint.hidden = false; return; }
    hint.hidden = true;
    m.selected = !m.selected;
    chip.setAttribute("aria-pressed", String(m.selected));
    source.setMoments(moments);
    if (m.selected) source.seek(m.start_us);
    update();
  });
  document.getElementById("reset").onclick = () => {
    for (const [name] of COPY) { form[name].value = original[name]; form[name].dispatchEvent(new Event("input")); }
    form.product.value = original.product; form.product.dispatchEvent(new Event("input"));
    moments.forEach((m) => { m.selected = original.moments.includes(m.index); });
    form.querySelectorAll("[data-moment]").forEach((chip) => chip.setAttribute("aria-pressed", String(original.moments.includes(Number(chip.dataset.moment)))));
    source.setMoments(moments);
    update();
  };
  update();
  if (sessionStorage.getItem("adloom.focus") === "product") {
    sessionStorage.removeItem("adloom.focus");
    document.getElementById("product").scrollIntoView();
    form.product.focus();
  }

  form.onsubmit = async (event) => {
    event.preventDefault();
    const body = changes();
    if (!Object.keys(body).length) return;
    if (!form.reportValidity()) return;
    save.disabled = true;
    save.innerHTML = `<span class="spinner"></span> Saving revision ${job.revision + 1}`;
    form.querySelectorAll("input,textarea,button").forEach((el) => el.disabled = true);
    const impact = document.getElementById("impact");
    const show = (h) => { impact.innerHTML = `<div class="cv-title"><h2>Re-running</h2><span class="badge b-progress">revision ${job.revision + 1}</span></div>${stepList(activeStep(h))}`; };
    show({ ...job, state: "product" in body ? "UNDERSTOOD" : "ENRICHED", run_state: "IDLE" });
    const stop = poll(async () => show((await api(`/api/jobs/${jobId}`)).job), 800, onRoute(hash));
    try {
      await api(`/api/jobs/${jobId}/edit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      stop();
      toast(`Saved revision ${job.revision + 1}`);
      if (onRoute(hash)()) location.hash = `#/jobs/${jobId}`;
    } catch (err) {
      stop();
      toast(errorText(err), true);
      if (onRoute(hash)()) location.hash = `#/jobs/${jobId}`;
    }
  };
}
