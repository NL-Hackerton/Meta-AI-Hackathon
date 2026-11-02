import { app, esc, api, toast, errorText, setNav, head, stepList, onLeave } from "../core.js";
import { activeStep, failureCard, wireResume, needsNote, poll, onRoute } from "../flow.js";
import { refreshBell } from "../notify.js";
import { voiceHtml, mountVoice } from "../recorder.js";

const MIN_S = 3, MAX_S = 45, MAX_MB = 256;
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

/** Reads duration and size from the file's own metadata before anything is uploaded. */
function probe(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file), v = document.createElement("video");
    const done = (info) => { clearTimeout(timer); resolve(info ? { ...info, url } : { url }); };
    const timer = setTimeout(() => done(null), 8000);
    v.preload = "metadata"; v.muted = true;
    v.onerror = () => done(null);
    v.onloadedmetadata = () => done({ duration: Number.isFinite(v.duration) ? v.duration : undefined, width: v.videoWidth, height: v.videoHeight });
    v.src = url;
  });
}

export async function viewNew() {
  setNav("new");
  const profile = await api("/api/profile").then((r) => r.profile).catch(() => null);
  app.innerHTML = head(`<a href="#/jobs">Jobs</a> / New`, "New job", "Drop one 3–45 second video. We recut it into 9:16, 4:5 and 1:1 with two hooks each.") +
  `<form class="grid2" id="form" novalidate>
    <div class="stack">
      <div class="card"><h2>Video</h2><div id="videoBox"></div>
        <input type="file" id="video" accept="video/mp4,video/quicktime,.mp4,.mov" hidden></div>
      <div class="card stack"><h2 style="margin:0">About this ad</h2>
        <div class="field" role="group" aria-labelledby="descLabel"><span id="descLabel">One-line description</span>
          <div class="cv-seg"><button type="button" class="chip" data-mode="text" aria-pressed="true">Type it</button><button type="button" class="chip" data-mode="voice" aria-pressed="false">Say it</button></div>
        </div>
        <label class="field" id="textBox"><span class="cv-sr">One-line description</span>
          <textarea class="input" name="note" id="note" maxlength="200" placeholder="What you sell, where, and what makes it worth a call"></textarea>
          <span class="counter" id="noteCount">0 / 200</span></label>
        <div id="voiceBox" hidden>${voiceHtml()}</div>
        <div class="row3">
          <label class="field">Area<input class="input" name="region" required maxlength="60" value="${esc(profile?.region || "")}" placeholder="Namyangju"></label>
          <label class="field">Daily budget (KRW)<input class="input mono" name="budget" type="number" min="1000" step="1" inputmode="numeric" value="${esc(profile?.daily_budget_krw ?? 10000)}" required></label>
          <label class="field">Landing URL<input class="input" name="destination" type="url" pattern="https://.*" value="${esc(profile?.destination_url || "")}" placeholder="https://"></label>
        </div>
        ${profile ? `<p class="hint" style="margin:0">Filled from your business profile · <a href="#/me/profile">${esc(profile.business_name)}</a>. Changes here apply to this job only.</p>` : `<p class="hint" style="margin:0">Save a <a href="#/me/profile">business profile</a> to fill these in next time.</p>`}
      </div>
    </div>
    <div class="stack">
      <div class="card" id="progress"><h2>What happens next</h2>${stepList(-1)}</div>
      <div class="note mint">Fixture mode: the video stays on this machine and no model is called. With live mode, it goes to the Meta Model API in Standard mode only.</div>
      <button class="btn coral wide" id="submit" type="submit">Make 6 ads</button>
      <div id="formError" role="alert"></div>
    </div>
  </form>`;

  const form = document.getElementById("form"), input = document.getElementById("video");
  const state = { file: null, info: null, ok: false, mode: "text", audio: null, language: profile?.language || "ko", submitting: false };
  const note = document.getElementById("note");
  note.oninput = () => {
    const c = document.getElementById("noteCount");
    c.textContent = `${note.value.length} / 200`;
  };
  form.querySelectorAll("[data-mode]").forEach((b) => b.onclick = () => {
    state.mode = b.dataset.mode;
    form.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    document.getElementById("textBox").hidden = state.mode !== "text";
    document.getElementById("voiceBox").hidden = state.mode !== "voice";
  });
  mountVoice(document.getElementById("voiceBox"), (file) => { state.audio = file; });

  const box = document.getElementById("videoBox");
  const renderDrop = () => {
    box.innerHTML = `<div class="drop" id="drop" tabindex="0" role="button" aria-label="Choose a video">
        <span class="uplogo" aria-hidden="true"></span><strong>Drag a video here</strong>
        <span class="hint">MP4 or MOV · 3–45 s · up to ${MAX_MB} MB</span><span class="btn light small">Choose file</span></div>`;
    const drop = document.getElementById("drop");
    drop.onclick = () => input.click();
    drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  };
  // A file dropped anywhere on the page is picked instead of the browser navigating to it.
  // The video card (empty or with a file chosen) highlights as the drop target.
  let depth = 0;
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  const onEnter = (e) => { if (!hasFiles(e)) return; depth++; box.classList.add("cv-dropping"); };
  const onLeaveDrag = () => { depth = Math.max(0, depth - 1); if (!depth) box.classList.remove("cv-dropping"); };
  const onOver = (e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = state.submitting ? "none" : "copy"; } };
  const onDrop = (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0; box.classList.remove("cv-dropping");
    if (!state.submitting) pick(e.dataTransfer.files[0]);
  };
  window.addEventListener("dragenter", onEnter);
  window.addEventListener("dragleave", onLeaveDrag);
  window.addEventListener("dragover", onOver);
  window.addEventListener("drop", onDrop);
  onLeave(() => {
    window.removeEventListener("dragenter", onEnter);
    window.removeEventListener("dragleave", onLeaveDrag);
    window.removeEventListener("dragover", onOver);
    window.removeEventListener("drop", onDrop);
    if (state.info?.url) URL.revokeObjectURL(state.info.url);
  });
  const renderPicked = () => {
    const { file, info } = state;
    const mb = file.size >= 1048576 ? `${(file.size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;
    const dur = info.duration;
    const tooLong = dur > MAX_S, tooShort = dur < MIN_S, tooBig = file.size > MAX_MB * 1048576;
    const bad = tooLong || tooShort || tooBig;
    const badge = tooLong ? `${mmss(dur)} · over ${MAX_S} s` : tooShort ? `${dur.toFixed(1)} s · under ${MIN_S} s` : tooBig ? `${mb} · over ${MAX_MB} MB` : "";
    const meta = [dur ? mmss(dur) : null, info.width ? `${info.width}×${info.height}` : null, mb].filter(Boolean).join(" · ");
    box.innerHTML = `<div class="cv-picked${bad ? " bad" : ""}">
        <video src="${info.url}#t=0.5" muted playsinline preload="metadata" aria-hidden="true"></video>
        <div>${bad ? `<span class="cv-flag danger">${esc(badge)}</span>` : `<span class="cv-flag ok">Ready to upload</span>`}
          <b>${esc(file.name)}</b><span class="hint">${esc(meta)}${dur ? "" : " · length is checked on upload"}</span>
          ${bad ? "" : `<button type="button" class="cv-link" id="another">Choose another video</button><span class="hint">or drop another file here</span>`}</div></div>
      ${bad ? `<div class="cv-c1">
        <h3>${tooLong ? "This video is too long" : tooShort ? "This video is too short" : "This file is too large"}</h3>
        <p class="hint">${tooBig && !tooLong && !tooShort ? `AdLoom accepts files up to ${MAX_MB} MB. Export a shorter or smaller clip.` : `AdLoom works with clips between ${MIN_S} and ${MAX_S} seconds so every ad stays short and focused. ${tooLong ? "Trim it in your camera app, or record a shorter clip of just the product in action." : "Record a few more seconds of the product in action."}`}</p>
        <ul class="cv-tips"><li><b>10–30 seconds</b><span>Start on the product, not the doorway</span></li>
          <li><b>Keep the product in frame</b><span>We follow it into 9:16, 4:5 and 1:1</span></li>
          <li><b>Talk if you like</b><span>Speech becomes captions you can edit</span></li></ul>
        <button type="button" class="btn coral" id="another">Choose another video</button></div>` : ""}`;
    document.getElementById("another").onclick = () => input.click();
    state.ok = !bad;
    document.getElementById("submit").disabled = bad;
  };
  async function pick(file) {
    if (!file || state.submitting) return;
    if (state.info?.url) URL.revokeObjectURL(state.info.url);
    state.file = file;
    state.info = await probe(file);
    document.getElementById("formError").innerHTML = "";
    renderPicked();
  }
  input.onchange = () => { pick(input.files[0]); input.value = ""; };
  renderDrop();
  form.onsubmit = (event) => { event.preventDefault(); submitJob(form, state); };
}

function upload(data, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.setRequestHeader("X-AdLoom-Request", "1");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.upload.onload = () => onProgress(1);
    xhr.onload = () => {
      const body = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300) return resolve(body);
      const error = new Error(body.error?.detail || `Request failed (${xhr.status})`);
      error.code = body.error?.code;
      reject(error);
    };
    xhr.onerror = () => reject(new Error("The connection to AdLoom dropped during upload"));
    xhr.send(data);
  });
}

async function submitJob(form, state) {
  const errorBox = document.getElementById("formError"), button = document.getElementById("submit");
  if (state.submitting) return;
  state.submitting = true;
  button.disabled = true;
  const fail = (msg) => { errorBox.innerHTML = `<div class="note pink">${esc(msg)}</div>`; state.submitting = false; button.disabled = !state.ok; };
  errorBox.innerHTML = "";
  if (!state.file) return fail("Choose a video first.");
  if (!state.ok) return fail(`Choose a video between ${MIN_S} and ${MAX_S} seconds.`);
  const text = form.note.value.trim();
  if (state.mode === "text" && !text) { form.note.focus(); return fail("Write one line about this ad, or switch to Say it."); }
  if (state.mode === "voice" && !state.audio) return fail("Record your description or attach an audio file first.");
  if (!form.region.value.trim()) { form.region.focus(); return fail("Enter the area this ad is for."); }
  if (!form.reportValidity()) { state.submitting = false; button.disabled = false; return; }
  const data = new FormData();
  data.append("video", state.file, state.file.name);
  if (state.mode === "text") data.append("note", text);
  else data.append("note_audio", state.audio, state.audio.name);
  data.append("region", form.region.value.trim());
  data.append("budget", form.budget.value);
  data.append("language", state.language);
  if (form.destination.value.trim()) data.append("destination", form.destination.value.trim());

  const before = new Set((await api("/api/jobs").catch(() => [])).map((j) => j.job_id));
  const progress = document.getElementById("progress");
  const hash = location.hash;
  const making = (job, uploaded) => {
    const step = job ? activeStep(job) : 0;
    const head = uploaded < 1 ? `Uploading ${Math.round(uploaded * 100)}%` : job ? (job.note_status !== "CONFIRMED" ? "Turning your voice into text" : "Making") : "Starting";
    progress.innerHTML = `<div class="cv-title"><h2>Making your ads</h2><span class="badge b-progress">${esc(head)}</span></div>
      <div class="cv-bar" role="progressbar" aria-label="Upload" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(uploaded * 100)}"><i style="width:${(uploaded * 100).toFixed(1)}%"></i></div>
      ${stepList(step)}<p class="hint">You can keep using AdLoom. The job keeps running and shows up in Jobs.</p>`;
  };
  let uploaded = 0, current = null;
  button.innerHTML = `<span class="spinner"></span> Making 6 ads`;
  form.querySelectorAll("input,textarea,.chip").forEach((el) => el.disabled = true);
  making(null, 0);
  const stop = poll(async () => {
    const jobs = await api("/api/jobs");
    current = jobs.find((j) => !before.has(j.job_id)) || current;
    making(current, uploaded);
  }, 1000, onRoute(hash));
  try {
    const job = await upload(data, (p) => { uploaded = p; making(current, p); });
    stop();
    refreshBell();
    if (!onRoute(hash)()) { toast(needsNote(job) ? "Check the description we heard" : "Six videos are ready to review"); return; }
    if (needsNote(job)) toast(job.state === "FAILED" ? "We couldn't turn the recording into text. Type it instead." : "Check the description we heard");
    else if (job.state === "AWAITING_APPROVAL") toast("Six videos are ready to review");
    location.hash = `#/jobs/${job.job_id}`;
  } catch (err) {
    stop();
    const jobs = await api("/api/jobs", { global: true }).catch(() => []);
    const failed = jobs.find((j) => !before.has(j.job_id));
    if (!onRoute(hash)()) { toast(errorText(err), true); return; }
    state.submitting = false;
    refreshBell();
    form.querySelectorAll("input,textarea,.chip").forEach((el) => el.disabled = false);
    button.textContent = "Make 6 ads";
    if (failed && failed.state === "FAILED") {
      button.disabled = true;
      progress.innerHTML = failureCard(failed, { openLink: true, startOver: false }).replace(/^<div class="card cv-fail">/, `<div class="cv-fail">`) +
        `<p class="hint">Or choose another video on the left to start a new job.</p>`;
      wireResume(progress, (id) => { location.hash = `#/jobs/${id}`; });
    } else {
      button.disabled = false;
      progress.innerHTML = `<h2>What happens next</h2>${stepList(-1)}`;
      errorBox.innerHTML = `<div class="note pink">${esc(errorText(err))}<p>Nothing was saved. Fix the input and try again.</p></div>`;
    }
  }
}
