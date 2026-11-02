# Marketing API live publisher (`src/adloom/adapters/marketing.py`)

Docs read on 2026-11-02 (reference pages render v25.0 examples; guides show v26.0, the current
latest). No real API call was made; `tests/test_live_marketing.py` uses `httpx.MockTransport`.
The Graph version is never hard-coded: `LiveMarketing(graph_version=...)` must match
`v<major>.<minor>` and every URL is `https://graph.facebook.com/{graph_version}/...`.

## Sources

| Short name | URL |
| --- | --- |
| campaigns | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/campaigns |
| campaign node | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-campaign-group |
| adsets | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/adsets |
| adset node | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-campaign |
| ads | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/ads |
| adcreatives | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/adcreatives |
| video_data | https://developers.facebook.com/docs/graph-api/reference/ad-creative-video-data/ |
| call_to_action | https://developers.facebook.com/docs/marketing-api/reference/ad-creative-link-data-call-to-action/ |
| adimages | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/adimages |
| ad image | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-image |
| advideos | https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-account/advideos |
| video ads guide | https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/videoads |
| FB video ads | https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/videoads/fbvideoads |
| video status | https://developers.facebook.com/docs/graph-api/reference/video-status/ |
| currencies | https://developers.facebook.com/documentation/ads-commerce/marketing-api/currencies |
| errors (Marketing) | https://developers.facebook.com/documentation/ads-commerce/marketing-api/error-reference |
| errors (Graph) | https://developers.facebook.com/docs/graph-api/guides/error-handling/ |
| rate limiting | https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/rate-limiting |

## Transport

- Every request carries `Authorization: Bearer <token>`; the token is never put in a URL, a
  form body, an error detail or `repr` (tests assert all four). Doc examples pass
  `access_token=` as a form field, and the upload guide uses `Authorization: OAuth {access-token}`
  — see open question 1.
- Create calls are `application/x-www-form-urlencoded` (video: `multipart/form-data`); objects
  and lists are JSON-encoded strings, matching the doc examples (`-F 'targeting={...}'`,
  `special_ad_categories=%5B%5D`).
- No POST is ever retried (one request per `create`, asserted in tests). No redirects are
  followed, `trust_env=False`, response bodies are capped at 1 MiB.

## Requests

### campaign — `POST act_{id}/campaigns`

```text
name=<job_id>  objective=OUTCOME_TRAFFIC  status=PAUSED  special_ad_categories=[]
is_adset_budget_sharing_enabled=false
```

- `name`: "Name for this campaign" (campaigns).
- `objective`: enum includes `OUTCOME_TRAFFIC`; "If it is specified the API will validate that any
  ads created under the campaign match that objective" (campaigns).
- `status`: "Only `ACTIVE` and `PAUSED` are valid during creation" (campaigns).
- `special_ad_categories`: "**[required]**" (campaigns); docs example sends `[]`.
- `is_adset_budget_sharing_enabled`: every create example sends it
  (`...&special_ad_categories=%5B%5D&is_adset_budget_sharing_enabled=0`); node doc: "Whether the
  child ad sets are managed under ad set budget sharing" (campaign node). Budget is set on the ad
  set — "You can either set budget at the campaign level or at the adset level, not both"
  (campaigns `daily_budget`).

### adset — `POST act_{id}/adsets`

```text
name=<operation_key>  campaign_id=<id>  daily_budget=<KRW integer>  status=PAUSED
billing_event=IMPRESSIONS  optimization_goal=LINK_CLICKS  targeting={"geo_locations":{"countries":["KR"]}}
bid_strategy=LOWEST_COST_WITHOUT_CAP  destination_type=WEBSITE
```

- `name`: "Ad set name, max length of 400 characters. **[required]**" (adsets). The publish
  payload has no name, so the adapter uses the journal `operation_key`.
- `campaign_id`: "The ad campaign you wish to add this ad set to." (adsets)
- `daily_budget`: "The daily budget defined in your account currency, allowed only for ad sets
  with a duration (difference between `end_time` and `start_time`) longer than 24 hours."
  (adsets). Currency table: "Korean Won | KRW | 1"; "If a currency has an offset of `1`, then the
  minimum bid equals one base currency unit" (currencies); ad set node: "cents for currencies like
  USD, EUR, and the basic unit for currencies like JPY, KRW" (adsets `bid_amount`). So the KRW
  value is sent unchanged (₩10,000 → `10000`). Non-positive, fractional, boolean or string
  budgets are refused before sending.
- `billing_event`: "IMPRESSIONS: Pay when the ads are shown to people." (adsets)
- `optimization_goal`: ODAX mapping row "`LINK_CLICKS` | `OUTCOME_TRAFFIC` | — | `LINK_CLICKS`"
  (campaign node, `#odax-mapping`); ODAX table "Traffic … Website … API enum {`LANDING_PAGE_VIEWS`,
  `LINK_CLICKS`, `IMPRESSIONS`, `REACH`}" (adset node).
- `targeting`: "An ad set's targeting structure. "countries" is required." (adsets) — the adapter
  refuses a targeting object without `geo_locations.countries`.
