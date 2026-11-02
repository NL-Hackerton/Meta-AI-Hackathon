# AdLoom — Meta AI Hackathon

영상 1개와 설명을 광고 영상 6종(3비율 × 훅 A/B)으로 만들고, **원본 근거를 확인·수정한 뒤 승인한 내용 그대로** 9:16 광고 2개를 Meta 계정에 PAUSED 상태로 준비하는 기획이다.

## 현재 상태

- 고객 검증 불가 조건에 맞춰 제품 완성도 중심으로 BMAD 기획을 보완했다. 고객 인터뷰·실고객 확보·매출/CTR 개선은 gate가 아니다.
- T00~T09의 mock 경로를 구현했다. CLI에서 입력 정규화→fixture 이해→합성 추적→보강→6종 영상 렌더→사람 승인→PAUSED mock 게시까지 실행할 수 있다. `make check`는 ruff·mypy strict·pytest를 실행한다.
- 루트 [SPEC.md](../SPEC.md)는 보존했다. 팀원 [기획안](https://github.com/NL-Hackerton/Meta-AI-Hackathon/blob/bf82ac60e31a740f7b2bce9dd21796c17229672d/docs/plan/기획안-SMB-광고영상-자동화-초안.md) 반영 요청에 따라 기존 스키마를 재사용해 구현했다.
- 로컬 웹 화면(FastAPI + 단일 HTML)을 구현했다. 작업 목록, 영상 업로드, 6종 검토·승인, 문구 편집, PAUSED mock 게시, 게시 기록, 설정 화면을 제공하며 디자인 원본은 [Figma 파일](https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5)이다. 화면 문구는 영어다.
- Spark·SAM·Image·Voice live 어댑터 코드는 있으나 `get_adapters`는 mock만 반환한다. T10~T13은 H2/H3 대기로 BLOCKED다. `ADLOOM_LIVE=1`은 `E_API_AUTH`로 거부하며 조용히 mock으로 전환하지 않는다. 실제 모델 추론이나 광고 생성 완료를 뜻하지 않는다.

## 코드베이스 아키텍처와 확보한 코드

- [Architecture Spine](../_bmad-output/planning-artifacts/architecture/architecture-AdLoom-2026-10-25/ARCHITECTURE-SPINE.md): modular monolith, 공용 command, 단일 worker, revision·승인·복구 경계.
- [모듈·API·저장 계약](architecture/codebase.md): 구현할 디렉터리와 책임, atomic head/immutable artifacts, lock·timebase·Unicode span 규약.
- [의존성 기준선](architecture/dependencies.md): CPython3.12.15, 직접 의존성9개와 uv.lock. `.venv`는 로컬 설치 환경이며 Git 제외다.
- [외부 원본](../third_party/README.md): 공식 meta-sam-parser0.1.0 source archive와 SAM License, Noto Sans KR 원본 TTF와 OFL. 출처·commit·SHA256은 manifest에 고정했다.
- [실행 확인](architecture/baseline-verification.md): parser 정상/오류/미완료, 한글 렌더, H.264/AAC, Range/SSE, OS lock 상속을 확인했다. 제품 기능·실제 API 검증과는 별개다.
- [스키마 구현과 사용](architecture/schemas.md): 타입·시간/경로/출처 규약, 승인 projection, 실제 검증 범위.

```sh
uv sync --locked
make check
```

`uv sync --locked`는 의존성과 저장소의 AdLoom 패키지를 editable 설치한다. Python 3.12와 시스템 ffmpeg/ffprobe 9 계열이 필요하다. 렌더 통합 검사를 포함한 전체 검사와 반복 렌더는 5080 서버에서 실행했다. 동일 입력의 frame hash 일치는 같은 ffmpeg·폰트·renderer build 범위에서만 검증한다.

## mock 실행

`tests/fixtures/sample.mp4`는 생성기로 만든 10초 합성 영상이며 저장된 SHA-256 fixture와 짝을 이룬다. 임의 영상은 해당 digest의 이해 fixture가 없으면 실패한다. mock 추적·이미지·전사는 실제 모델 결과가 아니다. `make_sample.sh`로 다른 ffmpeg build에서 다시 만든 파일은 digest가 달라질 수 있으므로 처음에는 포함된 샘플을 사용한다.

```sh
uv run --locked python -m adloom run \
  --video tests/fixtures/sample.mp4 --note "합성 샘플" --region "서울" --budget 10000
uv run --locked python -m adloom list
uv run --locked python -m adloom inspect JOB_ID
uv run --locked python -m adloom approve JOB_ID --actor local-reviewer --digest CONTENT_DIGEST
uv run --locked python -m adloom publish JOB_ID
```

`JOB_ID`는 `run` 출력의 `job_id`, `CONTENT_DIGEST`는 `inspect` 출력의 `content_digest`로 바꾼다. 영상은 `data/jobs/JOB_ID/renders/r000001/`에 저장된다. 먼저 mp4 6개와 `inspect`의 문구·정책 플래그·품질 경고를 확인한 뒤 승인한다. `publish` 결과의 `fixture-` ID는 실제 Meta 광고 ID가 아니다.

```sh
uv run --locked python -m adloom edit JOB_ID --hook-a "수정한 문구"
uv run --locked python -m adloom resume JOB_ID
```

`edit`는 게시 전 작업의 훅 A/B·본문·제목만 수정한다. 실제 변경이 있으면 revision을 올리고 승인을 무효화한 뒤 다시 렌더한다. `resume`은 저장된 실패 단계부터 재개한다. 게시 요청의 결과가 불명이면 자동 재전송하지 않는다. `ADLOOM_DATA_DIR`로 작업 저장 위치를 지정할 수 있다. 이미지 실패는 원본 대표 프레임·단색 카드와 경고로 남기고, 낮은 추적 coverage는 중앙 크롭과 degraded 표시로 남긴다.

안전 영역(위 14%·아래 22%), 문구 한도, 30초 영상 상한은 제품 잠정값이다. 정책 점검은 현재 규칙표의 표현만 탐지하며, 사실성이나 Meta 심사 통과를 보장하지 않는다. 예산·목표·CTA의 fixture 설정을 실제 계정 설정으로 사용하지 않는다.

## 웹 실행

```sh
uv run --locked python -m adloom.web
```

`http://127.0.0.1:8000`에서 연다. `ADLOOM_HOST`·`ADLOOM_PORT`로 주소를 바꾸고 `ADLOOM_DATA_DIR`로 작업 저장 위치를 지정한다. 기본 주소는 loopback이며 인증이 없으므로 외부에 공개하지 않는다. 웹 경로도 CLI와 같은 `pipeline` 명령을 사용한다. 승인 기록은 `channel: "web"`으로 남고, 승인 fingerprint가 현재 내용과 다르면 `E_REVISION_CONFLICT`로 거부한다. 업로드 원본은 작업 폴더로 복사한 직후 임시 파일을 지운다. mock 이해 fixture가 SHA-256에 묶여 있으므로 지금은 `tests/fixtures/sample.mp4`만 끝까지 처리된다.

화면은 하나의 반응형 앱이다. 960px 이하에서는 하단 탭(Home, My ads, 새 작업, Approve, MY)을 쓴다. 제공 화면은 Home, Welcome, 사업자 프로필, Meta 연결 상태, 새 작업(길이 사전 검사, 글 또는 음성 설명), 설명 확인, 검토·승인(원본 위 추적 박스와 3비율 크롭 표시), 편집(문구·추적 대상·사용 장면), 게시 진행·결과 불명 처리, 승인 대기, 내 광고·광고 상세, MY, 데이터 삭제, 알림, 게시 기록, 설정이다. 로그인과 실제 Meta 계정 연결은 H3 전이라 만들지 않았고, Meta 연결 화면은 미연결 상태와 필요한 권한만 보여 준다. 음성 설명은 전사 결과를 사람이 확인한 뒤에만 사용한다(`confirm-note`). fixture 모드에는 `tests/fixtures/voice/note-sample.wav`의 전사만 있으므로 다른 녹음은 실패하고, 이때는 설명을 직접 입력해 이어 간다. CLI의 `run --note-audio`도 전사 확인 대기에서 멈추며 `python -m adloom confirm-note JOB_ID --text "…"`로 이어 간다.

## 읽는 순서

1. [BMAD kernel](../_bmad-output/specs/spec-adloom/SPEC.md): 기존 8개 capability를 유지하고 원본 연결·제한 편집 CAP-9를 추가했다.
2. [사용자 흐름](../_bmad-output/specs/spec-adloom/product-flow.md): 웹에서 만들기→검토·수정→승인·내보내기/실제 게시까지 이어지는 전 과정이다.
3. [구현 계약 상세안](../_bmad-output/specs/spec-adloom/implementation-contracts.md): source reference, 객체·문구 수정, 영향 범위 재생성, 승인 fingerprint, 게시 복구, 크롭·시간축을 정의한다.
4. [수용·진행 계획](../_bmad-output/specs/spec-adloom/acceptance-plan.md): 기존 AC21·BA18과 제품 품질 PQ01~PQ10, 미디어 12개 개발/평가 분리, 초기 웹·실연동과 마지막 2일 검증 계획이다. 데이터·측정 결과는 아직 없다.
5. [API 확인 장부](api_notes/verification.md), [OSS 재사용 조사](../research/oss.md): 문서로 확인한 사실과 live/규정 확인이 필요한 조건.
6. [TASKS.md](../TASKS.md), [STATUS.md](../STATUS.md): 기존 구현 상태와 진행 기록.

연결된 외부 기획 artifact는 로그인 화면으로 본문을 확인하지 못했다. 이번 구체화의 직접 기획 근거는 원격에 있는 SPEC.md·TASKS.md이며, 공식 API 문서는 별도로 조사했다.

## BMAD 사용

설치된 `bmad-spec`·`bmad-architecture` 스킬의 kernel, append-only memlog, architecture spine과 검증 절차를 적용했다. `_bmad/scripts/`는 upstream BMAD-METHOD 최소 지원 스크립트4개이며 출처 commit·hash는 [_bmad/upstream.json](../_bmad/upstream.json), MIT 고지는 [_bmad/LICENSE](../_bmad/LICENSE)에 있다. BMAD 전체 프레임워크는 설치하지 않았고 제품 runtime 의존성은 위 baseline으로 별도 관리한다.

Python 3.11+와 `uv`가 있는 환경에서 프로젝트 설정을 확인한다.

```sh
uv run _bmad/scripts/resolve_config.py --project-root .
```

명세 갱신은 memlog와 근거를 통해 기록하고 루트 SPEC 변경은 별도 승인 절차를 유지한다. 현재 검증은 스키마와 mock pipeline·승인·편집·부분 게시 재개를 포함하며, 실제 API·광고 계정·제품 UI 검증과는 구분한다.

## live 연동 전 결정

- 원본 명세와 SC-001~SC-017의 차이 정리, H2/H3 승인.
- 직접 촬영 또는 적법한 실물 자산, 광고 목적·destination. 고객 영상이나 고객 모집은 요구하지 않는다.
- H1 공식 규정, H2 모델 접근·데이터 동의·비용 한도, H3 실제 광고 계정·권한·목표, H4 촬영·제출.

## 보완안의 핵심

- 원본·결과 대응 재생과 근거 클릭, SAM 기존 객체 후보 선택, 구간·훅·카피·자막의 제한 편집을 제공한다. 출처 연결은 진실성·Meta 정책 승인 보증이 아니다.
- 편집 후 새 revision의 결과가 준비돼야 다시 승인할 수 있다. 이전 결과·dirty 편집·결과 불명·실패·키 없음 상태를 숨기지 않는다.
- 직접 촬영/적법한 실물 4개와 합성 8개를 계획하고, 개발 6개와 고정 평가 6개를 분리한다. 중앙 크롭 대조, 가독성, 자막, 수정 반영, 승인·게시, 복구, 설치를 검증한다.
- 기능 수를 늘리는 대신 하나의 완결 경로를 만든다. 범용 편집기·자유 mask·공개 SaaS·다중 계정·광고 자동 활성화는 추가하지 않는다.
- Meta 자체 생성·편집·승인 도구와의 중복을 인정한다. 보완안의 차별성과 우승 가능성은 검증된 사실이 아니며, 고객 성과나 임의 심사 점수로 포장하지 않는다.