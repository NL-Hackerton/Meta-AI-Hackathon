# AdLoom — Meta AI Hackathon

영상 1개와 설명을 광고 영상 6종(3비율 × 훅 A/B)으로 만들고, **원본 근거를 확인·수정한 뒤 승인한 내용 그대로** 9:16 광고 2개를 Meta 계정에 PAUSED 상태로 준비하는 기획이다.

## 현재 상태

- 고객 검증 불가 조건에 맞춰 제품 완성도 중심으로 BMAD 기획을 보완했다. 고객 인터뷰·실고객 확보·매출/CTR 개선은 gate가 아니다.
- `src/adloom/schemas.py`의 공유 모델44개와 순수 검증, 회귀 테스트51개를 구현했다. `make check`가 ruff·mypy strict·pytest를 실행한다. config·저장·worker·제품 서버/CLI·provider 호출·광고 생성은 아직 없다.
- 루트 [SPEC.md](SPEC.md)는 원본 구현 명세다. **BMAD 초안은 이를 대체하지 않는다.**
- [변경 기록](SPEC_CHANGES.md)의 SC-001~SC-015는 루트 명세에 미반영이다. 사용자 요청으로 스키마 범위를 구현했으며, 제품 전체·대회 규정·live 실행 승인을 뜻하지 않는다.

## 코드베이스 아키텍처와 확보한 코드

- [Architecture Spine](_bmad-output/planning-artifacts/architecture/architecture-AdLoom-2026-10-25/ARCHITECTURE-SPINE.md): modular monolith, 공용 command, 단일 worker, revision·승인·복구 경계.
- [모듈·API·저장 계약](docs/architecture/codebase.md): 구현할 디렉터리와 책임, atomic head/immutable artifacts, lock·timebase·Unicode span 규약.
- [의존성 기준선](docs/architecture/dependencies.md): CPython3.12.15, 직접 의존성9개와 uv.lock. `.venv`는 로컬 설치 환경이며 Git 제외다.
- [외부 원본](third_party/README.md): 공식 meta-sam-parser0.1.0 source archive와 SAM License, Noto Sans KR 원본 TTF와 OFL. 출처·commit·SHA256은 manifest에 고정했다.
- [실행 확인](docs/architecture/baseline-verification.md): parser 정상/오류/미완료, 한글 렌더, H.264/AAC, Range/SSE, OS lock 상속을 확인했다. 제품 기능·실제 API 검증과는 별개다.
- [스키마 구현과 사용](docs/architecture/schemas.md): 타입·시간/경로/출처 규약, 승인 projection, 실제 검증 범위.

```sh
uv sync --locked
make check
```

`uv sync --locked`는 의존성과 AdLoom 스키마 패키지를 설치한다. 현재 제품 CLI·웹 실행 명령은 없다. ffmpeg/ffprobe9.0.2는 별도 시스템 의존성이다. 전체 FastAPI 템플릿이나 Hello World 생성기는 가져오지 않았다.

## 읽는 순서

1. [BMAD kernel](_bmad-output/specs/spec-adloom/SPEC.md): 기존 8개 capability를 유지하고 원본 연결·제한 편집 CAP-9를 추가했다.
2. [사용자 흐름](_bmad-output/specs/spec-adloom/product-flow.md): 웹에서 만들기→검토·수정→승인·내보내기/실제 게시까지 이어지는 전 과정이다.
3. [구현 계약 상세안](_bmad-output/specs/spec-adloom/implementation-contracts.md): source reference, 객체·문구 수정, 영향 범위 재생성, 승인 fingerprint, 게시 복구, 크롭·시간축을 정의한다.
4. [수용·진행 계획](_bmad-output/specs/spec-adloom/acceptance-plan.md): 기존 AC21·BA18과 제품 품질 PQ01~PQ10, 미디어 12개 개발/평가 분리, 초기 웹·실연동과 마지막 2일 검증 계획이다. 데이터·측정 결과는 아직 없다.
5. [API 확인 장부](docs/api_notes/verification.md), [OSS 재사용 조사](research/oss.md): 문서로 확인한 사실과 live/규정 확인이 필요한 조건.
6. [TASKS.md](TASKS.md), [STATUS.md](STATUS.md): 기존 구현 상태와 진행 기록.

연결된 외부 기획 artifact는 로그인 화면으로 본문을 확인하지 못했다. 이번 구체화의 직접 기획 근거는 원격에 있는 SPEC.md·TASKS.md이며, 공식 API 문서는 별도로 조사했다.

## BMAD 사용

설치된 `bmad-spec`·`bmad-architecture` 스킬의 kernel, append-only memlog, architecture spine과 검증 절차를 적용했다. `_bmad/scripts/`는 upstream BMAD-METHOD 최소 지원 스크립트4개이며 출처 commit·hash는 [_bmad/upstream.json](_bmad/upstream.json), MIT 고지는 [_bmad/LICENSE](_bmad/LICENSE)에 있다. BMAD 전체 프레임워크는 설치하지 않았고 제품 runtime 의존성은 위 baseline으로 별도 관리한다.

Python 3.11+와 `uv`가 있는 환경에서 프로젝트 설정을 확인한다.

```sh
uv run _bmad/scripts/resolve_config.py --project-root .
```

명세 갱신은 memlog와 근거를 통해 기록하고 루트 SPEC 변경은 별도 승인 절차를 유지한다. 현재 `make check`는 스키마 구현 범위를 검사하며 미구현 pipeline·전체 INV·live 검증 완료를 뜻하지 않는다.

## 구현 전 결정

- SC-001~SC-015의 루트 명세 반영과 후속 서비스 구현.
- 직접 촬영 또는 적법한 실물 자산, 광고 목적·destination. 고객 영상이나 고객 모집은 요구하지 않는다.
- H1 공식 규정, H2 모델 접근·데이터 동의·비용 한도, H3 실제 광고 계정·권한·목표, H4 촬영·제출.

## 보완안의 핵심

- 원본·결과 대응 재생과 근거 클릭, SAM 기존 객체 후보 선택, 구간·훅·카피·자막의 제한 편집을 제공한다. 출처 연결은 진실성·Meta 정책 승인 보증이 아니다.
- 편집 후 새 revision의 결과가 준비돼야 다시 승인할 수 있다. 이전 결과·dirty 편집·결과 불명·실패·키 없음 상태를 숨기지 않는다.
- 직접 촬영/적법한 실물 4개와 합성 8개를 계획하고, 개발 6개와 고정 평가 6개를 분리한다. 중앙 크롭 대조, 가독성, 자막, 수정 반영, 승인·게시, 복구, 설치를 검증한다.
- 기능 수를 늘리는 대신 하나의 완결 경로를 만든다. 범용 편집기·자유 mask·공개 SaaS·다중 계정·광고 자동 활성화는 추가하지 않는다.
- Meta 자체 생성·편집·승인 도구와의 중복을 인정한다. 보완안의 차별성과 우승 가능성은 검증된 사실이 아니며, 고객 성과나 임의 심사 점수로 포장하지 않는다.