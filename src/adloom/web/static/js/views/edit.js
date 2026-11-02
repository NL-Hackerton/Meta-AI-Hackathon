import { app, esc, won, short, when, MAKING, STATE, stateBadge, PHASE, RESOURCE, resourceName, api, toast, errorText, setNav, head, resume, STEPS, stepList } from "../core.js";

/* Edit */
export async function viewEdit(jobId) {
  setNav("jobs");
  const d = await api(`/api/jobs/${jobId}`);
  const u = d.snapshot.understanding, job = d.job;
  if (!u || !["AWAITING_APPROVAL", "APPROVED"].includes(job.state)) { location.hash = `#/jobs/${jobId}`; return; }
  const hooks = d.snapshot.render_plan ? d.snapshot.render_plan.hooks : u.hook_candidates;
  const field = (name, label, value, max, area = false) => `<label class="field">${label}
      ${area ? `<textarea class="input" name="${name}" maxlength="${max}" required>${esc(value)}</textarea>` : `<input class="input" name="${name}" maxlength="${max}" required value="${esc(value)}">`}
      <span class="counter" data-for="${name}">${value.length} / ${max}</span></label>`;
  app.innerHTML = head(`<a href="#/jobs">Jobs</a> / <a href="#/jobs/${jobId}">${esc(u.product_name)}</a> / revision ${job.revision}`, "Edit before approving",
      "Changes create a new revision. Only the affected steps re-run, and the previous approval is cleared.") +
    `<form class="grid2" id="edit"><div class="card stack"><h2 style="margin:0">Copy</h2>
       ${field("hook_a", "Hook A · first 3 s", hooks[0].text, 22)}
       ${field("hook_b", "Hook B · first 3 s", hooks[1].text, 22)}
       ${field("headline", "Headline", u.headline, 40)}
       ${field("primary_text", "Primary text", u.primary_text, 125, true)}
     </div><div class="stack">
       <div class="card"><h2>What will re-run</h2><dl class="kv">
         <dt>Policy</dt><dd>Rules checked again</dd><dt>Videos</dt><dd>All 6 re-assembled</dd><dt>Tracking</dt><dd>Reused, not re-run</dd>
         <dt>Approval</dt><dd style="color:var(--coral-deep)">Cleared · approve again</dd></dl></div>
       <button class="btn wide" id="save">Save as revision ${job.revision + 1}</button>
       <a class="btn light wide" href="#/jobs/${jobId}">Cancel</a>
     </div></form>`;
  const form = document.getElementById("edit");
  form.querySelectorAll("input,textarea").forEach((el) => el.oninput = () => {
    const c = form.querySelector(`[data-for="${el.name}"]`); c.textContent = `${el.value.length} / ${el.maxLength}`;
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const button = document.getElementById("save");
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Re-assembling 6 videos`;
    const body = Object.fromEntries(["hook_a", "hook_b", "headline", "primary_text"].map((k) => [k, form[k].value.trim()]));
    try { await api(`/api/jobs/${jobId}/edit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); toast("Saved a new revision"); location.hash = `#/jobs/${jobId}`; }
    catch (err) { toast(errorText(err), true); button.disabled = false; button.textContent = `Save as revision ${job.revision + 1}`; }
  };
}
