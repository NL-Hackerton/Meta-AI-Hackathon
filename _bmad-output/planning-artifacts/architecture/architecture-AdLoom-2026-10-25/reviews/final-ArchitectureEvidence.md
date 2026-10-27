Main, 최신 spine과 codebase 기준으로 이전 finding 5건은 모두 해소됐습니다. 남은 critical·high도 직접 모순도 없어 **판정은 통과입니다.** 이번에도 읽기 전용이었고 테스트·린트·빌드는 하지 않았습니다.

**이전 finding 해소 여부**
1. **SSE 상한 (해소):** spine AD-10(:112)과 codebase §7(:187, :194)에 HTTPX 공개 byte-stream wrapper가 들어갔습니다. httpx-sse보다 먼저 identity 인코딩 강제, 전체 64MiB, 물리 줄 2MiB를 제한합니다. 이벤트 상한은 decode 후에야 검사하므로, 이벤트 하나가 최대 64MiB까지 버퍼링될 수 있다는 한계도 명시했습니다. httpx-sse private 모듈은 import하지 않습니다. 앞서 확인한 httpx-sse 0.4.3 소스 동작과 맞습니다.
2. **예외 매핑 (해소):** codebase §5 표(:152~161)가 다음을 모두 다룹니다.
   - SSE 순회 전 401·403·429 status 검사
   - `SourceError`·`ParserError`는 `.cause`를 꺼내 분류
   - timeout과 연결 오류, 자원 한도와 MemoryError, refusal, provider failed·event, schema, incomplete·eof
   
   parser `_stream.py`가 실제로 던지는 예외와 대조했고 빠진 경로가 없습니다. Spark 재요청 규칙을 SAM에 쓰지 않는다는 분리도 들어갔습니다.
3. **업로드 상한 (해소):** codebase :192에 들어갔습니다. ASGI receive wrapper가 handler보다 먼저 Content-Length를 검사하고 누적 257MiB에서 끊으며, file part 256MiB는 따로 확인합니다. 앱 시작 전에 `tempfile` 경로를 data/tmp로 고정하므로, Starlette의 `SpooledTemporaryFile`이 data root 밖으로 새는 문제가 사라집니다.
4. **ffmpeg 기록 (해소):** `media-baseline.json`의 ffmpeg SHA-256 `768609fb…013e`가 실제 `/opt/homebrew/Cellar/ffmpeg/9.0.2_1/bin/ffmpeg` 해시와 같습니다. revision 9.0.2_1, 전체 configuration, GPL-3.0-or-later 표기도 들어 있습니다. `dependencies.md` §4, `oss.md`(:138, :158, :190), spine Stack 표기가 이제 서로 맞습니다.
5. **고지 라이선스 목록 (해소):** `oss.md`(:189, :194)가 직접 의존성 9개와 전이 의존성 13개, Apache-2.0·MPL-2.0·PSF-2.0을 적고, `dependencies.md` §2·3을 정본으로 연결했습니다.

**새로 추가된 부분:** reconcile에서 `confirm_absent`를 금지하고 abandon은 미완료로 남긴 채 명시적인 새 job만 허용하는 설계, 음성 confirm 흐름, frameindex·codepoint 규칙을 확인했습니다. 앞의 finding이나 공식 parser·Starlette 동작과 부딪히는 곳은 없었습니다.

**아직 확인하지 못한 것:** 실연동 SSE 형식(예: 종료 sentinel 여부), H1·H2 gate, 실제 206 응답과 lock smoke 결과입니다. 이 결과는 baseline-verification.md에 있다고 하는데, 그 내용은 이번에 다시 대조하지 않았습니다.
