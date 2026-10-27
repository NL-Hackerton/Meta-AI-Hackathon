# 아키텍처 게이트 리뷰: 루브릭 검토 결과

**판정:** 조건부 통과가 아니라 **수정 후 재검토**가 필요합니다. 결정할 수 있는 경계(lock, 원자적 head, 좌표·시간, SAM parser, 로컬 웹 신뢰 경계)는 대부분 실제 divergence를 막습니다. 하지만 아래 네 가지 때문에 두 구현 단위가 서로 다르게 만들 수 있습니다.
- 편집으로 생기는 사업 상태 전이가 정의되지 않았습니다.
- `UNKNOWN` 해소 경로가 없습니다.
- Model Files 원격 보관 lifecycle이 빠졌습니다.
- `[ADOPTED]` 표기가 원본 제약을 약화합니다.

구현 코드가 없다는 점은 finding으로 다루지 않았습니다. 6영상, PAUSED 광고 2개, 4모델, CLI·웹, CAP-9 범위를 줄이자는 제안도 없습니다.

## 핵심 finding

### 1. [high] 편집 후 재실행할 때의 사업 상태 전이가 정해지지 않았습니다
- **위치:** SPINE AD-4(L73), AD-8(L97), codebase §4. 소스는 SPEC.md §3, implementation-contracts §6, product-flow §4.4입니다.
- **문제:** 원본 전이표는 닫혀 있습니다. "표에 없는 전이는 모두 금지"이고, T02가 전이표 전체를 테스트합니다. 이 표에서 편집은 `AWAITING_APPROVAL/APPROVED → RENDERED`로 가며 조립만 다시 합니다. 그런데 CAP-9는 다음 단계까지 다시 실행해야 합니다.
  - note 수정 → 이해 단계
  - object 변경 → crop
  - 구간 변경 → timeline

  contracts §6은 "수정 요청 순간에 RENDERED라고 하지 않는다"고만 할 뿐, 재실행 중 `job.json.state` 값은 어디에도 없습니다. 스파인은 revision·manifest_seq만 정합니다.
- **충돌 예:** `jobs.py`를 만드는 쪽은 원본 표대로 `→RENDERED`만 허용합니다. pipeline을 만드는 쪽은 note를 수정하면 `UNDERSTOOD`에서 다시 시작합니다. 그러면 전이 예외가 나거나, 재실행 중인 job이 `RENDERED`로 표시되어 승인 UI가 열립니다.
- **최소 수정:** 스파인에 AD를 하나 추가합니다(SC-014로 연결). 내용은 다음과 같습니다.
  - 편집 commit 때 사업 상태를 "영향받는 첫 단계의 직전 성공 상태"로 되돌립니다. 예: note→`CREATED`, object·구간·자막·훅·CTA→`TRACKED` 또는 `ENRICHED`, 본문·제목만 변경→`AWAITING_APPROVAL` 유지.
  - 이 확장 전이표를 원본 표의 대체 제안으로 명시합니다.

### 2. [high] `[ADOPTED]` 표기가 승인되지 않은 SC를 확정된 것처럼 만들고 원본 INV-2/AC-16을 약화합니다
- **위치:** AD-1(L51), AD-5(L75·79), AD-11(L111). 스파인 서두는 "미반영 제안을 승인된 것으로 취급하지 않는다"고 적고 있습니다. spec memlog는 "SC-001~010 … None approved"입니다.
- **문제:** BMAD에서 `[ADOPTED]`는 사용자나 현실이 이미 확정했다는 뜻입니다. 그런데 표기된 AD들은 미승인 제안에 기대고 있습니다.
  - AD-1: 웹 전 과정(SC-011)
  - AD-5: "campaign/adset/ad에만 PAUSED"(SC-001), digest·journal(SC-003·004)
  - AD-11: stage별 gate(SC-008)

  특히 AD-5 Rule은 원본 AC-16("기록된 요청 6종 모두 PAUSED", ACTIVE grep 0건)과 정면으로 다르며, 조건이 붙어 있지 않습니다.
- **충돌 예:** marketing adapter 구현자는 AD-5를 근거로 asset 요청에서 status를 빼고 AC-16 테스트를 고칩니다. root T13 검증자는 AC-16 원문으로 불통과를 판정합니다.
- **최소 수정:**
  - AD-1·5·11에서 `[ADOPTED]`를 빼고 해당 SC ID를 명시합니다.
  - AD-5의 PAUSED 범위는 "SC-001 승인 전에는 publish 구현 착수 불가(원본 AC-16과 충돌)"로 Deferred 또는 Open에 blocker로 올립니다.

