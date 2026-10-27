# AdLoom seam 검수 결과 (다른 reviewer 결과와 중복 정리)

문서 근거는 spine, `docs/architecture/codebase.md`, implementation-contracts, product-flow입니다. parser·SSE 동작은 `.venv`에 설치된 httpx-sse, meta-sam-parser, httpx 코드를 읽어 확인했습니다. 파일 수정이나 실행은 하지 않았습니다.

## 다른 reviewer 결과와 겹치는 부분 (짧게만 덧붙임)
- **실행 모드(fixture/live/replay)와 산출물 연결:** operation_key에도 mode를 넣어야 합니다. 넣지 않으면 fixture 게시 때 CONFIRMED로 기록된 mock ID가, 같은 revision을 live로 게시할 때 "CONFIRMED 재사용" 규칙에 따라 그대로 쓰입니다. 근거는 implementation-contracts L77과 L81입니다.
- **UNKNOWN 해소 명령, 원격 Model Files 수명:** 추가할 내용 없습니다. 판정 근거로는 AD-3 "원격 부작용이 있으면 journal 대조 없이 재실행 금지"를 Model Files 업로드에도 똑같이 적용하면 됩니다.
- **SSE 사전 상한과 예외 원인 매핑:** 두 가지를 보강합니다.
  - httpx 기본 `Accept-Encoding: gzip, deflate`(`_client.py` L120, L310) 때문에 전송 계층에서 센 바이트 수는 압축을 푼 크기를 제한하지 못합니다. SSE 요청은 `identity`로 보내고, 다른 Content-Encoding 응답은 거부하는 문구가 필요합니다.
  - parser는 delta가 올 때마다 바로 처리하고(`_stream.py` L276–277), delta가 없으면 done 텍스트 전체를 한 번에 처리합니다(L357–359). 그래서 mask header 검사는 source generator 안에서 직전 delta의 끝부분을 이어 붙여 해야 합니다. 그래야 두 delta에 걸쳐 나뉜 header를 놓치지 않습니다.
- **편집 rollback 상태표:** 편집 후 재렌더를 누가 시작하는지가 정해져 있지 않습니다. PATCH `/draft`는 "재계산 필요 범위 반환"만 하고, product-flow §4.4는 "적용 시 재계산"이라고 합니다. 다른 job의 worker가 실행 중이면, 승인 무효화는 commit되었는데 재렌더를 시작할 수 없는 상태가 됩니다. 이 경우를 상태표에 넣어야 합니다.

## 새로 찾은 seam (다른 결과와 겹치지 않음)

### 1. [high] 중단된 실행이 RUNNING에 남는 문제: worker 생존 판정, 시작 확인(handshake), 차단 표식(fencing)
- **위치:** `codebase.md` L32–37, L43, AD-2
- **충돌:**
  - 복구는 "서버 재시작 시"에만 일어납니다. 그래서 서버가 살아 있는 동안 worker가 SIGKILL되거나 CLI에서 Ctrl-C로 끊기면, job이 계속 RUNNING이고 새 실행 요청은 409를 받습니다. 이때 취소하면 CANCEL_REQUESTED가 되는데, product-flow §6에서 이 상태의 가능한 행동은 "—"입니다.
  - "lease"가 정의되지 않았습니다. pid나 heartbeat 파일로 구현하면 두 번째 서버가 뜰 때 살아 있는 worker의 job을 INTERRUPTED로 바꿔 버립니다.
  - runner가 handshake 동안 job lock을 쥐고 있으면, 첫 commit으로 handshake를 하는 worker와 서로 기다리게 됩니다(deadlock).
  - spawn 실패 처리에서 active_run_id를 지우지 않으면, 늦게 뜬 worker가 IDLE job에 commit합니다.
  - worker가 단계를 시작할 때 RUNNING을 다시 쓰면 그 사이에 들어온 취소 요청이 사라집니다.
- **수정 문구:**
  - "worker 생존 = run.lock 보유. run.lock을 LOCK_NB로 획득한 프로세스는 그 보유 구간 안에서, RUNNING 또는 CANCEL_REQUESTED인 job을 모두 INTERRUPTED로 바꾸고 active_run_id를 비운다. 이 처리는 서버 시작, 모든 run/resume/publish 요청 입장, request_cancel 시 LOCK_NB 시도 성공 때 수행한다."
  - "RUNNING commit 후 job-lock을 풀고 worker를 띄운다. handshake는 worker가 fenced commit을 한 뒤 pipe로 run_id를 되돌려 보내는 것이다."
  - "실패 시 runner는 자기가 띄운 Popen에 `kill()`과 `wait()`를 호출한 뒤, run_id가 같을 때만 IDLE로 바꾸고 active_run_id를 비운다."
  - "RUNNING으로 바꾸는 것은 입장 처리만 한다. worker는 CANCEL_REQUESTED를 그대로 보존한다."

