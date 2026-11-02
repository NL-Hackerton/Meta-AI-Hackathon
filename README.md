# AdLoom

**AdLoom turns one phone video from a small business into six Meta-ready ad videos and two PAUSED ads in the owner's account — using Meta's Muse Spark, SAM 3.1, Muse Image and Muse Voice — and publishes nothing until the owner approves exactly what they saw.**

Built for the Meta Global AI Developer Hackathon.

- Write-up (Devpost style): [docs/submission/WRITEUP.md](docs/submission/WRITEUP.md)
- Architecture and safety invariants: [docs/submission/ARCHITECTURE.md](docs/submission/ARCHITECTURE.md)
- 3-minute demo script: [docs/demo.md](docs/demo.md)
- UI design (Figma): <https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5>
- Korean developer notes (original README): [docs/README.ko.md](docs/README.ko.md)

## The problem

Small local businesses have footage of their work on their phones, but turning it into video ads takes time, money and editing skill they do not have.

- Only **27.2%** of Korean small businesses use any digital or smart technology (2024 national survey). — [Ministry of SMEs and Startups, 2026-03-13](https://www.mss.go.kr/site/smba/ex/bbs/View.do?cbIdx=86&bcIdx=1066231)
- Among about 300 small businesses (mostly US/Canada), **26%** use video marketing or ads, **52%** spend under $1,000 a month on marketing, and **50%** have no marketing staff. — [LocaliQ, 2025-10-27](https://localiq.com/blog/small-business-marketing-trends-report-2026/)
- *Meta-reported:* campaigns that included 9:16 video ads with audio and key messages in the safe zone had **34.5% lower cost per result** than image ads (meta-analysis of 15 split tests). — [Meta for Business, Reels ads](https://www.facebook.com/business/ads/facebook-instagram-reels-ads)

So the formats that work on Meta are exactly the ones small owners are least able to produce. More sources are in the [write-up](docs/submission/WRITEUP.md#inspiration).

## What AdLoom does

1. The owner uploads one video (3–45 seconds) and types or says one sentence about the business.
2. AdLoom picks the best moments, writes three short hooks and the ad copy, and finds the product in every frame.
3. It renders six videos — 9:16, 4:5 and 1:1, each with hook A and hook B — with the crop following the product, subtitles, and an end card.
4. The owner reviews everything on one screen (tracked product box over the source, crops, six videos, copy, flagged phrases with suggested rewrites, warnings) and can edit hooks, copy, scenes or the product to follow.
5. The owner approves. AdLoom stores a SHA-256 fingerprint of what was reviewed.
6. AdLoom creates a campaign, an ad set and two 9:16 ads (hook A and B) in the owner's Meta ad account, all **PAUSED**. The owner switches them on in Ads Manager.

Screens in the web app: Home, Welcome and business profile, Meta connection status, New ad, description confirmation, Review & approve, Edit, publish progress, Approve queue, My ads, notifications, publish log, data deletion and settings. The designs are in the [Figma file](https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5). UI text is in English.

## How it uses Meta AI

| Model | Job in AdLoom |
| --- | --- |
| Muse Spark `muse-spark-1.3` | Watches the video and reads the note; returns key moments, 3 hooks, copy, CTA, a product phrase for SAM, and classified claims as strict JSON. |
| SAM 3.1 `sam-3.1` | Tracks that product through the video so the 9:16, 4:5 and 1:1 crops follow it. |
| Muse Image `muse-image-1.0` | Text-free background images for thumbnails and end cards. Still images only. |
| Muse Voice `muse-voice-transcribe-1.0` | Transcribes a spoken description (owner confirms it) and the video's audio for subtitles. |
| Marketing API | Creates the campaign, ad set and two ads, all PAUSED. |

Why each model, and the guardrails around it: [write-up, "How it uses Meta AI"](docs/submission/WRITEUP.md#how-it-uses-meta-ai).

## Architecture

One Python package (`src/adloom/`) with one shared pipeline used by a CLI and a local FastAPI web app. Stages: normalize → Spark understand → local schema and policy checks → SAM track → crop plans per ratio → Muse Image and Voice enrichment → deterministic ffmpeg render (6 videos) → approval fingerprint → journaled PAUSED publish. Every external call goes through an adapter with a mock and a live implementation. Full diagram and stage table: [docs/submission/ARCHITECTURE.md](docs/submission/ARCHITECTURE.md).

## Safety and trust

- **Approval required.** Publishing re-checks that the approval file is intact and that the SHA-256 of the current content matches the approved fingerprint. Any edit creates a new revision and cancels the approval.
- **PAUSED only.** Campaigns, ad sets and ads are always created with `status: PAUSED`; both publishers refuse anything else before sending. AdLoom never turns an ad on.
- **No generated video.** Every video frame comes from the owner's own footage. Muse Image is used only for still thumbnails and end cards, and all on-screen words are drawn by AdLoom.
- **Standard models only.** Only the four Standard model IDs above are accepted; `-contributor` IDs are refused in code.
- **No silent retries on publish.** Every Marketing API request is journaled. If the outcome of a request is unknown, AdLoom does not send it again; the owner decides.
- **Data handling.** Uploaded videos are stored only in the local `data/` folder and sent only to Meta's APIs. Files uploaded to the Model API are deleted after use. HTTP clients use fixed Meta base URLs, ignore proxy settings and do not follow redirects. Keys and tokens are read only from environment variables. The web app listens on `127.0.0.1` and has no login, so it must not be exposed to a network.
- **Limits we state openly.** The policy check is a small phrase rule table, not a guarantee of passing Meta's ad review. Evidence links show where a claim came from; they do not prove it is true.

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
- **Verified:** latest `make check` — **247 passed** (ruff, mypy strict, pytest). Two renders of the same job produced identical frame hashes on the same ffmpeg build, and a partial publish followed by resume produced 9 requests and 2 ads with no duplicates in the mock publisher (both recorded in [STATUS.md](STATUS.md)).
- **Implemented but gated:** live adapters for Muse Spark, SAM 3.1, Muse Image, Muse Voice and the Marketing API, tested against mocked HTTP responses. Live mode stays off until the Model API key and the ad account are available; `ADLOOM_LIVE=1` is currently refused rather than silently falling back to mocks.
- **No live model call and no real ad has been made yet.** Live results: [fill after live run: date, models called, demo video SAM coverage, ad IDs of the 2 PAUSED ads from Ads Manager].
- **Not built yet:** a claim-review screen (jobs where Spark reports factual claims are held back from approval until it exists), and a read-only lookup for publish requests with an unknown outcome.
- **Current market setup:** ad copy, end-card CTA text and targeting are set up for Korea (Korean text, KRW budget, KR targeting).

## Team and license

- Team: [fill in: team members and roles]
- License: [fill in: no license file has been chosen yet]. Third-party components keep their own licenses: Meta's `meta-sam-parser` (SAM License) and Noto Sans KR (SIL OFL) — see [third_party/README.md](third_party/README.md). BMAD support scripts are MIT — see [_bmad/LICENSE](_bmad/LICENSE).

## More documentation

- Korean developer notes, planning links and design contracts: [docs/README.ko.md](docs/README.ko.md)
- Codebase contract (Korean): [docs/architecture/codebase.md](docs/architecture/codebase.md)
- API verification notes: [docs/api_notes/](docs/api_notes/)
- Original specification (Korean): [SPEC.md](SPEC.md), tasks: [TASKS.md](TASKS.md), progress log: [STATUS.md](STATUS.md)