### 3. [high] `UNKNOWN`/`PREPARED`를 해소하는 command와 데이터가 없습니다
- **위치:** AD-5(L79), AD-3(L67), codebase §3·§5 API 표. product-flow §5.3과 §6 "결과 불명 → 원격 조회/운영자 대조"와 연결됩니다.
- **문제:** 막는 규칙(자동 재전송 금지, 가짜 성공 금지)만 있습니다. 해소에 필요한 것이 정의되지 않았습니다.
  - 운영자가 remote ID를 연결할지, "미생성 확인"을 기록할지
  - Graph에서 이름(job_id·operation_key)으로 자동 조회할지
  - 어떤 command·endpoint를 쓸지

  `resume_job`은 "journal 검사 후 202"뿐입니다. codebase §3은 UNKNOWN이 남은 revision의 편집도 금지합니다. 결국 timeout이 한 번만 나도 CAP-7을 완료할 경로가 없습니다.
- **충돌 예:** CLI는 `--remote-id`로 수동 연결하고, 웹은 Graph 조회로 자동 연결하고, resume은 계속 거부하는 식으로 세 경로가 따로 생깁니다. 이렇게 되면 BA-04/PQ07의 결과가 구현마다 달라집니다.
- **최소 수정:** AD-5에 다음을 추가합니다.
  - `reconcile_publish_operation(operation_key, resolution={remote_id|absent}, actor)` command를 둡니다.
  - 해소 결과를 journal에 append하며, CONFIRMED 또는 확인된 absent만 resume 대상이 됩니다.
  - 원격 조회는 Graph read-only 읽기로만 하고, 판정은 운영자 입력으로 합니다.
  - codebase API 표에 이 endpoint를 추가합니다.

### 4. [high] Model Files 원격 보관 lifecycle과 Image 도구 비활성화가 빠졌습니다 (provider·운영 dimension)
- **위치:** AD-10(L109), AD-3(publish journal만 다룸), Deferred L189("보관 동의는 H2"). 근거는 다음 문서입니다.
  - verification.md L65-67: Files는 "Uploaded files don't expire"이므로 ID·삭제를 추적하자는 제안
  - verification.md L35: Image의 search/shell이 기본 활성
  - implementation-contracts §10, BA-17
- **문제:** Spark·SAM은 `/v1/files` 업로드라는 원격 부작용을 만듭니다. 그런데 다음이 어디에도 없습니다. codebase 전체에서도 "Files"와 "삭제"가 검색되지 않습니다.
  - file ID의 소유자(adapter 사이 공유 여부)
  - crash 전에 ID를 보존할 journal
  - 삭제 시점(note 편집이나 resume은 다시 사용할 수 있음)
  - 삭제 실패 경고

  Deferred가 다루는 것은 "동의"뿐이고 메커니즘은 다루지 않습니다.
- **충돌 예:**
  - Spark adapter가 호출 직후 삭제하고 SAM adapter가 같은 ID를 재사용하면 404가 납니다.
  - 반대로 둘 다 따로 업로드하고 아무도 삭제하지 않으면 고객 영상이 영구 보관됩니다(INV-8·SC-008 의도 위반).
  - 업로드 후 ID 기록 전에 crash가 나면 orphan이 남습니다.
- **최소 수정:** AD를 하나 추가합니다.
  - job별 `remote_files` journal을 둡니다. 업로드 응답 직후 원자 기록하고, revision을 공유합니다.
  - 삭제는 pipeline이 소유합니다. 시점은 "해당 revision의 understand·track 완료와 job 종료 또는 명시 cleanup"입니다. 실패하면 warning을 남깁니다.
  - Image 요청에는 `enable_image_search`/`enable_web_search`/`enable_shell`=false를 고정합니다.
  - 보관 기간 값만 H2 Deferred로 남깁니다.

### 5. [medium] CAP-1의 음성 전사 위치와 사람 확인 단계가 정해지지 않았습니다
- **위치:** Capability Map L176(CAP-1에 voice adapter·stage가 없고 AD-11도 없음), Structural Seed의 stages(input·transcribe 없음), codebase §5 `POST /api/jobs`(CREATED 201, "실행과 별도"). product-flow §3은 "전사본을 텍스트로 확정하기 전에 보여 준다… 전사본이 근거 인용의 기준 문서"라고 합니다.
- **문제:** 전사는 유료 live 호출이고 H2 gate가 걸립니다. 그런데 어느 프로세스에서 실행하는지(HTTP 요청 안인지 worker인지), 어느 상태에서인지, 사용자 확정을 위해 멈추는 지점이 어디인지가 없습니다. AD-7의 note NFC codepoint 기준 snapshot이 언제 고정되는지도 이에 달려 있습니다.
- **충돌 예:** 웹은 create 요청 안에서 동기로 전사합니다(10분 음성인데 HTTP 120s timeout, run lock 없이 provider 호출). CLI는 pipeline 첫 단계에서 전사하고 확인 없이 진행합니다. 그 결과 EvidenceRef span의 기준 문서가 서로 달라집니다.
- **최소 수정:** CAP-1 행에 `adapters/voice.py`와 전사 단계를 넣고, AD-11을 연결합니다. 전사는 worker stage(run lock 아래)에서 실행합니다. 결과는 `CREATED`에서 "note 미확정"으로 멈추고, `confirm_note`(base_revision) commit을 한 뒤에만 understand로 넘어간다고 규정합니다.

