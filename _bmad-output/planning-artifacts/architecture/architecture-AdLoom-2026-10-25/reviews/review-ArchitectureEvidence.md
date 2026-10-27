# AdLoom 아키텍처 리뷰: 공식 근거와 실제 동작 대조

리뷰는 읽기 전용으로 진행했습니다. 파일을 고치지 않았고 테스트·린트·빌드·유료 API 호출도 하지 않았습니다. 확인 방법은 세 가지였습니다. 설치된 `.venv` 소스와 sdist 원문을 읽었고, `shasum`과 `ffmpeg -version` 같은 읽기 전용 명령을 실행했고, 공식 페이지 3곳(PyPI JSON, dev.meta.ai client-libraries, full-stack template의 `pyproject.toml`)을 읽었습니다.

## 문서 주장과 일치한 것

- **해시와 크기:** `third_party` 파일 4개의 SHA-256과 바이트 수가 `manifest.json`과 같습니다. sdist 해시는 `uv.lock`의 해시와도 같습니다. 설치된 wheel의 `meta_sam_parser/*.py` 8개 파일은 sdist 원문과 내용이 같습니다.
- **meta-sam-parser 버전:** PyPI에서 0.1.0이 최신이고 철회(yanked)되지 않았습니다. 라이선스는 SAM License(2025-11-19)이고, 루트 `__all__`이 공개 API입니다. 공식 문서도 "패키지 루트에서만 import하라"고 적고 있습니다.
- **좌표 변환:** 반열림(half-open) 변환은 `_segmentation.py`에서 `right=inclusive_right + 1`로 확인했습니다. 공식 문서도 "inclusive wire `x2`/`y2` become half-open"이라고 적습니다. 진단 코드(`ignored_field`, `ignored_token`, `ignored_confidence`)와 completed/incomplete 구분도 문서 설명과 같습니다.
- **Range 지원:** Starlette 1.10.0의 `FileResponse`에 Range 처리가 있습니다. 단일 범위는 206, 범위 밖 요청은 416, 범위 개수는 100개 상한입니다. 실제 206 응답은 실행해 보지 않았습니다.
- **런타임 환경:** `pyvenv.cfg`는 3.12.15, `uv`는 0.11.21, ffmpeg는 9.0.2입니다. FastAPI 0.162.0이 `opentelemetry-api`를 필수 의존성으로 요구한다는 기록도 맞습니다. `uv.lock`은 23항목(프로젝트 포함)이고 설치 패키지는 22개입니다.
- **template 제외 근거:** full-stack template의 `backend/pyproject.toml`이 `requires-python = ">=3.14,<4.0"`, `fastapi[standard]`, sqlmodel, psycopg, pyjwt를 요구합니다. 제외 근거가 맞습니다.
- **폰트 라이선스:** `OFL.txt`에 "Reserved Font Name 'Source'"가 실제로 있습니다.

## 주요 문제

### 1. [medium] httpx-sse 공개 API로는 "줄·이벤트별 2MiB, 누적하면서 중단" 상한을 지킬 수 없음
- **위치:** spine AD-10(`ARCHITECTURE-SPINE.md:109`), `codebase.md:131`, `:136`, `dependencies.md:29`
- **실제 동작:** `httpx_sse/_api.py`의 `aiter_sse()`는 내부에서 `response.aiter_text()`를 읽습니다. `_decoders.py`의 `SSELineDecoder.buffer`는 줄바꿈이 올 때까지 크기 제한 없이 쌓입니다. `SSEDecoder._data`도 빈 줄이 올 때까지 쌓입니다. 공개 export는 `EventSource`, `aconnect_sse`, `ServerSentEvent`, `SSEError` 네 가지뿐이고, 크기 상한 옵션이 없습니다.
- **충돌 예:** adapter 구현자가 문서대로 `aiter_sse()` 위에서 상한을 검사하면, 끝나지 않는 `data:` 줄이나 빈 줄이 없는 이벤트가 이미 메모리에 다 올라온 뒤에야 첫 검사가 가능합니다. 문서가 막겠다는 "누적 중 중단"이 성립하지 않습니다.
- **최소 수정:** AD-10과 `codebase.md` §7에 실제 경계를 명시합니다. 둘 중 하나를 고릅니다.
  - `response.aiter_bytes()` 단계에서 전체 바이트와 줄 길이를 세는 얇은 counting wrapper를 두고, httpx-sse는 프레이밍 해석에만 씁니다.
  - "줄·이벤트 상한은 httpx-sse가 버퍼링한 뒤에 검사한다"는 한계를 그대로 적습니다.
  
  `httpx_sse` 내부 모듈(`_decoders`)은 공개 API가 아니므로 직접 import하는 방식은 계약으로 삼지 않아야 합니다.

### 2. [medium] parser·SSE가 던지는 예외 대부분이 오류 매핑에 없음
- **위치:** `codebase.md:118`, §5 오류 envelope, 루트 SPEC §5 오류 표(`E_API_AUTH`/`E_API_RATE`/`E_API_SCHEMA`)
- **실제 동작:**
  - `_stream.py`는 refusal, `response.failed`, `error` 이벤트, lane 위반을 결과로 돌려주지 않고 `ResponsesStream*Error` 예외로 던집니다.
  - source가 던진 예외는 모두 `ResponsesStreamSourceError(operation="next", cause=…)`로 감쌉니다. 여기에는 httpx timeout과 adapter가 직접 던진 상한 초과 예외도 포함됩니다.
  - parser 안의 `MemoryError`는 `ResponsesStreamParserError`로 감쌉니다. 따라서 "MemoryError는 그대로 전파된다"는 공식 README 문구는 `decode_mask_to_raster`를 직접 부를 때만 맞습니다.
  - `aiter_sse()`는 Content-Type이 `text/event-stream`이 아니면 `SSEError`를 던집니다. 401·429처럼 JSON으로 오는 오류 응답도 status 검사 없이 iterate하면 `SSEError`가 되고, 다시 `SourceError`로 감싸집니다.
