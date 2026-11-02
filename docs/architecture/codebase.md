# AdLoom 코드베이스 설계 계약

작성: 2026-10-25, 상태 갱신: 2026-11-02. [Architecture Spine](../../_bmad-output/planning-artifacts/architecture/architecture-AdLoom-2026-10-25/ARCHITECTURE-SPINE.md)의 서비스 설계 계약이다. 기존 스키마에 config·atomic job 저장·크롭·정책·mock 어댑터·단계·렌더·승인/게시·CLI를 연결했다. 현재 실행은 data-root lock 아래 동기 CLI와 같은 명령을 부르는 동기 로컬 웹(`web/app.py`, `web/static/index.html`)이다. claim 검토(§4.3)는 웹·pipeline에 구현했다. 아래의 별도 worker·202 비동기 실행·session·장면/객체 편집 계약은 설계 상태다. 실행 방법은 루트 README, 태스크별 증거는 STATUS에 있다. root SPEC는 보존하며 설계는 SC-014, 데이터 규약은 SC-015, 재개 기록은 SC-017에 둔다.

## 1. 모듈별 단일 책임

| 모듈 | 소유 책임 | 해서는 안 되는 일 |
| --- | --- | --- |
| `schemas.py` | Pydantic 경계 모델·enum·반개구간·유한 수치 | provider/HTTP·파일 I/O import |
| `config.py` | env·상수·provider별 준비 상태 | 키를 JSON·로그로 직렬화 |
| `application.py` | create/edit/confirm-note/review/approve/run/publish/reconcile/cancel 공통 명령 | FastAPI Request나 CLI 인자에 의존 |
| `jobs.py` | head/manifest/approval/journal commit, lock, revision CAS | 모델·ffmpeg 실행 |
| `runner.py` | data-root 실행 입장 제어, worker spawn, run_id, 중단·재시작 판정 | 자체 대기열·무한 재시작 |
| `worker.py` | 전달받은 실행 context에서 pipeline 실행·종료 | 별도 schema·승인 로직 |
| `pipeline.py` | 단계 순서·fingerprint·무효화·단계 commit | provider별 요청 형식 분기 |
| `crop.py`, `timeline.py`, `policy.py` | 입력→계획/검사 결과 순수 함수 | 네트워크·job 상태 갱신 |
| `render.py` | 고정 RenderPlan→ffmpeg 인자·실행·probe·프레임 hash | 자유 shell·모델 호출 |
| `adapters/base.py` | Understanding/Tracking/Image/Voice/Marketing Protocol | generic plugin/event bus |
| `adapters/*.py` | 외부 응답 정규화·오류 분류·요청 자격 | approval를 만들거나 root state를 변경 |
| `stages/*.py` | 명시적 입력 모델→stage output 조합 | 산출물 완료를 검증 없이 commit |
| `web/app.py`, `routes.py` | app factory, 보안 경계, HTTP 변환, static/media serving | 서버 전용 workflow |
| `web/static/` | index.html·ES module app.js·styles.css, video+Canvas | 브라우저 토큰 보관·Meta 직접 호출 |
| `cli.py` | 공용 명령의 인자·출력 변환 | web과 다른 job 해석 |

Protocol은 원본의 5개를 유지하되 `TrackingAdapter`는 후보 trajectories를 반환하고 선택된 TrackResult는 track stage에서 만든다. 기존 파일 이름은 최대한 유지한다. 도메인 서비스마다 새 class 계층을 만들지 않고 불변 Pydantic 데이터와 함수·얇은 Protocol로 시작한다.

MarketingPublisher는 원본의 전체 publish 한 번 호출 대신 원격 리소스별 단일 연산(upload_video/upload_image/create_creative/create_campaign/create_adset/create_ad/read_resource)을 노출하는 SC-014 제안이다. stages/publish가 승인 Subject에서 payload를 구성하고 각 연산 전후 journal을 commit한다. adapter 내부에 여러 생성 POST를 숨겨 중간 ID 기록을 건너뛰지 않는다.

## 2. 실행 모델과 lock 계약

### 2.1 worker 입장과 READY/GO

