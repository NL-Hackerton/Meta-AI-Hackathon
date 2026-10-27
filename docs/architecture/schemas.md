# 도메인 스키마 구현

구현 위치: `src/adloom/schemas.py`. 사용자 요청에 따라 먼저 구현한 44개 Pydantic 모델과 순수 검증 함수를 재사용해 2026-10-27에 config·파일 저장·mock 어댑터·규칙 기반 정책·렌더·승인/게시·CLI를 연결했다. 별도 worker·웹 API·live 어댑터는 아직 없다. 루트 SPEC는 보존하고 내부 계약 명료화는 SC-015로 기록한다.

## 사용과 검증

```sh
uv sync --locked
make check
```

`make check`는 ruff, mypy strict, pytest를 실행한다. 패키지는 Hatchling으로 editable 설치되므로 `from adloom.schemas import Brief`처럼 import할 수 있다. 현재 제품 CLI·웹 서버 실행 명령은 없다.

```python
from adloom.schemas import Brief, NoteDocument, NoteEvidence, assess_evidence

brief = Brief.model_validate({
    "video_path": "input/product.mov",
    "note_text": "제품 설명",
    "region": "남양주",
    "daily_budget_krw": 10000,
})
assert brief.note_text is not None
note = NoteDocument(text=brief.note_text)
reference = NoteEvidence(
    source_digest=note.sha256, start=0, end=2, quote="제품"
)
result = assess_evidence("note-1", reference, note=note)
assert result.valid
```

`model_validate_json`은 JSON 원문에, `model_validate`는 이미 decode한 HTTP/adapter 입력에 사용한다. 선언된 tuple 필드의 JSON list만 tuple로 변환하며 시간·예산·좌표의 숫자 문자열이나 boolean을 수치로 바꾸지 않는다. ISO datetime 문자열은 timezone을 요구하고 UTC로 정규화한다. 파일 저장은 `jobs.py`가 담당한다.

## 모델 그룹

| 영역 | 주요 모델 | 검증 경계 |
| --- | --- | --- |
| 입력·미디어 | Brief, NoteDocument, InputBundle, MediaInfo, FrameRate | 설명 text/audio 중 하나, NFC200 codepoint, mp4/mov path, 길이3~45초, normalized fps/크기/프레임 수 |
| 이해 | Moment, Hook, Flag, Understanding, ClaimCandidate | 훅3개·고유 ID·22자, source 범위·시간순·겹침, 카피 길이, provider 결과에 review 필드 금지 |
| 근거 | NoteEvidence, VideoEvidence, EvidenceAssessment, ClaimReview | source digest·codepoint span·quote·시간 범위, 근거별 invalid 사유, 사람 결정의 actor 기록 |
| 추적·크롭 | Rect, BBox, TrackResult, ObjectTrack, TrackCandidates, CropPlan | 유한 좌표·경계·고정 crop 크기·이동 상한·frame 수, 보간 전 coverage, 실제 후보 선택 |
| 시간축·렌더 입력 | TimelineSpan, TimelinePlan, RenderSource, EnrichResult, RenderPlan | 출력 연속성·반개구간·원본 순서, 명시 padding pass, 본영상6~28초+카드2초, 정규화 video1개, 허용 image 출처 |
| 산출물·출처 | Provenance, ArtifactRef, ArtifactRecord, AspectImage, VariantDigest, RenderedVariant, ImageDigest | job-relative path·SHA256 형식·stage/model 출처·3비율 해상도·코덱·Image fallback 기록 |
| 승인·게시 | MarketingProfile, PublishPlan, ApprovalSubject, ApprovalRecord, PublishOperation, PublishedAd, PublishResult, RemoteFileAttempt | 설정/승인 자산 분리, 영상6조합, mode 일치, PAUSED 설정, phase/ID/오류 일치, UNKNOWN 업로드의 명시 재시도 기록 |
| 현재 상태 | ErrorDetail, JobManifest | schema version, owner/run_state, 실패·pending stage, 승인 참조, 재개할 상태의 note 확정, timezone·관측 시각 |

`DomainModel`은 extra=forbid, frozen, strict, finite 수치, default 검증, nested instance 재검증을 공통 적용한다. 선언된 컬렉션은 tuple로 보존하며 모델 필드에 mutable dict/list를 저장하지 않는다. Pydantic의 model_construct·model_copy(update=...)는 검증을 우회하는 trusted API이므로 외부 입력·업무 수정에 사용하지 않는다. 수정 데이터는 다시 validation해야 한다.

## 고정한 데이터 규약

