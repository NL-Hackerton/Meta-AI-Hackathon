# 구현 경계 상세안

갱신: 2026-10-25. 스키마·순수 검증은 사용자 지시로 구현했으며 실제 사용 계약은 [schemas.md](../../../docs/architecture/schemas.md)에 있다. config·저장·worker·제품 API는 미구현이다. SC-001~SC-015는 루트 명세에 미반영이며 [Architecture Spine](../../planning-artifacts/architecture/architecture-AdLoom-2026-10-25/ARCHITECTURE-SPINE.md)의 AD-1~14를 후속 서비스 경계로 유지한다. 고객 검증은 요구하지 않는다.

## 1. 경계와 소유권

CLI/웹 → pipeline/stages → 순수 계획 함수·adapters → 파일/ffmpeg/Meta 구조를 유지한다. 웹의 생성·편집·승인도 같은 서비스를 사용하며 별도 상태 머신을 만들지 않는다. adapters는 요청·응답 변환만 담당하고 job/승인을 직접 쓰지 않는다.

| 소유 모듈 | 정본 데이터 | 책임 |
| --- | --- | --- |
| `config.py` | 실행 모드, 모델 ID, provider 설정 | 환경변수, stage별 live 게이트; 미확인 설정을 성공 기본값으로 대체하지 않음 |
| `schemas.py` | 경계 모델 | extra=forbid, finite 수치, 시간/좌표/문구/source reference 검증 |
| `jobs.py` | job·revision·artifact·승인·게시 journal | 단일 writer, 원자적 commit, stale revision 거부 |
| `pipeline.py` / stages | 단계 실행·의존성 | 실패 기록, 입력 digest 기반 재사용/무효화 |
| `crop.py` / render plan | geometry·timeline·overlays | 순수 계산; 파일 생성은 renderer에 한정 |
| adapters | 공급자 계약 | 인증·HTTP·파싱; workflow 승인/상태 변경 금지 |

job lock은 CLI/웹을 직렬화한다. 렌더/게시 중 같은 job 편집은 거부한다. 임시 파일→flush/fsync→같은 filesystem rename 후 manifest가 산출물을 참조하도록 commit한다. manifest 밖 임시 결과는 완료 증거가 아니다. process death로 영구 점유되지 않는 OS lock을 사용한다. [SC-003·005]

[SC-011] 웹 긴 작업은 동일 pipeline을 실행하는 로컬 worker로 처리한다. 한 앱 인스턴스의 동시 실행은 1개, 새 외부 queue는 없다. 생성 요청은 job ID와 202를 반환하고 UI는 manifest의 단계·완료 산출물·오류를 조회한다. RUNNING 중 요청은 중복 실행하지 않고 기존 job을 표시하거나 busy로 거부한다. 표시용 가짜 percent·예측 남은 시간은 만들지 않는다.

## 2. 공용 데이터 계약

원본에 빠진 필드는 SC 승인 후 추가한다. 비밀값은 아래 어떤 모델에도 저장하지 않는다.

| 모델 | 제안 필드와 의미 |
| --- | --- |
| `JobManifest` | schema_version, job_id, revision, state, last_success_state, failed_stage, error, artifact_manifest, execution_mode, created_at/updated_at, run_state |
| `ArtifactRecord` | job 내부 상대 path, bytes sha256, kind, stage, revision; 원격 signed URL·고객 경로를 로그에 노출하지 않음 |
| `MediaInfo` | 회전 적용 크기, duration, 원본 timebase/PTS, normalized fps/frame_count, audio 유무, source/normalized digest |
| `RenderPlan` | revision, 소스/폰트/설정 digest, timeline spans, 비율별 crop, overlays, 출력 profile, renderer fingerprint |
| `TimelineSpan` | source_id, source start/end, output start/end, 반복 번호; 반개구간 [start,end) |
| `ApprovalRecord` | job_id, revision, content_digest, approved_at, actor, channel |
| `PublishPlan` | 계정/Page, 통화/예산, Graph 버전, objective/optimization/billing/placement/일정, CTA/destination만 고정한 게시 설정. asset·thumbnail hash는 ApprovalSubject에서 가져오며 승인 digest는 publish command의 expected_approval_digest로 전달 |
| `PublishOperation` | operation_key, 요청 fingerprint, resource_kind, phase(PREPARED/CONFIRMED/FAILED/UNKNOWN), remote_id, safe error |
| `PublishResult` | campaign/adset IDs, hook별 video/creative/ad IDs, thumbnail hash, configured/effective 상태, 확인시각, 완료/부분 결과 |
| `EvidenceRef` | source_kind(note/video), source_digest, note start/end+정확 quote 또는 video start/end, 연결된 claim/scene ID |
| `ClaimReview` | claim_id, 표시문구, explicit/observation/inference, EvidenceRef 목록, pending/accepted/rejected, 검토 revision/actor |
| `TrackCandidates` | 응답의 기존 object ID와 trajectories, 대표 frame, selected_object_id; TrackResult는 선택된 trajectory로 도출 |

