# 런타임 의존성 기준선

이 문서는 AdLoom의 Python 런타임 의존성 고정 내용과 근거를 기록한다. 2026-10-25 기준 PyPI JSON metadata(`https://pypi.org/pypi/<이름>/json`)에서 최신 버전, 비철회(non-yanked) 여부, `requires_python`, 라이선스를 확인하였다.

- **현재 상태:** 스키마·설정·파일 저장·mock pipeline·렌더·승인/게시·CLI를 구현했다. 실행 명령은 루트 README에 있다. 별도 worker·웹 서버·live 어댑터는 아직 없다.
- `version = "0.0.0"`은 정식 배포 전 개발 버전이다. Hatchling1.27.0 build backend로 `src/adloom`을 editable 설치한다. 이전 dependency-only `package=false` 설정은 제거했다.
- 외부 코드 확보와 스키마 구현은 대회 규정(H1) 허용 판정이나 제품 전체 완료를 뜻하지 않는다.
- root SPEC는 보존한다. T00~T09의 mock 경로를 완료했으며 H2/H3와 웹 설계·검수 선행 조건은 유지한다. 태스크 상태와 실행 증거는 TASKS·STATUS에 기록한다.

## 1. 확인한 환경

| 항목 | 값 | 확인 방법 |
| --- | --- | --- |
| OS·아키텍처 | macOS(darwin 25.5.0), arm64 | 작업 환경 |
| Python | CPython 3.12.15 (Homebrew `python@3.12`) | `python3.12 -c "import sys; print(sys.version)"` |
| uv | 0.11.21 (Homebrew) | `uv --version` |
| ffmpeg / ffprobe | 9.0.2 (Homebrew, `/opt/homebrew/bin`) | `ffmpeg -version`, `ffprobe -version` |

- 설치된 runtime 중 3.12 계열의 최신 patch인 3.12.15를 `.python-version`에 고정하였다. 3.13·3.14·3.15도 설치되어 있으나 기획의 3.11+ 조건을 만족하는 안정 계열 중 3.12를 선택하였다.
- `requires-python = ">=3.12,<3.13"`이다. Pillow 13.0.0은 Python ≥3.11을 요구하므로 3.11도 이론상 가능하나, 잠금 파일은 3.12 계열만 검증 대상으로 둔다.

## 2. 직접 의존성 핀

