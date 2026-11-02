"use strict";
// Source video with the tracked product box and the three crop frames drawn per frame.
import { esc, onLeave } from "./core.js";
import { ASPECTS, clock } from "./flow.js";

export const CROP_COLORS = { "9:16": "#FF4F7B", "4:5": "#3D7BFF", "1:1": "#A994FF" };
const BOX_COLOR = "#FFFFFF";

const durationOf = (d) => d.snapshot?.media?.duration_us || 0;

/** Text summary of the selected source spans, e.g. "0:00–0:06, 0:12–0:14". */
export function spanText(moments) {
  const used = (moments || []).filter((m) => m.selected);
  return used.length ? used.map((m) => `${clock(m.start_us)}–${clock(m.end_us)}`).join(", ") : "no scenes";
}

/** Timeline strip: selected moments over the full source duration, with a playhead. */
export function stripHtml(moments, durationUs) {
  if (!durationUs) return "";
  const spans = (moments || []).map((m) => {
    const left = (m.start_us / durationUs) * 100, width = ((m.end_us - m.start_us) / durationUs) * 100;
    return `<span class="cv-span${m.selected ? " on" : ""}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%" title="Scene ${m.index + 1} · ${clock(m.start_us)}–${clock(m.end_us)}"><b>${m.index + 1}</b></span>`;
  }).join("");
  return `${spans}<i class="cv-playhead" style="left:0%"></i>`;
}

