# Meta API 계약 확인 장부

확인일: 2026-10-23. 범위: 공식 문서 읽기. **계정 접근·키 확인·API 실호출은 수행하지 않았다.** 아래 사실은 제품 코드가 작동한다는 증거가 아니다. 원본 §9의 미확인 항목을 이 장부로 좁히되 원본 수정은 `SPEC_CHANGES.md` 승인 절차를 따른다.

## 1. 어댑터별 확인 사실

### Spark — 영상 이해와 구조화 출력

- 기본 URL `https://api.meta.ai/v1`, Bearer `MODEL_API_KEY`, Standard `muse-spark-1.3`은 [개요](https://dev.meta.ai/docs/overview)에 명시되어 있다.
- [영상 가이드](https://dev.meta.ai/docs/video-understanding)는 MP4 업로드를 설명한다. [Files](https://dev.meta.ai/docs/file-handling)에 multipart `purpose=user_data`, `file`을 보내고 반환된 ID를 user message의 `input_file.file_id`로 참조한다. `input_video`도 별도 지원 형식이다.
- Responses의 구조화 출력은 `text.format={type:"json_schema",name,schema,strict}`이다. Chat Completions의 `response_format`과 혼용하지 않는다. 공식 경고: “A parameter from the other endpoint does not configure structured output.” [구조화 출력](https://dev.meta.ai/docs/structured-output), [Responses schemas](https://dev.meta.ai/docs/api-reference/responses/schemas).
- 공통 Files 한도는 인라인 50,000,000 bytes, 업로드 1,073,741,824 bytes다. 이것을 Spark의 별도 영상 길이 제한으로 해석하지 않는다. 45초는 제품의 잠정 제한이다.
- [모델 문서](https://dev.meta.ai/docs/models)는 Spark 1.3의 음성 이해가 완전 지원되지 않는다고 경고한다. INV-4를 유지하고 음성 전사는 Voice로 처리하는 원본 방향을 유지한다.
- 내부 `Understanding`은 provider 응답 envelope를 변환한 결과다. JSON schema 외에도 key moment의 duration·중복·순서를 내부에서 검증해야 한다.

### SAM — 추적과 좌표

- [요청 가이드](https://dev.meta.ai/docs/sam/segmenting): `model=sam-3.1`, 사용자 message에 `input_text`와 `input_video.file_id`, `stream=true`; confidence가 필요하면 `metadata.include_confidence="true"`다. 문자열이며 boolean이 아니다.
- MP4/MOV, H.264/H.265/MPEG-4, 최대 15,000프레임, 영상 프레임당 최대 16개 객체가 문서상 한도다. 6단어 프롬프트는 제품 규칙이지 확인된 API 한도가 아니다.
- [응답 문법](https://dev.meta.ai/docs/sam/reading-segmentation): `response.output_text.delta`의 `<Nf>object_id<|box;...|><|mask;...|>`를 파싱한다. JSON bbox 배열을 기대하면 안 된다.
- **box를 직접 제공하므로 크롭을 위해 마스크에서 박스를 계산할 필요가 없다.** raw wire의 `w,h`는 frame 크기이고 포함 끝점은 `x2-x1+1`, `y2-y1+1`로 변환한다. 2026-10-25 선정한 공식 `meta-sam-parser==0.1.0`은 이미 half-open `right/bottom`을 반환하므로 어댑터에서는 `right-left`, `bottom-top`을 사용한다. +1을 다시 더하지 않는다.
- frame index는 누락·역순이 가능하고 object ID는 sparse하다. 줄 순서를 frame index로, 배열 위치를 object ID로 쓰지 않는다.
- zero-match는 빈 출력으로 정상 완료한다. 가림·화면 이탈 이후 객체 동일성은 보장하지 않는다. mask는 base85이며 COCO RLE/base64라고 가정하지 않는다.
- T11의 “마스크→박스 변환”을 공식 parser 재사용·대상 선택·좌표/프레임 정규화로 정정하는 SC-009·010·014를 제안한다. [공식 client libraries](https://dev.meta.ai/docs/sam/client-libraries)와 [확보·실행 증거](../architecture/baseline-verification.md)를 따른다. parser는 내부 mask 검증을 수행하므로 비용·quota가 없어지는 것은 아니다.

### Muse Image — 이미지 형식과 후처리

[이미지 가이드](https://dev.meta.ai/docs/image-generation):

- `/v1/images/generations`에 `model=muse-image-1.0`, `prompt`, `n`, `size`, `response_format`, `output_format`을 사용한다. `n`은 1~10이다.
- 기본 이미지 형식은 WebP다. 내부 PNG 계약에는 `output_format="png"`를 명시한다.
- `size`는 **정확한 픽셀 크기가 아니라 종횡비**를 설정한다. 정확한 출력 해상도는 후처리로 맞춘다. 16:1을 초과하는 비율은 허용되지 않는다.
- 기본 응답은 `data[].b64_json`; URL 모드는 `data[].url`의 임시 서명 URL이다. base64 방식은 별도 CDN fetch 허용 문제를 줄인다.
- 편집 raw JSON은 `images` 배열, 각 항목의 `image_url` 또는 `file_id` 하나를 사용한다. SDK multipart 형식과 혼동하지 않는다.
- 이미지·웹 검색과 shell이 기본 활성화된다. `tool_enablement.enable_image_search`, `enable_web_search`, `enable_shell`을 false로 지정하는 개인정보 경계안을 SC-008에서 제안한다.
- 한국어 prompt/한글 글자 품질을 검증하지 않았다. 문자를 코드로 그리는 원본 결정을 유지한다.

### Muse Voice — 전사와 자막

[음성 가이드](https://dev.meta.ai/docs/speech-to-text):

- Korean이 지원 언어 25개에 포함된다. 내부 `ko`는 `languageBias=["Korean"]`로 매핑한다. 이는 언어 강제가 아니라 hint다.
- `/v1/asr/transcribe`는 multipart `request`(JSON)와 `audio`(WAV)를 받는다.
- 오디오는 RIFF/WAVE, mono, signed 16-bit PCM, 16kHz 또는 24kHz다. 영상·MP3를 그대로 보내지 않는다. 최대 본문 32MB, 음성 10분이 문서상 한도다.
- `request`에 `model=muse-voice-transcribe-1.0`, `audioEncoding=WAV`, `mode=ENDPOINTING`을 사용하는 자막 경로를 제안한다.
- 기본 `PUSH_TO_TALK`는 단일 전사이며 turns가 비어 있다. 구간 자막에는 ENDPOINTING 또는 DIARIZATION이 필요하다.
- 응답 `turns[].startMs/endMs/transcript`를 내부 초 단위 Segment로 변환한다. word-level timestamps나 confidence는 제공하지 않는다.
- 한국어 지원은 문서 확인이며 실제 점포 소음 환경의 정확도는 T12/T15에서 측정해야 한다.

### Marketing — 리소스·썸네일·예산

- campaign/adset/ad 생성에 `status=PAUSED`를 사용한다. 업로드 영상·이미지·creative에 동일 status 계약을 강제하지 않는다. [Campaign](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-campaign-group), [Ad Set](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-campaign), [Ad](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/adgroup).
- `configured_status`와 `effective_status`를 구분한다. 부모 중지의 결과가 `CAMPAIGN_PAUSED` 또는 `ADSET_PAUSED`일 수 있다. 모든 상태 문자열이 PAUSED여야 한다는 검사는 부정확하다.
- [Video Data](https://developers.facebook.com/docs/marketing-api/reference/ad-creative-video-data/)는 `image_hash`를 “Hash of an image ... to use as thumbnail”로 정의한다. [Ad Image](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-image) 업로드 hash를 `object_story_spec.video_data.image_hash`로 사용할 수 있다. 공개 썸네일 서버가 필수는 아니다.
- 소재는 `object_story_spec.page_id`와 `video_data` 아래 `video_id`, `image_hash`, `message`, `title`, `call_to_action`을 둔다. 내부 `primary_text→message`, `headline→title` 매핑이 필요하다. CTA별 조건은 선택한 목표에 맞춰 확인한다. [Ad Creative](https://developers.facebook.com/documentation/ads-commerce/marketing-api/reference/ad-creative).
- 캠페인과 광고 세트 양쪽에 예산을 동시에 설정하지 않는다. 원본의 adset `daily_budget` 사용을 유지한다.
- [통화 표](https://developers.facebook.com/documentation/ads-commerce/marketing-api/currencies)의 KRW offset은 1이다. **계정 통화가 KRW일 때 원 단위이며 ×100하지 않는다.** 계정 통화 검증·최소 예산은 H3가 남는다.
- objective/optimization/billing/CTA는 광고 목적 결정 후 한 조합으로 검증한다. [영상 가이드](https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/videoads)의 설명과 예시가 서로 다른 목표를 사용하므로 섞지 않는다.
- daily budget 기간·종료 없음 설정과 lifetime budget의 end_time 요구는 다르다. 과거 예시 일정을 복사하지 않는다. 실제 일정은 승인 대상에 포함하는 안을 제안한다.
- [Authorization](https://developers.facebook.com/documentation/ads-commerce/marketing-api/get-started/authorization): “Calls on ANY access level are against production data.” 개발 앱·테스트 계정이라는 명칭만으로 sandbox라고 판단하지 않는다. 영상 가이드에 ads_management/pages_read_engagement가 명시되어 있으며 본인/타인 계정의 access level/App Review 요구를 확인해야 한다.
- 문서 예시에 v25.0/v26.0이 혼재한다. 원본의 명시적 `META_GRAPH_VERSION` 설정을 유지하고 실제 사용할 버전으로 H3에서 확인한다.

## 2. 개인정보·보관

[가격/모드](https://dev.meta.ai/docs/pricing-rate-limits): Standard는 콘텐츠를 모델 훈련에 사용하지 않는다. Contributor는 제공 콘텐츠의 미래 모델 훈련 사용을 허용한다. 그러나 **Standard는 zero-retention 보장이 아니다.** [Files](https://dev.meta.ai/docs/file-handling)는 “Uploaded files don't expire”라고 명시한다.

따라서 업로드 파일 ID, 마지막 사용 단계, 삭제 요청·실패 상태를 추적하는 방안을 제안한다. Responses 저장과 Files 보관은 별개다. Marketing 소재 보관과 Model API 임시 파일도 구분한다. 고객 동의·보관 기간·삭제 시점을 결정하기 전 고객 데이터 live 호출을 시작하지 않는다.

## 3. 아직 해제되지 않은 조건

| 조건 | 책임 역할 | 해제 증거 |
| --- | --- | --- |
| 공식 규정·사전 제작물·허용 모델·제출 형식 | 참가 책임자 H1 | 해당 대회의 공식 규정 원문과 확인 일자 |
| Model API 팀 접근·한국 호출 가능 여부·비용 한도 | 키 관리 담당 H2 | 승인된 환경에서 각 모델 최소 호출의 sanitized 결과 |
| Spark 별도 영상 초/프레임 제한 | 구현 담당+H2 | 공식 문서 또는 승인된 경계 호출; 45초를 provider 한도로 주장하지 않음 |
| 영상 촬영·전송 권리, 파일 보관/삭제, Image 도구 허용 | 데이터 소유자+H2 | 동의와 보관 정책; 원격 삭제 검증 |
| 광고 목표·CTA·destination·배치·Graph 버전 | 광고 운영 담당 H3 | 단일 PublishPlan과 승인된 계정 검증 |
| KRW 계정 여부·최소 예산·일정·권한 | 광고 운영 담당 H3 | 계정 metadata와 API 검증, 필요한 권한 확인 |
| 125자/40자, 30초, safe area | 구현 담당+H3 | 선택 배치의 Ads Guide 근거; 전역 하드 한도로 사용하지 않음 |
| 렌더·크롭·자막 품질 | 구현 담당+영상 소유자 | 실제 영상 1~2건과 synthetic 경계 사례 |

원본 §9의 폰트 라이선스는 `research/oss.md`의 후보 검토로 이어진다. 후보 조사만으로 실제 배포 binary·폰트 파일의 라이선스 확인을 완료한 것으로 처리하지 않는다.