1. runner가 실제 data root의 `.locks/run.lock`을 `LOCK_EX|LOCK_NB`로 획득한다. 파일 존재·pid·heartbeat가 아니라 OS lock이 worker lease다. busy이면 현재 작업을 표시하고409로 거부한다.
2. lock을 획득했다면 해당 보유 구간에서 과거 RUNNING/CANCEL_REQUESTED job을 짧은 job lock 아래 INTERRUPTED로 바꾸고 active_run_id를 비운다. 살아 있는 worker가 있으면 global lock 획득 자체가 불가능하므로 덮어쓰지 않는다.
3. 대상 job lock에서 mode/gate/base 값과 입력을 검증하고 새 run_id·RUNNING을 commit한다. **job lock을 해제한 뒤** worker를 spawn한다. global lock fd는 pass_fds로 상속하며 부모는 LOCK_UN 없이 자기 fd만 닫는다.
4. worker는 job lock에서 run_id/revision을 대조한 뒤 pipe로 READY와 run_id를 보낸다. 부모가 GO를 보내기 전에는 provider·ffmpeg를 실행하지 않는다. READY 제한은10초다. GO 이전 pipe EOF면 worker는 종료하고, 부모의 timeout/오류 경로는 자신이 만든 Popen을 kill+wait한 뒤 같은 run_id일 때만 INTERRUPTED·active_run_id=null로 복구한다.
5. GO 이후 202를 반환한다. long HTTP/ffmpeg 중 job lock은 잡지 않는다. 모든 단계 commit은 active_run_id/revision을 대조하고 CANCEL_REQUESTED를 보존한다. worker가 단계마다 RUNNING을 다시 써서 취소를 덮어쓰지 않는다.

lock 순서는 global-run→job이다. job lock을 잡고 global lock을 기다리지 않는다. 서버 시작과 모든 run/resume/publish 입장 때 stale lease 회수를 수행한다. 취소도 global lock을 nonblocking으로 시도해 획득하면 stale 회수, 실패하면 해당 job에 CANCEL_REQUESTED만 기록한다. GET은 상태를 변경하지 않으며 worker 소실 관측을 표시해 복구 명령을 안내한다. 서버가 소유한 child의 종료 감시도 같은 회수 절차를 사용한다.

### 2.2 중단·복구

정상 완료 단계는 verified artifact/state를 commit한 뒤 다음 단계 전에 IDLE로 멈춘다. ffmpeg 종료 시 partial output은 commit하지 않는다. 이미 받은 remote ID는 취소 중에도 journal에 기록한다. 결과 불명은 UNKNOWN이며 원격 취소 성공으로 표시하지 않는다. FAILED/INTERRUPTED 재개는 입력 fingerprint와 journal을 대조하고 last_success_state로 복귀한 뒤 실패 단계를 다시 실행한다. 사업 상태 복구와 RUNNING 입장은 같은 fenced commit이다.

## 3. 저장 구조와 원자성

```text
data/
  .locks/run.lock
  jobs/<job-id>/
    .lock
    job.json
    input/source.mp4
    input/note.json
    objects/<sha256>.<ext>
    revisions/r000001/
      manifests/m000001.json
      manifests/m000002.json
      approvals/a000003/approval.json
      publish/<operation-key>.json
    remote-files/<upload-attempt>.json
    runs/<run-id>/
      events.jsonl
      provider-captures/
      render-build.json
    tmp/<run-id>/
```

- `job.json`은 schema_version, job_id, 불변 execution_mode, revision, manifest_seq, state, last_success_state, run_state, active_run_id, note_status, manifest_ref, approval_ref, failed_stage, pending_stage, safe error, 관측 시각을 가진다. **현재 상태는 이 head가 정본**이다. failed_stage는 최근 실패 기록, pending_stage는 현재 revision에서 다시 실행할 첫 단계다. 각 artifact에는 origin_mode·capture_id·생성/재사용 출처를 기록한다.
- manifest는 Brief/Understanding/TrackCandidates/선택 ID/CropPlan/TimelinePlan/EnrichResult/RenderedVariant/EvidenceRef/ClaimReview/PublishPlan의 불변 참조·digest를 담는다. 진행 상태를 별도 manifest에서 현재 상태인 것처럼 복제하지 않는다.
- objects는 content-addressed 불변 bytes다. 이전 revision의 artifact를 재사용하면 ref를 공유하고 bytes를 복사하지 않는다. runtime cleanup에서 현재/과거 승인·journal 참조 파일을 지우지 않는다.
- artifact와 manifest를 임시 경로에 쓴 뒤 fsync→동일 filesystem rename→directory fsync하고, 마지막에 job.json을 원자 교체한다. crash 전후 어느 head를 읽어도 완전한 manifest만 참조한다. 고아 파일은 이후 정리 대상이지 자동 복구 결과가 아니다.
- approval는 revision별 불변 파일이며 head가 가리키는 것만 유효하다. 편집 시 head approval_ref를 제거하며 과거 파일을 새 revision 승인으로 재사용하지 않는다.
- publish journal은 operation_key별 현재 phase를 원자 갱신한다. remote ID 수신 후 journal fsync가 먼저, business state 갱신은 나중이다. crash 후 remote side effect가 local state보다 앞설 수 있다는 전제로 복구한다.
- 부분 게시에 CONFIRMED/UNKNOWN이 남거나 게시가 완료된 revision은 편집하지 않는다. 기존 시도를 확인·종료한 뒤 **새 job**으로 시작한다. 같은 job의 게시 revision fork 명령은 제공하지 않으며 과거 remote 객체를 수정하지 않는다.
- JSON schema_version 미지원은 읽기를 거부하고 명시 migration을 요구한다. NFS·동기화 드라이브·다중 호스트를 저장 위치로 지원하지 않는다.