한 게시 revision에 campaign1/adset1/video2/creative2/ad2를 제안한다. 썸네일 수와 공유 여부는 승인 계획에 고정하고 hash로 재사용한다. fingerprint에서 토큰은 제외하되 실제 광고 계정·Page·예산 등 승인 내용은 포함한다. [SC-003·004·010·012]

## 3. 원본에 연결된 검토와 제한 편집

[SC-012] 제품의 차별성 가설은 자유 생성이 아니라 **결과의 근거를 보고 잘못된 부분을 고칠 수 있는 연결성**이다. 이를 객관적 진실 판정기·광고 정책 인증기로 표현하지 않는다.

- 장면 선택은 source asset digest와 timestamp에 연결한다. 결과 영상의 seek는 TimelineSpan을 통해 원본 구간으로 대응한다. 생성 엔드카드에는 존재하지 않는 원본 frame 링크를 만들지 않는다.
- 문구는 정확한 note span 또는 관찰 영상 구간에 연결하고 explicit/observation/inference를 구별한다. note quote는 문자 offset과 실제 substring이 일치해야 한다. 영상 범위는 normalized duration 안이어야 한다.
- 모델은 EvidenceCandidate의 구조와 reference 후보만 제안하고 accepted·approved를 설정하지 못한다. 구조 오류는 schema 실패, source ID/범위/quote의 의미 불일치는 근거별 invalid와 사유로 남겨 claim 승인을 차단한다. 사용자 편집의 잘못된 reference는 상태 변경 없이 거부한다. 오류 단위는 Architecture codebase §6을 따른다.
- 가격·할인·성능·효능·순위·보장 같은 검증 요구 주장은 명시된 note 근거 없으면 생성/승인 후보에서 차단한다. 근거를 모델이 만들어 채우지 않는다. 사용자가 명시 입력으로 추가해도 외부 사실 검증 완료가 아니라 사용자 제공 주장으로 남긴다.
- explicit·observation 사실형 주장과 고위험 주장은 사람의 개별 accepted가 필요하다. 모델은 accepted를 쓸 수 없고 출처 존재만으로 검토 상태를 바꾸지 않는다. 순수 주관적·창작 inference는 억지 근거 링크나 개별 accepted를 요구하지 않고 최종 승인에서 검토한다. 사실형·고위험 문구를 inference로 라벨만 바꾸어 차단을 우회하지 못하게 한다.
- 수정은 SAM 기존 object ID 선택, 선택 구간의 포함/제외·경계, 훅 후보 A/B 선택·문구, 본문·제목·자막에 한정한다. 자유 mask 그리기·임의 전환효과·범용 타임라인·무제한 prompt chat은 제외한다. 구간은 원본 시간순으로 정렬하며 새 겹침을 거부한다.
- 기존 “수동 object 선택 UI 제외”는 이 제안에서 교체한다. 최초 자동 선택은 최대 면적, 동률 최소 ID이고, 사용자는 반환된 후보만 바꿀 수 있다. 선택 후 같은 object ID를 유지하고 가림 뒤 다른 ID로 조용히 바꾸지 않는다.
- object 후보·원본 모델 응답을 보존하므로 선택 변경만으로 SAM을 다시 호출하지 않는다. object 변경은 crop→render, 구간/자막은 timeline→render, 훅은 overlay→render, 본문/제목은 policy→publish plan을 갱신한다. CTA가 카드에도 있으면 카드→render도 무효화한다.
- dirty 편집 초안은 현재 승인 revision과 분리한다. 저장 때 base_revision을 비교하고 새 revision을 commit한다. 필요한 재생성 동안 이전 미리보기는 “이전 결과”이며 승인 버튼을 막는다. 모든 현재 산출물이 준비돼야 재승인한다.

