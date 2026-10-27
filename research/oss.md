# AdLoom 오픈소스 재사용 조사

최초 조사일: 2026-10-23 · 갱신일: 2026-10-25 · 범위: 재사용 판단과 외부 원본 자료 확보 · 상태: **자료 확보 완료, 제품 통합·해커톤 허용 미확정**

## 1. 요약

AdLoom은 3~45초 영상과 설명을 이해·추적·보강하여 3비율×2훅 영상을 만들고, 사람 승인 후 PAUSED 광고 2개를 생성하는 기획이다. 루트 `SPEC.md` §1~5·§9, `TASKS.md`, 보완 기획 `_bmad-output/specs/spec-adloom/`를 기준으로 8개 구성 요소를 검토하였다.

- **가져다 쓴다:** Python 표준 라이브러리, Pydantic 2, HTTPX, 시스템 FFmpeg/ffprobe, FastAPI, Pillow, Noto Sans KR 1종, 그리고 **공식 SAM 파서 `meta-sam-parser` 0.1.0**(이전 판의 "SAM 응답 직접 파싱" 권장을 정정).
- **직접 만든다:** 작업 상태·source-linked 수정·승인 revision 무효화·PAUSED 강제·UNKNOWN 게시 처리·부분 게시 재개·크롭 계획·안전 영역 배치·정책 규칙·API 응답 매핑, SSE 이벤트를 파서 입력으로 넘기는 얇은 어댑터.
- **가져오지 않는다:** FastAPI Full Stack 템플릿, `fastapi-new` 생성기, MoviePy, pycocotools·rpycocotools, 로컬 모델 가중치.

### 1.1 확보와 승인의 구분

| 단계 | 상태 | 근거 |
| --- | --- | --- |
| 원본 자료 확보(파일·출처·해시·라이선스) | **완료**: SAM 파서 sdist·LICENSE, Noto Sans KR TTF·OFL.txt | `third_party/manifest.json` |
| 런타임 의존성 핀 | 이 문서 범위 밖 | `pyproject.toml`·`uv.lock`, `docs/architecture/dependencies.md` |
| 제품 코드 통합·동작 확인 | **미수행** | 테스트·빌드·렌더를 실행하지 않음 |
| 해커톤 규정상 외부 코드·폰트 허용 | **미확인**(TASKS.md H1) | 공식 규정 원문 미확보 |

표 3·4의 버전·별 수는 조사 시점 값이며 런타임 핀이 아니다. 예를 들어 FastAPI는 2026-10-23 조사 때 0.161.1이었고, 런타임 핀(0.162.0)은 `pyproject.toml`이 정한다. `SPEC.md`와 `TASKS.md`는 수정하지 않는다. mock 성공은 실제 API·광고 생성 성공의 증거가 아니다.

## 2. 구성 요소 목록

공식 심사기준·배점은 미확인이다. "관련 품질 목표"는 **[가정]**이며 공식 평가항목이 아니다.

| 구성 요소·원본 연결 | 해야 할 일 | 관련 품질 목표 [가정] |
| --- | --- | --- |
| 1. 계약·설정; T01 | 스키마 검증, 설정·LIVE 게이트 | 오류 설명·계약 일관성 |
| 2. 통신·어댑터; T05, T10~13 | 모델·Marketing API 요청과 오류 변환, mock/live 분리 | 실제 API 근거·실패 복구 |
| 3. 영상·오디오; T07, T12 | 원본 6개 영상 탐지·크롭·합성, 음성 전처리 | 결정론·영상 품질 |
| 4. 이미지·문구; T06~07, T12 | 문구 PNG 렌더, 안전 영역 배치 | 한글 가독성 |
| 5. 한글 폰트; SPEC §4.5 | 재현 가능한 단일 한글 폰트 | 한글 품질·권리 |
| 6. SAM→TrackResult; T11 | SAM 3.1 출력 파싱, bbox·프레임·객체 ID 매핑 | 추적 정합성 |
| 7. 승인 화면; T14 | 단일 HTML 미리보기·승인 라우트 | 승인 흐름·데모 이해도 |
| 8. 작업·안전·CLI; T02~04, T08~09 | 상태 전이·승인 무효화·PAUSED·정책 | 안전성·독창적 제품 흐름 |

<p>표 1. 구성 요소 목록</p>