- `status`: "Only `ACTIVE` and `PAUSED` are valid for creation." (adsets)
- `bid_strategy`: "`LOWEST_COST_WITHOUT_CAP`: Designed to get the most results for your budget …
  This strategy is also known as *automatic bidding*" (adsets); campaign node notes "If you do not
  enable campaign budget optimization, you should get bid_strategy at the ad set level." With
  this strategy no `bid_amount` is needed ("`bid_amount` is required if `bid_strategy` is set to
  `LOWEST_COST_WITH_BID_CAP` or `COST_CAP`").
- `destination_type`: enum includes `WEBSITE`; "Destination of ads in this Ad Set. Options
  include: Website, App, Messenger…" (adsets).
- `promoted_object`: not sent. "**LINK_CLICKS** • `application_id` and `object_store_url` for
  mobile app or Canvas app engagement link clicks" (adsets) — only app traffic needs it.

### image — `POST act_{id}/adimages`

```text
bytes=<base64 of the approved PNG>
```

- `bytes`: "Image file. Example: `bytes = <image content in bytes format>`" — *Base64 UTF-8
  string* (adimages).
- Response: "Map {string: Map {string: Struct {hash: string, url: string, …}}}" i.e.
  `{"images": {"<name>": {"hash": …}}}`; the single `hash` is returned (adimages).
- Size: creatives "Not to exceed 8MB in size" (adcreatives `image_file`); the adapter refuses
  files over 8,000,000 bytes before sending.

### video — `POST act_{id}/advideos`, then `GET {video_id}?fields=status`

```text
multipart: source=@<file>.mp4 (video/mp4), name=<operation_key>
```

- `source`: "The video, encoded as form data." (advideos); `name`: "The name of the video in the
  library." (advideos). Return type contains `id` / `video_id` (advideos); the adapter accepts
  either.
- Video ads guide: "a video uploaded to either the `act_{ad-account-id}/advideos` endpoint" can be
  used in `video_data.video_id`.
- Processing: `video_status` "Status of a video, either "ready" (uploaded, encoded, thumbnails
  extracted), "processing" (not ready yet) or "error" (processing failed)." (video status). The
  FB video ads guide reads it with `GET /<VIDEO_ID>?fields=status` and lists
  `ready, processing, expired, error`.
- Bounded wait: up to `max_polls` (default 60) GETs, `poll_interval` (default 5 s) apart.
  `ready` → return id; `error`/`expired` → `E_API_REMOTE`; still processing → `E_API_INCOMPLETE`
  with the video id in the detail. These are raised after the upload succeeded, so they are plain
  `AdLoomError` (journal UNKNOWN; the video exists remotely and is never re-uploaded).
- Size: the adapter refuses files over 100 MiB for this single-request upload (self-imposed; see
  open question 4).

### creative — `POST act_{id}/adcreatives`

```text
name=<operation_key>
object_story_spec={"page_id":<page>,"video_data":{"video_id":…,"image_hash":…,"message":<primary_text>,
  "title":<headline>,"call_to_action":{"type":"LEARN_MORE","value":{"link":<destination_url>}}}}
```

- `name`: "Name of this ad creative as seen in the ad account's library." (adcreatives)
- `object_story_spec`: "The Page ID and the content to create a new unpublished page post.
  Specify `link_data`, `photo_data`, `video_data`, `text_data` or `template_data`" (adcreatives).
- `video_data.video_id`: "ID of video that user has permission to or a video in ad account video
  library" (video_data).
- `video_data.image_hash`: "Hash of an image in your image library with Facebook to use as
  thumbnail" (video_data).
- `video_data.message`: "The main body of the video post." (video_data)
- `video_data.title`: "The title of the video. This cannot be used with `LIKE_PAGE` call to
  action." (video_data)
