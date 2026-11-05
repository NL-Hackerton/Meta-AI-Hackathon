# AdLoom

**AdLoom is designed to turn one phone video from a small business into six ad videos sized for Meta placements and two PAUSED ads in the owner's own ad account. It uses Meta's Muse Spark, SAM 3.1, Muse Image and Muse Voice, and it publishes nothing until the owner approves the reviewed content.**

So far it runs end to end in fixture mode (mock providers, bundled sample clip). The live adapters are built and tested against mocked HTTP, but no live model call and no real ad has been made yet — see [Project status](#project-status).

Built for the Meta Global AI Developer Hackathon.

- Write-up (Devpost style): [docs/submission/WRITEUP.md](docs/submission/WRITEUP.md)
- Architecture and safety invariants: [docs/submission/ARCHITECTURE.md](docs/submission/ARCHITECTURE.md)
- 3-minute demo script: [docs/demo.md](docs/demo.md)
- UI design (Figma): <https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5>
- Korean developer notes (original README): [docs/README.ko.md](docs/README.ko.md)

## The problem

Small local businesses have footage of their work on their phones, but turning it into video ads takes time, money and editing skill they do not have.

- Among about 300 small businesses (mostly US/Canada), **26%** use video marketing or ads, **52%** spend under $1,000 a month on marketing, and **50%** have no marketing staff. — [LocaliQ, 2025-10-27](https://localiq.com/blog/small-business-marketing-trends-report-2026/)
- Among US small businesses that advertise on social media, Facebook and Instagram are the most popular platforms, and young, larger firms are **7×** more likely to use video ads than small, older ones. — [Intuit SMB MediaLabs, 2025](https://quickbooks.intuit.com/r/small-business-data/advertising-trends-2025/)
- *Meta-reported (Meta's own split tests, not an AdLoom result):* campaigns that included 9:16 video ads with audio and key messages in the safe zone had **34.5% lower cost per result** than image ads (meta-analysis of 15 split tests). — [Meta for Business, Reels ads](https://www.facebook.com/business/ads/facebook-instagram-reels-ads)

So the formats Meta recommends are the ones small owners are least able to produce. AdLoom aims to make them from footage the owner already has; it has not been measured against any of the figures above. More sources are in the [write-up](docs/submission/WRITEUP.md#inspiration).

**Supported market today:** targeting and budget are set up for Korea (KR targeting, KRW budget). Each job has a language, Korean or English: the end-card call to action ("자세히 보기" / "Learn more") and Muse Voice transcription follow it, and English on-screen words wrap whole. Korean text is drawn with Noto Sans KR.

## What AdLoom does

1. The owner uploads one video (3–45 seconds) and types or says one sentence about the business.
2. Muse Spark is designed to pick the best moments, write three short hooks and the ad copy, and name the product; SAM 3.1 is designed to find that product in every frame.
3. AdLoom renders six videos — 9:16, 4:5 and 1:1, each with hook A and hook B — with the crop following the product, subtitles, and an end card.
4. The owner reviews everything on one screen (tracked product box over the source, crops, a "Product kept whole in the frame" table comparing AdLoom's crop with a plain center crop, six videos, copy, factual claims to mark True or Not true next to their evidence, flagged phrases with suggested rewrites, warnings) and can edit hooks, copy, scenes or the product to follow.
5. The owner approves. AdLoom stores a SHA-256 fingerprint of the reviewed content (videos, thumbnails, copy and publish settings); publishing stops if any of it has changed since.
6. AdLoom creates a campaign, an ad set and two 9:16 ads (hook A and B) in the owner's Meta ad account, all **PAUSED**. The owner switches them on in Ads Manager.

Screens in the web app: Home, Welcome and business profile, Meta connection status, New ad, description confirmation, Review & approve, Edit, publish progress, Approve queue, My ads, notifications, publish log, data deletion and settings. The designs are in the [Figma file](https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5). UI text is in English.

## How it uses Meta AI

All model calls below are implemented and tested against mocked HTTP responses only. The model IDs come from Meta's developer documentation ([api notes](docs/api_notes/verification.md)) and have not yet been confirmed against the live API.

| Model | Job it is designed to do in AdLoom |
| --- | --- |
| Muse Spark `muse-spark-1.3` | Takes the video and the note; returns key moments, 3 hooks, copy, CTA, a product phrase for SAM, and classified claims as strict JSON. |
| SAM 3.1 `sam-3.1` | Tracks that product through the video so the 9:16, 4:5 and 1:1 crops follow it. |
| Muse Image `muse-image-1.0` | Text-free background images for thumbnails and end cards. Still images only. |
| Muse Voice `muse-voice-transcribe-1.0` | Transcribes a spoken description (owner confirms it) and the video's audio for subtitles. |
| Marketing API | Creates the campaign, ad set and two ads, all PAUSED. |

Why each model, and the guardrails around it: [write-up, "How it uses Meta AI"](docs/submission/WRITEUP.md#how-it-uses-meta-ai).

## Architecture

One Python package (`src/adloom/`) with one shared pipeline used by a CLI and a local FastAPI web app. Stages: normalize → Spark understand → local schema and policy checks → SAM track → crop plans per ratio → Muse Image and Voice enrichment → deterministic ffmpeg render (6 videos) → approval fingerprint → journaled PAUSED publish. Every external call goes through an adapter with a mock and a live implementation. Full diagram and stage table: [docs/submission/ARCHITECTURE.md](docs/submission/ARCHITECTURE.md).

## Safety and trust

- **Approval required.** Publishing re-checks that the approval file is intact and that the SHA-256 of the current content matches the approved fingerprint. Any edit creates a new revision and cancels the approval. The fingerprint covers the stored files and fields the review screen shows; it cannot prove what the owner actually looked at.
- **PAUSED only.** Campaigns, ad sets and ads are always created with `status: PAUSED`; both publishers refuse anything else before sending. AdLoom never turns an ad on.
- **No generated video.** Every video frame comes from the owner's own footage. Muse Image is used only for still thumbnails and end cards, and all on-screen words are drawn by AdLoom.
- **Standard models only.** Only the four Standard model IDs above are accepted; `-contributor` IDs are refused in code.
- **No silent retries on publish.** Every Marketing API request is journaled. If the outcome of a request is unknown, AdLoom does not send it again; the owner decides.
- **Data handling.** Uploaded videos are stored only in the local `data/` folder and, in live mode, sent only to Meta's APIs. Files uploaded to the Model API are designed to be deleted after the stage that used them (wired and tested with mocked HTTP, not yet run live). HTTP clients use fixed Meta base URLs, ignore proxy settings and do not follow redirects. Keys and tokens are read only from environment variables. The web app listens on `127.0.0.1` and has no login, so it must not be exposed to a network.
- **Policy pre-check, not a review.** Ad copy and subtitles are checked locally against 20 rules (Korean and English) in `src/adloom/policy_rules.yaml`, covering 8 areas of [Meta's Advertising Standards](https://transparency.meta.com/policies/ad-standards) such as personal attributes, health claims and income promises. Each rule cites the Meta page it is based on and stores a suggested rewrite. A `block` rule locks approval until the text changes; a `warn` rule is shown but does not block. Matches in subtitles are reported as warnings, because subtitles come from the confirmed narration. The check does not predict or guarantee the outcome of Meta's ad review. Details: [policy notes](docs/api_notes/policy.md).
- **The owner confirms claims; AdLoom checks only their structure.** Spark classifies each factual claim as `explicit` (in the note), `observation` (visible in the video) or `inference`, with evidence. AdLoom checks only that the evidence is well formed (a quote that exists in the note, a time span inside this video). On the review screen the owner marks each claim **True** or **Not true** next to its evidence. A claim marked Not true blocks approval until the copy is edited, and the edit drops that claim. Changing a decision after approval clears the approval.

The eight safety invariants (INV-1 to INV-8), where each is enforced, and which tests cover it: [ARCHITECTURE.md](docs/submission/ARCHITECTURE.md#safety-invariants).

## Run it locally

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and ffmpeg/ffprobe (9.x) on `PATH`.

```sh
uv sync --locked
make check            # ruff + mypy --strict + pytest
uv run --locked python -m adloom.web   # open http://127.0.0.1:8000
```

In the default fixture mode, only the bundled synthetic clip `tests/fixtures/sample.mp4` runs end to end, because the mock understanding results are keyed to that file's SHA-256.

The same pipeline from the command line:

```sh
uv run --locked python -m adloom run \
  --video tests/fixtures/sample.mp4 --note "Synthetic sample" --region "Seoul" --budget 10000
uv run --locked python -m adloom list
uv run --locked python -m adloom inspect JOB_ID          # shows content_digest, flags, warnings
uv run --locked python -m adloom approve JOB_ID --actor local-reviewer --digest CONTENT_DIGEST
uv run --locked python -m adloom publish JOB_ID
uv run --locked python -m adloom edit JOB_ID --hook-a "New hook text"
uv run --locked python -m adloom resume JOB_ID
```

Rendered videos are written to `data/jobs/JOB_ID/renders/r000001/`. `ADLOOM_DATA_DIR` changes the data folder; `ADLOOM_HOST` and `ADLOOM_PORT` change the web address.

## Project status

- **Working now (fixture mode):** the full path — upload, understand, track, crop, enrich, render six videos, review, edit, approve, publish two PAUSED ads — from both the CLI and the web app, using mock providers and fixture data. Publish IDs starting with `fixture-` are not Meta IDs.
- **Verified (2026-11-02):** `make check` (ruff, mypy strict, pytest) — **520 passed**. This is the only place the test count is recorded; other documents link here. Earlier checks, also in [STATUS.md](STATUS.md): two renders of the same job produced identical frame hashes on the same ffmpeg build (synthetic sample clip only), and a partial publish followed by resume produced 9 requests and 2 ads with no duplicates in the mock publisher.
- **Implemented but gated:** live adapters for Muse Spark, SAM 3.1, Muse Image, Muse Voice and the Marketing API, tested against mocked HTTP responses only. Live mode stays off until the Model API key and the ad account are available; `ADLOOM_LIVE=1` is currently refused rather than silently falling back to mocks.
- **No live model call and no real ad has been made yet.** The submitted demonstration uses the bundled synthetic clip and simulated provider responses. There are no live performance, cost or ad-delivery results to report.
- **Unknown-outcome demo in fixture mode:** `ADLOOM_FIXTURE_FAULT=publish_unknown_once` (fixture mode only, off by default) makes the mock publisher lose the reply to the first ad-set request in each server process. The journal records `UNKNOWN`, and the web app shows "Publish result unknown" and **Stop attempt**, without touching a real account. Restart the server to show it again.
- **Not built yet:** a read-only lookup on Meta for publish requests with an unknown outcome (the live publisher has a `read()` method for it, but nothing calls it yet).

## Team and license

- Contributor roles are recorded in the repository history; participant identity is provided through the submission portal.
- No project-wide license has been granted. Third-party components retain their respective licenses: Meta's `meta-sam-parser` (SAM License) and Noto Sans KR (SIL OFL) — see [third_party/README.md](third_party/README.md). BMAD support scripts are MIT — see [_bmad/LICENSE](_bmad/LICENSE).

## More documentation

- Korean developer notes, planning links and design contracts: [docs/README.ko.md](docs/README.ko.md)
- Codebase contract (Korean): [docs/architecture/codebase.md](docs/architecture/codebase.md)
- API verification notes: [docs/api_notes/](docs/api_notes/)
- Original specification (Korean): [SPEC.md](SPEC.md), tasks: [TASKS.md](TASKS.md), progress log: [STATUS.md](STATUS.md)