고아 파일 정리는 global run lock을 nonblocking으로 획득한 동안에만 한다. 모든 revision manifest·approval·publish/remote-files journal의 참조를 합쳐 도달하지 않는 파일만 대상으로 삼는다. head에 아직 연결되지 않은 실행 중 산출물을 정리자가 삭제하지 못하게 한다. 자동 주기 GC는 이번 범위에 추가하지 않는다.

### 3.1 Model Files 수명

pipeline이 `adapters/files.py`의 얇은 업로드/삭제 helper를 호출하고 resource lifecycle을 소유한다. 업로드 전 remote-files journal에 source digest·purpose·attempt·PREPARED, 응답 ID 직후 CONFIRMED를 원자 기록한다. 같은 normalized asset의 Spark/SAM 소비자는 그 ID를 공유하며 adapter가 임의 삭제하지 않는다.

해당 실행의 understand/track 소비자가 끝나거나 실행이 실패·중단되면 finally cleanup에서 삭제를 요청한다. 삭제 성공은 DELETED, 실패는 CLEANUP_REQUIRED와 경고다. 서버 crash 뒤 lease 회수도 journal 기반 cleanup 대상을 드러낸다. 재계산이 필요하면 삭제된 ID를 재사용하지 않고 새 승인된 upload attempt를 만든다. 업로드 응답 유실은 UNKNOWN으로 남기고 자동 재업로드하지 않는다. provider에서 ID를 확인할 수 없으면 원격 잔존 가능성을 보고하며 삭제됐다고 하지 않는다.

UNKNOWN upload에서 계속하려면 resume_job에 new_upload_attempt 옵션과 abandon_attempt_id, expected_phase=UNKNOWN, ack_possible_remote_retention=true를 명시한다. 운영자 actor를 기록하고 이전 attempt를 삭제하지 않은 채 CLEANUP_REQUIRED 경고를 보존한다. 이 승인은 새 upload attempt1회에만 소비된다. 옵션 없는 resume은 재업로드하지 않는다. 이는 원격 파일 잔존 위험을 인정한 명시적 재시도이며 광고 생성 UNKNOWN의 자동 재POST 금지와 다르다.

Image의 enable_image_search, enable_web_search, enable_shell은 false로 고정한다. 보관 동의·비용 한도는 H2가 정하되 ID 소유권·삭제·실패 기록 메커니즘은 이 계약에 고정한다.

## 4. revision·검토·승인

내용 편집은 base_revision, review/approve는 base_revision+base_manifest_seq를 요구한다. 의미상 no-op는 revision/seq/digest/승인을 유지한다. 실행 중이거나 현재 revision에 PREPARED/CONFIRMED/UNKNOWN 게시 operation이 있으면 편집·review·approve를409로 거부한다. 게시 뒤 변경은 새 job으로만 시작한다.

### 4.1 편집의 확장 전이표

이 표는 원본 §3의 닫힌 전이를 대체하는 SC-005·014 제안이며 상태의 **상한**이다. rollback 상태는 표의 상태와 현재 유효 산출물의 마지막 완료 상태 중 더 이른 값이다. last_success_state도 같은 값으로 낮추고 pending_stage는 기존 미완료 단계와 새 무효화 단계 중 가장 이른 단계로 고정한다. 실패·중단 상태에서는 failed_stage/error 기록과 FAILED/INTERRUPTED를 worker 입장 전까지 유지한다. 본문만 바꿔도 빠진 렌더를 건너뛰어 AWAITING_APPROVAL로 상승하지 않는다.

| 변경 | 허용되는 최대 사업 상태 | 실행할 첫 단계 |
| --- | --- | --- |
| note 확정·수정 | CREATED | understand(음성 미확정이면 input) |
| 기존 object 후보 변경 | UNDERSTOOD | track 계획, 저장한 후보 재사용 |
| 사용 구간·CTA | TRACKED | enrich; 동일 이미지/전사는 fingerprint로 재사용 |
| 훅·자막 문구 | ENRICHED | assemble |
| 본문·제목·예산·destination·게시 profile 갱신 | AWAITING_APPROVAL | 정책/근거/게시 계획 재검사, 영상 재사용 |
| claim 검토 변경 | AWAITING_APPROVAL | manifest_seq만 증가, 기존 승인 무효화(재렌더 없음) |