## 3. 구성 요소별 결정

포크가 필요한 후보는 없다. `defer`는 현 요구에서 도입하지 않고 필요성이 달라질 때 재검토한다는 뜻이다.

| 구성 요소 | 결정·고른 후보 | 이유·직접 구현 범위 | 절감한 작업을 돌릴 품질 목표 [가정] |
| --- | --- | --- | --- |
| 1 | `reuse`: Pydantic 2 + `os`, `pathlib`, `enum` | 스키마·`extra="forbid"`·모델 ID·LIVE 게이트는 `build`. v1 혼용 금지 | 오류 설명·계약 일관성 |
| 2 | `reuse`: HTTPX | 요청·응답 매핑, 오류 변환, mock/live 분리, SPEC의 재시도만 `build`. HTTP 라이브러리가 승인·PAUSED·멱등성을 보장하지 않음 | 실제 API 근거·실패 복구 |
| 3 | `reuse`: 시스템 FFmpeg/ffprobe. MoviePy는 `reference` | `subprocess` 인자 목록·필터·6종 타임라인은 `build`. Voice 입력은 FFmpeg로 mono PCM16, 16/24kHz WAV 전처리(도메인 조사 전달 사항). 서로 다른 빌드의 프레임 동일성은 단정하지 않음 | 결정론·영상 품질 |
| 4 | `reuse`: Pillow Image/ImageDraw/ImageFont + FFmpeg 합성 | 문구별 정적 RGBA PNG를 만들어 시간 지정 합성. Image 요청 `output_format=png`와 반환 이미지 resize 통합(도메인 조사 전달 사항). 줄바꿈·실측 폭·안전 영역은 `build` | 한글 가독성 |
| 5 | `reuse`: Noto Sans KR 원본 TTF 1개(**확보 완료**) | 가변 폰트 1개로 굵기 축을 쓰고 서브셋·이름 변경·수정하지 않음. 실제 렌더 품질은 미검증 | 한글 품질·권리·재현성 |
| 6 | **`reuse`: `meta-sam-parser` 0.1.0(확보 완료)** — 이전 판의 직접 파싱(`build`) 권장을 정정 | 공식 파서가 `<Nf>` 프레임, 객체 ID 문자열, box·mask 토큰, 선택 `c` 신뢰도, 진단, 완료·미완료 구분을 처리. **TrackResult 매핑과 SSE→이벤트 어댑터만 `build`**. 4.3절 제한 참조 | 추적 정합성·불필요한 파서 코드 제거 |
| 7 | `reuse`: FastAPI 기본 패키지 + Uvicorn. 템플릿은 가져오지 않음(5절) | 단일 HTML·브라우저 video/fetch·승인 라우트만 `build` | 승인 흐름·데모 이해도 |
| 8 | `reuse`: `json`, `tempfile`, `os.replace`, `hashlib`, `argparse`, `re`; 제품 규칙은 `build` | 상태 전이·승인 무효화·생성 ID 기록·부분 재개·PAUSED·UNKNOWN 처리·정책 규칙을 직접 구현. DB·워크플로 엔진 불필요. YAML 파서 핀은 런타임 의존성 문서 소관 | 안전성·독창적 제품 흐름 |

<p>표 2. 구성 요소별 결정</p>

## 4. 공식 SAM 파서 검토

### 4.1 출처와 확보본

