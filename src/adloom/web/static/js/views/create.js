import { app, esc, won, short, when, MAKING, STATE, stateBadge, PHASE, RESOURCE, resourceName, api, toast, errorText, setNav, head, resume, STEPS, stepList } from "../core.js";

export function viewNew() {
  setNav("new");
  app.innerHTML = head(`<a href="#/jobs">Jobs</a> / New`, "New job", "Drop one 3–45 second video. We recut it into 9:16, 4:5 and 1:1 with two hooks each.") +
  `<form class="grid2" id="form" novalidate>
    <div class="stack">
      <div class="card"><h2>Video</h2>
        <label class="drop" id="drop" tabindex="0">
          <span class="uplogo" aria-hidden="true"></span>
          <strong id="dropTitle">Drag a video here</strong>
          <span class="hint" id="dropHint">MP4 or MOV · 3–45 s · up to 256 MB</span>
          <span class="btn light small">Choose file</span>
          <input type="file" id="video" name="video" accept="video/mp4,video/quicktime,.mp4,.mov" hidden>
        </label>
      </div>
      <div class="card stack"><h2 style="margin:0">About this ad</h2>
        <label class="field">One-line description
          <textarea class="input" name="note" id="note" maxlength="200" required placeholder="What you sell, where, and what makes it worth a call"></textarea>
          <span class="counter" id="noteCount">0 / 200</span>
        </label>
        <div class="row3">
          <label class="field">Area<input class="input" name="region" required placeholder="Namyangju"></label>
          <label class="field">Daily budget (KRW)<input class="input mono" name="budget" type="number" min="1000" step="1000" value="10000" required></label>
          <label class="field">Landing URL<input class="input" name="destination" type="url" placeholder="https://"></label>
        </div>
      </div>
    </div>
    <div class="stack">
      <div class="card" id="progress"><h2>What happens next</h2>${stepList(-1)}</div>
      <div class="note mint">Fixture mode: the video stays on this machine and no model is called. With live mode, it goes to the Meta Model API in Standard mode only.</div>
      <button class="btn coral wide" id="submit" type="submit">Make 6 ads</button>
      <div id="formError"></div>
    </div>
  </form>`;
  const input = document.getElementById("video"), drop = document.getElementById("drop");
  const note = document.getElementById("note");
  note.oninput = () => { document.getElementById("noteCount").textContent = `${note.value.length} / 200`; };
  const pick = (file) => {
    if (!file) return;
    const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;
    document.getElementById("dropTitle").textContent = file.name;
    document.getElementById("dropHint").textContent = `${(file.size / 1048576).toFixed(1)} MB · ready`;
  };
  input.onchange = () => pick(input.files[0]);
  drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
  document.getElementById("form").onsubmit = submitJob;
}
export async function submitJob(event) {
  event.preventDefault();
  const form = event.target, errorBox = document.getElementById("formError");
  errorBox.innerHTML = "";
  if (!form.video.files.length) { errorBox.innerHTML = `<div class="note pink">Choose a video first.</div>`; return; }
  if (!form.reportValidity()) return;
  const button = document.getElementById("submit");
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Making 6 ads`;
  const data = new FormData(form);
  if (!data.get("destination")) data.delete("destination");
  const started = Date.now();
  const progress = document.getElementById("progress");
  progress.innerHTML = `<h2>Making your ads</h2>${stepList(0)}`;
  const timer = setInterval(async () => {
    try {
      const jobs = await api("/api/jobs");
      const job = jobs.find((j) => Date.parse(j.created_at) >= started - 2000);
      if (job && MAKING.includes(job.state)) progress.innerHTML = `<h2>Making your ads</h2>${stepList(Math.min(MAKING.indexOf(job.state), 3))}`;
    } catch (_) { /* polling is best effort */ }
  }, 1000);
  try {
    const job = await api("/api/jobs", { method: "POST", body: data });
    clearInterval(timer);
    toast("Six videos are ready to review");
    location.hash = `#/jobs/${job.job_id}`;
  } catch (err) {
    clearInterval(timer);
    const jobs = await api("/api/jobs").catch(() => []);
    const failed = jobs.find((j) => Date.parse(j.created_at) >= started - 2000);
    const at = failed && failed.failed_stage ? ["understand", "track", "enrich", "assemble"].indexOf(failed.failed_stage) : 0;
    progress.innerHTML = `<h2>Making stopped</h2>${stepList(Math.max(at, 0), true)}`;
    errorBox.innerHTML = `<div class="note pink">${esc(errorText(err))}<p>${failed ? `Finished steps are saved. <a href="#/jobs/${failed.job_id}">Open the job</a> to resume from the failed step.` : "Nothing was saved. Fix the input and try again."}</p></div>`;
    button.disabled = false;
    button.textContent = "Make 6 ads";
  }
}