검토 상태는 정해진 유형·fixture 범위에서 검사할 수 있다. 일반 자연어의 모든 허위 주장을 탐지한다거나 완전한 fact checking을 제공한다고 보장하지 않는다.

## 4. 승인과 정책

content_digest는 schemas.ApprovalSubject의 명시 projection에서만 만든다. 6개 결과·게시 자산·문구·근거·검토·경고·fallback·origin_mode·PublishPlan을 포함하고 manifest_seq/ref·PublishResult·remote IDs·journal·runtime 상태·시각은 제외한다. canonical JSON·실제 bytes hash와 publish/resume/reconcile 기준값은 Architecture codebase §4.2가 정본이다.

1. 같은 lock 안에서 현재 revision·파일 hash·schema·정책·검토 상태를 검사한다.
2. block·필수 검토 pending/rejected·dirty·stale render가 있으면 승인하지 않는다. warn/degraded는 숨기지 않고 사람이 확인한다.
3. 게시 직전 동일 검사를 다시 수행한다. 승인 파일만 존재하거나 fingerprint가 다르면 외부 호출 전에 거부한다.
4. 실행 중 수정은 거부한다. 게시 뒤 내용 변경은 새 job이며 기존 원격 객체를 자동 활성화·수정하지 않는다.
5. 웹은 loopback bind, 명시적 POST, CSRF token/Origin 검사를 적용한다. GET·모델 응답·페이지 로드로 승인하지 않는다.

정책 검사는 실제 보이는 훅/본문/제목/CTA/엔드카드/자막에 적용한다. rewrite는 수정 제안이지 사실 검증이 아니다. 보장 문구를 지워도 근거 없는 효능 주장이 남을 수 있으므로 원문·수정안을 표시하고 재검사한다. Meta의 광고 심사를 대신하지 않는다. [SC-003·012]

## 5. 게시 복구

서버 생성 뒤 응답 유실 또는 로컬 ID 저장 전 crash는 이름의 job ID만으로 해결되지 않는다. exactly-once를 보장한다고 표현하지 않는다. [SC-004]

| 시점 | journal과 다음 행동 |
| --- | --- |
| 요청 전 | job/revision/mode/resource/hook operation key, 요청 fingerprint, PREPARED 기록 |
| 성공 응답 | remote ID와 CONFIRMED 원자적 기록 후 다음 단계 |
| 명시적 거부 | 확정 실패만 FAILED, 오류 종류에 따라 원본 retry 규칙 |
| timeout/연결 종료/요청 후 crash | UNKNOWN; 생성 POST 자동 재전송 금지 |
| 재개 | CONFIRMED 재사용. UNKNOWN·PREPARED는 공용 reconcile 명령으로 원격 ID를 확인·연결하거나 abandon한다. 검색 결과 없음으로 미생성을 선언하지 않으며 자동 재POST하지 않는다. |
| 전체 완료 | 광고2개·부모 객체 read-back, configured PAUSED와 승인 소재 대응 확인 후 PUBLISHED_PAUSED |

generic backoff가 결과 불명의 생성 POST를 반복하지 못하게 한다. provider idempotency는 해당 endpoint의 공식 보장이 있을 때만 적용한다. E_PUBLISH_PARTIAL에는 비밀 제거한 operation key와 reconciliation 필요 여부를 담는다.

[SC-001] PAUSED는 campaign/adset/ad 생성에만 강제한다. 영상·이미지·creative에는 무관한 status를 넣지 않는다. effective_status는 CAMPAIGN_PAUSED/ADSET_PAUSED일 수 있어 configured_status와 구분한다. 테스트 계정이라는 이름도 sandbox 보장은 아니다.

## 6. 실패·편집·중단 전이

정상 사업 상태열은 유지한다. FAILED 탈출은 실패 단계의 유효 입력과 재실행 성공으로 제한한다. [SC-005]