`edit_job`은 pending_stage가 있으면 먼저 global run 입장을 예약한다. busy에는 무변경409다. 예약 뒤 revision 증가·승인 무효화·rollback/pending_stage를 원자 commit하고 READY/GO로 재계산한다. 실패·중단 편집도 pending_stage부터 재개하며 이전 실패 기록은 보존한다. spawn 실패는 새 revision을 rollback하지 않고 INTERRUPTED로 둔다. 미완료 단계가 없는 무렌더 편집만200이며, current6개가 없는 편집은 승인 대기로 바로 전이하지 않는다.

### 4.2 ApprovalSubject와 게시 기준값

digest의 유일한 입력은 `schemas.ApprovalSubject`의 **포함 목록 projection**이다. manifest 전체에서 일부 키를 빼는 방식은 금지한다. UTF-8/sorted keys/고정 separators/allow_nan=false/NFC/정수 time_us/stable list order로 서버에서만 직렬화한다.

포함: source·6개 variant·실제 게시/thumbnail byte hashes, 선택 object/구간, 문구, 유효 EvidenceRef와 ClaimReview, 정책 규칙/결과, warnings/degraded/clipped/Image fallback, artifact origin_mode/capture 출처, 불변 PublishPlan. 제외: manifest_seq/ref, run_state, phase, PublishResult, remote IDs, journal, 관측 timestamp, approval 자신. 부분 게시가 진행돼도 Subject가 변하지 않는다.

PublishPlan은 revision 내용으로 create, refresh_publish_plan, 게시 설정을 바꾸는 edit_job commit에서만 snapshot한다. 설정 edit은 기존 account/Page/Graph/profile을 유지하고 예산·CTA·destination 등 명시 변경만 반영한다. env의 새 profile은 명시 refresh로만 반영한다. approve/publish는 plan을 다시 만들지 않고 config와 대조해 다르면409다. fixture는 명시 mock profile을 사용하며 실제 env/H2/H3를 요구하지 않는다. live config가 불완전하면 plan은 unready이고 렌더·다운로드만 가능하다. 모든 plan 변경은 새 content revision·재승인 대상이다.

PublishPlan은 게시 설정만 보유한다. 렌더 전 create에서도 만들 수 있도록 asset·thumbnail digest는 넣지 않는다. 실제 게시 영상·썸네일·문구는 승인 시 고정한 ApprovalSubject에서만 가져오므로 편집 후 새 결과와 plan 안의 낡은 hash가 충돌하지 않는다.

publish와 게시 resume/reconcile 요청은 확인 화면의 base_revision+expected_approval_digest를 필수로 보낸다. 현재 Subject digest와 다르면409다. 진행 때문에 바뀌는 manifest_seq를 게시 동일성 기준으로 쓰지 않는다.

공통 approval_issues(subject)가 웹 차단 이유·approve·publish 직전 판정에 쓰인다. current6개·schema·artifact hash·최종 policy·필수 ClaimReview·source·mode를 검사하며 H2/H3·실제 env gate는 live에만 적용한다. fixture는 명시 mock profile로 run→approve→mock publish 경로를 완결한다. 모델 accepted·고위험 inference 라벨 우회를 거부하며 source 연결을 사실/Meta 심사 인증으로 표시하지 않는다.

job.execution_mode는 create 시 fixture 또는 live로 고정한다. artifact의 모든 provider origin이 live(또는 해당 live 실패의 명시된 허용 local fallback/무오디오 skip)여야 live publish 가능하다. fixture artifact를 live job에 이식하지 않는다. replay는 capture를 읽고 재채점하는 read-only 경로이며 publish/편집/승인을 하지 않는다. operation_key에는 job/revision/mode/resource/hook을 포함해 mock ID와 live ID 공간을 분리한다.

publish는 immutable approved snapshot과 업로드 직전 hash를 확인한 같은 열린 자산을 사용한다. 소유자의 악의적 로컬 파일 변조까지 막는다고 주장하지 않되 hash 불일치는 거부한다.

### 4.3 claim 검토 (구현)

