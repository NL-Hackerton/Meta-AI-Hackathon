# AdLoom — 3-minute demo script

Target length: 3:00. Recording: screen capture of the local web app at `http://127.0.0.1:8000` (start with `uv run --locked python -m adloom.web`), plus one browser tab on Meta Ads Manager. Screen routes are hash routes in the single-page app (`src/adloom/web/static/js/main.js`).

## Decide the version before recording

Pick one version and record the whole main take in it. A take that mixes live and fixture shots will confuse judges. Never present fixture output as a live result.

- **Live (preferred):** `ADLOOM_LIVE=1` with all live settings present; the owner's own clip; real model calls; real PAUSED ads in Ads Manager. Live mode is still refused in code (`load_config()` in `src/adloom/config.py`) until the Model API key and ad account are approved, so this version needs that gate opened first.
- **Fixture:** default mode. Only `tests/fixtures/sample.mp4` (a synthetic 10-second clip) runs end to end, because mock understanding results are keyed to that file's SHA-256. Publish IDs start with `fixture-` and are not Meta IDs; keep the "Fixture mode · mock IDs only" note on the publish card visible. Ads Manager cannot be shown; use My ads (`#/ads`) and say so.

The only exception is the failure-and-recovery beat (2:08–2:23). It is always pre-recorded in fixture mode and labeled on screen, so it cannot fail during the main take and never touches a real account.

## Script

| Time | Screen (route) | On-screen action | Voiceover |
| --- | --- | --- | --- |
| 0:00–0:07 | Montage → Ads Manager | Fast cuts of the six output videos (9:16, 4:5, 1:1 × hook A/B), ending on Ads Manager with two ads marked Paused. Fixture: end on My ads (`#/ads`) with the fixture note. | "Six ad videos and two paused ads in Ads Manager — made from one phone video." |
| 0:07–0:15 | Home (`#/`) | Caption: "26% of small businesses use video ads · 50% have no marketing staff — LocaliQ, 2025". | "Half of small businesses have no marketing staff, and only about a quarter use video ads. AdLoom starts from footage they already have." |
| 0:15–0:23 | New ad (`#/new`) | Choose the clip, length pre-check passes, type one sentence, press **Make 6 ads**. Keep it to 8 seconds; skip voice recording unless it takes only a few seconds. | "The owner uploads one clip and one sentence about the shop." |
| 0:23–0:40 | Job progress → Review (`#/jobs/<id>`) | Split screen: Spark's returned hooks and product phrase on one side, the source video with SAM's dashed tracking box on the other. Live: show the request-ID overlay or log line for each call (no keys or account IDs). | "Muse Spark watches the clip and returns a checked plan: the best moments, three hooks, the copy and a name for the product. SAM 3.1 follows that product through every frame." |
| 0:40–1:20 | Review (`#/jobs/<id>`) — tracking | Show the **Product kept whole in the frame** table. Tick **Show plain center crop** to compare it with AdLoom's crop on the 9:16 preview, then untick. Play a 9:16 hook A and a 1:1 hook B. Keep the table's percentages on screen. | "Here's why tracking matters. A plain center crop cuts the product out of a vertical frame; AdLoom's crop follows it. This table counts frames where the whole product stays in the shot: [fill after live run: 9:16 AdLoom crop %] percent for AdLoom, [fill after live run: 9:16 center crop %] for a center crop. Three ratios, two hooks: six videos, every frame from the owner's own footage." |
| 1:20–1:35 | Review — claims | Show the claims list: each factual claim next to its evidence (note quote or video time span). The owner presses **True** on each one and **Approve revision N** unlocks. If a claim is wrong, pressing **Not true** keeps approval locked until the copy is edited. Show a policy flag only if the recorded note produces a real one; never script a flag. In the fixture version there are no claims, so give these 15 s to the tracking beat. | "Spark lists every factual claim with its evidence. The owner marks each one true or not true; nothing can be approved until they do." |
| 1:35–1:43 | Edit (`#/jobs/<id>/edit`) | Change hook A, save; back on review the revision number has gone up and the approval is cleared. | "An edit rebuilds only what changed and cancels the earlier approval." |
| 1:43–1:50 | Review → approve sheet | Open **Approve these ads?**, show the fingerprint for about 3 seconds, press **Approve revision N**. | "What the owner reviewed is fingerprinted. If anything changes, publishing stops." |
| 1:50–2:08 | Review → publish (`#/jobs/<id>/log`) | Press **Create 2 paused ads**. Show the journal filling in: campaign, ad set, thumbnail, then video, creative and ad for hooks A and B, each Confirmed with its remote ID. Live: redact the ad account ID if it appears. | "AdLoom creates a campaign, an ad set and two ads in the owner's account. Every one is paused, and every ID comes back from Meta." |
| 2:08–2:23 | Pre-recorded, fixture mode | Caption: "Pre-recorded · fixture mode · simulated lost reply". With `ADLOOM_FIXTURE_FAULT=publish_unknown_once`, the ad-set request comes back Unknown, the job shows "Publish result unknown", the journal notes that UNKNOWN requests are never re-sent automatically, and the owner presses **Stop attempt**. | "If a reply is lost, AdLoom doesn't guess. The request is marked unknown, never re-sent on its own, and the owner decides." |
| 2:23–2:50 | Ads Manager (live) | Open the campaign, then the ad set, then the two ads, all with status Paused. Open one ad preview so hook A is visible, then the other for hook B. Fixture: not possible; this version cannot have this beat. | "Here they are in Ads Manager: one campaign, two paused ads, hook A and hook B. The owner checks them here and switches them on when they're ready." |
| 2:50–3:00 | Closing card | Measured numbers on screen: upload-to-review time, tracked vs center crop "kept whole" per ratio, Model API spend for the job. | "[fill after live run: upload-to-review time] from upload to review, six videos, two paused ads. Your footage, Meta's models, your decision." |

