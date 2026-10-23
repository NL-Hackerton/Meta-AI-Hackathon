# AdLoom 구현 명세서 (SDD, 에이전트 루프용)

작성: 2026-10-23 · 김유빈 · 상태: 초안 v0.1 (사람 검토 전)

## 1. 목적·범위·불변 제약

이 문서는 AdLoom(소상공인 영상 1개 → Meta 광고 일시중지 상태로 생성)을 에이전트 루프가 구현할 때 따르는 단일 기준입니다. 기획 배경은 [Meta 해커톤 기획안](https://claude.ai/artifact/YUUTopMr9zqxzNMs7h68zs)에 있고, 이 문서는 "무엇을 만들면 완료인가"만 정합니다. 문서와 코드가 다르면 문서가 맞고, 문서를 고쳐야 하면 에이전트는 코드를 고치지 않고 `SPEC_CHANGES.md`에 제안만 남깁니다.

**완료 정의:** 입력 영상 1개와 한 줄 설명으로 3개 비율 영상, 카피, 정책 점검 결과가 만들어지고, 사람이 승인하면 테스트 광고 계정에 PAUSED 광고가 생성된다. 제출 마감은 2026-11-05 11:00 KST.

**범위(MVP):**

- 파이프라인 6단계: 입력 → 이해 → 추적 → 보강 → 조립 → 승인·게시
- 비율 3종(9:16, 4:5, 1:1) × 훅 2종(A/B)
- CLI로 끝까지 실행 가능하고, 웹 화면은 승인·미리보기만 담당

**비목표:** 광고 자동 활성화, 결제, 다중 계정·팀, 성과 분석, 영상 생성, 모바일 앱.

**불변 제약 (어기면 실패로 간주, 테스트로 강제):**

| ID | 제약 | 강제 방법 |
| --- | --- | --- |
| INV-1 | 출력 영상의 모든 프레임은 입력 영상, 사용자 사진, Muse Image 이미지 중 하나에서만 온다. 영상 생성 모델 사용 금지 | 렌더 입력 목록에 허용 소스 타입만 받는 타입 검사 |
| INV-2 | Marketing API로 만드는 캠페인·광고 세트·광고의 `status`는 항상 `PAUSED`. `ACTIVE`로 보내는 코드 경로 없음 | 게시 모듈의 요청 본문 검증 + 소스 전체 grep 테스트 |
| INV-3 | 사람 승인 기록(`approval.json`) 없이는 게시 함수가 실행되지 않는다 | 승인 없으면 예외 발생하는 단위 테스트 |
| INV-4 | Muse Spark는 Standard 모델 ID(`muse-spark-1.3`)만 쓴다. `-contributor` ID 금지 | 설정 검증 테스트 |
| INV-5 | 렌더 단계는 결정론적이다. 같은 입력과 설정이면 같은 프레임 해시 | 프레임 해시 비교 테스트 |
| INV-6 | API 키·토큰은 환경변수로만 읽는다. 코드·로그·fixture·커밋에 값이 없다 | 비밀 패턴 스캔 테스트 |
| INV-7 | 외부 호출은 어댑터를 거치고, 기본은 mock. 실호출은 `ADLOOM_LIVE=1`일 때만 | 어댑터 팩토리 테스트 |
| INV-8 | 고객 영상은 `data/` 안에만 저장하고, Meta API 호출 외에는 밖으로 보내지 않는다 | 네트워크 호출 허용 호스트 목록 테스트 |

## 2. 아키텍처와 스택

파이프라인은 사람이 보지 않아도 테스트로 검증되도록 라이브러리와 CLI를 먼저 만들고, 웹 화면은 마지막에 얹습니다. 아래 스택은 제안 결정이며 사람이 바꾸면 이 표만 고칩니다.

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| 언어 | Python 3.11+ | Meta API·ffmpeg 연동과 테스트가 가장 빠름 |
| 모델·검증 | pydantic v2 | 모든 모듈 경계를 스키마로 고정 |
| HTTP | httpx | 동기·비동기 모두 지원, 모킹 쉬움 |
| 렌더 | 시스템 `ffmpeg` / `ffprobe` | 결정론적 옵션 고정 가능 |
| 테스트·품질 | pytest, ruff, mypy(strict) | `make check` 한 줄로 루프 판정 |
| 저장 | 로컬 파일(`data/jobs/<job_id>/`) + `job.json` | DB 없이 상태 재현 가능 |
| 웹 | FastAPI + 단일 HTML 페이지 (T14에서만) | 승인·미리보기 전용 |

**설정(환경변수) — 코드에 값을 쓰지 않는다 (INV-6):**

| 변수 | 용도 | 기본값 |
| --- | --- | --- |
| `ADLOOM_LIVE` | `1`이면 실제 외부 호출 허용 | `0` (mock) |
| `MODEL_API_KEY` | Meta Model API Bearer 토큰 | 없음 |
| `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID` | Marketing API 호출 | 없음 |
| `META_GRAPH_VERSION` | Marketing API 버전 | 없음 (LIVE일 때 필수, 값은 사람이 지정) |
| `ADLOOM_DATA_DIR` | 작업 저장 위치 | `./data` |

**저장소 구조:**

```text
adloom/
  SPEC.md  TASKS.md  STATUS.md  SPEC_CHANGES.md  AGENTS.md
  src/adloom/
    config.py            # 환경변수 로드, LIVE 게이트
    schemas.py           # 모든 pydantic 모델 (§4 계약의 유일한 원천)
    jobs.py              # Job 저장·상태 머신 (§3)
    adapters/
      base.py            # Protocol 4개 + MarketingPublisher
      spark.py  sam.py  image.py  voice.py  marketing.py   # 각각 Mock + Live
    stages/
      understand.py  track.py  enrich.py  assemble.py  publish.py
    crop.py              # 순수 함수: bbox 시퀀스 → 크롭 계획
    policy.py            # 규칙 기반 정책 점검
    render.py            # ffmpeg 명령 조립·실행
    cli.py               # python -m adloom run / approve / publish
    web/                 # T14
  tests/
    fixtures/            # 작은 샘플 영상, 녹화된 응답 JSON
    unit/  integration/  live/   # live는 ADLOOM_LIVE=1에서만
Makefile                 # make check = ruff + mypy + pytest(live 제외)
```

## 3. 작업(Job) 상태 머신

**상태 목록 (8개 + 실패):** `CREATED` → `UNDERSTOOD` → `TRACKED` → `ENRICHED` → `RENDERED` → `AWAITING_APPROVAL` → `APPROVED` → `PUBLISHED_PAUSED`, 그리고 어느 상태에서든 갈 수 있는 `FAILED`.

| 전이 | 트리거 | 해당 단계가 남기는 산출물 |
| --- | --- | --- |
| (시작) → `CREATED` | `adloom run` 입력 검증 통과 | `job.json`, `brief.json` |
| `CREATED` → `UNDERSTOOD` | 이해 단계 성공 | `understanding.json`, 정책 점검 결과 |
| `UNDERSTOOD` → `TRACKED` | 추적 단계 성공 (coverage 낮으면 `degraded=true`로도 성공) | `track.json`, 비율별 `crop_plan.json` |
| `TRACKED` → `ENRICHED` | 보강 단계 성공 (Image 실패는 대체물 + `warnings`) | 썸네일·엔드카드 PNG, `transcript.json` |
| `ENRICHED` → `RENDERED` | 조립 단계 성공 | 변형 6개 mp4, `frame_hash` 목록 |
| `RENDERED` → `AWAITING_APPROVAL` | 렌더 직후 자동 | 승인 화면용 요약 (`degraded`, 정책 플래그 포함) |
| `AWAITING_APPROVAL` → `APPROVED` | 사람이 승인 (`adloom approve` 또는 웹 버튼) | `approval.json` |
| `APPROVED` → `PUBLISHED_PAUSED` | 게시 단계 성공, 생성된 모든 ID(영상·소재·캠페인·광고 세트·광고)를 기록 | `publish.json` (모든 `status=PAUSED`) |
| `AWAITING_APPROVAL` 또는 `APPROVED` → `RENDERED` | 사람이 수정 요청 | `approval.json` 무효화(삭제/보관), 조립 단계만 재실행 |
| 임의 상태 → `FAILED` | 단계 실패 | `failed_stage`, `AdLoomError` 상세, 같은 단계부터 재실행 |

위 표에 없는 전이는 모두 금지입니다.

전이마다 직전 상태가 만든 산출물이 `job.json`과 파일로 남아 있어야 다음 상태로 넘어가고, 어느 단계에서든 실패하면 `FAILED`와 `failed_stage`를 기록한 뒤 같은 단계부터 재실행합니다. 게시 함수는 `APPROVED`가 아니면 실행되지 않으며(INV-3), 사람이 수정을 요청하면 승인 기록은 무효가 되고 조립 단계만 다시 돕니다. 허용되지 않은 전이는 `jobs.py`가 예외로 거부하고 그 전이 표 전체가 T02의 테스트입니다.

## 4. 모듈 계약

모든 모델은 `schemas.py`의 pydantic v2 모델이며 `extra="forbid"`입니다. 시간은 초(float), 좌표는 원본 영상 픽셀입니다. 수치 한도는 `config.py`의 상수로 두고 아래 표에 기본값을 적습니다. **"[미확인]"이 붙은 값은 Meta 공식 문서로 확인하기 전까지 잠정값이며, 확인되면 코드가 아니라 설정만 바꿉니다.**

### 4.1 입력 `Brief`

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| `video_path` | str | mp4 또는 mov. 길이 3~45초 (`MAX_INPUT_SEC=45`). 벗어나면 `E_INPUT_INVALID` |
| `note_text` | str \| None | 사장님 한 줄 설명, 200자 이하 |
| `note_audio_path` | str \| None | `note_text`가 없으면 필수. 있으면 Voice 어댑터로 전사해 `note_text`를 채움 |
| `region` | str | 예: "남양주". MVP에서는 기록만 하고 타기팅은 국가(KR) 단위 |
| `daily_budget_krw` | int | 0보다 큼 |
| `language` | "ko" \| "en" | 기본 "ko" |
| `destination_url` | str \| None | 광고 클릭 시 이동할 주소(예약 페이지·웹사이트). LIVE 게시에서는 필수, mock에서는 생략 가능. 링크가 필요한 CTA 유형인지는 [미확인] |

### 4.2 이해 단계 출력 `Understanding` (Muse Spark, 구조화 출력)

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| `product_name` | str | 1~40자 |
| `sam_prompt` | str | 영어 명사구 6단어 이하. SAM 3.1 텍스트 프롬프트로 그대로 사용 |
| `key_moments` | list[Moment] | 1~5개. `Moment{t_start,t_end,reason}`, 영상 길이 안, 서로 겹치지 않음 |
| `hook_candidates` | list[Hook] | 정확히 3개. `Hook{id,text}`, `text` 22자 이하(`MAX_HOOK_CHARS`). 렌더는 앞 2개를 A/B로 사용 |
| `primary_text` | str | 125자 이하 [미확인: Meta 표시 한도] |
| `headline` | str | 40자 이하 [미확인] |
| `cta` | enum | Marketing API가 허용하는 값만. 목록은 설정에 두고 [미확인] |
| `policy_flags` | list[Flag] | `Flag{field,original,rule_id,severity,rewrite}`, `severity`는 "warn" 또는 "block" |

검증 실패(JSON 불일치, 한도 초과)는 1회에 한해 "오류 내용을 포함한 재요청"으로 복구하고, 그래도 실패하면 `E_API_SCHEMA`입니다. 모델이 돌려준 문구는 `policy.py`가 항상 재검사하며, 모델 판단만 믿지 않습니다.

### 4.3 추적 `TrackResult`과 크롭 계획 `CropPlan`

`TrackResult`는 SAM 어댑터의 출력입니다: `source_width`, `source_height`, `fps`, `frame_count`, `boxes`(길이가 `frame_count`인 리스트, 각 원소는 `BBox{x,y,w,h,score}` 또는 null), `coverage`(박스가 있는 프레임 비율).

`coverage`가 0.6 미만이면 실패시키지 않고 **중앙 크롭으로 대체하며 `degraded=true`를 기록**합니다. 승인 화면은 이 표시를 반드시 보여 줍니다. 박스가 없는 프레임은 앞뒤 박스를 선형 보간합니다.

`crop.py`는 입출력이 없는 순수 함수 `plan_crops(track, aspect) -> CropPlan`입니다.

| 규칙 | 값 |
| --- | --- |
| 출력 크기 | 9:16은 1080×1920, 4:5는 1080×1350, 1:1은 1080×1080 |
| 크롭 크기 | 원본 안에 들어가는 해당 비율의 최대 직사각형. 프레임 내내 같은 크기, 위치만 이동 |
| 위치 | 제품 박스 중심을 지수 평활(`alpha=0.15`)로 따라가고 프레임당 이동 상한(`MAX_STEP_PX`) 적용 |
| 여백 | 박스가 크롭 안에 들어가고 크롭 폭의 6% 이상 여유(`BBOX_MARGIN=0.06`). 박스가 크롭보다 크면 박스 중심에 맞추고 `clipped=true` |
| 안전 영역 | 9:16 위 14%, 아래 22%는 글자·핵심 피사체 금지(`SAFE_TOP`, `SAFE_BOTTOM`) [미확인: Meta 배치별 공식 안전 영역으로 교체] |
| 경계 | 크롭은 항상 원본 프레임 안 (바깥으로 나가면 안쪽으로 밀어 넣음) |

### 4.4 보강 `EnrichResult`

- `thumbnail_path`: 비율별 PNG. Muse Image가 만든 장면 이미지를 쓰되 **Muse Image에는 글자를 그리라고 요청하지 않습니다.** 모든 글자는 코드(PIL 또는 ffmpeg)가 그립니다. 이미지 모델의 한글 글자 품질을 믿을 수 없기 때문입니다.
- `endcard_paths`: 비율별 PNG. 배경은 Muse Image 또는 단색, CTA 문구는 코드가 그림.
- `transcript`: `Segment{t_start,t_end,text}` 리스트. 영상 속 말이 없으면 빈 리스트이며 자막은 만들지 않습니다.
- Muse Image 호출이 실패해도 파이프라인은 멈추지 않습니다. 원본 영상의 대표 프레임과 단색 엔드카드로 대체하고 `warnings`에 기록합니다.

### 4.5 조립 `RenderedVariant`

입력은 `Understanding`, `CropPlan`(비율별), `EnrichResult`, 원본 영상입니다. 출력은 비율 3종 × 훅 2종 = 6개의 `RenderedVariant{aspect, hook_id, path, duration_sec, frame_hash}`입니다.

| 규칙 | 값 |
| --- | --- |
| 타임라인 | `key_moments`를 시간순으로 이어 붙임. 합계가 `MAX_AD_SEC=30`을 넘으면 뒤쪽 순서부터 잘라냄 [미확인: Meta 길이 제한] |
| 짧을 때 | 합계가 6초 미만이면 원본 앞부분으로 채우되 INV-1을 지키는 소스만 사용 |
| 정지 이미지 | 줌 1.0→1.08 느린 확대만 허용 (움직임 생성 금지) |
| 오버레이 | 훅 문구는 0~3초, 자막은 `transcript` 시간대, 엔드카드는 마지막 2초. 글자는 안전 영역 안 |
| 인코딩 | H.264 yuv420p, AAC 128k 44.1kHz 스테레오, fps는 원본과 30 중 작은 값, `-threads 1`, `-bitexact` 계열 플래그 |
| 오디오 | 원본 오디오 유지. 없으면 무음 트랙 |
| 폰트 | 저장소에 포함한 폰트 1종 (라이선스 확인 필요) |

`frame_hash`는 출력 영상 프레임을 디코드해 계산한 해시이며 INV-5 테스트의 비교 대상입니다(파일 바이트가 아니라 프레임 기준).

### 4.6 게시 `PublishResult`

MVP는 **9:16 영상으로 훅 A·B 광고 2개**를 만듭니다(`PRIMARY_ASPECT`). 나머지 비율은 파일로만 제공하며, 배치별 소재 지정은 MVP 이후 과제입니다. 입력은 승인 기록, 대표 `RenderedVariant` 2개, `Understanding`, 대표 썸네일, `Brief.destination_url`(LIVE에서 필수)입니다.

순서(모든 `status`는 `PAUSED`, INV-2):

1. 영상 업로드 `POST act_{id}/advideos` → `video_id`
2. 썸네일 준비 — 가이드는 `image_url`을 요구하므로 업로드 방식은 [미확인] (공개 URL 또는 이미지 업로드 후 참조)
3. 소재 `POST act_{id}/adcreatives` — `page_id`, `video_data`(`video_id`, 썸네일), 본문(`primary_text`), 제목(`headline`), CTA
4. 캠페인 `POST act_{id}/campaigns` — `name`, `objective`, `status=PAUSED`, `special_ad_categories=[]`
5. 광고 세트 `POST act_{id}/adsets` — `campaign_id`, `daily_budget`, 목적 최적화 값, 타기팅 국가 KR, `status=PAUSED`
6. 광고 `POST act_{id}/ads` — `adset_id`, `creative`, `status=PAUSED`

`objective`, 최적화 목표, 과금 이벤트, 예산 단위(KRW 최소 단위), 시작·종료 시각은 가이드 예시와 본문이 서로 달라 **[미확인]**입니다. 전부 `config.py` 상수로 두고, 확정 전에는 mock이 기대하는 값과 라이브 호출을 분리합니다. 이름에는 `job_id`를 넣고, 각 단계에서 만들어진 ID는 즉시 `job.json`에 기록해 재실행이 이어서 진행되게 합니다(멱등).

### 4.7 오류 규칙

`AdLoomError(code, stage, retryable, detail)` 하나만 던집니다.

| 코드 | 의미 | 처리 |
| --- | --- | --- |
| `E_INPUT_INVALID` | 입력 길이·형식 위반 | 즉시 실패, 사람에게 메시지 |
| `E_API_AUTH` | 키·토큰 오류 | 재시도 없음, 사람 개입 |
| `E_API_RATE` | 호출 한도 | 지수 백오프 3회 후 실패 |
| `E_API_SCHEMA` | 모델 출력이 스키마 불일치 | 오류 내용 포함 재요청 1회 후 실패 |
| `E_TRACK_LOW_COVERAGE` | 추적 coverage 낮음 | 실패가 아니라 `degraded=true`로 중앙 크롭 |
| `E_POLICY_BLOCK` | `severity=block` 문구 남음 | 승인 불가, 문구 수정 후 재검사 |
| `E_RENDER_FAILED` | ffmpeg 실패 | 로그 저장, 1회 재시도 |
| `E_PUBLISH_PARTIAL` | 게시 중간 실패 | 만들어진 ID 기록, 재실행으로 이어서 진행 (PAUSED이므로 롤백 불필요) |
| `E_APPROVAL_REQUIRED` | 승인 기록 없이 게시 시도 (INV-3) | 어댑터 호출 전에 즉시 거부, 재시도 없음 |

## 5. 외부 API 어댑터와 mock

모든 외부 호출은 아래 5개 인터페이스 뒤에 있습니다(INV-7). 팩토리 `get_adapters(config)`는 `ADLOOM_LIVE=1`이고 필요한 키가 모두 있을 때만 Live 구현을 돌려주고, 아니면 Mock을 돌려줍니다. LIVE인데 키가 없으면 조용히 mock으로 떨어지지 않고 `E_API_AUTH`를 던집니다.

```python
class UnderstandingAdapter(Protocol):
    def understand(self, video: Path, note_text: str, language: str) -> Understanding: ...
class TrackingAdapter(Protocol):
    def track(self, video: Path, prompt: str) -> TrackResult: ...
class ImageAdapter(Protocol):
    def generate_scene(self, prompt: str, size: tuple[int, int]) -> Path: ...
class VoiceAdapter(Protocol):
    def transcribe(self, media: Path, language: str) -> list[Segment]: ...
class MarketingPublisher(Protocol):
    def publish(self, plan: PublishPlan) -> PublishResult: ...
```

| 어댑터 | Mock 동작 | Live 대상 (공식 문서 기준) | 구현 전에 확인할 것 |
| --- | --- | --- | --- |
| Understanding | 영상 파일 SHA-256으로 `tests/fixtures/understanding/<sha>.json`을 찾아 반환 | `POST /v1/responses`, 모델 `muse-spark-1.3` | 영상 입력 방식(파일 업로드 vs 인라인), 구조화 출력 요청 형식, 길이·용량 한도 |
| Tracking | 영상 크기·프레임 수에서 계산한 합성 박스 경로(완만한 곡선)를 반환. 일부 프레임은 일부러 null | `POST /v1/files` 후 `POST /v1/responses`, 모델 `sam-3.1` | 영상 추적 요청 형식(Media segmentation 가이드), 마스크 → 박스 변환 필요 여부 |
| Image | 고정 시드로 만든 단색·그라디언트 PNG를 반환 | `POST /v1/images/generations`, `/v1/images/edits`, 모델 `muse-image-1.0` | 지원 크기, 응답이 URL인지 base64인지 |
| Voice | `tests/fixtures/voice/<sha>.json` 반환 | `POST /v1/asr/transcribe`, 모델 `muse-voice-transcribe-1.0` | 한국어 지원, 입력 파일 형식, 타임스탬프 단위 |
| Marketing | 요청을 메모리에 기록하고 **모든 요청에서 INV-2를 검사**, 가짜 ID를 순서대로 반환 | Graph API `act_{id}/advideos` 외 5개 엔드포인트 (§4.6) | Graph 버전, 권한 범위, 썸네일 방식, objective·최적화 값 |

공통 사실: Model API의 기본 URL은 `https://api.meta.ai/v1`, 인증은 `MODEL_API_KEY` Bearer 토큰입니다([개요 문서](https://dev.meta.ai/docs/overview)). 요청·응답 본문의 세부 형식은 이 문서가 확정하지 않았습니다.

**Live 어댑터 작성 규칙:**

- 해당 태스크(T10~T13)를 시작하기 전에 공식 문서의 해당 페이지를 읽고, 근거가 된 요청·응답 예시를 `docs/api_notes/<adapter>.md`에 발췌해 남긴다. 문서에 없는 필드는 추측해서 쓰지 않고 §9 미확정 사항에 추가한다.
- Live 응답은 키·토큰·개인정보를 제거한 뒤 `tests/fixtures/`에 녹화하고, Mock과 Live가 같은 `schemas.py` 모델로 파싱되는지 테스트한다.
- Live 테스트(`tests/live/`)는 `ADLOOM_LIVE=1`이고 사람이 해당 태스크를 `LIVE-OK`로 표시했을 때만 실행한다.

## 6. 수용 기준

각 기준은 자동 테스트 하나 이상으로 구현하며, 태스크(§8)는 자신이 담당하는 AC가 모두 통과해야 완료입니다. 모든 테스트는 기본적으로 mock에서 돌아갑니다.

| ID | Given | When | Then |
| --- | --- | --- | --- |
| AC-01 | 60초짜리 영상 | Brief 검증 | `E_INPUT_INVALID` (한도 `MAX_INPUT_SEC=45`) |
| AC-02 | `note_audio_path`만 있는 Brief | 입력 단계 | Voice 어댑터로 전사해 `note_text`를 채움 |
| AC-03 | Mock Spark fixture | `understand` | 훅 후보 3개, 각 22자 이하, `cta`가 허용 목록 안 |
| AC-04 | 첫 응답이 훅 4개를 돌려주는 Spark | `understand` | 오류 내용을 담아 1회만 재요청해 성공. 2회 연속 실패면 `E_API_SCHEMA` |
| AC-05 | `primary_text`에 "100% 보장" 포함 | `policy.check` | `severity=block` 플래그와 `rewrite` 생성. 순화본을 재검사하면 block 0건 |
| AC-06 | 1920×1080 영상의 합성 박스 경로 | `plan_crops(…, "9:16")` | 모든 프레임에서 크롭이 원본 안, 박스가 크롭 안(여백 6% 이상), 프레임 간 이동량이 `MAX_STEP_PX` 이하 |
| AC-07 | 세 비율 각각 | `plan_crops` | 크롭 비율이 목표 비율과 1px 이내로 일치하고 프레임 내내 크기가 같음 |
| AC-08 | `coverage=0.4`인 TrackResult | 추적 단계 | 예외 없이 `degraded=true`, 중앙 크롭 계획 |
| AC-09 | 중간 프레임이 null인 박스열 | 보간 | 앞뒤 박스의 선형 보간으로 채워짐, 맨 앞·맨 뒤 null은 가장 가까운 박스로 채움 |
| AC-10 | 예외를 던지는 Image 어댑터 | 보강 단계 | 파이프라인이 계속되고 대표 프레임·단색 엔드카드로 대체, `warnings`에 기록 |
| AC-11 | 합성 입력 | 조립 단계 | 6개 파일, 해상도 정확(1080×1920 · 1080×1350 · 1080×1080), `ffprobe`로 h264·yuv420p·aac, 길이 `MAX_AD_SEC` 이하 |
| AC-12 | 같은 입력과 설정으로 두 번 | 조립 단계 | 6개 모두 `frame_hash` 동일 (INV-5) |
| AC-13 | 훅 A의 렌더 계획 | 오버레이 검사 | 훅 문구가 0~3초에만 있고 모든 텍스트 박스가 안전 영역 안 |
| AC-14 | 허용 소스 외(예: 외부 URL 영상)를 넣은 RenderSpec | 검증 | 예외로 거부 (INV-1) |
| AC-15 | `approval.json`이 없는 job | `publish` | 어댑터를 한 번도 부르지 않고 `E_APPROVAL_REQUIRED` (INV-3) |
| AC-16 | Mock Marketing | `publish` 전체 | 기록된 요청 6종 모두 `status == "PAUSED"`. 소스 전체 grep에서 `"ACTIVE"` 0건(테스트 파일 제외) (INV-2) |
| AC-17 | 3번째 요청에서 실패하도록 만든 Mock | 실패 후 재실행 | 이미 만든 ID는 다시 만들지 않고 이어서 완료, 최종 ID 중복 없음 |
| AC-18 | 설정에 `muse-spark-1.3-contributor` | 설정 로드 | 거부 (INV-4) |
| AC-19 | 저장소 전체 | 비밀 패턴 스캔 | 키·토큰 형태 문자열 0건 (INV-6) |
| AC-20 | 샘플 영상, mock | `adloom run` → `approve` → `publish` | 상태가 `AWAITING_APPROVAL`을 거쳐 `PUBLISHED_PAUSED`, 변형 6개와 `job.json` 생성 |
| AC-21 | LIVE=1, 키 없음 | 어댑터 생성 | mock으로 조용히 떨어지지 않고 `E_API_AUTH` (INV-7) |

## 7. 에이전트 루프 규칙

루프는 매 반복마다 `AGENTS.md`(이 섹션의 요약본)를 먼저 읽고, 한 반복에서 태스크 하나만 끝냅니다. 작업 기억은 대화가 아니라 파일에 둡니다: `SPEC.md`(불변), `TASKS.md`(상태), `STATUS.md`(진행 로그), `SPEC_CHANGES.md`(스펙 변경 제안).

**한 반복의 절차:**

1. `SPEC.md` §1 불변 제약, `TASKS.md`, `STATUS.md`를 읽는다.
2. 상태가 `TODO`이고 선행이 모두 `DONE`인 첫 태스크를 고른다. 없으면 종료 보고를 쓴다.
3. 담당 AC를 읽고 **먼저 실패하는 테스트**를 쓴다. `make check`에서 새 테스트만 실패하는지 확인한다.
4. 태스크의 "파일" 범위 안에서 최소 구현을 한다.
5. `make check`(ruff + mypy strict + pytest, live 제외)와 INV 테스트 전체가 통과해야 한다.
6. `TASKS.md`를 `DONE`으로, `STATUS.md`에 한 줄(날짜 · 태스크 · 결과 · 남은 위험)을 쓰고 로컬 커밋한다.
7. 다음 반복으로 간다.

**중단 조건 (하나라도 해당하면 멈추고 사람에게 보고):**

- 같은 태스크에서 `make check`가 연속 3회 실패 → 태스크를 `BLOCKED`로 표시하고 시도한 것과 원인을 기록한 뒤, 선행 관계가 없는 다음 태스크로 간다.
- 사람 게이트(H1~H4) 태스크에 도달.
- 공식 문서가 이 스펙과 다르다고 확인됨 → 코드를 바꾸지 말고 `SPEC_CHANGES.md`에 근거(링크·발췌)와 제안을 남기고 `BLOCKED`.
- 모든 태스크가 `DONE` 또는 `BLOCKED`.

**금지 행동:**

- LIVE 태스크가 아닌 곳에서의 실제 외부 호출, 비밀값을 파일·로그·커밋·대화에 쓰기 (INV-6, INV-7)
- `git push`, 강제 덮어쓰기, `data/` 밖 파일 삭제
- `SPEC.md` 수정 (변경은 제안만)
- 테스트를 삭제·skip·완화해서 통과시키기
- 태스크에 명시되지 않은 의존성 추가 (필요하면 제안)
- 상태 `ACTIVE` 사용, 영상 생성 모델 호출 (INV-1, INV-2)

**사람 게이트:**

| 게이트 | 내용 | 막히는 태스크 |
| --- | --- | --- |
| H1 | Official Rules 확인(10/26 전 공개): 허용 모델, 기존 코드 사용, 제출 형식 | 제출 준비(T16) |
| H2 | API 키 발급 후 환경변수 설정, 한국에서 호출 가능한지 확인 | T10~T12의 live 검증 |
| H3 | 테스트 Meta 앱·광고 계정·페이지·토큰 준비 | T13의 live 검증, T15 |
| H4 | 데모 영상 촬영·제출 (사람이 직접) | T16 |

**STATUS.md 한 줄 예:** `2026-10-27 · T03 crop.py · DONE (AC-06,07,09) · 남은 위험: SAFE_TOP/BOTTOM 미확인`

**종료 보고에 반드시 넣을 것:** 완료된 AC 목록, `BLOCKED` 태스크와 이유, 아직 [미확인]인 설정값, 사람이 해야 할 다음 행동.

## 8. 태스크 분해

T00~T09는 외부 키 없이 mock만으로 끝납니다. 킥오프(10/26) 전에 루프를 돌릴 수 있는 부분이 여기까지입니다. 목표일은 지연 시 뒤 순서를 밀지 않고 버퍼로 쓰는 소프트 마감입니다. 상태는 모두 `TODO`에서 시작합니다.

| ID | 내용 | 선행 | 파일 | 담당 AC | 목표일 |
| --- | --- | --- | --- | --- | --- |
| T00 | 스캐폴드: pyproject, Makefile(`make check`), ruff·mypy·pytest 설정, `AGENTS.md`, ffmpeg로 1920×1080 10초 합성 샘플 영상(움직이는 도형) 생성 스크립트 | 없음 | `pyproject.toml`, `Makefile`, `tests/fixtures/make_sample.sh` | AC-19 스캔 테스트 골격 | 10/24 |
| T01 | `schemas.py`, `config.py`: 모델·상수, LIVE 게이트, Contributor ID 거부 | T00 | `schemas.py`, `config.py` | AC-01(스키마), AC-18, AC-21 | 10/24 |
| T02 | `jobs.py`: Job 저장, 상태 머신 전이 규칙(§3), `job.json` 원자적 쓰기 | T01 | `jobs.py` | §3 전이 테스트 | 10/24 |
| T03 | `crop.py` 순수 함수와 박스 보간 | T01 | `crop.py` | AC-06, 07, 09 | 10/24 |
| T04 | `policy.py` 규칙 기반 점검과 순화 (규칙 표는 `policy_rules.yaml`) | T01 | `policy.py`, `policy_rules.yaml` | AC-05 | 10/25 |
| T05 | 어댑터 Protocol 5개 + Mock 5종 + 팩토리 | T01 | `adapters/base.py`, `adapters/mock_*.py` | AC-21 | 10/25 |
| T06 | 스테이지: 입력·이해·추적·보강 | T02, T03, T04, T05 | `stages/` | AC-01, 02, 03, 04, 08, 10 | 10/25 |
| T07 | `render.py` + 조립 스테이지: ffmpeg 렌더, 훅·자막·엔드카드 오버레이, 폰트 | T03 | `render.py`, `stages/assemble.py` | AC-11, 12, 13, 14 | 10/25 |
| T08 | Marketing Mock과 게시 스테이지, 멱등성 | T02, T05 | `stages/publish.py` | AC-15, 16, 17 | 10/25 |
| T09 | `cli.py`와 파이프라인 오케스트레이터, mock E2E | T06, T07, T08 | `cli.py`, `pipeline.py` | AC-20 | 10/25 |
| T10 | Live Spark 어댑터 (**H2**) | T09 | `adapters/spark.py` | live 테스트, AC-03·04를 Live 응답 fixture로 재검증 | 10/27 |
| T11 | Live SAM 어댑터, 마스크 → 박스 변환 (**H2**) | T09 | `adapters/sam.py` | live 테스트, AC-06 재검증 | 10/28 |
| T12 | Live Image·Voice 어댑터 (**H2**) | T09 | `adapters/image.py`, `voice.py` | live 테스트, AC-10 | 10/29 |
| T13 | Live Marketing 어댑터 (**H3**) | T09 | `adapters/marketing.py` | live 테스트, AC-16·17 재검증 | 11/2 |
| T14 | 웹 승인 화면: 변형 6개 미리보기, `degraded`·정책 플래그 표시, 승인 버튼 → `approval.json` | T09 | `web/` | AC-15 (웹 경로) + 수동 확인 | 10/30 |
| T15 | 실영상 LIVE 리허설: 실제 점포 영상 1~2건 전 과정, 실패 기록 | T10~T13, T14 | `docs/rehearsal.md` | 완료 정의(§1) | 11/3 |
| T16 | 제출물: README, 데모 대본·촬영 체크리스트 (**H1, H4**) | T15 | `README.md`, `docs/demo.md` | — | 11/4 |

## 9. 미확정 사항

아래 값은 이 스펙에서 잠정값이거나 공식 문서를 아직 못 읽어 정하지 못한 것입니다. 에이전트는 이 값들을 `config.py` 상수로만 두고, 확인되면 상수만 바꾸며 그 근거를 `docs/api_notes/`에 남깁니다.

| 항목 | 잠정값 | 확인 위치 |
| --- | --- | --- |
| 입력 영상 최대 길이 | 45초 (임의 가정) | Spark 영상 입력 한도 문서, 실측 |
| 본문·제목 글자 수 | 125자 · 40자 | Meta 광고 소재 규격 문서 |
| CTA 허용 목록과 링크 필요 여부 | 미정 | Marketing API 소재 문서 |
| 안전 영역 (9:16) | 위 14%, 아래 22% | Meta 배치별 안전 영역 안내 |
| 광고 영상 최대 길이·용량·비율 | 30초 | Advertiser Help Center |
| 썸네일 제공 방식 | 미정 (`image_url` 요구, 업로드 방식 불명) | Graph API 이미지 업로드 문서 |
| `objective`, 최적화 목표, 과금 이벤트 | 가이드 예시가 서로 다름 | Marketing API 캠페인·광고 세트 문서 |
| KRW 예산 단위와 시작·종료 시각 | 미정 | 위 문서, 테스트 계정 실측 |
| Graph API 버전 | 없음 (환경변수로 지정) | Marketing API 변경 이력 |
| Spark 영상 입력 방식과 구조화 출력 형식 | 미정 | Model API quickstart·Responses 가이드 |
| SAM 3.1 영상 요청 형식과 마스크 형태 | 미정 | Media segmentation 가이드 |
| 한국에서 Model API 호출 가능 여부 | 미확인 | 키 발급 후 첫 호출 (H2) |
| 심사 제출 형식과 허용 모델·기존 코드 규정 | 미공개 | Official Rules (H1) |
| 폰트 라이선스 | 미정 | 폰트 라이선스 확인 |

**사람이 결정할 것:**

- [ ] 스택 확정 (Python + FastAPI 제안). 바꾸면 §2만 고친다.
- [ ] 데모에 쓸 업종과 실제 영상 (본인 소유 또는 동의 받은 것)
- [ ] 승인 후 목표(클릭 링크, 메시지, 전화) — `destination_url`의 의미를 정한다
- [ ] 루프를 돌릴 환경 (로컬 PC의 Claude Code 등)와 반복 횟수·비용 한도
- [ ] 키·토큰 발급 담당과 시점 (H2, H3)