- `video_data.call_to_action`: "An optional call to action." (video_data); `type` enum includes
  `LEARN_MORE`, `value` is "JSON containing the call to action data" (call_to_action). Shape
  `{"type":"LEARN_MORE","value":{"link":"https://…"}}` matches the Reels guide sample
  (https://developers.facebook.com/documentation/ads-commerce/marketing-api/creative/reels-ads).
- `page_id` is always the configured Page; a payload with a different `page_id` is refused.
- `destination_url is None` → refused with `PublishNotSent(E_INPUT_INVALID)` before sending
  (open question 2). Only `ALLOWED_CTAS` (`LEARN_MORE`) and http(s) links are accepted.

### ad — `POST act_{id}/ads`

```text
name=<operation_key>  adset_id=<id>  creative={"creative_id":"<id>"}  status=PAUSED
```

- `name`: "Name of the ad. **[required]**" (ads).
- `adset_id`: "The ID of the ad set, required on creation." (ads)
- `creative`: "You may supply the ID within an object as follows: `{"creative_id": <CREATIVE_ID>}`"
  (ads).
- `status`: "During testing, it is recommended to set ads to a `PAUSED` status so as to not incur
  accidental spend." (ads)

### read — `GET {id}?fields=a,b`

Reconcile only; numeric id and `[a-z_][a-z0-9_]*` field names are enforced; never mutates.

## Guards (all before any request → `PublishNotSent(E_INPUT_INVALID)`)

- `account_id` must match `act_\d+`, `page_id` numeric, `graph_version` `v\d+.\d+` (constructor
  raises `AdLoomError`).
- campaign/adset/ad `status` must be exactly `PAUSED`; the string `ACTIVE` anywhere in any payload
  (keys or values, nested) is refused; unknown payload keys are refused.
- image/video: `path` must resolve (symlinks followed) to a regular file inside `job_dir`; the
  bytes read once are SHA-256-checked against the payload and those same bytes are sent.

## Error mapping

Graph error body: `{"error": {"message", "type", "code", "error_subcode", "fbtrace_id"}}` (errors
(Graph)). Only `code`, `error_subcode` and a `[A-Za-z_]` `type` token reach error details; the
message is dropped because it can echo request data.

| Graph code | ErrorCode | Create outcome |
| --- | --- | --- |
| 190, 102, 104, 10, 200–299 | `E_API_AUTH` | `PublishNotSent` if HTTP 4xx |
| 4, 17, 32, 613, 80000–80014 | `E_API_RATE` (retryable) | `PublishNotSent` if HTTP 4xx |
| anything else (incl. 100, 1, 2, 368), unparseable bodies, 5xx | `E_API_REMOTE` | `AdLoomError` → journal UNKNOWN |

- Doc support: "190 Invalid OAuth 2.0 Access Token", "102 Session key invalid", "10 Application
  does not have permission for this action", "200 Permission error" (errors (Marketing));
  "200-299 API Permission … Permission is either not granted or has been removed" (errors
  (Graph)); "4 Application request limit reached", "17 User request limit reached" (errors
  (Marketing)); "613 … There have been too many calls from this ad-account"; "80000, 80003,
  80004, 80014 … There have been too many calls from this ad-account. Wait a bit and try again"
  (rate limiting); 4/17: "Temporary issue due to throttling. Wait and retry the operation"
  (errors (Graph)).
- `PublishNotSent` for auth/rate is an **[INFERENCE]**: the docs say to retry rate limits and
  re-authenticate, which implies the call was rejected, but they never state in words that no
  object was created. Validation errors (code 100, e.g. "The budget for your Ad-Set is too low",
  1487901) almost certainly create nothing, but no doc says so, so they stay UNKNOWN and need
  reconcile or `abandon`.
- Transport: `ConnectError`/`ConnectTimeout`/`PoolTimeout` → `PublishNotSent(E_API_NETWORK)`
  (nothing left the process). Read/write timeouts, read errors and protocol errors after sending →
  `AdLoomError(E_PUBLISH_PARTIAL)`. A 2xx with malformed JSON, no id/hash or an oversized body →
  `E_PUBLISH_PARTIAL`.
- `read()` and video polling use the same codes but never raise `PublishNotSent`.

## Open questions (resolve with the first real account, H3)

1. **Bearer header.** Marketing docs show `access_token=` in forms and `Authorization: OAuth
   {access-token}` for rupload; `Bearer` is the contract's choice and is documented for other
   graph.facebook.com products (WhatsApp Cloud API) but not on the Marketing pages read. If Graph
   rejects it with 190, switch the scheme to `OAuth` (same header, no URL token).
2. **Page-only CTA.** `video_data.call_to_action` is "optional" and `LIKE_PAGE` is only described
   for PAGE_LIKES campaigns; nothing documents a link-less CTA for an `OUTCOME_TRAFFIC` /
   `LINK_CLICKS` video ad. The adapter therefore refuses `destination_url=None` before sending;
   the plan should require a URL for traffic objectives.
3. **Required ad set fields for OUTCOME_TRAFFIC / LINK_CLICKS.** The ODAX mapping row has
   destination type "—"; the adapter sends `destination_type=WEBSITE` and
   `bid_strategy=LOWEST_COST_WITHOUT_CAP` explicitly. Unverified: whether Graph v26.0 rejects
   `daily_budget` on an ad set with no `end_time` (doc: "allowed only for ad sets with a duration …
   longer than 24 hours") and the KRW minimum daily budget (error 1487901 "budget … too low").
   `is_adset_budget_sharing_enabled=false` is taken from the create examples; confirm it is
   accepted as `false` (examples use `0`).
4. **Video upload path and limits.** `advideos` documents `source` plus a chunked
   (`upload_phase`/`start_offset`) protocol, and the newer FB Video Ads guide uses a resumable
   `video_ads` + rupload flow ("Up to 10 GB recommended"). No single-request size cap was found;
   100 MiB is a local cap. Also unconfirmed: whether a video from `advideos` must reach
   `video_status=ready` before `adcreatives` accepts it (the adapter waits, bounded, to be safe).
5. **KRW offset** is documented as 1 (above). The adapter does not convert currencies, so confirm
   the ad account currency is KRW (Ads Manager, or `GET act_<id>?fields=currency`; `read()` only
   accepts numeric node ids) before the first publish.