### 2. [high] 승인 digest 입력 정의가 갈림, 게시 요청에 기준값 없음
- **위치:** AD-5 L79는 포함 목록과 제외 목록을 같이 씁니다. `codebase.md` L81은 포함 목록이며 경고가 빠져 있습니다. 게시 행(L100)에는 기준값이 없습니다.
- **충돌:**
  - 제외 목록 방식으로 구현하면 "manifest − 제외 항목"이 digest 입력이 됩니다. PublishResult나 remote ID가 들어간 다음 manifest에서 digest가 달라지고, 부분 게시 재개(BA-05/AC-17)가 거부됩니다.
  - 탭 A가 rev3 확인 화면을 띄운 사이 CLI가 rev4를 수정·재승인하면, 탭 A의 게시 버튼이 확인하지 않은 rev4 예산을 게시합니다.
- **수정 문구:**
  - "digest 입력은 `schemas.ApprovalSubject` 하나다. 포함 목록 기준이며 warnings, degraded, clipped, Image 대체, mode를 포함한다. seq, manifest_ref, PublishResult, journal은 제외한다."
  - "게시 유효성은 seq가 아니라 이 digest를 다시 계산해 판정한다."
  - "publish, resume, reconcile 요청은 확인 화면에 보인 approval digest를 필수 기준값으로 보낸다. 다르면 409."

### 3. [medium] 미디어 시간축과 근거 문자 위치
- **(a) Voice 오디오 출처**
  - **위치:** implementation-contracts L104는 "원본 audio"에서 추출한다고 합니다. 반면 `codebase.md` L113의 consumer 목록에는 Voice가 없고, 정규화 MP4가 오디오를 유지하는지 정하지 않았습니다.
  - **충돌:** start_time이 0이 아니거나 edit list가 있는 MOV는 정규화 과정에서 0 기준으로 다시 맞춰집니다. 원본 오디오로 만든 자막은 그 차이만큼 밀리고, 렌더에 쓰는 오디오와 영상도 어긋납니다.
  - **수정 문구:** "정규화 MP4는 오디오를 같은 0 기준으로 포함한다. Voice, 렌더, Spark는 정규화본만 사용한다."
- **(b) 프레임 번호와 µs 변환**
  - **충돌:** fps가 30000/1001 같은 비정수 값이면 crop은 round, timeline은 floor로 변환해 구간 경계에서 한 프레임씩 어긋날 수 있습니다. JS가 경계 시각으로 seek하면 바로 앞 프레임이 표시됩니다.
  - **수정 문구:** "`timeline.py`의 `frame_start_us(i) = floor(i·10⁶·den/num)`와 `frame_at_us(t)`만 사용한다. API는 구간 정보에 frame index도 내려주고, JS는 프레임 중앙 시각으로 seek한다."
- **(c) 근거 하나의 오류가 응답 전체 실패로 번짐**
  - **위치:** implementation-contracts L49는 "불일치 quote는 schema 오류로 거부"라고 하고, product-flow L77은 근거 하나 단위로 "유효하지 않은 근거"로 표시한다고 합니다.
  - **충돌:** 이 검사를 Pydantic validator에 넣으면 Spark 응답 전체가 `E_API_SCHEMA`가 되어 이해 단계가 실패합니다.
  - **수정 문구:** "모델 출력은 EvidenceCandidate의 구조만 검증한다. 문자 위치와 quote가 맞는지는 순수 함수가 근거 하나씩 판정한다. 200자는 NFC 정규화 후 codepoint 수로 센다."

### 4. [medium] 고아 파일 정리와 worker commit이 동시에 실행되는 문제
- **위치:** AD-3 "고아 파일은 이후 정리 대상", `codebase.md` §3
- **충돌:** 정리 담당자는 "head가 참조하지 않는 objects와 tmp"를 고아로 보고 지웁니다. 실행 중인 worker가 fsync와 rename을 마쳤지만 아직 job.json을 commit하지 않은 산출물이 바로 그 조건에 걸립니다. 정리가 그 파일을 지우면, 이어지는 head commit이 존재하지 않는 파일을 가리키게 됩니다.
- **수정 문구:** "정리는 run.lock을 LOCK_NB로 쥔 동안에만 실행한다. 대상은 모든 revision의 manifest, approval, journal이 참조하지 않는 파일로 한정한다."

### 5. [medium] 이전 revision 결과 재생 경로
- **위치:** AD-9 "manifest의 검증된 경로로 resolve", product-flow §4.7 "이전 revision 결과를 비교용으로 재생", §5.2 "다운로드는 현재 revision만"
- **충돌:** 파일 경로를 head manifest만으로 찾으면, 재렌더 중에 이전 결과를 비교 재생할 때 404가 납니다. 반대로 `objects/<sha>`를 아무 조건 없이 열어 주면, 이전·미승인 결과를 현재 결과로 다운로드할 수 있습니다.
- **수정 문구:** "artifact 경로 resolve는 `(revision, manifest_ref)`를 받는다. 현재 head가 아니면 응답에 stale 표시를 붙이고 다운로드 manifest를 만들지 않는다."

## 판정
**incorrect** (확신도 0.8). 범위를 줄이지 않고, 위 문구를 `codebase.md` §2–7과 AD-2·3·5·9에 반영하면 닫을 수 있습니다.

1번과 4번에서 시스템이 실제로 오동작하는지는 실행해 보지 않고 코드 경로로 추론했습니다([INFERENCE]). 제품 구현은 아직 없습니다.