### 6. [medium] 실행 mode가 revision이나 승인 대상에 묶이지 않아 fixture/replay 결과를 live로 게시할 수 있습니다
- **위치:** AD-11(L115: "run manifest에 mode를 고정"), AD-5(digest 포함·제외 목록에 mode 없음). 근거는 다음 문서입니다.
  - SPEC CAP-7: "fixture/replay 결과로 live 완료를 대체하지 않는다"
  - product-flow §1-5
  - acceptance §5
- **문제:** mode는 run 단위로만 고정됩니다. 그래서 이해·추적 run은 fixture나 replay로 하고, 나중에 publish run만 live로 실행할 수 있습니다. 이를 금지하는 규칙이 없습니다. 승인 digest에도 산출물의 mode 출처가 들어가지 않습니다.
- **충돌 예:** publish stage 구현자는 "현재 run이 live이고 H3를 통과"했는지만 검사합니다. 그러면 replay snapshot이나 mock 이해 결과로 만든 revision이 실제 PAUSED 광고가 됩니다. PQ06/§5의 증거 오염입니다.
- **최소 수정:** 각 stage artifact의 manifest에 생성 mode를 기록하고 digest에 포함합니다. live publish는 승인 revision의 모든 모델 산출 stage가 live일 때만 허용하고, 아니면 409로 거부합니다. 이 내용을 AD-11 Rule에 추가합니다.

## 그 밖의 finding (medium·low 5건)
- **[medium] AD-2/AD-4가 실행 중이나 게시 후의 편집 거부를 빠뜨렸습니다.** 스파인 memlog의 AD-2에는 "run_state로 편집거부"가 있었습니다. 그런데 스파인 Rule에는 worker commit CAS만 남았습니다. 편집 거부 규칙은 codebase §3·§4(L74·L85)에만 있습니다. 이 상태로는 publish 중 편집이 먼저 commit되어 원격 객체가 있는 revision이 대체될 수 있습니다. AD-4에 "run_state가 IDLE이 아니거나 해당 revision에 PREPARED/CONFIRMED/UNKNOWN operation이 있으면 content 편집·review·approve는 409"를 추가해야 합니다.
- **[medium] 승인 gate 판정과 정책 재검사를 다루는 AD가 없습니다.** CAP-2 행(L177)은 SAM parser용인 AD-6을 근거로 들고 있습니다. 반면 schema 재요청 1회, 최종 자막·엔드카드·CTA 정책 재검사(BA-02), approve와 publish 직전의 동일 검사는 AD에 없습니다. web의 버튼 활성화 조건과 서버 `approve`가 같은 predicate를 쓰도록 `policy`와 `application.approve`를 묶는 AD가 필요합니다.
- **[medium] PublishPlan의 정본이 정해지지 않았습니다.** account·Page·Graph 버전은 env(SPEC §2)에서 오고, 예산·destination은 job 입력에서 옵니다. AD-5는 이를 digest에 넣지만, 언제 revision에 snapshot하는지와 env가 바뀌었을 때 어떻게 할지가 없습니다. 이대로면 publish가 snapshot 계정을 쓰는 구현과 env 계정을 쓰는 구현으로 갈립니다. "승인 시 PublishPlan을 revision에 고정하고, publish 시 env와 다르면 거부"를 명시해야 합니다.
- **[low] AD-8의 재생성 열거에 CTA와 note 변경이 빠졌습니다.** CTA는 엔드카드에 그려지므로 6개를 다시 렌더해야 합니다(product-flow §4.4). note 변경은 이해 단계부터 다시 실행합니다(이 경우 SAM 재호출 비용이 생길 수 있습니다). fingerprint 규칙이 일반 원칙이긴 하지만, 열거만 보고 구현하면 CTA 변경 후 영상을 그대로 재사용할 수 있습니다.
- **[low] ffmpeg 핀 상태가 문서마다 다릅니다.** dependencies.md §4는 "정확한 ffmpeg 버전 고정은 아직 정하지 않았다"인데, 스파인 Stack은 9.0.2를 핀합니다. 실제 build가 핀과 다를 때 렌더를 거부할지, 기록만 할지 규칙이 없습니다.

## 확인했지만 문제가 없던 항목
- AD-6의 half-open 주장은 설치된 `meta_sam_parser/_object_prompt.py` docstring으로 확인했습니다.
- Stack 버전은 `pyproject.toml`, `uv.lock`, `.python-version`과 일치합니다.
- 고객 검증을 요구하는 조항은 다시 들어가지 않았습니다.
- 범위 축소는 없습니다.

**신뢰도:** 0.8. 모든 finding은 문서 원문을 대조해 나온 것입니다. 실행이나 런타임으로는 검증하지 않았습니다.