| 패키지 | 핀 | Python 요구 | 라이선스 | 배포일(UTC) | 선택 이유 | 공식 출처 |
| --- | --- | --- | --- | --- | --- | --- |
| FastAPI | 0.162.0 | ≥3.10 | MIT | 2026-10-23 | 웹 생성·검토·편집·승인 API(SC-011). 기본 패키지만 사용 | [PyPI](https://pypi.org/pypi/fastapi/json), [소스](https://github.com/fastapi/fastapi) |
| Pydantic | 2.14.1 | ≥3.10 | MIT | 2026-10-11 | 모든 모듈 경계 스키마(SPEC §1). `pydantic-core==2.50.1`을 정확히 요구 | [PyPI](https://pypi.org/pypi/pydantic/json), [소스](https://github.com/pydantic/pydantic) |
| HTTPX | 0.28.1 | ≥3.8 | BSD-3-Clause | 2024-12-06 | Meta API 통신(SPEC §1). 최신 배포이며 extra 미사용 | [PyPI](https://pypi.org/pypi/httpx/json), [소스](https://github.com/encode/httpx) |
| httpx-sse | 0.4.3 | ≥3.9 | MIT | 2025-10-10 | SAM 요청은 `stream=true` SSE 응답이다. `meta-sam-parser`는 HTTP SSE 전송을 포함하지 않는다. 여러 `data:` 줄 결합·이벤트 경계·주석 줄 등 SSE 프레이밍 처리를 직접 작성하지 않기 위해 선택. 런타임 의존성 없음 | [PyPI](https://pypi.org/pypi/httpx-sse/json), [소스](https://github.com/florimondmanca/httpx-sse) |
| meta-sam-parser | 0.1.0 | ≥3.10 | SAM License(MIT 아님) | 2026-10-06 | Meta 공식 SAM 응답 문법 파서. 런타임 의존성 없음, Alpha | [PyPI](https://pypi.org/pypi/meta-sam-parser/json), [소스](https://github.com/meta-models/meta-sam), [문서](https://dev.meta.ai/docs/sam/client-libraries) |
| Pillow | 13.0.0 | ≥3.11 | MIT-CMU | 2026-10-16 | 문구별 정적 RGBA PNG 합성(research/oss.md 표 1 4행). cp312 macOS arm64 wheel 존재 | [PyPI](https://pypi.org/pypi/pillow/json), [소스](https://github.com/python-pillow/Pillow) |
| Uvicorn | 0.54.0 | ≥3.10 | BSD-3-Clause | 2026-09-25 | FastAPI 실행용 ASGI 서버. `[standard]` extra 제외 | [PyPI](https://pypi.org/pypi/uvicorn/json), [소스](https://github.com/Kludex/uvicorn) |
| python-multipart | 0.0.32 | ≥3.10 | Apache-2.0 | 2026-06-04 | 로컬 웹 업로드(FastAPI `UploadFile`/`Form`) 파싱 | [PyPI](https://pypi.org/pypi/python-multipart/json), [소스](https://github.com/Kludex/python-multipart) |
| PyYAML | 6.0.3 | ≥3.8 | MIT | 2025-09-25 | 원본 기획의 `policy_rules.yaml`(T04) 읽기. 표준 라이브러리에 YAML 파서가 없음 | [PyPI](https://pypi.org/pypi/pyyaml/json), [소스](https://github.com/yaml/pyyaml) |

- 모든 핀은 확인 시점의 PyPI 최신 버전이며 철회 표시가 없다.
- OpenAI SDK는 추가하지 않았다. 공식 SAM 문서 예시는 OpenAI 클라이언트를 사용하지만, 파서는 전송을 클라이언트에 맡기므로 HTTPX + httpx-sse로 Responses 이벤트를 받아 파서에 넘기는 구성을 택한다.
- **meta-sam-parser 사용 주의:** 파서가 포함 끝점(inclusive) wire 좌표를 이미 반열린(half-open) right/bottom으로 변환한다. 어댑터에서 `+1`을 다시 더하지 않는다(docs/api_notes/verification.md의 `x2-x1+1` 규약은 원시 wire 값 기준). 파서는 잘못된 줄을 진단에 남기고 계속 진행하며 completed/incomplete를 구분한다. 마스크 검증 시 메모리 할당이 있고 자체 quota가 없으므로 입력 크기 제한은 앱이 담당한다.
- **SAM License:** 사용·재배포 조건이 MIT와 다르다. 최종 고지와 대회 규정(H1) 검토 대상에 포함한다.

## 3. 전이 의존성(uv.lock 기준)

`uv lock`이 해석한 전체 23개 항목(프로젝트 `adloom` 포함) 중 전이 의존성은 다음과 같다. 라이선스는 설치된 패키지 metadata 기준이다.

| 패키지 | 버전 | 라이선스 | 끌어온 직접 의존성 |
| --- | --- | --- | --- |
| pydantic-core | 2.50.1 | MIT | pydantic |
| annotated-types | 0.8.0 | MIT | pydantic |
| typing-extensions | 4.16.0 | PSF-2.0 | pydantic, fastapi |
| typing-inspection | 0.4.4 | MIT | pydantic, fastapi |
| starlette | 1.10.0 | BSD-3-Clause | fastapi |
| annotated-doc | 0.0.5 | MIT | fastapi |
| opentelemetry-api | 1.45.1 | Apache-2.0 | fastapi(0.162.0의 기본 의존성) |
| anyio | 4.15.1 | MIT | httpx, starlette |
| httpcore | 1.0.9 | BSD-3-Clause | httpx |
| h11 | 0.16.0 | MIT | httpcore, uvicorn |
| certifi | 2026.10.23 | MPL-2.0 | httpx |
| idna | 3.20 | BSD-3-Clause | httpx |
| click | 8.5.0 | BSD-3-Clause | uvicorn |

- certifi는 MPL-2.0이므로 수정 배포 시 파일 단위 소스 공개 조건을 확인한다. 현재 수정 계획은 없다.

## 4. 시스템 요구사항

- **ffmpeg / ffprobe는 Python 패키지가 아니며 uv로 설치되지 않는다.** 현재 개발 baseline은 Homebrew ffmpeg9.0.2이며 `--enable-gpl --enable-libx264 --enable-version3` build다. version·build 설정을 render fingerprint에 포함하고 다른 build의 동일 픽셀을 보장하지 않는다. 바이너리는 third_party에 동봉하지 않는다. 제한된 실제 인코딩·decoded hash 검증은 [baseline-verification.md](baseline-verification.md)에 기록한다.
- 현재 binary SHA256, 전체 version/configuration 출력은 [media-baseline.json](media-baseline.json)에 보존했다. runtime preflight는9.0.2와 필요한 codec을 요구한다. 다른9.0.2 build는 실제 fingerprint를 기록하되 동일환경 결정론 비교에서 제외하며 새 baseline 확인이 필요하다. 다른 버전은 설정 갱신 전 거부한다.
- 한글 폰트는 `third_party/fonts/`에서 관리하며 이 문서의 범위가 아니다.

## 5. 설치 명령

```sh
uv lock                 # pyproject.toml → uv.lock 해석
uv sync --locked        # uv.lock 그대로 .venv 설치
```

- baseline 단계에는 runtime22개를 설치했고, 스키마 구현 단계에는 dev 그룹과 editable adloom을 추가했다. 현재 정확한 설치 대상과 핀은 uv.lock이 정본이다.
- 이후 부모 통합 검증에서 실제 parser·Pillow 한글·ffmpeg·Range/SSE·lock smoke를 실행했다. 범위와 한계는 [baseline-verification.md](baseline-verification.md)에 있으며 제품 기능의 구현 완료를 뜻하지 않는다.
- uv가 다른 Python을 고르는 경우 `uv sync --locked --python 3.12.15`로 지정한다.

## 6. 개발·빌드 도구

스키마 구현에 필요한 개발 도구를 다음 버전으로 고정해 설치했다. `make check`는 ruff·mypy strict·pytest를 실행한다.

| 도구 | 설치 핀 | Python 요구 | 라이선스 | 출처 |
| --- | --- | --- | --- | --- |
| ruff | 0.17.2 | ≥3.7 | MIT | [PyPI](https://pypi.org/pypi/ruff/json) |
| mypy | 2.4.0 | ≥3.10 | MIT | [PyPI](https://pypi.org/pypi/mypy/json) |
| pytest | 9.1.1 | ≥3.10 | MIT | [PyPI](https://pypi.org/pypi/pytest/json) |

build backend는 Hatchling1.27.0이다. dev 도구와 package 설치는 `uv sync --locked`, 검증은 `make check`로 재현한다. 현재 검증 결과는 [schemas.md](schemas.md)에 기록한다.

## 7. 추가하지 않은 것

OpenAI SDK, `uvicorn[standard]`, pydantic-settings, SQLAlchemy·Postgres·Celery, React, Jinja2, MoviePy, pycocotools·rpycocotools, numpy. 근거는 SPEC §1과 research/oss.md를 따른다.