The voiceover is about 260 words, leaving room for the videos to play. If the take runs long, trim the 0:07 line first. The Ads Manager beat should keep at least 25 seconds.

## Shot checklist

| # | Shot | Must be live for the live version | Fixture fallback |
| --- | --- | --- | --- |
| 1 | Opening montage ending on Ads Manager | Yes (Ads Manager) | My ads (`#/ads`) with the fixture note |
| 2 | Upload of the owner's own clip (not the synthetic sample) | Yes | `tests/fixtures/sample.mp4`, labeled "synthetic sample" |
| 3 | Spark hooks and product phrase beside the SAM box | Yes | Fixture understanding and synthetic tracking; label it |
| 4 | "Product kept whole in the frame" table with the center-crop toggle | Yes (depends on 3) | Same code on synthetic tracking |
| 5 | Six variants playing | No (rendering is local) | Same |
| 6 | Claim review with evidence | Yes (claims come from Spark) | Fixture has no claims; skip |
| 7 | Edit → new revision → approval cleared | No | Same |
| 8 | Approve sheet with fingerprint | No | Same |
| 9 | Publish journal with remote IDs | Yes | `fixture-` IDs with the "Fixture mode" note visible |
| 10 | Unknown result → Stop attempt | No (always pre-recorded in fixture mode) | Same |
| 11 | Ads Manager: 2 ads, status Paused | Yes | Not possible |
| 12 | Closing numbers | Yes | Not possible; do not show fixture numbers as results |

## Before recording

- Clear old jobs or use a fresh `ADLOOM_DATA_DIR` so the job list is clean.
- Hide the terminal and any environment variables. No API key, token or ad account ID may appear on screen (INV-6).
- Live version: confirm `ADLOOM_SPEND_LIMIT_USD` is set, and after the take confirm every ad in the account is still Paused.
- Set the job language to English so hooks, copy, subtitles and the end card ("Learn more") are readable by judges. Targeting and budget currency remain Korea and KRW in the current build.
- Use a clean clip with one clearly visible product, and a note with one or two simple true facts (for example how long the shop has been open) and no prices, awards or health statements. Rehearse once so SAM tracks well and the claims list is short.
- Keep one cached good take as a fallback in case of rate limits.
- Record the failure beat separately: `ADLOOM_FIXTURE_FAULT=publish_unknown_once uv run --locked python -m adloom.web`, run the sample clip, approve, publish. The fault fires on the first ad-set request in each server process, so restart the server before each retake.

## Pre-submission checklist

Every `[fill …]` slot must be replaced with a measured value or removed before submission. No placeholder may ship.

In this script:

- [ ] 0:40 voiceover and closing card: 9:16 "kept whole" percentage for AdLoom's crop, from the review table of the recorded job.
- [ ] 0:40 voiceover and closing card: 9:16 "kept whole" percentage for the plain center crop, from the same table.
- [ ] Closing card: "kept whole" percentages for 4:5 and 1:1 (AdLoom crop and center crop).
- [ ] 2:50 voiceover and closing card: upload-to-review time of the recorded job.
- [ ] Closing card: Model API spend for the recorded job against `ADLOOM_SPEND_LIMIT_USD`.
- [ ] If the live take produces no claims, cut the 1:20 claims beat and give its 15 s to the tracking beat.

In the other submission documents:

- [ ] [README.md](../README.md#project-status): live results (date, models called, demo clip SAM coverage, ad IDs of the 2 PAUSED ads).
- [ ] [README.md](../README.md#project-status): re-run `make check` and update the single dated test count if code changed after 2026-11-02.
- [ ] [README.md](../README.md#team-and-license): team members and roles; license.
- [ ] [WRITEUP.md](submission/WRITEUP.md#how-it-uses-meta-ai): live measurements (date, model IDs, requests per model, Spark hooks, SAM coverage, tracked vs center crop percentages, image fallback, spend).
- [ ] [ARCHITECTURE.md](submission/ARCHITECTURE.md#what-is-not-claimed): live request IDs or dates and the Ads Manager read-back.
