"use strict";
// Voice description: record with MediaRecorder or attach an audio file, then preview.
import { esc } from "./core.js";

const MAX_SECONDS = 60;
const MAX_BYTES = 32 * 1024 * 1024;
const AUDIO_EXT = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3" };
const ACCEPT = ".webm,.ogg,.m4a,.mp4,.wav,.mp3,audio/webm,audio/ogg,audio/mp4,audio/x-m4a,audio/wav,audio/mpeg";
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

export function voiceHtml() {
  return `<div class="cv-voice">
      <canvas class="cv-wave" aria-hidden="true"></canvas>
      <b class="cv-timer mono" data-timer>0:00</b>
      <button type="button" class="cv-rec" data-rec aria-label="Start recording"><i></i></button>
      <span class="hint" data-rec-hint>Tap to record · up to ${MAX_SECONDS} seconds</span>
      <div class="cv-take" data-take hidden></div>
      <label class="btn light small cv-attach">Attach an audio file<input type="file" data-audio-file accept="${ACCEPT}" hidden></label>
      <p class="hint cv-voice-note">Speech becomes text you check before anything is written. Nothing you said is used until you confirm it.</p>
    </div>`;
}

/** Wires voiceHtml inside `root`. `onChange(file|null)` fires whenever the take changes. */
export function mountVoice(root, onChange) {
  const button = root.querySelector("[data-rec]"), hint = root.querySelector("[data-rec-hint]");
  const timer = root.querySelector("[data-timer]"), take = root.querySelector("[data-take]");
  const wave = root.querySelector(".cv-wave"), input = root.querySelector("[data-audio-file]");
  const supported = !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
  let recorder = null, stream = null, chunks = [], started = 0, tick = 0, audioCtx = null, previewUrl = "";

  const setHint = (text, error = false) => { hint.textContent = text; hint.classList.toggle("cv-bad", error); };
  if (!supported) {
    button.disabled = true;
    setHint("Recording isn't available in this browser. Attach an audio file instead.", true);
  }

  const showTake = (file, source) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!file) { take.hidden = true; take.innerHTML = ""; previewUrl = ""; onChange(null); return; }
    previewUrl = URL.createObjectURL(file);
    take.hidden = false;
    take.innerHTML = `<audio controls src="${previewUrl}" aria-label="Your recording"></audio>
      <span class="hint">${esc(source)} · ${(file.size / 1024).toFixed(0)} KB</span>
      <button type="button" class="btn light small" data-remove>Remove</button>`;
    take.querySelector("[data-remove]").onclick = () => { showTake(null); timer.textContent = "0:00"; setHint(supported ? `Tap to record · up to ${MAX_SECONDS} seconds` : "Attach an audio file instead.", !supported); };
    onChange(file);
  };

  const drawWave = (analyser) => {
    const g = wave.getContext("2d"), data = new Uint8Array(analyser.frequencyBinCount);
    const frame = () => {
      if (!recorder || recorder.state !== "recording") { g.clearRect(0, 0, wave.width, wave.height); return; }
      wave.width = wave.clientWidth * devicePixelRatio; wave.height = wave.clientHeight * devicePixelRatio;
      analyser.getByteFrequencyData(data);
      const bars = 28, gap = wave.width / bars;
      const grad = g.createLinearGradient(0, 0, wave.width, 0);
      grad.addColorStop(0, "#FF6A3D"); grad.addColorStop(.5, "#FF4F7B"); grad.addColorStop(1, "#7B61FF");
      g.clearRect(0, 0, wave.width, wave.height);
      g.fillStyle = grad;
      for (let i = 0; i < bars; i++) {
        const v = data[Math.floor((i / bars) * data.length * .6)] / 255;
        const h = Math.max(4 * devicePixelRatio, v * wave.height);
        g.fillRect(i * gap + gap * .3, (wave.height - h) / 2, gap * .4, h);
      }
      if (!reduceMotion()) requestAnimationFrame(frame);
    };
    frame();
  };

  const stop = () => { if (recorder && recorder.state === "recording") recorder.stop(); };
  const start = async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
      setHint(denied ? "Microphone access was blocked. Allow it in your browser, or attach an audio file." : "No microphone was found. Attach an audio file instead.", true);
      return;
    }
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      clearInterval(tick);
      stream.getTracks().forEach((track) => track.stop());
      audioCtx?.close();
      button.classList.remove("on");
      button.setAttribute("aria-label", "Start recording");
      const type = (recorder.mimeType || "audio/webm").split(";")[0];
      const blob = new Blob(chunks, { type });
      if (!blob.size) { setHint("Nothing was recorded. Try again.", true); return; }
      setHint("Recorded. Play it back, or record again.");
      showTake(new File([blob], `voice-note.${AUDIO_EXT[type] || "webm"}`, { type }), "Recording");
    };
    recorder.start(250);
    started = Date.now();
    button.classList.add("on");
    button.setAttribute("aria-label", "Stop recording");
    setHint("Recording… tap to stop");
    showTake(null);
    tick = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      timer.textContent = `0:${String(Math.min(s, MAX_SECONDS)).padStart(2, "0")}`;
      if (s >= MAX_SECONDS) stop();
    }, 250);
    try {
      audioCtx = new AudioContext();
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128;
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      drawWave(analyser);
    } catch (_) { /* waveform is decorative */ }
  };
  button.onclick = () => (recorder && recorder.state === "recording" ? stop() : start());

  input.onchange = () => {
    const file = input.files[0];
    input.value = "";
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["webm", "ogg", "m4a", "mp4", "wav", "mp3"].includes(ext)) { setHint("Use a WebM, OGG, M4A, MP4, WAV or MP3 audio file.", true); return; }
    if (file.size > MAX_BYTES) { setHint("Audio files can be up to 32 MB.", true); return; }
    setHint("Attached. Play it back to check.");
    showTake(file, file.name);
  };
  return { stop };
}
