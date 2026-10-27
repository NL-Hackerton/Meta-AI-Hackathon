# AdLoom SPEC_CHANGES

에이전트는 `SPEC.md`를 직접 고치지 않고 여기에 제안만 남깁니다. 사람이 검토해 `SPEC.md`에 반영하거나 반려합니다.

## 형식

```
### SC-001 · 제목
- 제안자/날짜:
- 관련 섹션·태스크:
- 근거: (공식 문서 링크·발췌, 또는 실패 로그)
- 제안:
- 상태: 제안 | 반영 | 반려
```

---

### SC-001 · PAUSED 적용 대상과 행동 검증 정정
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §1 INV-2, §4.6, AC-16, T08·T13
- 근거: [Campaign](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-campaign-group), [Ad Set](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-campaign), [Video Data](https://developers.facebook.com/docs/marketing-api/reference/ad-creative-video-data/). 업로드와 creative는 campaign/adset/ad와 같은 status 계약이 아니다.
- 제안: PAUSED 강제는 campaign/adset/ad 생성에 한정한다. 다른 요청에는 무관한 status를 추가하지 않는다. configured/effective 상태를 분리한다. 소스 단어 grep 대신 실제 요청 경계의 활성화 거부·PAUSED payload·read-back을 검증한다.
- 상태: 제안

### SC-002 · 크롭의 불가능 조건과 품질 표시
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §4.3, AC-06·07·08·09, T03
- 근거: 1920×1080의 9:16 최대 crop 폭은 607.5px이므로 폭 800px bbox를 담을 수 없다. 급격한 이동에서는 포함 조건과 MAX_STEP_PX도 충돌한다.
- 제안: 원본 경계·이동상한을 hard constraint로 두고 feasible 위치 교집합 안에서 평활 목표에 가장 가까운 crop을 선택한다. 교집합이 없으면 clipped/safe_area_violation을 표시한다. coverage는 보간 전에 계산하고 all-null은 중앙 crop한다. MAX_STEP_PX의 단위·거리 정의·수치를 확정한다. AC-06을 feasible 포함 검증과 infeasible 경고 검증으로 나눈다.
- 상태: 제안

### SC-003 · 승인 대상 fingerprint와 최종 정책 검증
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: INV-3, §3, §4.6, AC-05·15, T02·T04·T08·T14
- 근거: 승인 파일 존재만 확인하면 승인 후 영상·카피·destination·예산·계정이 바뀌어도 게시할 수 있다. 정책 검사가 Understanding만 대상으로 하면 수정된 최종 문구를 놓친다.
- 제안: approval에 job/revision/content_digest를 기록하고 게시 직전 실제 파일·payload digest를 다시 검사한다. 최종 화면 텍스트 전체를 재검사하며 block이면 승인·게시 모두 거부한다. job lock으로 편집·승인·게시를 직렬화한다. 웹은 loopback·명시적 POST·CSRF 검사를 적용하고 승인과 publish를 분리한다. 순화 제안을 사실 검증·정책 승인으로 간주하지 않는다.
- 상태: 제안

### SC-004 · 게시 결과 불명과 중복 생성 방지
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §4.6·4.7, AC-17, T08·T13
- 근거: 원격 생성 뒤 응답 유실 또는 ID 저장 전 crash이면 로컬 ID가 없다. job_id가 들어간 이름만으로 중복 생성 방지가 보장되지 않는다.
- 제안: 요청 전 operation key/fingerprint/PREPARED를 journal에 기록한다. ID 확인 시 CONFIRMED, 결과 불명은 UNKNOWN으로 두고 자동 생성 재전송을 막는다. 재개 시 원격 대조·운영자 확인으로만 ID를 연결한다. 기존 오류 재시도도 생성 결과가 불명하면 중단한다. 이 동작을 exactly-once 보장으로 표현하지 않는다.
- 상태: 제안

### SC-005 · 실패 재개와 편집 전이 명시
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §3, T02·T06·T09·T14
- 근거: 원본은 표 외 전이를 금지하지만 FAILED 탈출 전이가 없다. 수정 요청에서 즉시 RENDERED로 전이하면서 실제로는 재렌더해야 한다. 입력·제품·카피 변경이 모두 조립만 재실행해서 해결되지는 않는다.
- 제안: last_success_state/failed_stage/input fingerprint를 저장하고 유효 입력을 검증한 뒤 해당 단계 재실행 성공 시 목표 상태로 전이한다. 수정은 승인 무효화→revision 증가→영향 단계 재실행→RENDERED→AWAITING_APPROVAL 순서다. 원본 영상 교체는 새 job, 게시 후 편집은 신규 게시 revision으로 분리한다.
- 상태: 제안

### SC-006 · 엔드카드 포함 길이와 편집 시간축
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §4.4·4.5, AC-11·13, T07
- 근거: 선택 구간 합계 30초에 2초 카드를 덧붙이면 32초다. source 자막 timestamp는 구간을 자른 출력의 시간과 다르다. 3초 입력을 원본 앞부분으로 한 번 채워도 6초가 되지 않는다.
- 제안: 총 30초에 카드 2초를 포함하고 본 영상 상한은 28초로 둔다. 최소 본 영상 6초를 명시하고 부족분은 허용 원본 구간 반복으로 채운다. source→output timeline map을 만들어 자막·오디오를 같은 구간으로 자르고 이동한다. 카드 구간은 무음, 훅은 최종 [0,3)초다.
- 상태: 제안

### SC-007 · 허용 콘텐츠와 renderer 레이어 구분
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: INV-1, §4.4·4.5, AC-14, T01·T07
- 근거: 원본의 모든 프레임 출처 제한을 픽셀 단위로 해석하면 명시적으로 허용한 문자 오버레이·단색 엔드카드·합성 테스트 영상과 충돌한다.
- 제안: 실제 콘텐츠 자산은 원본/사용자 사진/Muse Image만 허용하고 문자·도형·단색은 renderer layer로 구분한다. synthetic 영상은 테스트 fixture에서만 사용한다. 생성 동영상·외부 URL 영상의 사용 금지는 유지한다.
- 상태: 제안

### SC-008 · live 승인과 고객 파일 보관 경계
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: INV-6·7·8, §5, H2·H3, T01·T05·T10~T13
- 근거: 원본 팩토리는 LIVE+키를 설명하지만 live 테스트는 별도 사람 LIVE-OK를 요구한다. [Files](https://dev.meta.ai/docs/file-handling)는 업로드 파일이 만료되지 않음을 명시한다. [Image](https://dev.meta.ai/docs/image-generation)는 내부 검색/shell 기능 기본 활성화를 설명한다.
- 제안: LIVE와 해당 사람 게이트를 모두 검사하고 stage별 자격증명을 검증한다. 고객 파일 경로·임시 파일·전송 host/redirect를 통제한다. Standard를 무보관으로 설명하지 않는다. Model Files 삭제 시점·실패 기록을 정책화하고 Image 검색/shell을 비활성화한다. 실제 보관 기간·동의·비용 한도는 H2/H3 결정 대상으로 둔다.
- 상태: 제안

### SC-009 · 미디어 정규화와 실제 API 변환
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §4.1·4.3·4.4·4.5·5, INV-5, T06·T07·T10~T12
- 근거: [Spark 영상](https://dev.meta.ai/docs/video-understanding)은 MP4, [Voice](https://dev.meta.ai/docs/speech-to-text)는 mono PCM16 WAV를 사용한다. [SAM](https://dev.meta.ai/docs/sam/reading-segmentation)은 box 직접 반환·명시 frame/object ID를 제공한다. [Image](https://dev.meta.ai/docs/image-generation)의 size는 정확한 해상도가 아니다.
- 제안: 회전/VFR을 정규화한 공통 MP4를 Spark/SAM/render의 좌표·시간 기준으로 사용한다. Voice WAV 추출·ENDPOINTING·ms→s 변환, Image PNG 지정·resize, SAM box 파싱과 객체 선택을 명시한다. 결정론의 동일 입력에 모델 결과 snapshot·폰트·ffmpeg build를 포함하고 환경 간 무조건 동일 hash를 요구하지 않는다.
- 상태: 제안

### SC-010 · 누락된 공용 계약과 태스크 선행 관계
- 제안자/날짜: BMAD 검토 / 2026-10-23
- 관련 섹션·태스크: §2·4·8, T01·T02·T06·T07·T08·T11·T14
- 근거: PublishPlan·ApprovalRecord·RenderSpec은 참조만 있고 정의가 없다. T07은 T03만 선행하지만 Understanding/EnrichResult/job commit 경계가 필요하다. T11의 마스크→박스 구현은 공식 box 응답과 불필요하게 겹친다.
- 제안: schemas에 job/artifact/approval/publish/timeline 공용 계약을 먼저 확정한다. T07의 순수 렌더 부분과 T06 이후 통합 검증을 구분하고 T08의 승인 digest/정책 계약 선행을 명시한다. T11은 box 파싱/객체 선택/프레임 정렬로 변경한다. 새 태스크를 무조건 늘리지 않고 기존 T00~T16에 반영한다.
- 상태: 제안

### SC-011 · 웹 전 과정과 제품 완결 경험
- 제안자/날짜: BMAD 기획 보완 / 2026-10-24
- 관련 섹션·태스크: §1 웹 범위, §2 구조, T06~T09·T14
- 근거: 사용자 직접 지시 — 고객 검증은 불가능하므로 제품 완성도를 중심으로 기획 보완. 기존 웹은 미리보기·승인만 제공하므로 심사자가 CLI 도움 없이 생성·수정·복구를 경험할 수 없다.
- 제안: FastAPI 단일 HTML에서 만들기→검토·수정→승인·내보내기/실제 PAUSED 게시를 완결한다. CLI와 같은 서비스·job을 사용하고 새 frontend framework·DB·작업 큐·공개 SaaS는 추가하지 않는다. 진행 단계·실패·재개·키 없음·dirty/stale revision·부분 게시를 실제 상태로 표시한다. 최종 6개 영상과 실제 광고 2개 범위는 유지한다.
- 상태: 제안

### SC-012 · 원본에 연결된 검토와 제한 편집
- 제안자/날짜: BMAD 기획 보완 / 2026-10-24
- 관련 섹션·태스크: §4.2·4.3·4.5, T01·T03·T04·T06·T07·T14, CAP-9
- 근거: [Meta 2026-10-06 발표](https://www.facebook.com/business/news/advertising-week-new-york-2026)는 훅·자막·엔드 장면 편집과 승인 흐름을 이미 설명한다. 단순 생성·승인만으로 차별성을 주장하지 않고 원본 근거·수정 영향·승인 내용의 연결을 제품에서 확인할 수 있어야 한다.
- 제안: 장면은 asset digest+timestamp, 문구는 정확한 note span 또는 관찰 구간에 연결한다. 명시 입력·관찰·추론을 구분하며 출처 링크를 진실 보증으로 표시하지 않는다. 가격·할인·효능·성능 등 검증 요구 주장은 명시 입력 없으면 생성·승인을 차단한다. SAM이 반환한 기존 object ID 후보 선택과 구간·훅·카피·자막 편집만 제공하고 변경 후 영향 범위 재생성·승인 무효화를 연결한다. 기존 상세안의 수동 object 선택 비목표는 이 제안에서 교체하며 임의 mask 편집은 계속 제외한다.
- 상태: 제안

### SC-013 · 고객 검증 없는 품질 입증과 구현 순서
- 제안자/날짜: BMAD 기획 보완 / 2026-10-24
- 관련 섹션·태스크: §6·8·9, T00~T16, H1·H2·H3·H4
- 근거: 고객 인터뷰·실사용자 검증 불가라는 사용자 제약. [공식 대회](https://dev.meta.ai/events/global-hackathon)의 공개 Indie 기준은 창의성·기술적 도전성·작동 여부이며, 고객 모집은 공개 기준의 필수요건으로 명시되어 있지 않다. 세부 규정은 별도 확인한다.
- 제안: 실제 고객/점포 확보를 완료 gate에서 제거하고 직접 촬영 또는 적법 사용 권리의 실물 영상으로 T15를 검증한다. 12개 미디어 사례(합성8·실물4)를 개발6/고정평가6으로 분리하고, 중앙 크롭 대조·출처 검토·가독성·자막·편집·승인·실패 복구·실연동·초기 실행의 PQ01~PQ10을 추가한다. 모든 결과는 미실측 목표로 시작하고 실패 사례·미검증 항목도 보고한다. 웹 vertical slice와 provider 확인을 앞당기고 마지막 2일은 품질·리허설 중심으로 둔다. 실제 PAUSED 게시와 H1~H4는 제거하지 않는다.
- 사전 개발 경계: 원본 H1은 T16 gate지만, 보완안에서는 기존 코드·개발 시작 시점 규정 확인도 실행 선행으로 둔다. 확인 전에는 문서·권리 확인·데이터 설계·환경 목록만 준비하고 제품 코드·합성 생성기는 공식 허용 시점부터 시작한다.
- 상태: 제안

### SC-014 · 아키텍처 기준선과 공식 재사용 코드
- 제안자/날짜: 아키텍처 설계 / 2026-10-25
- 관련 섹션·태스크: §2·3·4·5·8, T00~T16
- 근거: 사용자 직접 요청 — 코드베이스 아키텍처 설계 및 웹 베이스라인 확보. [Meta 공식 SAM client](https://dev.meta.ai/docs/sam/client-libraries)는 Python parser와 이미 정규화된 half-open 좌표를 제공한다. pin·source·라이선스·실제 smoke는 docs/architecture와 third_party에 기록한다.
- 제안: Python3.12.15·uv lock modular monolith, 공용 command, 원자 head/불변 artifact, data-root worker1개와 READY/GO·짧은 lock을 사용한다. revision/seq·ApprovalSubject·mode·게시/remoteFiles journal, 음성 확정·편집 rollback·reconcile·cleanup 경계를 AD-1~14와 codebase companion에 고정한다. official SAM parser와 HTTPX/SSE를 사용하며 half-open 좌표에 +1을 반복하지 않는다. 라이브러리 이전의 body/SSE quota와 예외 cause 분류를 명시한다.
- 확보 범위: 사용자가 요청한 외부 dependency baseline·source archive·폰트는 로컬 확보 및 제한된 smoke 확인. 이는 원본 기능 계약 반영, T00~T16 완료, H1 허용 확정, live 호출 승인이 아니다. 무거운 FastAPI full-stack 템플릿과 Hello World 생성기는 채택하지 않는다.
- 상태: 제안

### SC-015 · 스키마 구현의 내부 데이터 규약
- 제안자/날짜: 스키마 구현 / 2026-10-25
- 관련 섹션·태스크: §4·5, T00·T01 및 후속 모듈 계약
- 근거: 사용자 직접 요청 — 아키텍처 확인 후 스키마부터 구현. `src/adloom/schemas.py`, `tests/test_schemas.py`, docs/architecture/schemas.md의 실행 결과.
- 명료화: 내부 시간은 정수 microseconds·반개구간, fps는 기약분수, 설명은 NFC codepoint, 컬렉션은 immutable tuple로 통일한다. raw JSON과 decode한 dict를 모두 받되 수치 coercion은 거부한다. Brief의 파일 길이는 pure MediaInfo/InputBundle로 검증하며 실제 probe는 후속 입력 서비스가 담당한다.
- 경계: HookId를 안전한32자 slug로 제한하고 journal key는 dot 구분+_shared를 사용한다. 반복은 짧은 본영상의 명시 padding만, source video는 normalized1개만, Image fallback은 Image 출처만 허용한다. PAUSED 설정·mode·승인 projection·실패 재개 metadata를 검증한다. 미확인 live CTA/objective는 명시 MarketingProfile 입력으로 남긴다.
- 구현 상태: 사용자 지시에 따른 스키마 범위와 최소 검사 환경 구현·51개 회귀·JSON/ASGI smoke 완료. root SPEC의 필드 표·T01 config/LIVE gate·나머지 서비스·H1~H4를 완료 처리하지 않는다.
- 상태: 제안

### SC-016 · 공개된 Official Rules와 사람 게이트 갱신
- 제안자/날짜: 재개 점검 / 2026-10-27
- 관련 섹션·태스크: 원본 7절·9절, H1·H2·H4, T16
- 근거: [Meta 행사 페이지](https://dev.meta.ai/events/global-hackathon)는 여전히 공개 예정이라고 안내하지만, 연결된 [Official Rules 및 Event Waiver](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver)의 동적 본문에서 규정 전문을 확인했다. 페이지 하단 날짜는 October 25, 2026이며 실제 최초 공개 시점은 확인하지 못했다.
- 심사 기준: “Impact (30%)”, “Use of Meta AI Tooling (25%)”, “Technical Depth & Execution (20%)”, “Demo (25%)”를 명시한다. 참가 신청 평가와 프로젝트 심사를 구분하며, 메인 페이지의 트랙별 소개만으로 프로젝트 심사표를 대체하지 않는다.
- 허용 모델: 규정은 “Muse Spark, Glimmer, SAM 3, and any other Meta AI products identified on the Event page”를 명시한다. 행사 페이지에는 Muse Spark series·Muse Image·SAM 3.1·Meta open weights가 있다. API의 정확한 모델 ID·Muse Voice 사용 범위·한국 계정 접근은 이 문구만으로 확정하지 않는다. INV-1·INV-4를 변경하거나 live를 승인하지 않는다.
- 기존 코드: “Participants may also include open source software or hardware, provided applicable open source licenses are followed and the Submission enhances or builds upon the underlying open source product.” 라이선스를 준수하고 기존 OSS를 확장하는 사용은 허용한다. 대회 전 작성한 자체 코드의 허용 여부·개발 시작 시점 제한·별도 공개 의무는 확인한 규정 본문에 명시되지 않았다. 기존 스키마와 외부 코드의 사용 범위를 참가자 안내 또는 주최 측 답변으로 확인한다.
- 권리·참가 조건: 참가 승인, 만 18세 및 거주지 성년 요건, 제외 대상 여부, 팀 대표 권한을 참가자가 확인한다. Indie 팀은 최대 4명이다. 참가자는 제출물 소유권을 유지하지만 주최 측에 영구적·취소 불가·전 세계·무상·비독점 이용권을 부여하며, 자료의 비밀유지도 보장되지 않는다. 약관 수락·서명은 수행하지 않았다.
- 제출: 규정이 지정한 [제출 포털](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit)은 비로그인 브라우저에서 로그인 화면으로 이동했다. 데모 영상 길이·언어·파일 형식·저장소 공개 여부는 확인하지 못했다. 행사 페이지의 11월 4일 21:00 ET를 America/New_York 기준으로 계산한 결과는 11월 5일 11:00 KST로 원본 마감과 같다.
- 비용: waiver가 연결한 `Meta Model API: Global AI Developer Hackathon Credit Terms`의 1.2·3.5·3.6·3.7·3.8을 확인했다. Model API 이용에는 유효한 결제 수단이 필요하고, 적용된 $150 크레딧은 소진 또는 계정 종료까지 유지되며 소진 후 사용료는 결제 수단으로 청구된다. 크레딧 신청·사용은 대회 참가나 심사에 필수가 아니다. waiver의 “valid for a 10-day development window”와 유효기간 표현이 달라 Credit Terms의 크레딧 관련 우선 조항을 함께 확인해야 한다.
- 제안: 원본 9절의 규정 미공개 항목을 공개 원문·심사 배점·OSS 조건으로 갱신하되 사전 자체 코드·제출 양식은 미확인으로 분리한다. H1은 원문 확인과 참가자 수락을 구분하고, H2는 결제 수단·초과 사용 비용 한도·데이터 전송/보관 동의를 확인한다. H3는 실제 계정 권한·광고 목적·Graph 버전·예산·일정 및 사용자 실행 승인을 유지한다. H4는 로그인 후 양식 확인과 직접 촬영·제출을 유지한다.
- 상태: 제안

### SC-017 · 부분 진행 태스크의 재개 규칙과 구현 기준 확정
- 제안자/날짜: 재개 점검 / 2026-10-27
- 관련 섹션·태스크: 원본 4절·7절, T00~T09, SC-015
- 근거: TASKS의 T00·T01은 IN_PROGRESS이고 DONE인 태스크가 없다. 상태표를 읽어 선행 조건을 계산한 결과 선택 가능한 TODO는 0개였다. 원본 7절은 이 경우 종료 보고를 요구하며 IN_PROGRESS 재개 절차를 정의하지 않는다.
- 구현 기준 차이: 원본 4절은 초(float)·리스트를 사용하지만 기존 `schemas.py`는 정수 microseconds·반개구간·immutable tuple을 사용한다. SC-015는 스키마 구현 요청의 범위를 기록했으며 후속 서비스 계약까지 원본에 반영한 승인은 아니다. 원본의 실패 재개·크롭·렌더·게시 계약에도 SC-001~010의 미반영 제안이 남아 있다.
- 제안: 이미 진행 중인 태스크를 재개할 수 있도록 선택 규칙을 명시하고 T00→T01→선행 완료된 첫 TODO 순서를 적용한다. 후속 서비스에 적용할 스키마·전이·렌더·게시 계약은 관련 SC별로 채택 또는 반려한 뒤 확정한다. 기존 구현을 삭제하거나 두 번째 스키마 체계를 추가하는 방식으로 차이를 숨기지 않는다.
- 경계: 이번 점검은 T00/T01을 TODO나 DONE으로 임의 변경하지 않으며 원본 SPEC·제품 코드·테스트를 수정하지 않는다. 재개 규칙과 구현 기준이 확정되면 태스크별 실패 테스트→최소 구현→make check·INV→실행 검증→로컬 커밋 순서로 진행한다.
- 상태: 제안

## 상세 설계와 확인 자료

- [BMAD kernel](_bmad-output/specs/spec-adloom/SPEC.md)
- [구현 계약 상세안](_bmad-output/specs/spec-adloom/implementation-contracts.md)
- [수용·진행 계획](_bmad-output/specs/spec-adloom/acceptance-plan.md)
- [공식 API 확인 장부](docs/api_notes/verification.md)
- [코드베이스 아키텍처](_bmad-output/planning-artifacts/architecture/architecture-AdLoom-2026-10-25/ARCHITECTURE-SPINE.md)
- [재사용 baseline 확인](docs/architecture/baseline-verification.md)
- [스키마 구현 계약](docs/architecture/schemas.md)

위 제안은 원본에 반영되지 않았다. 고객 검증 불가·제품 완성도 우선은 사용자가 정한 기획 조건이며, 구체적 SC 계약과 루트 SPEC.md·TASKS.md의 정의·상태는 별도 승인·반영 전까지 유지한다.