- 실패 시 last_success_state/failed_stage/input fingerprint/safe error를 저장한다. resume은 입력 digest를 확인하고 해당 단계를 실행한 뒤 목표 상태로 전이한다.
- 6개 렌더 파일과 manifest가 완전하기 전 RENDERED로 commit하지 않는다. 중간 파일을 새 결과로 표시하지 않는다.
- 수정은 승인 무효화·revision 증가 후, Architecture codebase §4.1의 rollback 상한과 현재 유효 산출물 완료 상태 중 더 이른 상태를 사용한다. 실패·중단 기록과 pending_stage를 보존하므로 본문 수정만으로 누락된 렌더를 건너뛰지 않는다. 재계산 예약 busy는 무변경409다.
- 제품 프롬프트 변경은 추적 이후를 무효화한다. 기존 후보 선택은 crop 이후만 무효화한다. 원본 영상 교체는 새 job을 제안한다.
- 게시 뒤 편집은 새 job으로 시작하며 과거 approval/publish 기록은 남긴다. 같은 job의 새 게시 revision fork는 제공하지 않는다.

[SC-011] 실행 제어 `run_state=IDLE/RUNNING/CANCEL_REQUESTED/INTERRUPTED`는 사업 상태와 별개다. 중단 요청 후 현재 단계가 정상 완료되면 검증된 산출물과 상태를 commit하고 다음 단계 전 IDLE로 멈춘다. renderer를 종료했다면 partial output은 commit하지 않고 마지막 완료 상태를 보존한다. 원격 요청 즉시 취소는 보장하지 않으며 확정된 원격 ID는 취소 여부와 무관하게 journal에 남긴다. 게시 이후 결과 불명의 중단·timeout은 UNKNOWN 확인 경로로 간다. 앱 재시작 때 살아 있지 않은 worker의 RUNNING은 INTERRUPTED로 표시하되 확정 산출물을 없애지 않는다.

## 7. 미디어 입력과 공급자 변환

MOV 허용을 유지하되 회전/VFR을 정규화한 MP4를 Spark/SAM/render의 공통 좌표·시간 기준으로 제안한다. 원본 bytes도 보존한다. VFR은 PTS를 읽어 CFR로 정규화하고 대응을 기록한다. 유효 표시 fps와30 중 작은 값을 기준으로 하되 모호한 fps는 임의 값 대신 오류/검토로 둔다. [SC-009]

- Voice: 동영상 전사는 audio/video를 동일0 기준으로 정규화한 MP4의 audio에서 mono PCM16 WAV24kHz를 추출한다. 설명 음성은 별도 worker input 단계에서 전사·사용자 confirm_note 후 정본으로 만든다. ENDPOINTING, languageBias=["Korean"], ms→s 변환을 적용하며 무오디오 영상 전사는 생략한다.
- SAM: 공식 meta-sam-parser0.1.0의 명시 frame index·object_id를 사용한다. raw wire의 포함 끝점은 parser가 half-open right/bottom으로 변환하므로 내부 폭/높이는 right-left/bottom-top이고 +1을 반복하지 않는다. confidence 누락을1.0으로 꾸미지 않는다. 완료·diagnostics를 검사한 뒤 box를 도출하며, parser 내부 mask 검증에 대한 입력 quota를 둔다.
- Image: output_format=png, 가능하면 base64 응답을 사용하여 CDN fetch 경계를 줄인다. 요청 size는 비율이므로 실제 결과를 검사·목표 해상도로 변환한다.
- Spark: upload file ID와 Responses text.format schema를 사용한다. schema와 key moment 시간 범위·중복 검사는 별개다.

실제 경로를 resolve하여 data root 밖 symlink/traversal을 거부한다. 외부 입력은 명시 import에서 data 내부로 복사한 뒤 adapter/ffmpeg에 전달한다. 영상·오디오 임시 파일도 data 내부다. remote playlist/protocol·HTTP redirect가 허용 전송 경계를 우회하지 못하게 한다. [SC-008·009]

## 8. 크롭 우선순위

1920×1080의 9:16 최대 crop 폭은 연속 좌표607.5px이므로 bbox폭800px을 담을 수 없다. 작은 대상도 급격히 이동하면 완전 포함과 이동상한이 충돌한다. [SC-002]

