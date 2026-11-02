# AdLoom — project write-up

**One video in, six ad videos out, two paused Meta ads ready for the owner to switch on — and nothing is published until the owner approves the reviewed content.**

Status in one line: the full path runs end to end in fixture mode (mock providers, bundled synthetic clip); the live adapters are built and tested against mocked HTTP only; no live model call and no real ad has been made yet. Verified test results and dates are kept in one place: [README, Project status](../../README.md#project-status).

Repository README: [../../README.md](../../README.md) · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Demo script: [../demo.md](../demo.md) · Figma: <https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5>

## Inspiration

Small local businesses — a café, a repair shop, a small restaurant — already have phones full of footage of their work. What they lack is the time, the money and the editing skill to turn that footage into ads in the formats Meta recommends.

The numbers point the same way:

- In a 2025–26 survey of about 300 small businesses (87% US/Canada), **26%** use video marketing or ads, **52%** spend under $1,000 a month on marketing, and **50%** have no dedicated marketing staff. ([LocaliQ, 2025-10-27](https://localiq.com/blog/small-business-marketing-trends-report-2026/))
- Among US small businesses that advertise on social media, Meta's Facebook and Instagram are the most popular platforms, and young, larger firms are **7×** more likely to use video ads than small, older ones. ([Intuit SMB MediaLabs, 2025](https://quickbooks.intuit.com/r/small-business-data/advertising-trends-2025/))
- Marketers who do not use video most often say it is **too expensive (24%)** or that they **lack time (19%)**. Small sample (266), not SMB-only. ([Wyzowl, 2026](https://wyzowl.com/video-marketing-statistics/))
- Korea, our first supported market: in the 2024 national small-business survey, only **27.2%** of small businesses use any digital or smart technology at all — a broader measure than video ads. ([Ministry of SMEs and Startups, 2026-03-13](https://www.mss.go.kr/site/smba/ex/bbs/View.do?cbIdx=86&bcIdx=1066231))

Meta's own guidance tells advertisers what works — but each step is work a small owner does not have time for. The figures below are Meta's published results and recommendations, not results AdLoom has produced or measured:

- *Meta-reported:* campaigns that included 9:16 video ads with audio and key messages in the safe zone had **34.5% lower cost per result** than image ads (meta-analysis of 15 split tests). ([Meta for Business, Reels ads](https://www.facebook.com/business/ads/facebook-instagram-reels-ads))
- *Meta-reported:* great Reels "nail the hook" in the first few seconds. ([Meta, Reel Talk Creative Playbook for Small Businesses](https://paulinachyla.pl/wp-content/uploads/2024/06/MetaReelTalkCreativePlaybookForSmallBusinesses-3.pdf), Meta document hosted by a third party)
- *Meta-reported:* Meta recommends creative diversification, for example one ad built on emotional appeal and another on product features. ([Meta, Demystifying Creative Diversification, 2025-12-16](https://www.facebook.com/business/news/demystifying-creative-diversification))
- Meta's ad review is mostly automated, and a violation can lead to rejection and account restrictions. ([Meta Transparency Center, Advertising Standards](https://transparency.meta.com/policies/ad-standards)) A small owner cannot afford to learn the rules by getting an account restricted.

We wanted a tool designed to apply this guidance to footage the owner already has, without making things up about their business and without spending their money behind their back.

## What it does

1. The owner uploads one phone video (3–45 s) and writes or says one sentence about the business.
2. Muse Spark is designed to find the best moments, write three short hooks plus ad copy, and name the product; SAM 3.1 is designed to find that product in every frame.
3. AdLoom renders **six** ad videos sized for Meta placements: 9:16, 4:5 and 1:1, each with hook A and hook B. The crop follows the product instead of cutting the center. Each video ends with a short end card.
4. The owner reviews everything in one screen: the source video with the tracked product box, the three crops, a "Product kept whole in the frame" table that compares AdLoom's crop with a plain center crop (with a "Show plain center crop" toggle), all six videos, the copy, any flagged phrases (with a suggested rewrite), and warnings such as "tracking was weak, so this ratio uses a center crop".
5. The owner can edit the hooks, the copy, which moments to use, or what product to follow. Only the affected parts are rebuilt.
6. The owner approves. AdLoom records a SHA-256 fingerprint of the reviewed content — the six videos, thumbnails, copy, claims, flags and publish settings. Publishing stops if any of it has changed. (The fingerprint covers what is stored and shown; it cannot prove what the owner actually looked at.)
7. AdLoom creates **two 9:16 ads (hook A and hook B) in the owner's Meta ad account, all in PAUSED status**. The owner turns them on in Ads Manager.

The web app (`python -m adloom.web`) has these screens: Home, Welcome and business profile, Meta connection status, New ad (length pre-check; typed or spoken description), description confirmation, Review & approve, Edit, publish progress and "unknown result" handling, Approve queue, My ads and ad detail, notifications, publish log, data deletion, and settings. Designs: [Figma file](https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5).

## How we built it

- **Python 3.12**, one package (`src/adloom/`), dependencies pinned in `uv.lock`. Pydantic models (`src/adloom/schemas.py`) define every boundary: model output, crop plans, render plans, the approval subject and publish journal entries.
- **One pipeline, two front ends.** `src/adloom/pipeline.py` is shared by the CLI (`src/adloom/cli.py`) and a FastAPI app with a single-page front end (`src/adloom/web/`). The web server listens on loopback only.
- **Adapters for every external call** (`src/adloom/adapters/base.py`): Understanding (Spark), Tracking (SAM), Image, Voice and Marketing. Each has a mock and a live implementation. Live HTTP code shares one client module with fixed base URLs, size limits, timeouts and error mapping (`src/adloom/adapters/model_api.py`).
- **Media** is done with ffmpeg/ffprobe and Pillow. Crop planning is a pure function (`src/adloom/crop.py`). Rendering builds one ffmpeg filter graph per variant from a validated plan (`src/adloom/render.py`). Korean text is drawn with a bundled Noto Sans KR font (OFL, see [third_party](../../third_party/README.md)).
- **Storage** is a folder per job: an atomically replaced `job.json` head, immutable hash-checked artifacts, one approval file per revision, and one journal file per publish request (`src/adloom/jobs.py`, `src/adloom/stages/publish.py`).
- **Checks:** `make check` runs ruff, mypy in strict mode and pytest. The latest verified result and its date are in the [README](../../README.md#project-status).
- Specifications and architecture decisions were written first (`SPEC.md`, [codebase contract](../architecture/codebase.md), BMAD planning artifacts), then implemented task by task with a failing test first (`TASKS.md`, `STATUS.md`).

## How it uses Meta AI

All four models are called through the Meta Model API (`https://api.meta.ai/v1`); ads are created through the Marketing API (Graph API). Everything in this section is implemented and tested against mocked HTTP responses; none of it has been run against the live APIs yet. The model IDs come from Meta's developer documentation ([api notes](../api_notes/verification.md)). Only Standard model IDs are allowed; any other ID, including `-contributor` variants, is refused in code (`require_standard_model()` in `src/adloom/adapters/model_api.py`, `load_config()` in `src/adloom/config.py`).

| Model / API | Job it is designed to do in the AdLoom pipeline | Why this model | Guardrails |
| --- | --- | --- | --- |
| **Muse Spark** `muse-spark-1.3` | Receives the normalized video and the owner's note. Must return one JSON object that matches a strict schema: 1–5 key moments in microseconds, exactly 3 hooks (≤ 22 characters), primary text (≤ 125), headline and product name (≤ 40), CTA, a short English noun phrase naming the product for SAM, and every factual claim classified as `explicit` / `observation` / `inference` with evidence references. (`src/adloom/adapters/spark.py`, `src/adloom/stages/understand.py`) | It is the model that takes video and text together and supports strict structured output, so one call gives us both the edit plan and the copy in a form we can validate. | Standard model only. Strict JSON schema; output is validated again locally and gets at most one repair retry. CTA must be on an allowlist. The instructions forbid invented prices, discounts, awards or health effects. Policy flags are never taken from the model; they are recomputed locally and come with a suggested rewrite. Approval checks that each claim's evidence is well formed (a quote that exists in the note, a time span inside the video) — a structural check, not proof the claim is true. Uploaded files are designed to be deleted after the call. |
| **SAM 3.1** `sam-3.1` | Tracks the product named by Spark through every frame of the video and returns per-frame boxes. AdLoom turns them into smooth crop paths for 9:16, 4:5 and 1:1. (`src/adloom/adapters/sam.py`, `src/adloom/crop.py`) | Re-framing a 16:9 phone video into vertical and square formats needs to know where the product is in each frame; SAM 3.1 does promptable video segmentation from a short text phrase. | Responses are parsed with Meta's official `meta-sam-parser` (source and license kept in [third_party](../../third_party/README.md)). Incomplete or malformed streams fail the stage instead of being guessed. If the product is found in under 60% of frames, AdLoom uses a center crop and tells the owner. Crop movement is limited to 24 px per frame. |
| **Muse Image** `muse-image-1.0` | Generates one text-free background scene per ratio, used for the thumbnail and the end card. (`src/adloom/adapters/image.py`, `src/adloom/stages/enrich.py`) | Thumbnails and end cards are still images in the exact ad sizes; generating them avoids asking the owner for extra assets. | Still images only — no video is ever generated. The prompt asks for no text, letters, numbers or logos; all words on screen are drawn by AdLoom. Web search, image search and shell tools are disabled in every request. If generation fails, a real frame from the owner's video and a plain card are used, and the review screen says so. |
| **Muse Voice** `muse-voice-transcribe-1.0` | (1) Transcribes a spoken description when the owner records one instead of typing. (2) Transcribes the video's own audio; the segments become burned-in subtitles. (`src/adloom/adapters/voice.py`, `src/adloom/stages/input.py`, `src/adloom/stages/enrich.py`) | Owners often find it easier to talk than to type, and Meta's Reels guidance assumes sound on; subtitles keep the message readable with sound off. | A transcribed description is shown to the owner and used only after they confirm it. Subtitles are part of the approval fingerprint and of the policy check. |
| **Marketing API** (Graph API) | Creates, in order: campaign, ad set, thumbnail image, then for each of the two 9:16 variants a video, a creative and an ad. (`src/adloom/stages/publish.py`, `src/adloom/adapters/marketing.py`) | It is how the result lands in the owner's own ad account, ready for Ads Manager. | **PAUSED only:** campaign, ad set and ad are always `PAUSED`; the publisher refuses any other status before sending. **Approval fingerprint:** publishing re-checks that the approval file is intact and that the SHA-256 of the current content equals the approved one. **Journal:** each request is recorded before it is sent and after it returns; a request whose outcome is unknown is never re-sent automatically. |

Everything above is wired and tested with mocked HTTP only. Live measurements: [fill after live run: date, model IDs called, number of requests per model, Spark output for the demo video (hooks), SAM coverage on the demo video, tracked vs center crop "kept whole" percentages per ratio, image fallback yes/no, total Model API spend against the configured limit].

## Challenges we ran into

- **Keeping the approval honest.** "The owner approved it" only means something if what gets published is byte-for-byte what was reviewed. We defined an explicit `ApprovalSubject` (an allow-list of fields, not "the manifest minus some keys"), hash its canonical JSON, and re-check it at publish time. Any edit creates a new revision and drops the approval.
- **Publishing without duplicates.** A network timeout after a create request does not tell you whether the ad exists. Retrying could create a second ad; giving up could leave an orphan. We journal every request (`PREPARED` → `CONFIRMED` or `UNKNOWN`), reuse confirmed IDs on resume, and stop at `UNKNOWN` until a person decides.
- **Model output we can trust enough to edit with.** Spark's output goes through a strict schema, a local validation pass, one repair retry, a CTA allowlist and a local policy pre-check. Claims carry evidence references that are checked for structure against the real note text and video duration; whether a claim is true is for the owner to confirm, which is why a claim-review step is being added.
- **A policy pre-check that is honest about its limits.** A handful of phrases is not a meaningful pre-check, so the local rule table is being expanded into rules grounded in Meta's Advertising Standards, each with a suggested rewrite. It still only pre-checks copy and subtitles; it does not predict Meta's ad review.
- **Reproducible rendering.** We needed the same inputs to give the same frames so that an approval stays valid. Encoding runs single-threaded and the plan records a fingerprint of the ffmpeg build, renderer code and font; rendering refuses to run if any of them changed.
- **No live access during most of the build.** The Model API key and the ad account were not available while we built. We implemented the live adapters against the documented APIs, tested them with mocked HTTP responses, and kept them behind a single gate so nothing could reach a real endpoint by accident.

## Accomplishments that we're proud of

- An end-to-end path — upload, understand, track, crop, enrich, render 6 videos, review, edit, approve, publish 2 PAUSED ads — works from both the CLI and the web app in fixture mode.
- Six variants render deterministically: two renders of the same job gave identical frame hashes on the same ffmpeg build (synthetic sample clip only; recorded in `STATUS.md`, 2026-10-27).
- A partial publish failure followed by resume produced 9 requests and 2 ads with no duplicates in the mock publisher (recorded in `STATUS.md`, 2026-10-27).
- The review screen measures, per ratio, the share of frames where the whole product box stays inside AdLoom's crop versus a plain center crop, so the benefit of tracking is a number rather than a claim.
- Safety rules (INV-1 to INV-8 in [ARCHITECTURE.md](ARCHITECTURE.md#safety-invariants)) are enforced in code and covered by tests against mock providers, not only written in a document. Tests and checks: see [README, Project status](../../README.md#project-status).

## What we learned

- Video understanding is most useful when its output is a plan we can check (time spans, a noun phrase, classified claims) rather than finished prose.
- Text-prompted tracking makes re-framing practical, but the product needs a fallback when tracking is weak — and the owner should be told, not surprised.
- For ad tooling, the hard part is not generating content but making sure nothing goes live that the owner did not see and approve.

## What's next

- Run the live path end to end with the Model API key and a real ad account, and fill in the measurements marked above.
- Finish the claim-review step, now being added: the owner confirms each factual claim next to its evidence. Until it lands, any job where Spark reports factual claims is held back from approval (`make_subject()` in `src/adloom/stages/publish.py`).
- Finish the policy rule table expansion grounded in Meta's Advertising Standards.
- Show unknown-outcome recovery in fixture mode with `ADLOOM_FIXTURE_FAULT=publish_unknown_once` (being added): the mock publisher loses the reply to the ad-set request once, the journal records `UNKNOWN`, and the owner chooses **Stop attempt**.
- A read-only "reconcile" step that looks up an `UNKNOWN` publish request on Meta before the owner decides.
- A configurable market for targeting and budget currency (currently Korea only), and English end-card text and subtitles end to end (being added; the Spark and Voice adapters already accept `en`).
- Evaluation on a fixed set of real owner videos (planned in the acceptance plan; no results yet).