- **시간:** 모든 도메인 시간 구간은 정수 microseconds와 `[start,end)`다. 원본의 float seconds는 향후 adapter 경계에서 변환한다. MediaInfo.duration_us는 마지막 정규화 frame 끝을 넘을 수 없다.
- **프레임:** fps는 양의 기약분수다. coverage는 null이 아닌 실제 검출 bbox 수/frame_count와 일치해야 하며 보간 결과로 높이지 않는다. confidence 결측은 None이다.
- **반복:** 첫 pass는0, 원본 순서·비중첩을 유지한다. 반복 번호는1씩 증가하며 짧은 본영상을 원본 앞부분으로 채울 때만 허용한다. padding이 있으면 본영상은 정확히6초에서 끝난다.
- **식별자:** job/run/attempt는32자리 소문자 hex, SHA256은64자리 hex다. hook ID는 `[a-z0-9][a-z0-9_-]{0,31}`이며 모델 문구와 별개다. revision·예산 등 공유 정수는 JavaScript safe-integer 범위로 제한한다.
- **journal key:** job/revision/mode/resource/hook을 `.`으로 결합한다. 공용 hook 표식 `_shared`는 허용 HookId와 겹치지 않는다. key는 `/`·NUL·URL 문자가 없어 같은 RelativePath 규칙으로 journal 경로에 넣을 수 있다.
- **path:** canonical job-relative POSIX 경로만 허용한다. absolute·상위 경로·역슬래시·URL/escape 문자는 거부한다. 이는 lexical 검사이지 symlink·실제 filesystem containment 검사가 아니다.
- **문자:** 설명은 NFC 정규화 후 codepoint로 센다. note span도 같은 기준이다. UTF-16 offset을 직접 사용하지 않는다.

## 승인 projection과 권한의 구분

`PublishPlan`은 계정·Page·Graph·예산·CTA·destination·명시 profile 등 설정만 담는다. 렌더 자산 hash나 approval digest를 넣으면 extra 필드 오류다. 미확정 live CTA 목록·objective·최소 예산은 코드에 추측해 기본값으로 넣지 않고 MarketingProfile을 명시 입력한다.

`ApprovalSubject`는 source·timeline·훅/카피·영상6개·thumbnail·provider 출처·근거/검토·정책/경고·PublishPlan의 명시 projection이다. progress, manifest_seq, journal, remote ID, 파일 path는 포함하지 않는다. variant/evidence/claim 목록은 안정된 식별자 순서로 정렬한다. 다른 ordered tuple의 순서는 계약 입력의 일부이므로 작성자가 안정적으로 유지한다. canonical JSON은 UTF-8·키 정렬·고정 separators·finite 수치로 직렬화한다.

`approval_issues`는 block 정책, 미검토 사실형/고위험 주장, 잘못된 source reference를 순수 계산으로 반환한다. EvidenceAssessment.valid=true도 신뢰하지 않고 현재 note/source와 다시 대조한다. 이 함수는 문장의 고위험 여부를 분류하는 policy 엔진이나 live 권한 검사 자체가 아니다.

ClaimCandidate는 provider용이고 status/actor를 받지 않는다. ClaimReview·ApprovalRecord는 신뢰된 서비스가 사람 동작을 확인한 뒤 만드는 기록이다. 이 타입으로 JSON을 읽었다는 사실만으로 실제 사람 승인이나 계정 권한이 생기지 않는다. ApprovalRecord.matches는 content 연결을 검사할 뿐 인증·파일 hash 실측을 대신하지 않는다.

## 최초 스키마 구현 시 실행한 검증(2026-10-25)

- 당시 `make check`: ruff 통과, mypy strict 통과, pytest **51개 통과**. 후속 pipeline 검증은 STATUS에 별도로 기록한다.
- 설치된 패키지로 InputBundle JSON round-trip, NFC 정규화, 유효·잘못된 note reference, 60초 media 거부를 실행했다.
- 임시 FastAPI app의 실제 ASGI validation 경로에서 올바른 Understanding JSON은200, 수치 문자열은422를 확인했다. 이것은 제품 API 구현이 아니다.
- 44개 모델의 JSON Schema 생성에 성공했다. 산출물은 Git 제외 `data/schema-smoke-mrooru91/`에 있다.
- 미디어/승인·상태 독립 리뷰에서 발견한 마지막 frame 이후 시간, 잘못된 반복, 추가 video, journal key 충돌, FAILED 재개 상태, PREPARED abandon, Image/Voice fallback 혼동을 회귀 사례로 추가했다.

## 후속 서비스 검증과 남은 경계

2026-10-27에 파일 hash 실측·job 경로 containment·설정/live 차단·전이/원자 저장·mock 렌더·승인 digest·게시 재개를 연결하고 테스트했다. 스키마 함수만으로 이 검사가 수행된다고 해석하지 않는다. 사람의 대회 약관 수락·계정 권한·실제 provider 응답·정책 문장의 의미·실영상 품질·실제 PAUSED 광고·웹 인증은 검증하지 않았다.