live Spark의 `Understanding.claims`는 승인을 막는 예외가 아니라 검토 대상이다. `make_subject`는 claim마다 참조를 `assess_evidence`로 확정 note·정규화 원본과 대조해 `ApprovalSubject.evidence`(ID `<claim id>#<n>`)를 만들고, `Snapshot.claim_reviews`의 소유자 결정을 붙인 `ClaimReview`를 `ApprovalSubject.claims`에 넣는다. 결정이 없거나 claim 문장이 바뀌면 pending이다. 고위험 판정 규칙은 아직 없어 `high_risk=False`다. 차단 판단은 `approval_issues`가 한다: 필수(inference가 아닌) claim의 pending은 `unreviewed_claim`, 근거 부족·무효는 `missing_*_evidence`·`invalid_evidence`, 거절은 필수 여부와 무관하게 `rejected_claim`이다.

`review_claims(settings, job_id, decisions, actor)`(`POST /api/jobs/:id/claims`)는 execution lock 아래 AWAITING_APPROVAL/APPROVED이고 게시 기록이 없는 job만 받는다. 모든 ID가 현재 claim이고 값이 accepted/rejected여야 하며 아니면 무변경422다. 같은 결정이면 no-op, 바뀌면 같은 revision에 새 manifest_seq를 commit하고 approval_ref를 지워 AWAITING_APPROVAL로 되돌린다(재렌더 없음, 기존 승인 digest는 409).

거절은 "이 문장은 사실이 아니다"라는 소유자 판단이다. 승인은 소유자가 문구를 고칠 때까지 막힌다. `edit_job`에서 훅·제목·본문 중 하나라도 바뀌면 거절된 claim을 `Understanding.claims`와 `claim_reviews`에서 함께 빼고(소유자가 문구를 다시 썼다는 뜻), 수락 결정은 유지한다. 장면·추적 대상만 바꾸는 편집은 거절을 유지한다.

## 5. API·CLI 공용 명령 계약

아래 endpoint는 설계다. 2026-11-02 구현한 로컬 웹은 이 중 일부를 동기 요청으로 제공한다: `GET/POST /api/jobs`(업로드 후 같은 요청에서 mock 파이프라인 실행, 음성만 있으면 전사 확인 대기에서 멈춤), `GET/DELETE /api/jobs/:id`, `POST /api/jobs/:id/{approve,publish,edit,resume,confirm-note,claims}`, `POST /api/jobs/:id/publish/abandon`, `GET/PUT /api/profile`, `GET /api/notifications`, `GET /api/status`, 검토용 미디어 `GET /api/jobs/:id/files/{renders,enrichment,images}/…`와 `input/normalized.mp4`(Range 지원). edit는 문구 외에 `moments`(사용할 key moment 색인)와 `product`(추적 대상 문구)를 받아 §4.1 표대로 assemble 또는 track부터 다시 실행한다. session 대신 loopback Host 허용목록, 쓰기 요청의 `X-AdLoom-Request: 1` 헤더·Origin 일치, Content-Length 257MiB 사전 검사로 교차 사이트 쓰기를 403/413으로 거부한다. 승인은 화면에서 본 `content_digest`를 보내며 다르면 409다. 설계의 쓰기 요청은 session/CSRF와 명시 base 값을 검증한다.

| HTTP | 공용 command | 결과 |
| --- | --- | --- |
| GET `/api/jobs` | list_jobs | 저장된 local job 요약, 비밀/절대경로 제외 |
| POST `/api/jobs` | create_job | multipart 입력을 data에 수용하고 CREATED job201; 실행과 별도 |
| GET `/api/jobs/:id` | get_job | current head+필요 summary, provider 준비 boolean |
| POST `/api/jobs/:id/run` | run_job | 모델·렌더 worker202 또는 busy409 |
| PATCH `/api/jobs/:id/draft` | edit_job | base_revision 검사; busy이면 무변경409, 무렌더 편집200, 재계산 예약·commit 뒤202 |
| POST `/api/jobs/:id/claims` | review_claims | `{actor, decisions: {id: accepted\|rejected}}`, manifest_seq 갱신·승인 무효화 |
| POST `/api/jobs/:id/approve` | approve_job | 현재 revision의 유효 approval 생성 |
| POST `/api/jobs/:id/publish` | publish_job | base_revision+expected_approval_digest·gate 검사 후202 |
| POST `/api/jobs/:id/cancel` | request_cancel | run_state 변경202; 원격 취소 보장 없음 |
| POST `/api/jobs/:id/resume` | resume_job | 실패/중단 입력 대조; 게시 재개는 expected_approval_digest 필수 |
| POST `/api/jobs/:id/publish/reconcile` | reconcile_publish | expected_phase·revision·승인 digest를 대조한 읽기 전용 원격 확인 worker |
| POST `/api/jobs/:id/confirm-note` | confirm_note | 전사 초안의 사용자 확정, NFC/codepoint 검증 후 CREATED |
| POST `/api/jobs/:id/publish-plan` | refresh_publish_plan | 현재 config를 새 revision에 snapshot, 재승인 필요 |
| GET `/api/jobs/:id/artifacts/:artifact` | resolve_artifact | revision+manifest_ref 필수, manifest 소속 검증 후 Range206 |

