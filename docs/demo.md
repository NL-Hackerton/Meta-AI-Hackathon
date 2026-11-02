# AdLoom — 3-minute demo script

Target length: 3:00. Recording: screen capture of the local web app at `http://127.0.0.1:8000` (start with `uv run --locked python -m adloom.web`), plus one browser tab on Meta Ads Manager for the final shot. Screen routes are hash routes in the single-page app (`src/adloom/web/static/js/main.js`).

Two versions of the recording are possible. Record the **live** version if the Model API key and ad account are available before the deadline; otherwise record the **fixture** version and say so on screen. Never present fixture output as a live result.

- **Live:** `ADLOOM_LIVE=1` with all live settings present; the owner's own video; real model calls; real PAUSED ads in Ads Manager.
- **Fixture:** default mode; only `tests/fixtures/sample.mp4` (a synthetic 10-second clip) runs end to end, because mock understanding results are keyed to that file's SHA-256. Publish IDs start with `fixture-` and are not Meta IDs. The app shows "Fixture mode · mock IDs only" on the publish card — keep it visible.

## Script

| Time | Screen (route) | On-screen action | Voiceover |
| --- | --- | --- | --- |
| 0:00–0:15 | Home (`#/`) | Show the home screen with an empty or short job list. | "Most small businesses have phones full of footage but no time to make video ads. In Korea, 72.8% of small businesses use no digital tools at all. AdLoom turns one phone video into Meta-ready ads — and nothing goes out until the owner approves it." |
| 0:15–0:35 | New ad (`#/new`) | Choose the video. Show the length pre-check passing. Type one sentence about the business (or press "Say it" and record it, then confirm the transcript under "What we heard"). Press **Make 6 ads**. | "The owner uploads one video and says one sentence about the business. If they speak it, Muse Voice transcribes it, and they confirm the text before we use it." |
| 0:35–0:55 | Job progress (`#/jobs/<id>`) | Show the steps advancing: understand, track, enrich, assemble. | "Muse Spark watches the video and reads the note. It returns a strict, schema-checked plan: the best moments, three short hooks, the ad copy, and a short name for the product. SAM 3.1 then follows that product through every frame." |
| 0:55–1:25 | Review (`#/jobs/<id>`) | Play the source video with the dashed tracking box. Point at the three crop previews. Scroll to **Six variants · H.264 · AAC** and play a 9:16 hook A and a 1:1 hook B. | "Because SAM knows where the product is, the vertical and square crops follow it instead of cutting the middle. That gives six videos: three ratios, two hooks each. Thumbnails and end cards use a Muse Image background with no text in it — every word you see is drawn by AdLoom, and every video frame comes from the owner's own footage." |
| 1:25–1:45 | Review (`#/jobs/<id>`) — flags | Show a flagged phrase with the suggested rewrite and the approve button locked. Press **Use suggestion**. | "Copy is checked against a policy rule table. A risky phrase blocks approval and comes with a safer rewrite. This is a first screen, not a guarantee of Meta's review." |
| 1:45–2:05 | Edit (`#/jobs/<id>/edit`) | Change hook A text. Save. Return to review: revision number increased, previous approval gone, videos re-rendered. | "The owner can change a hook, the copy, the scenes, or the product to follow. Only what changed is rebuilt — and any edit cancels the earlier approval." |
| 2:05–2:25 | Review → approve sheet | Open **Approve these ads?**. Point at the fingerprint (`sha256 …`). Press **Approve revision N**. | "Approval records a SHA-256 fingerprint of exactly what the owner saw: all six videos, thumbnails, copy, hooks and publish settings. If anything differs at publish time, publishing stops." |
| 2:25–2:45 | Review → publish | Press **Create 2 paused ads**. Show the publish journal (`#/jobs/<id>/log`): 9 requests, each confirmed. | "AdLoom creates a campaign, an ad set and two 9:16 ads — hook A and hook B — and every one of them is PAUSED. Each request is journaled; if a reply is lost, AdLoom never re-sends it on its own." |
| 2:45–3:00 | Live: Ads Manager. Fixture: My ads (`#/ads`) | Live: show the two ads in Ads Manager with status Paused. Fixture: show the two ads with `fixture-` IDs and the "Fixture mode" note. | "The owner turns them on when they are ready. AdLoom: your footage, Meta's models, your decision." |

The voiceover is about 320 words, which fits 3 minutes at a calm pace with pauses for the videos. Trim the 1:25 line first if the take runs long.

## Shot checklist

| # | Shot | Must be live for the live version | Fixture fallback | Status |
| --- | --- | --- | --- | --- |
| 1 | Home screen | No | Same | [fill after recording] |
| 2 | Upload of the owner's own video (not the synthetic sample) | Yes | `tests/fixtures/sample.mp4`, labeled "synthetic sample" | [fill after recording] |
| 3 | Spoken description → Muse Voice transcript → confirm | Yes | Mock transcript; label it | [fill after recording] |
| 4 | Spark output: hooks and copy for the owner's video | Yes | Fixture understanding; label it | [fill after live run: hook texts returned by Spark] |
| 5 | SAM tracking box over the source video | Yes | Synthetic tracking; label it | [fill after live run: SAM coverage %] |
| 6 | Three crops following the product | Yes (depends on 5) | Same code on synthetic tracking | [fill after recording] |
| 7 | Six variants playing | No (rendering is local) | Same | [fill after recording] |
| 8 | Muse Image thumbnail / end card | Yes | Mock image or the "original frame used" fallback warning; label it | [fill after live run: generated or fallback] |
| 9 | Policy flag with rewrite, approval locked | No (local rule table) | Same | [fill after recording] |
| 10 | Edit → new revision → approval cleared | No | Same | [fill after recording] |
| 11 | Approve sheet with fingerprint | No | Same | [fill after recording] |
| 12 | Publish journal with 9 confirmed requests | Yes | `fixture-` IDs with the "Fixture mode" note visible | [fill after live run: campaign/ad set/ad IDs, redacted if needed] |
| 13 | Ads Manager showing 2 ads, status Paused | Yes | Not possible in fixture mode; show `#/ads` instead and say so | [fill after live run: screenshot] |

## Before recording

- Run `make check` and note the result in the video description: [fill after final check: test count].
- Clear old jobs or use a fresh `ADLOOM_DATA_DIR` so the job list is clean.
- Hide the terminal and any environment variables. No API key, token or ad account ID may appear on screen (INV-6).
- Live version: confirm `ADLOOM_SPEND_LIMIT_USD` is set and the ad account's ads are all Paused after the take.
- If the claim list from Spark is not empty, the job is held back from approval (the claim-review screen is not built yet). For the live take, use a video and note that do not invite factual claims (no prices, awards or health statements), or show the block honestly.