- **충돌 예:** 매핑 코드가 `await final_result()` 바깥에서 `httpx.TimeoutException`, 자체 상한 초과 예외, HTTP 429를 기다리면 하나도 잡히지 않습니다. 그러면 다음 문제가 생깁니다.
  - 429가 `E_API_RATE` 지수 백오프로 가지 않습니다.
  - timeout이 `E_API_SCHEMA`의 "오류 내용 포함 재요청"으로 잘못 분류될 수 있습니다.
- **최소 수정:** `codebase.md` §6/§5에 매핑 표를 추가합니다.
  1. iterate 전에 `event_source.response.status_code`와 Content-Type을 먼저 검사합니다(401/403 → `E_API_AUTH`, 429 → `E_API_RATE`).
  2. `ResponsesStreamSourceError`와 `ResponsesStreamParserError`는 `.cause`를 꺼내 분류합니다.
  3. refusal/failed/event/lane 오류의 대상 코드를 정합니다.

### 3. [low] 업로드 256MiB 상한은 FastAPI `UploadFile` 경로에서 handler보다 늦게 적용됨
- **위치:** `codebase.md:94`(multipart 입력 수용), `:128`(업로드 256MiB), `dependencies.md`의 python-multipart 행(`UploadFile`/`Form`)
- **실제 동작:** Starlette 1.10 `formparsers.py`의 `max_part_size`는 file part가 아닌 필드에만 적용됩니다. file part는 크기 제한 없이 `SpooledTemporaryFile`에 기록됩니다. 이 파일은 시스템 temp 디렉터리에 생기며 data root 밖입니다. FastAPI 0.162에는 이 한도를 바꾸는 인자가 없고, Uvicorn에도 요청 body 크기 제한이 없습니다.
- **충돌 예:** 문서는 256MiB 초과 입력을 "명시 거부"한다고 하지만, 실제 거부는 전체 body가 temp 디스크에 기록된 뒤에야 일어납니다.
- **최소 수정:** §7에 다음 중 하나를 명시합니다.
  - `Content-Length` 사전 거부와 `request.stream()` 바이트 카운터로 직접 수신합니다.
  - "spool 후 검사, temp는 data root 밖"이라는 한계를 적습니다.

### 4. [low] ffmpeg 핀 상태가 문서마다 다르고, 빌드 구성 기록이 companion에 없음
- **위치:** spine `:148`, `:150`(9.0.2 고정, "provenance 기록", "GPL/libx264"), `dependencies.md:65`("정확한 버전 고정은 아직 정하지 않았다", configuration은 "별도 기록한다"), `research/oss.md:138`, `:158`, `:190`("빌드 미선정")
- **실제 상태:** 설치본은 `/opt/homebrew/Cellar/ffmpeg/9.0.2_1`입니다. 구성은 `--enable-gpl --enable-version3 --enable-libx264 --enable-libx265 …`이므로 단순 GPL이 아니라 GPLv3 빌드입니다. 이 configuration 줄은 내부 `.memlog.md`에만 있고 companion 문서에는 없습니다.
- **충돌 예:** CAP-5의 "고정 renderer 환경에서 동일 frame hash"와 깨끗한 설치 검증을 할 때, 구현자가 spine을 읽으면 고정된 빌드라고 이해하고 dependencies 문서를 읽으면 아무 ffmpeg나 써도 된다고 이해합니다.
- **최소 수정:** `dependencies.md` §4에 다음을 기록하고, spine과 `oss.md`의 표현을 하나로 맞춥니다.
  - Homebrew revision 9.0.2_1
  - 전체 configuration 줄
  - libx264 버전
  - 라이선스 GPL-3.0-or-later 구성

### 5. [low] 제출 고지 초안의 라이선스 목록이 `uv.lock`과 맞지 않음
- **위치:** `research/oss.md:189`와 고지 문안 단락
- **문제:** 라이선스를 "MIT, BSD-3-Clause, MIT-CMU"로만 적었습니다. 실제 잠금 집합에는 다음이 더 있습니다.
  - Apache-2.0: python-multipart, opentelemetry-api
  - MPL-2.0: certifi
  - PSF-2.0: typing-extensions
  
  직접 의존성인 httpx-sse, python-multipart, PyYAML은 고지 문장에 이름이 없습니다. `dependencies.md` §2/§3에는 이 정보가 맞게 있으므로 문서끼리 어긋납니다.
- **최소 수정:** 표 6을 `dependencies.md` §2/§3 기준으로 다시 만들거나, 그 문서를 정본으로 참조하게 합니다.

## 판정
**조건부 통과입니다(critical·high 0건).** 버전·해시·라이선스 원문, parser 공개 API와 반열림 좌표, Range 지원, 런타임 환경, boilerplate 제외 근거는 공식 자료나 실제 파일과 일치했습니다. 다만 AD-10의 "SSE를 받으면서 상한 적용"과 parser·SSE 예외의 오류 코드 매핑(1·2번)은 고른 라이브러리의 실제 동작과 맞지 않습니다. 구현 전에 companion 계약을 고쳐야 합니다.

실연동 SSE 형식(예: 종료 sentinel 여부)과 H1/H2는 이번에 확인하지 못했습니다.