CLI는 같은 command를 호출한다. 승인 actor는 local session 또는 CLI identity이며 모델이 정하지 않는다. 렌더 준비 전 edit UI는 제한되고 invalid patch는 commit 전 거부한다. fixture 게시 명령은 명시 mock 결과이며 실제 광고 ID처럼 링크하지 않는다.

artifact는 명시 revision/manifest_ref 안에서만 resolve한다. 과거 결과도 비교 재생할 수 있지만 응답 metadata에 stale을 표시하고 current 다운로드 manifest에는 포함하지 않는다. raw objects hash URL만으로 파일을 노출하지 않는다.

`reconcile_publish`는 application 공용 명령이며 CLI `reconcile`도 사용한다. resolution은 `link_remote_id` 또는 `abandon`이다. link는 원격 readonly 조회로 resource kind·계정·부모 연결·노출된 payload 필드를 확인하고 운영자가 근거를 기록한 뒤 CONFIRMED로 바꾼다. provider가 원본 fingerprint를 노출하지 않으면 완전 자동 동일성 증명을 주장하지 않는다. 검색 결과 없음은 생성되지 않았다는 증거가 아니므로 `confirm_absent` 후 자동 재POST 경로는 제공하지 않는다. 확인 불가면 UNKNOWN 유지 또는 abandon으로 해당 게시 시도를 종료한다. abandon은 미완료이며 후속은 명시 새 job이고 기존 원격 PAUSED 객체 잔존 가능성을 표시한다.

음성-only create는 CREATED+note_status=AUDIO_PENDING이다. `stages/input.py`가 worker/run lock/H2 안에서 전사하고 proposal text를 저장한 뒤 CREATED+REVIEW_REQUIRED+IDLE로 멈춘다. 웹·CLI 모두 confirm_note로 NFC 정규화/200codepoint 제한의 사용자 확정본을 만든 후 understand를 실행한다. 입력 텍스트가 있으면 최초 명시 입력이 CONFIRMED다. 전사 모델의 문구를 사람 승인 없이 explicit 사용자 주장으로 승격하지 않는다.

오류 envelope는 `error.code`, `stage`, `retryable`, `message`, sanitized `details`다. 원본 AdLoomError 코드를 유지하고 새 command 충돌 코드는 SC-014에서 `E_JOB_BUSY`, `E_REVISION_CONFLICT`, `E_STATE_CONFLICT`를 제안한다. HTTP 입력422, 승인/정책/상태 충돌409, 권한/CSRF403, 미존재404, 준비 안 된 live provider503을 사용한다. FastAPI validation 응답도 같은 envelope로 변환한다. HTTP 오류와 worker의 비동기 FAILED 결과는 구분한다.

| 외부 실패 | 매핑·재시도 |
| --- | --- |
| SSE iterate 이전 HTTP401/403·429 | status를 먼저 검사해 E_API_AUTH / E_API_RATE; JSON 오류를 SSE 파싱하지 않음 |
| SourceError/ParserError | public `.cause`를 풀어 원래 예외를 아래 규칙으로 분류 |
| timeout/연결 오류 | E_API_NETWORK; 자동 schema 수정 재요청 금지, 원격 생성 결과 불명은 UNKNOWN |
| byte/pixel quota·MemoryError | E_RESOURCE_LIMIT, retryable=false |
| Refusal | E_API_REFUSED, retryable=false |
| provider Failed/Event | 명시 provider code의 auth/rate 우선, 그 외 E_API_REMOTE; 임의 rate 추정 금지 |
| lane·mask·진단·잘못된Content-Type/JSON | E_API_SCHEMA, SAM 자동 repair 없음 |
| incomplete/eof | E_API_INCOMPLETE, stage commit 금지·사용자 resume만 |

새 오류 코드는 SC-014 추가 제안이다. 원본의 schema 수정 재요청1회는 Spark 구조화 출력 검증에만 적용한다. SAM 실패를 Spark repair로 재시도하지 않는다. RATE backoff도 remote side-effect가 불명인 생성 POST에는 적용하지 않는다. 취소는 실패코드 대신 run_state로 보존한다.