1. 원본 내부 최대 crop 크기를 구한다. 실수 geometry와 고정 sampling 반올림 규칙을 사용하고 최종 출력은 지정 해상도다.
2. **보간 전** 유효 bbox 수/frame_count로 coverage를 구한다. coverage<0.6은 중앙 crop/degraded, all-null에는 보간을 적용하지 않는다.
3. 내부 null은 선형 보간, 양끝은 가장 가까운 bbox다. bbox는 finite·양의 크기·frame bounds를 검증한다.
4. 첫 위치는 대상 중심을 원본 경계 안으로 clamp, 이후 목표 중심은 alpha0.15로 평활한다.
5. 원본 경계·이동상한 허용 영역과 제품+여백·피사체 안전 영역을 만족하는 위치의 교집합에서 평활 목표에 가장 가까운 위치를 선택한다.
6. 교집합이 없으면 원본 경계·이동상한을 우선하고 clipped/safe_area_violation 원인을 표시한다. 포함·6%여백을 거짓 성공으로 보고하지 않는다. 장면 전환 crop reset은 별도 결정 전 임의 허용하지 않는다.
7. 텍스트는 안전 영역을 지키도록 줄바꿈/크기 조정하거나 검증 실패한다. 피사체는 자유도가 없을 수 있어 위반 표시·사람 검토가 필요하다.

MAX_STEP_PX의 원본 미정값은 실제 픽셀 좌표·축별 제한으로 통일하는 제안이며 수치는 fixture/제품 영상 평가에서 확정한다. AC-06은 feasible 포함 검증과 infeasible 경고 검증으로 분리한다. 중앙 크롭 대비 품질 측정은 독립 정답 bbox를 사용하고 SAM 예측을 정답으로 재사용하지 않는다.

## 9. 시간축과 렌더

[SC-006] 총30초는 엔드카드2초 포함, 본 영상은 최대28초로 제안한다. 선택 구간은 시간순 뒤쪽부터 자른다. 최소 본영상6초를 명료화하고 3초 입력은 원본 앞부분 반복으로 채워 총8초가 된다. 카드는 별도 정지 이미지 구간·무음이다. 이 정의는 승인 전 원본의 확정 해석이 아니다.

source[s,e)가 output offset o에 배치되면 자막[a,b)의 교집합[lo,hi)=[max(a,s),min(b,e))를 구해 비어 있지 않을 때 output[o+lo-s,o+hi-s)로 옮긴다. 반복도 각각 변환한다. 오디오는 동일 편집/반복/자르기를 적용한다. 훅은 최종[0,3)에만 표시한다. glyph 누락·긴 문구·레이아웃 초과는 화면 밖 출력 대신 명시 검증 실패다.

[SC-007] 콘텐츠 자산은 원본/사용자 사진/Muse Image로 제한하고 문자·도형·단색·허용 이미지의 기하 변환은 renderer layer로 구분한다. 생성 동영상·외부 URL 영상은 금지하고 synthetic는 fixture에서만 사용한다.

[SC-009] 결정론의 동일 입력은 원본·모델 결과 snapshot·폰트 bytes·RenderPlan·설정·ffmpeg build fingerprint다. 모델 재호출·서로 다른 OS/build의 같은 픽셀을 보장하지 않는다. 프레임 해시는 순서·크기·고정 pixel format·decoded bytes를 포함한다. 오디오는 별도 codec/duration 검사다. -threads1/bitexact만으로 환경 간 결정론을 주장하지 않는다.

## 10. live·보관·검증 경계

LIVE=1과 H2/H3 및 해당 task LIVE-OK를 모두 검사한다. run은 Marketing 자격 없이 모델 작업까지 가능하고 publish 직전에 Marketing 설정을 확인하는 stage-scoped 구성을 제안한다. live 자격/권한 오류를 fixture 성공으로 바꾸지 않는다. [SC-008]

Standard는 훈련 사용 제외이지 무보관이 아니다. Model Files ID와 마지막 사용을 기록하고 의존 호출 종료 후 삭제 요청·실패 경고를 남긴다. Image 검색/shell은 명시 비활성화안을 유지한다. Marketing 소재 보관과 Model Files 임시 보관을 혼동하지 않는다. 실제 보관 기간·동의는 H2/H3에서 확정한다.

[SC-013] 고객 모집·인터뷰는 필요 없다. 직접 촬영/적법한 실물 자산과 합성 경계 사례를 개발/고정평가로 나누어 검사한다. 평가용 source와 reference labels는 모델의 출력과 독립적으로 고정하고 실제 평가 전 결과를 기입하지 않는다. live·fixture·저장된 실결과 replay의 mode와 시각을 표시한다. replay는 네트워크 없는 재검토 기능이지 신규 live 생성 성공이 아니다. 제품 범위의 실제 PAUSED 광고2개는 반드시 H3 뒤 실제 계정에서 확인한다.