const RATIO = { "9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1 };

/** The plain center crop a naive resize would use for this aspect, in source pixels. */
export function centerCrop(t, aspect) {
  const r = RATIO[aspect], W = t.source_width, H = t.source_height;
  if (W / H > r) { const w = H * r; return [(W - w) / 2, 0, w, H]; }
  const h = W / r;
  return [0, (H - h) / 2, W, h];
}

const inside = ([bx, by, bw, bh], [cx, cy, cw, ch]) => bx >= cx - 0.5 && by >= cy - 0.5 && bx + bw <= cx + cw + 0.5 && by + bh <= cy + ch + 0.5;

/** Share of tracked frames where the whole product box stays inside each crop. */
export function cropComparison(t) {
  if (!t?.boxes) return null;
  const frames = t.boxes.map((box, f) => [box, f]).filter(([box]) => box);
  if (!frames.length) return null;
  return Object.fromEntries(ASPECTS.map((aspect) => {
    const center = centerCrop(t, aspect);
    let tracked = 0, plain = 0;
    for (const [box, f] of frames) {
      const crop = t.crops?.[aspect]?.[f];
      if (crop && inside(box, crop)) tracked++;
      if (inside(box, center)) plain++;
    }
    return [aspect, { tracked: tracked / frames.length, plain: plain / frames.length, frames: frames.length }];
  }));
}

const pct = (v) => `${Math.round(v * 100)}%`;

function compareHtml(t) {
  const cmp = cropComparison(t);
  if (!cmp) return "";
  const rows = ASPECTS.map((a) => {
    const c = cmp[a], lost = c.plain < c.tracked;
    return `<tr><th scope="row"><i style="background:${CROP_COLORS[a]}"></i>${a}</th>
      <td><b>${pct(c.tracked)}</b><span class="cv-meter"><i style="width:${pct(c.tracked)}"></i></span></td>
      <td class="${lost ? "cv-worse" : ""}">${pct(c.plain)}<span class="cv-meter plain"><i style="width:${pct(c.plain)}"></i></span></td></tr>`;
  }).join("");
  const frames = cmp[ASPECTS[0]].frames;
  return `<div class="cv-compare">
      <div class="cv-compare-head"><b>Product kept whole in the frame</b>
        <label class="cv-toggle"><input type="checkbox" data-center> Show plain center crop</label></div>
      <table><thead><tr><th scope="col">Ratio</th><th scope="col">AdLoom crop</th><th scope="col">Plain center crop</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="hint">Share of the ${frames} frames where SAM found the product and its whole box stays inside the crop.</p>
    </div>`;
}
export function sourcePanel(d, { title = "Source and tracked crops", stats = true, moments = d.moments } = {}) {
  const t = d.tracking, duration = durationOf(d);
  if (!d.source_url) return `<div class="card"><h2>${esc(title)}</h2><p class="hint">The source video is not available for this job.</p></div>`;
  const legend = t ? `<div class="cv-legend" aria-hidden="true">${ASPECTS.map((a) => `<span><i style="background:${CROP_COLORS[a]}"></i>${a}${t.degraded?.[a] ? " · center" : ""}</span>`).join("")}<span><i class="box"></i>SAM 3.1 box</span></div>` : "";
  let statLine = "";
  if (stats) {
    const crops = Object.fromEntries((d.snapshot?.crops || []).map((c) => [c.aspect, c]));
    const fallback = t ? ASPECTS.filter((a) => t.degraded?.[a]) : [];
    statLine = `<div class="cv-stats">
        ${(moments || []).length ? `<span>Uses ${esc(spanText(moments))} of ${clock(duration)}</span>` : `<span>Length ${clock(duration)}</span>`}
        ${t ? `<span>Coverage <b>${Math.round(t.coverage * 100)}%</b></span>
        <span>Following “${esc(t.prompt)}”</span>
        <span>Clipped frames ${ASPECTS.map((a) => crops[a]?.clipped_frames?.length ?? 0).join(" / ")}</span>
        <span>Center-crop fallback: <b class="${fallback.length ? "warn" : ""}">${fallback.length ? esc(fallback.join(", ")) : "off"}</b></span>` : `<span>Tracking has not run yet, so no crop frames to show.</span>`}
      </div>${compareHtml(t)}`;
  }
  return `<div class="card cv-source">
      <div class="cv-title"><h2>${esc(title)}</h2><span class="hint mono" data-frame>${t ? `frame 1 / ${t.frame_count}` : clock(duration)}</span></div>
      <div class="cv-stage">
        <video src="${esc(d.source_url)}" muted playsinline preload="metadata" controls aria-label="Source video"></video>
        <canvas aria-hidden="true"></canvas>${legend}
      </div>
      <div class="cv-strip" data-strip>${stripHtml(moments, duration)}</div>
      ${statLine}
    </div>`;
}

/** Wires the panel rendered by sourcePanel inside `root`. Returns { setMoments } for live strip updates. */
export function mountSource(root, d) {
  const panel = root.querySelector(".cv-source");
  if (!panel) return { setMoments() {} };
  const t = d.tracking, duration = durationOf(d);
  const video = panel.querySelector("video"), canvas = panel.querySelector("canvas");
  const stage = panel.querySelector(".cv-stage"), label = panel.querySelector("[data-frame]");
  const strip = panel.querySelector("[data-strip]");
  const ctx = canvas.getContext("2d");
  let dpr = 1;
  const centerToggle = panel.querySelector("[data-center]");
  if (centerToggle) centerToggle.onchange = () => draw(video.currentTime);

  const frameAt = (seconds) => {
    if (!t) return 0;
    const f = Math.floor((seconds * t.fps.numerator) / t.fps.denominator + 1e-6);
    return Math.max(0, Math.min(t.frame_count - 1, f));
  };
  const resize = () => {
    const box = stage.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(box.width * dpr));
    canvas.height = Math.max(1, Math.round(box.height * dpr));
    draw(video.currentTime);
  };
  function draw(seconds) {
    const head = strip?.querySelector(".cv-playhead");
    if (head && duration) head.style.left = `${Math.min(100, (seconds * 1e6 / duration) * 100)}%`;
    if (!t) { label.textContent = `${clock(seconds * 1e6, true)} / ${clock(duration)}`; return; }
    const f = frameAt(seconds);
    label.textContent = `frame ${f + 1} / ${t.frame_count} · ${clock(seconds * 1e6, true)}`;
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    const scale = Math.min(W / t.source_width, H / t.source_height);
    const ox = (W - t.source_width * scale) / 2, oy = (H - t.source_height * scale) / 2;
    const rect = ([x, y, w, h]) => [ox + x * scale, oy + y * scale, w * scale, h * scale];
    ctx.lineWidth = 2 * dpr;
    for (const aspect of ASPECTS) {
      const crop = t.crops?.[aspect]?.[f];
      if (!crop) continue;
      ctx.strokeStyle = CROP_COLORS[aspect];
      ctx.setLineDash(t.degraded?.[aspect] ? [8 * dpr, 6 * dpr] : []);
      ctx.strokeRect(...rect(crop));
    }
    if (centerToggle?.checked) {
      // What a naive resize would keep: thick dashed white frames with a dark halo.
      for (const aspect of ASPECTS) {
        const r = rect(centerCrop(t, aspect));
        ctx.setLineDash([10 * dpr, 7 * dpr]);
        ctx.lineWidth = 4 * dpr; ctx.strokeStyle = "rgba(23,25,30,.55)"; ctx.strokeRect(...r);
        ctx.lineWidth = 2 * dpr; ctx.strokeStyle = "rgba(255,255,255,.9)"; ctx.strokeRect(...r);
      }
      ctx.lineWidth = 2 * dpr;
    }
    const box = t.boxes?.[f];
    if (box) {
      const r = rect(box);
      ctx.fillStyle = "rgba(255,255,255,.14)";
      ctx.fillRect(...r);
      ctx.setLineDash([5 * dpr, 4 * dpr]);
      ctx.strokeStyle = BOX_COLOR;
      ctx.strokeRect(...r);
    }
    ctx.setLineDash([]);
  }

  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    const onFrame = (_, meta) => { draw(meta.mediaTime); if (video.isConnected) video.requestVideoFrameCallback(onFrame); };
    video.requestVideoFrameCallback(onFrame);
  } else {
    const loop = () => { if (!video.isConnected || video.paused) return; draw(video.currentTime); requestAnimationFrame(loop); };
    video.addEventListener("play", () => requestAnimationFrame(loop));
  }
  ["loadeddata", "seeked", "timeupdate"].forEach((name) => video.addEventListener(name, () => draw(video.currentTime)));
  const observer = new ResizeObserver(resize);
  observer.observe(stage);
  onLeave(() => { observer.disconnect(); video.pause(); });
  if (strip && duration) strip.onclick = (event) => {
    const box = strip.getBoundingClientRect();
    video.currentTime = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * duration / 1e6;
  };
  return {
    setMoments(moments) { if (strip) { strip.innerHTML = stripHtml(moments, duration); draw(video.currentTime); } },
    seek(us) { video.currentTime = us / 1e6; },
  };
}