브라우저 dirty는 로컬 초안이다. 서버는 unseen dirty를 추정하지 못하므로 승인 요청은 화면에서 검토한 manifest_seq/content_digest를 포함한다. 다른 탭의 저장 변경은 CAS로 거부하고, 저장되지 않은 다른 탭 초안이 서버 승인을 소급 무효화한다고 주장하지 않는다.

## 6. 미디어·문자·parser 정규화

- 입력 동영상은 회전/VFR과 audio/video start time을 함께0 기준으로 정규화한다. Voice 영상 전사·Spark/SAM·crop·render의 영상/오디오는 이 MP4에서만 가져온다. 원본 bytes는 digest·원본 표시용으로 보존하고 note 음성 파일은 별도 전사 경로다.
- 계획은 integer microseconds/rational fps/반개구간이다. `timeline.py`의 frame_start_us(i)=floor(i×1000000×den/num), frame_at_us(t)=start_us(i)≤t인 최대 i만 사용한다. API에 frame index·중앙 시각을 함께 보내고 JS는 중앙 시각으로 seek한다. 양끝 범위는 [0,frame_count)이며 끝 시각은 프레임 없음이다.
- note200자는 NFC 후 codepoint 수로 센다(JS Array.from(normalize('NFC'))). EvidenceCandidate 구조 검증과 근거별 span/quote 검증을 분리한다. 모델의 잘못된 근거는 invalid+사유로 남기고 관련 claim 승인 차단·수정을 허용한다. 사용자 PATCH의 잘못된 timestamp/quote는 전체 변경 없이422다. note 변경 시 과거 span/검토를 자동 이식하지 않는다.
- `meta_sam_parser`가 반환한 `SegmentationBoxRecord.right/bottom`은 half-open이다. width=right-left, height=bottom-top이며 **+1을 다시 더하지 않는다**. raw wire를 설명하는 기존 문서의 +1과 이 경계를 구분한다.
- `object_id`는 문자열 그대로 보존한다. numeric 순서가 필요한 tie-break에서만 정수 변환한다. frame index는 명시값으로 정렬하고 중복·범위 밖 값을 거부한다. confidence=None을0/1로 채우지 않는다.
- `parse_responses_stream(...).final_result()`로 최종 snapshot을 소비한다. 중간 누적 snapshots를 계속 합치지 않는다. outcome completed와 진단을 검사하고 malformed/ignored protocol field/confidence 오류는 E_API_SCHEMA로 기록한다. incomplete 결과는 정상 track으로 commit하지 않는다.
- 정상 완료 zero-match는 빈 candidates→coverage0→중앙 crop/degraded다. malformed mask로 box가 사라진 것을 zero-match로 혼동하지 않는다. selected object 변경은 이미 저장한 trajectories로만 수행한다.
- mask decoder 추가 라이브러리는 도입하지 않는다. 공식 parser가 내부 검증을 위해 mask를 decode한다는 비용은 인정한다. 저장한 stage output에는 필요한 bbox/ID/confidence만 도출하고 raw provider capture는 용량 한도 안에서 별도 보존한다.

## 7. 자원·네트워크·렌더 경계

아래 수치는 **제품 내부 보호 상한의 제안**이며 Meta 플랫폼의 공식 한도가 아니다. 실제 호환·품질을 개발 사례에서 확인한 뒤 승인한다.

| 경계 | 제안 상한/행동 |
| --- | --- |
| 업로드 동영상 | 256MiB, duration3~45초, 확장자보다 ffprobe 결과 우선 |
| normalized media | 최대 4096px 한 변, 8,847,360 pixels/frame, 최대30fps·1350frames; 초과 입력은 명시 거부 |
| 설명 음성 | Voice 문서의32MB body·10분 이내, 전사 note200자 규칙 별도 검증 |
| SAM response | identity encoding만, 전체64MiB/물리line2MiB는 SSE 이전 byte stream에서 제한; 반환 event data2MiB는 decode 후 검사. mask header H×W≤source area |
| Image decode | base64 body32MiB, 최대16,777,216pixels, 지정PNG/치수 검사; Pillow decompression-bomb warning은 오류로 취급 |
| HTTP | connect10s, pool10s, write120s, read120s, 전체 stage600s; 실제 POST 결과 불명은 UNKNOWN 우선 |
| subprocess | shell=False, 허용 local file/pipe protocol만; URL/playlist 입력 거부, stderr 비밀 제거·용량 제한 |

업로드는 handler가 받기 전에 ASGI receive wrapper에서 Content-Length 사전검사와 chunk 누적 총257MiB를 제한한다(file256MiB+multipart 여유). file part도256MiB를 별도 확인하고 application 시작 전 TMPDIR/tempfile 경로를 data/tmp로 고정한다. 따라서 FastAPI UploadFile의 spool이 data 밖으로 새지 않는다. 인증·Host/Origin·CSRF·body 상한은 multipart 파싱 전 적용한다.