- 공식 문서 [SAM client libraries](https://dev.meta.ai/docs/sam/client-libraries)가 Python용 `meta-sam-parser`를 안내한다(Main 직접 확인 사항).
- 저장소 [meta-models/meta-sam](https://github.com/meta-models/meta-sam): 보관 아님, 별 5, 마지막 푸시 2026-10-21. 릴리스 태그 `meta-sam-parser@0.1.0` → 커밋 `cdf2e8b5625a3471e6dab3be7127b80fa83beb0d`, GitHub 릴리스 2026-10-06.
- PyPI [meta-sam-parser 0.1.0](https://pypi.org/project/meta-sam-parser/): 업로드 2026-10-06, `requires-python >=3.10`, 런타임 의존성 0개, "Development Status :: 3 - Alpha".
- 확보본 `third_party/meta-sam-parser/meta_sam_parser-0.1.0.tar.gz`: 33,694바이트, SHA-256 `d59ca559…f17ef3bb40`. **PyPI JSON digest와 GitHub 릴리스 asset digest 양쪽과 일치**. archive는 원본 그대로이다.
- `third_party/meta-sam-parser/LICENSE`: sdist 안의 LICENSE를 그대로 추출. 태그 커밋의 `python/LICENSE`와 SHA-256이 같다.

### 4.2 사용 방법(README 기준)

공개 API는 패키지 루트에서만 import한다. 밑줄로 시작하는 모듈은 내부 구현이다.

- 직접 파싱: `video_segmentation_format().create_parser()` → `parser.push(chunk)`(임의 위치 분할 허용, 0~1개 누적 snapshot) → `parser.finish(CompletedOutcome())` 또는 `IncompleteOutcome(reason="response"|"eof", detail=...)` → `.result`.
- 스트림: `parse_responses_stream(source, video_segmentation_format())`. `source`는 OpenAI SDK 이벤트 객체 또는 같은 wire 필드의 mapping을 내는 async iterable. 반복 모드와 `await ….final_result()` 전용 모드가 있고, 중도 종료는 `async with` 또는 `aclose()`로 한다.
- 결과: `VideoSegmentationResult.records`는 `SegmentationTextRecord`·`SegmentationBoxRecord`(`object_id`, `left/top/right/bottom`, `frame.frame_index`, `confidence`)·`SegmentationMaskRecord`. `diagnostics`, `raw_output`, `outcome`도 함께 준다.
- 마스크 변환: `decode_mask_to_raster`, `decode_mask_to_rle`(COCO 압축 RLE), `decode_mask_to_svg_path`. 크롭은 box 레코드로 충분하므로 현 계획에서 호출하지 않는다.
- 객체 프롬프트: `build_object_prompt(size=..., objects=[PromptObject(...)])`는 요청 텍스트만 만들고 전송하지 않는다.

### 4.3 알려진 제한

1. **끝점 변환:** wire의 포함 끝점 `x2`/`y2`를 파서가 이미 반열림 `right`/`bottom`으로 바꾼다. TrackResult 어댑터에서 **+1을 다시 더하지 않는다**. `w`/`h`는 프레임 크기이지 박스 크기가 아니다.
2. **진단 후 계속:** 형식이 깨진 줄은 `diagnostics`에 남기고 파싱을 계속한다. 예외가 없다고 성공으로 보지 말고 진단 유무를 어댑터가 판정한다. 알 수 없는 키·토큰은 경고 후 레코드 유지, `c` 범위 밖 값은 `ignored_confidence` 경고 후 `confidence=None`이다.
3. **완료·미완료:** `CompletedOutcome`과 `IncompleteOutcome`이 구분된다. 빈 lane의 완료 응답은 레코드 0개의 정상 결과이다. 미완료 결과를 완료 추적으로 승격하지 않는다.
4. **프레임·ID:** `<Nf>`는 건너뛸 수 있고 순서도 보장되지 않는다(정방향 후 역방향 가능). 객체 ID는 조밀한 인덱스가 아닌 문자열이다. `confidence=None`은 0이 아니다.
5. **자원:** 모든 마스크를 삽입 전에 엄격 디코딩하므로 메모리 할당이 생기며, 파서에는 면적·payload 상한이 없다. `MemoryError`는 그대로 전파된다. 입력 크기 상한은 호출 측이 정한다.
6. **전송 없음:** HTTP·SSE 전송은 포함되지 않는다. `httpx`(+ SSE 디코더)로 받은 이벤트를 mapping으로 넘기는 어댑터를 직접 둔다. README는 실서비스 SAM Model API가 lane 종료를 `response.content_part.done`으로만 알린다고 적고 있다.
7. **성숙도:** Alpha 0.1.0이다. 공개 API가 바뀔 수 있으므로 버전을 고정한다.
8. **라이선스:** MIT가 아닌 **SAM License**이다(6.2절).

### 4.4 스모크용 샘플 입력(출처: sdist 내 `README.md` "Direct parser API" 절)

```python
from meta_sam_parser import CompletedOutcome, video_segmentation_format

output_text = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
    ",1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>\n"
)
parser = video_segmentation_format().create_parser()
split = output_text.index(",1<|box")
parser.push(output_text[:split])
parser.push(output_text[split:])
result = parser.finish(CompletedOutcome()).result
```

README가 밝힌 기대값: 두 번째 `push`의 snapshot은 revision 1·레코드 4개, 최종 결과는 box 2개·mask 2개, 객체 ID `"0"`·`"1"`, 프레임 0. **[가정]** 끝점 규칙(README의 `build_object_prompt` 예시에서 `PromptBox(10, 20, 40, 60)`이 `x2=39;y2=59`로 나감)에 따르면 객체 `"0"`의 box는 `left=211, top=228, right=271, bottom=255`이다. 이 값은 실행으로 확인하지 않았다.

마스크 변환 샘플(같은 README "Mask conversion" 절): `SegmentationMask(encoding="one_bit", payload="!!!!!(QO(0lu8?", width=5, height=5)`.

## 5. FastAPI 템플릿 비교

| 후보 | 확인 사실(2026-10-25) | 현 기획 통째 적합도 | 결정 |
| --- | --- | --- | --- |
| [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) (공식) | MIT, 별 46,062, 최신 릴리스 0.12.0(2026-08-12), 기본 브랜치 `master` 최신 커밋 `b1125d8`(2026-10-15), 보관 아님. 백엔드 의존성에 `fastapi[standard]`, SQLModel, Alembic, psycopg, PyJWT, pwdlib, sentry-sdk, emails, jinja2; `requires-python >=3.14`; React·Vite·Docker Compose 포함 | **부적합**. React·PostgreSQL·SQLAlchemy 계열·풀스택 인증이 계약상 추가 금지이고, Python 3.14 요구가 런타임 3.12 핀과 충돌 | 가져오지 않음. 라우터 분리 같은 구조만 참고 |
| [fastapi/fastapi-new](https://github.com/fastapi/fastapi-new) (공식, 최소 대안) | MIT, 별 269, 0.0.7(2026-06-19), 마지막 푸시 2026-10-06, 보관 아님. `uv add fastapi[standard]` 후 `main.py` 한 개(Hello World 라우트)만 생성. 생성기 의존성: typer, rich, rich-toolkit, typing-extensions | **부적합(가져올 것이 없음)**. 생성물이 사실상 빈 앱이고 `standard` extra가 런타임 핀 범위를 넘음 | 가져오지 않음. 생성기 설치·실행도 불필요 |
| 참고: [rafsaf/minimal-fastapi-postgres-template](https://github.com/rafsaf/minimal-fastapi-postgres-template) | MIT, 별 578, 7.0.0(2026-02-09). PostgreSQL·SQLAlchemy·Alembic·JWT, Python ≥3.14 | 부적합. 이름과 달리 DB·인증 중심 | 비교 대상에서 제외 |

<p>표 3. FastAPI 템플릿 비교</p>

**바로 쓸 패키지와 참고 자료의 구분**

- 바로 쓸 패키지: FastAPI, Uvicorn, Pydantic, HTTPX, Pillow, `meta-sam-parser`. 구체적 핀은 `pyproject.toml`과 `docs/architecture/dependencies.md`가 정한다.
- 확보한 원본 자료: `third_party/`의 SAM 파서 sdist·LICENSE, Noto Sans KR TTF·OFL.txt.
- 참고만 하는 자료: SAM 파서 README 예시, FastAPI 공식 문서. 템플릿 코드는 복사하지 않는다.

## 6. 후보 비교·라이선스

### 6.1 후보 비교

이 표는 조사 시점의 연구 기록이다. 런타임 핀은 `pyproject.toml`·`uv.lock`, 핀 근거는 `docs/architecture/dependencies.md`에 있다. 별 수와 푸시 시각은 `gh repo view` 조회값이며, 푸시 시각을 마지막 코드 커밋일과 같다고 단정하지 않는다.

| 구성 요소·후보·종류 | 라이선스 | 마지막 배포·푸시 | 별 | 적합도·통합 비용 | URL |
| --- | --- | --- | --- | --- | --- |
| 1·Pydantic 2.14.1·라이브러리 | MIT | 배포 2026-10-11 | 29,152 | 높음·낮음 | [소스](https://github.com/pydantic/pydantic) |
| 1·8·Python 표준 라이브러리 | PSF 등 | 3.11 문서 | 해당 없음 | 높음·낮음 | [문서](https://docs.python.org/3.11/library/index.html) |
| 2·HTTPX 0.28.1·라이브러리 | BSD-3-Clause | 배포 2024-12-06, 푸시 2026-10-02 | 15,723 | 높음·낮음 | [소스](https://github.com/encode/httpx) |
| 3·FFmpeg/ffprobe·실행 도구 | 기본 LGPL, 현재 선택 build GPL-3.0-or-later | 9.0.2(2026-09-18), Homebrew9.0.2_1 | 해당 없음 | 높음·중간; 현재 build·binary hash는 media-baseline.json | [배포](https://ffmpeg.org/download.html), [법적 안내](https://ffmpeg.org/legal.html) |
| 3·MoviePy 2.2.1·라이브러리 | MIT | 배포 2025-05-21 | 15,017 | 비채택·중간 이상 | [소스](https://github.com/Zulko/moviepy) |
| 4·Pillow 13.0.0·라이브러리 | MIT-CMU | 배포 2026-10-16 | 13,915 | 높음·낮음~중간 | [소스](https://github.com/python-pillow/Pillow) |
| 5·Noto Sans KR·폰트 | OFL-1.1 | 경로 커밋 `b38c5c9`(2026-03-25) | 해당 없음 | 높음·낮음; **확보 완료** | [경로](https://github.com/google/fonts/tree/b38c5c93af322c45f633e17ac440ec1e6c94d489/ofl/notosanskr) |
| 6·meta-sam-parser 0.1.0·공식 파서 | SAM License | 배포 2026-10-06, 푸시 2026-10-21 | 5 | 높음·낮음; 의존성 0, Alpha; **확보 완료** | [소스](https://github.com/meta-models/meta-sam), [PyPI](https://pypi.org/project/meta-sam-parser/) |
| 6·pycocotools 2.0.11·RLE | BSD-2-Clause 상당 | 푸시 2026-03-23 | 172 | **defer**·중간; 공식 파서가 RLE 변환을 제공 | [소스](https://github.com/ppwwyyxx/cocoapi) |
| 6·rpycocotools 0.0.7·RLE | PyPI MIT 표기, 원문 미확인 | 배포 2023-05-25 | 5 | **defer** | [패키지](https://pypi.org/project/rpycocotools/) |
| 7·FastAPI 0.161.1(조사 시점)·프레임워크 | MIT | 배포 2026-10-22 | 104,039 | 높음·낮음 | [소스](https://github.com/fastapi/fastapi) |
| 7·Uvicorn 0.54.0·ASGI 서버 | BSD-3-Clause | 배포 2026-09-25 | 11,031 | 높음·낮음 | [소스](https://github.com/Kludex/uvicorn) |
| 7·Full Stack FastAPI Template | MIT | 0.12.0(2026-08-12) | 46,062 | 부적합(5절) | [소스](https://github.com/fastapi/full-stack-fastapi-template) |
| 7·fastapi-new 0.0.7 | MIT | 0.0.7(2026-06-19) | 269 | 부적합(5절) | [소스](https://github.com/fastapi/fastapi-new) |

<p>표 4. 오픈소스 후보 비교</p>

### 6.2 라이선스별 제약

- **SAM License(`meta-sam-parser`):** 비독점·양도 불가·무상의 사용·복제·배포·수정 허가(1.a). 배포·제공 시 이 계약 조건으로만 하고 **계약서 사본을 함께 제공**한다(1.b.i). 연구 결과를 출판하면 SAM Materials 사용을 밝힌다(1.b.ii). 무역 통제·관련 법 준수, 역공학 조장 금지, ITAR·군사 등 금지 용도(1.b.iii~v). Meta 대상 IP 소송 시 라이선스 종료와 면책 의무(5.b), 캘리포니아 준거법(7), Meta의 일방 개정 가능(8). MIT·BSD 같은 허용 라이선스로 표기하지 않는다. 제출물이 이 파서를 포함·배포하면 `third_party/meta-sam-parser/LICENSE`를 동봉한다.
- **Noto Sans KR(OFL 1.1):** 원본 동봉·재배포 허용, 폰트 단독 판매 금지, 저작권·OFL 고지 동봉, 수정본에 Reserved Font Name 'Source' 사용 금지. 글꼴로 만든 영상에는 OFL이 적용되지 않는다. 원본 그대로 쓴다.
- **Pydantic·FastAPI(MIT), HTTPX·Uvicorn(BSD-3-Clause):** 저작권·허가·면책 고지 유지. BSD는 저작권자 이름으로 홍보를 암시하지 않는다.
- **Pillow(MIT-CMU):** 원문 유지, 홍보에서 저작권자 이름 사용 제한.
- **FFmpeg:** 개발 baseline은 Homebrew9.0.2_1의 GPL-3.0-or-later/libx264/version3 구성이다. binary SHA256·실제 configuration·라이브러리 버전은 [media-baseline.json](../docs/architecture/media-baseline.json)에 기록했다. 바이너리는 동봉하지 않는다. 다른 build와 같은 frame hash를 보장하지 않으며 H.264/AAC 특허 조건은 별개다.
- **템플릿:** MIT이지만 가져오지 않으므로 고지 대상이 아니다.
- **외부 모델·Marketing API:** OSS가 아니다. 이용약관·산출물 권리는 도메인 조사와 H2/H3 관문에서 판단한다. SAM API 사용 조건과 파서의 SAM License는 별개이다.

## 7. 해커톤 규정 관문: 미확인

저장소에 `CONTEST.md`, `.harness/gate.json`, `RUBRIC.md`, 공고 원문이 없다. `SPEC.md` §9는 허용 모델·기존 코드·제출 형식을 미공개로, `TASKS.md` H1은 Official Rules 확인을 대기로 둔다. **OSS 라이선스상 재사용 가능과 해커톤 출품 허용은 별개이며, 여기서 확보한 모든 자료의 대회 규정 호환성은 미확인이다.**

| 규칙 | 상태 | 적용할 관문 |
| --- | --- | --- |
| 외부 코드·폰트·사전학습 모델·외부 데이터 허용 | [가정] 미확인 | 모든 reuse는 H1 확인 후 확정 |
| 기존 작품·독창성 | [가정] 미확인 | 라이브러리와 제품 고유 기여를 분리 고지 |
| 출처·AI 활용 고지, 공개 의무 | [가정] 미확인 | 8절 문안을 규정에 맞춰 확정 |
| 저작권 귀속·주최자 이용권 | [가정] 미확인 | 제3자 코드·폰트를 참가자 소유로 양도한다고 약속하지 않음. SAM License 조건이 주최자 이용권 요구와 맞는지 확인 필요 |

<p>표 5. 미확인 해커톤 규정 관문</p>

확인 질문:

1. 기존 OSS·폰트·공식 SDK/파서·외부 데이터·지정 API 모델의 허용 범위와 개발 시작 시점 제한은 무엇인가?
2. 기존 작품 판단, 독창성 요건, 출처·AI 고지와 코드 공개 의무는 무엇인가?
3. 저작권 귀속·주최자 이용권 조건이 SAM License·OFL처럼 권리를 유보하는 제3자 라이선스를 허용하는가?

## 8. 제출물 고지 문안

아래는 `third_party/`에 확보한 항목과 런타임 핀 대상 패키지 기준의 초안이다. 실제 설치 버전은 `uv.lock`으로 확정하며, H1 확인 전에는 최종본이 아니다.

| 이름 | 버전·커밋 | 라이선스 | URL | 쓴 방식 |
| --- | --- | --- | --- | --- |
| meta-sam-parser | 0.1.0, 태그 커밋 `cdf2e8b5625a3471e6dab3be7127b80fa83beb0d`, sdist SHA-256 `d59ca55993c5975fc8910f29b76e33499bc2870f79e9afcc30c916f17ef3bb40` | SAM License(사본 동봉) | https://github.com/meta-models/meta-sam | SAM 3.1 출력 파싱 의존성 |
| Noto Sans KR | google/fonts 커밋 `b38c5c93af322c45f633e17ac440ec1e6c94d489`, `NotoSansKR[wght].ttf` SHA-256 `194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252` | SIL OFL 1.1(OFL.txt 동봉) | https://github.com/google/fonts/tree/main/ofl/notosanskr | 문구 렌더 폰트, 수정 없음 |
| FastAPI, Uvicorn, Pydantic, HTTPX, httpx-sse, Pillow, python-multipart, PyYAML 및 전이 의존성 | uv.lock 기준 | 정본은 [dependencies.md §2·3](../docs/architecture/dependencies.md): MIT, BSD-3-Clause, MIT-CMU, Apache-2.0, MPL-2.0, PSF-2.0 등 | 각 패키지 공식 출처는 정본 표에 연결 | runtime9개 직접·13개 전이 의존성 |
| FFmpeg/ffprobe | 9.0.2, Homebrew9.0.2_1 | 현재 GPL-3.0-or-later build | https://ffmpeg.org/ | 별도 실행 도구, 동봉하지 않음 |

<p>표 6. 사용 오픈소스 고지 초안</p>

> 외부 자료 확보 내역: SAM 응답 파싱용 meta-sam-parser0.1.0(SAM License 사본 포함), 한글 렌더용 Noto Sans KR(OFL1.1 원본 포함), 웹·검증·통신·이미지 처리를 위한 pyproject/uv.lock 의존성을 확보했다. 직접·전이 의존성의 라이선스와 출처는 docs/architecture/dependencies.md가 정본이다. FFmpeg/ffprobe는 별도 시스템 설치본이다. AdLoom 고유 상태 전이·승인·게시·크롭 기능은 아직 구현하지 않았다. 최종 제출 고지는 실제 구현·통합 범위와 H1 규정 확인 후 확정한다.

## 9. 출처·조사 한계

| 출처 | 확인일 | 확인 내용 |
| --- | --- | --- |
| https://pypi.org/pypi/meta-sam-parser/json | 2026-10-25 | 0.1.0 sdist·wheel URL·SHA-256·크기, 라이선스, Python 범위 |
| `gh api repos/meta-models/meta-sam/git/ref/tags/meta-sam-parser@0.1.0`, `…/releases/tags/meta-sam-parser@0.1.0` | 2026-10-25 | 태그 커밋, 릴리스 asset digest |
| `gh repo view meta-models/meta-sam` | 2026-10-25 | 별·푸시·보관·라이선스 표기(Other) |
| sdist 내 `README.md`, `LICENSE`, `pyproject.toml`, `src/meta_sam_parser/__init__.py`, `_types.py` | 2026-10-25 | 공개 API, 동작, 제한, 라이선스 원문(압축 해제 없이 읽음) |
| https://dev.meta.ai/docs/sam/client-libraries | Main 확인 | 공식 클라이언트 라이브러리 안내 |
| https://dev.meta.ai/docs/sam/reading-segmentation | 2026-10-23 | 응답 토큰 형식 |
| `gh api repos/google/fonts/commits?path=ofl/notosanskr`, `…/contents/ofl/notosanskr`, 커밋 `b38c5c9`의 `METADATA.pb` | 2026-10-25 | 경로 커밋, 파일 크기·blob sha, 업스트림 소스 커밋 |
| `gh repo view`·`gh api` fastapi/full-stack-fastapi-template(`backend/pyproject.toml` 포함), fastapi/fastapi-new(`src/fastapi_new/new.py` 포함), rafsaf/minimal-fastapi-postgres-template | 2026-10-25 | 라이선스·릴리스·구성·생성 내용 |
| https://raw.githubusercontent.com/fastapi/fastapi-new/main/README.md, https://raw.githubusercontent.com/rafsaf/minimal-fastapi-postgres-template/main/README.md | 2026-10-25 | 사용법·기능 목록 |
| https://pypi.org/pypi/fastapi-new/json | 2026-10-25 | 버전·의존성·라이선스 |
| 표 4의 나머지 링크 | 2026-10-23 | 이전 조사 값 그대로 |

- 다운로드한 파일은 `third_party/manifest.json`의 네 개뿐이다. 클론·설치·압축 해제·빌드·테스트·린트·폰트 렌더는 하지 않았다.
- 폰트의 SHA-256은 상류가 공개하지 않아 확보 시점 로컬 계산값이며, 무결성은 GitHub blob sha 일치로 확인하였다.
- 이 조사에서 제품 통합·실제 SAM API·열린 이슈 영향·전이 의존성 전체 감사는 수행하지 않았다. 부모 통합 단계에서 parser·한글 렌더·미디어·HTTP/lock의 제한된 smoke를 실행했으며 [baseline-verification.md](../docs/architecture/baseline-verification.md)에 범위와 한계를 기록한다.