SSE는 Accept-Encoding: identity를 요청하고 다른 Content-Encoding 응답을 거부한다. public HTTPX AsyncByteStream/transport wrapper가 httpx-sse 이전에 총 bytes와 CR/LF/CRLF 물리 line 길이를 제한한다. httpx-sse private decoder를 import하지 않는다. event data 상한은 decode 후 검사이므로 하나의 event가 검사 전에 최대 전체64MiB까지 버퍼링될 수 있음을 인정한다. 무한 버퍼링이 가능하다고 두지 않는다.

parser 앞의 async event source는 delta 사이 mask header carry를 유지해 분할된 H/W도 검사한다. delta 없이 done 전체 text가 오는 경로에도 같은 quota를 적용한다. SSE data JSON의 여러 text lane도 공식 parser가 검증하며 누적 snapshots를 중복 저장하지 않는다.

HTTPX는 trust_env=false와 follow_redirects=false를 기본으로 한다. provider base URL은 Model API/Graph 고정 허용목록이며 사용자 입력으로 endpoint를 교체하지 않는다. PNG base64 응답을 우선하여 signed CDN URL 다운로드 경로를 기본에 넣지 않는다. 고객 파일을 외부 font/CDN/telemetry endpoint로 전송하지 않는다. 설치 의존성의 OpenTelemetry API 존재는 telemetry exporter 활성화를 뜻하지 않으며 exporter는 설치·설정하지 않는다.

렌더는 ffmpeg9.0.2의 현재 build·font bytes·정규화 source·model snapshot·RenderPlan을 fingerprint에 기록한다. Pillow는 문구별 정적 RGBA layer 생성만 하고 영상 프레임마다 Python에서 합성하지 않는다. output sampling은 renderer가 고정 반올림·짝수 chroma 크기·경계 clamp를 적용하고 그 실제 rect를 plan에 남긴다. 픽셀 결정론은 동일 build 범위에서만 판정한다.

## 8. 구현 순서와 검증 접점

| 순서 | 구현 단위 | 실제 증거 |
| --- | --- | --- |
| 기반 | schemas/config/jobs/runner의 source boundary | 동시 실행·crash commit·revision CAS 동작 |
| provider contract | HTTPX/SSE→official parser, Spark/Image/Voice 변환 | 작은 승인된 live 응답과 오류 분류; 이번 baseline smoke와 별도 |
| 첫 웹 흐름 | upload→worker→6개 current results→승인 차단/승인 | 실제 browser 조작, fake placeholder 금지 |
| media | crop/timeline/render | 동일 frame hash, 중앙 crop 비교, 실제 재생 |
| 편집·검토 | source seek/claims/object/edit | 영향 산출물 재사용, stale 승인 거부 |
| 실제 게시 | immutable approval→journal→Graph | PAUSED광고2개/read-back, UNKNOWN 시나리오 |

영구 테스트는 consumer-visible 경계·전이·실패를 검사하고 문자열 존재·wiring·mock echo를 검사하지 않는다. fixture·live·replay를 명시적으로 구분한다. 개발6/평가6 및 AC21/BA18/PQ10은 기존 acceptance-plan을 유지한다. 새 라이브러리의 smoke는 제품 완료 증거가 아니며 고객 검증을 새 요구로 넣지 않는다.

## 9. 근거와 한계

- [Python fcntl](https://docs.python.org/3.12/library/fcntl.html): POSIX flock과 nonblocking 오류. lock fd 상속의 실제 환경 동작은 이번 baseline smoke에서 별도 확인한다.
- [Starlette Responses](https://starlette.dev/responses): FileResponse Range 지원. 패키지 핀에서 실제206 응답을 별도 확인한다.
- [Meta SAM client libraries](https://dev.meta.ai/docs/sam/client-libraries), [PyPI](https://pypi.org/project/meta-sam-parser/0.1.0/): public API, half-open 좌표, zero-match/diagnostics/incomplete, source 및 license.
- [패키지 핀](dependencies.md), [OSS 선택](../../research/oss.md), [원본 보존 자료](../../third_party/README.md).
- 2026-10-25 baseline은 의존성과 원본 확보 범위였고, 2026-10-27에 mock CLI 경로를 구현했다. 공개 규정의 OSS 허용 조건은 SC-016에 기록했다. 사전 자체 코드 조건·참가자 약관 수락·live 실행 승인·실제 제품 품질은 별도 확인 대상이다.
